"""Turn chunk passages into vectors for similarity search.

Embedding happens over DISTINCT passages, not over chunks. Half the corpus is
repeated text: 86,219 chunks collapse to 43,027 distinct passages, and one
passage appears in 38 deals across 7 depositors. Embedding each one once halves
the work and keeps a single passage from filling nine of ten result slots.

The backend is pluggable because the team is waiting on API budget approval.
Nothing here requires a key to run.

    tfidf   development placeholder. No key, no download, seconds to build.
            It is lexical, not semantic, so it does not satisfy Milestone 2 on
            its own. It exists so the rest of the pipeline can be built and
            tested now, and as a baseline to measure real embeddings against.
    openai  text-embedding-3-small. Needs OPENAI_API_KEY.

Usage:
    python src/embed.py            # build vectors for the default backend
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


DEFAULT_BACKEND = "tfidf"
OPENAI_MODEL = "text-embedding-3-small"
OPENAI_BATCH = 256
OPENAI_RETRIES = 6

# The key is shared across every PIMCO team, so rate limits are somebody else's
# traffic as much as ours. Finished batches are written to a part file as they
# land: a failure at batch 150 of 169 should not mean paying for the first 149
# a second time.
PART_SUFFIX = ".part.jsonl"


_PASSAGES = None


def load_passages():
    """Distinct passages across the corpus. Cached, it reads 154MB.

    Returns (shas, texts, where), where `where` maps a sha to the chunk records
    carrying it, so a hit can be expanded back to every deal it appears in.
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

    # sublinear_tf because these documents repeat a term many times inside one
    # passage without it mattering nine times as much.
    model = TfidfVectorizer(stop_words="english", sublinear_tf=True,
                            min_df=3, max_df=0.6, ngram_range=(1, 2))
    return model.fit_transform(texts), model


def _openai(texts):
    import os

    load_env()
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Put it in a .env file at the repo root; "
            ".gitignore already covers .env.")

    import numpy as np
    from openai import OpenAI

    client = OpenAI(api_key=key)
    part = VECTORS / ("openai" + PART_SUFFIX)
    VECTORS.mkdir(parents=True, exist_ok=True)

    done = {}
    if part.exists():
        for line in part.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            done[rec["i"]] = rec["v"]
        print(f"  resuming, {len(done):,} passages already embedded")

    with open(part, "a", encoding="utf-8") as fh:
        for start in range(0, len(texts), OPENAI_BATCH):
            batch = list(range(start, min(start + OPENAI_BATCH, len(texts))))
            batch = [i for i in batch if i not in done]
            if not batch:
                continue
            vectors = _embed_batch([texts[i] for i in batch])
            for i, vec in zip(batch, vectors):
                done[i] = vec
                fh.write(json.dumps({"i": i, "v": vec}) + "\n")
            fh.flush()
            print(f"  {len(done):,}/{len(texts):,}")

    matrix = np.array([done[i] for i in range(len(texts))], dtype="float32")
    part.unlink()
    return matrix, None


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


def build_vectors(texts, backend=DEFAULT_BACKEND):
    """Vectors for these passages, in order."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}, have {sorted(BACKENDS)}")
    return BACKENDS[backend](texts)


def cache_path(backend):
    return VECTORS / f"{backend}.pkl"


def matrix_path(backend):
    return VECTORS / f"{backend}.npy"


_CACHE = {}
_CLIENT = None


def client():
    """One OpenAI client per process.

    Building a client opens a connection, which measured at about 10 seconds
    on this network. Reused, the same embedding call takes 0.25s. Creating one
    per query made every question cost 10 seconds for no reason.
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

    Unpickling a 266MB dense array costs about 10 seconds. The same array as
    .npy memory-maps in milliseconds, which is the difference between ask.py
    answering immediately and sitting silent through a demo. Sparse matrices
    stay in the pickle; scipy does not memory-map and they load fast anyway.
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


def main(backend=DEFAULT_BACKEND, limit=None, dry_run=False):
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
    matrix, model = build_vectors(texts, backend)
    print(f"  matrix {matrix.shape}")

    name = backend if not limit else f"{backend}-smoke"
    save_cached(name, shas, matrix, model)
    print(f"wrote {cache_path(name)}")


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    backend = args[0] if args and not args[0].startswith("-") else DEFAULT_BACKEND
    limit = next((int(a.split("=")[1]) for a in args if a.startswith("--limit=")), None)
    main(backend, limit=limit, dry_run="--dry-run" in args)
