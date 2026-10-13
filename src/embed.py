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
from pathlib import Path

DATA = Path("data")
CHUNKS = DATA / "chunks"
VECTORS = DATA / "vectors"

DEFAULT_BACKEND = "tfidf"
OPENAI_MODEL = "text-embedding-3-small"
OPENAI_BATCH = 256


def load_passages():
    """Distinct passages across the corpus.

    Returns (shas, texts, where), where `where` maps a sha to the chunk records
    carrying it, so a hit can be expanded back to every deal it appears in.
    """
    where = {}
    for path in sorted(CHUNKS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            where.setdefault(rec["text_sha1"], []).append(rec)

    shas = sorted(where)
    texts = [where[s][0]["text"] for s in shas]
    return shas, texts, where


def _tfidf(texts):
    from sklearn.feature_extraction.text import TfidfVectorizer

    # sublinear_tf because these documents repeat a term many times inside one
    # passage without it mattering nine times as much.
    model = TfidfVectorizer(stop_words="english", sublinear_tf=True,
                            min_df=3, max_df=0.6, ngram_range=(1, 2))
    return model.fit_transform(texts), model


def _openai(texts):
    import os

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The team is waiting on API budget "
            "approval; use the tfidf backend until then.")

    import numpy as np
    from openai import OpenAI

    client = OpenAI(api_key=key)
    out = []
    for i in range(0, len(texts), OPENAI_BATCH):
        batch = client.embeddings.create(model=OPENAI_MODEL,
                                         input=texts[i:i + OPENAI_BATCH])
        out.extend(d.embedding for d in batch.data)
        print(f"  embedded {min(i + OPENAI_BATCH, len(texts))}/{len(texts)}")
    return np.array(out, dtype="float32"), None


BACKENDS = {"tfidf": _tfidf, "openai": _openai}


def build_vectors(texts, backend=DEFAULT_BACKEND):
    """Vectors for these passages, in order."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}, have {sorted(BACKENDS)}")
    return BACKENDS[backend](texts)


def cache_path(backend):
    return VECTORS / f"{backend}.pkl"


def load_cached(backend=DEFAULT_BACKEND):
    """Vectors from an earlier build, or None."""
    path = cache_path(backend)
    if not path.exists():
        return None
    with open(path, "rb") as fh:
        return pickle.load(fh)


def main(backend=DEFAULT_BACKEND):
    VECTORS.mkdir(parents=True, exist_ok=True)
    shas, texts, where = load_passages()
    chunks = sum(len(v) for v in where.values())
    print(f"{chunks:,} chunks -> {len(shas):,} distinct passages "
          f"({100 * len(shas) / chunks:.1f}%)")

    print(f"building vectors with backend {backend!r}")
    matrix, model = build_vectors(texts, backend)
    print(f"  matrix {matrix.shape}")

    with open(cache_path(backend), "wb") as fh:
        pickle.dump({"shas": shas, "matrix": matrix, "model": model}, fh)
    print(f"wrote {cache_path(backend)}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BACKEND)
