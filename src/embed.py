"""Turn chunk passages into vectors for similarity search.

Embedding happens over DISTINCT passages, not over chunks. Half the corpus is
repeated text: 86,219 chunks collapse to 43,027 distinct passages, and one
passage appears in 38 deals across 7 depositors. Embedding each one once halves
the work and keeps a single passage from filling nine of ten result slots.

    openai  text-embedding-3-small, what search uses. Needs OPENAI_API_KEY.
    tfidf   lexical baseline. No key, seconds to build, and much weaker, so it
            is there to measure against rather than to answer with.

Usage:
    python src/embed.py                    # tfidf, free
    python src/embed.py openai --dry-run   # size the paid build first
    python src/embed.py openai
"""

import json
import pickle
import time
from pathlib import Path

DATA = Path("data")
CHUNKS = DATA / "chunks"
VECTORS = DATA / "vectors"

def load_env():
    """Read .env from the repo root. Windows shells do not keep exports."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


DEFAULT_BACKEND = "openai"
# Building defaults to tfidf instead. main() deletes the openai part file after
# a build, so a bare run on openai would pay to re-embed everything.
BUILD_BACKEND = "tfidf"
OPENAI_MODEL = "text-embedding-3-small"
OPENAI_BATCH = 256
OPENAI_RETRIES = 6

# Finished batches land in a part file as they go. A failure at batch 150 of
# 169 should not mean paying for the first 149 again.
PART_SUFFIX = ".part.jsonl"


_PASSAGES = None


def load_passages():
    """Distinct passages, as (shas, texts, where). Cached, it reads 154MB.

    `where` maps a sha to the chunk records carrying it, so a hit expands back
    to every deal it appears in.
    """
    global _PASSAGES
    if _PASSAGES is not None:
        return _PASSAGES

    where = {}
    for path in sorted(CHUNKS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            where.setdefault(rec["text_sha1"], []).append(rec)

    shas = sorted(where)
    texts = [where[s][0]["text"] for s in shas]
    _PASSAGES = (shas, texts, where)
    return _PASSAGES


def _tfidf(texts):
    from sklearn.feature_extraction.text import TfidfVectorizer

    # sublinear_tf: these filings repeat a term many times in one passage
    # without it mattering proportionally.
    model = TfidfVectorizer(stop_words="english", sublinear_tf=True,
                            min_df=3, max_df=0.6, ngram_range=(1, 2))
    return model.fit_transform(texts), model


def _openai(texts, shas):
    import numpy as np

    wanted = set(shas)
    part = VECTORS / ("openai" + PART_SUFFIX)
    VECTORS.mkdir(parents=True, exist_ok=True)

    # Keyed by sha, not position. A re-chunk shifts sorted(where), and position
    # alone would pair every later vector with the wrong passage.
    done = {}
    if part.exists():
        stale = 0
        for line in part.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                stale += 1
                continue
            if rec.get("sha") in wanted:
                done[rec["sha"]] = rec["v"]
            else:
                stale += 1
        print(f"  resuming, {len(done):,} already embedded"
              + (f", {stale:,} stale entries dropped" if stale else ""))

    with open(part, "a", encoding="utf-8") as fh:
        for start in range(0, len(texts), OPENAI_BATCH):
            batch = [i for i in range(start, min(start + OPENAI_BATCH, len(texts)))
                     if shas[i] not in done]
            if not batch:
                continue
            for i, vec in zip(batch, _embed_batch([texts[i] for i in batch])):
                done[shas[i]] = vec
                fh.write(json.dumps({"sha": shas[i], "v": vec}) + '\n')
            fh.flush()
            print(f"  {len(done):,}/{len(texts):,}")

    # main() removes the part file once the cache is written. Deleting it here
    # would throw away a paid run if the save then failed.
    return np.array([done[s] for s in shas], dtype="float32"), None


def _embed_batch(texts):
    """One embeddings call, retrying on rate limits and transient failures."""
    for attempt in range(OPENAI_RETRIES):
        try:
            resp = client().embeddings.create(model=OPENAI_MODEL, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as exc:
            name = type(exc).__name__
            fatal = ("AuthenticationError", "PermissionDeniedError", "BadRequestError")
            if name in fatal or attempt == OPENAI_RETRIES - 1:
                raise
            wait = 2 ** attempt
            print(f"  {name}, retrying in {wait}s ({attempt + 1}/{OPENAI_RETRIES})")
            time.sleep(wait)


def estimate(texts):
    """Batches and rough token count, so a run can be sized before paying."""
    chars = sum(len(t) for t in texts)
    tokens = chars // 4
    return {
        "passages": len(texts),
        "batches": -(-len(texts) // OPENAI_BATCH),
        "est_tokens": tokens,
        "est_usd": round(tokens / 1_000_000 * 0.02, 3),
    }


BACKENDS = {"tfidf": _tfidf, "openai": _openai}
NEEDS_SHAS = {"openai"}


def build_vectors(texts, backend=BUILD_BACKEND, shas=None):
    """Vectors for these passages, in order."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}, have {sorted(BACKENDS)}")
    if backend in NEEDS_SHAS:
        return BACKENDS[backend](texts, shas)
    return BACKENDS[backend](texts)


def cache_path(backend):
    return VECTORS / f"{backend}.pkl"


def matrix_path(backend):
    return VECTORS / f"{backend}.npy"


_CACHE = {}
_CLIENT = None


def client():
    """One OpenAI client per process.

    Opening the connection measured at 10s here, the call itself at 0.25s, and
    the old code built a client per query.
    """
    global _CLIENT
    if _CLIENT is None:
        import os

        from openai import OpenAI

        load_env()
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Put it in a .env file at the repo "
                "root; .gitignore already covers .env.")
        _CLIENT = OpenAI(api_key=key)
    return _CLIENT


def save_cached(backend, shas, matrix, model):
    """Store vectors, keeping a dense matrix out of the pickle.

    A .npy sidecar memory-maps, so 266MB never enters the process. Sparse
    matrices stay in the pickle since scipy does not memory-map.
    """
    import numpy as np

    VECTORS.mkdir(parents=True, exist_ok=True)
    dense = isinstance(matrix, np.ndarray)
    if dense:
        np.save(matrix_path(backend), matrix)
    with open(cache_path(backend), "wb") as fh:
        pickle.dump({"shas": shas, "matrix": None if dense else matrix,
                     "model": model, "dense": dense}, fh)


def load_cached(backend=DEFAULT_BACKEND):
    """Vectors from an earlier build, or None. Cached per process."""
    if backend in _CACHE:
        return _CACHE[backend]

    path = cache_path(backend)
    if not path.exists():
        return None
    with open(path, "rb") as fh:
        blob = pickle.load(fh)

    if blob.get("dense"):
        import numpy as np

        if not matrix_path(backend).exists():
            raise FileNotFoundError(
                f"{cache_path(backend)} expects {matrix_path(backend)}, which is "
                f"missing. Rebuild with: python src/embed.py {backend}")
        blob["matrix"] = np.load(matrix_path(backend), mmap_mode="r")
    elif blob.get("matrix") is None:
        raise ValueError(
            f"{cache_path(backend)} was written by an older version. Rebuild "
            f"with: python src/embed.py {backend}")
    _CACHE[backend] = blob
    return blob


def main(backend=BUILD_BACKEND, limit=None, dry_run=False):
    load_env()
    VECTORS.mkdir(parents=True, exist_ok=True)
    shas, texts, where = load_passages()
    chunks = sum(len(v) for v in where.values())
    print(f"{chunks:,} chunks -> {len(shas):,} distinct passages "
          f"({100 * len(shas) / chunks:.1f}%)")

    if limit:
        shas, texts = shas[:limit], texts[:limit]
        print(f"LIMITED to the first {limit:,} passages")

    if backend == "openai":
        est = estimate(texts)
        print(f"  {est['batches']} batches, ~{est['est_tokens']:,} tokens, "
              f"~${est['est_usd']}")
        if dry_run:
            print("dry run, no API calls made")
            return

    print(f"building vectors with backend {backend!r}")
    matrix, model = build_vectors(texts, backend, shas)
    print(f"  matrix {matrix.shape}")

    name = backend if not limit else f"{backend}-smoke"
    save_cached(name, shas, matrix, model)
    print(f"wrote {cache_path(name)}")

    part = VECTORS / (name + PART_SUFFIX)
    if part.exists():
        part.unlink()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build passage vectors.")
    ap.add_argument("backend", nargs="?", default=BUILD_BACKEND,
                    choices=sorted(BACKENDS))
    ap.add_argument("--limit", type=int,
                    help="embed only the first N passages, for a smoke test")
    ap.add_argument("--dry-run", action="store_true",
                    help="report batches and cost without calling the API")
    parsed = ap.parse_args()
    main(parsed.backend, limit=parsed.limit, dry_run=parsed.dry_run)
