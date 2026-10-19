"""Semantic retrieval over prospectus passages.

Metadata filtering runs BEFORE similarity, not after. Simon's example question
is "the Toyota deal from April 2026, and then the question", so the issuer and
date narrow the corpus to one deal and the search happens inside it. Filtering
afterwards would rank the whole corpus first and throw most of it away.

A result is a passage plus every deal it appears in, because passages repeat
across filings. One passage occurs in 38 deals. Returning it 38 times would
bury everything else, and "which deals do X" is the question being asked
anyway.

Usage:
    from semantic_search import search
    search("where are collections deposited?", issuer="Toyota")
"""

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, str(Path(__file__).parent))
from embed import DEFAULT_BACKEND, client, load_cached, load_passages

DATA = Path("data")
INDEX = DATA / "deal_index.csv"


def load_deals():
    """The deal table, which owns all deal-level metadata."""
    return pd.read_csv(INDEX, dtype=str).fillna("")


def matching_accessions(deals, issuer=None, year=None, asset_class=None, deal=None):
    """Accessions passing the metadata filter. None of these is a text search."""
    keep = deals
    if issuer:
        low = issuer.casefold()
        keep = keep[keep.depositor_name.str.casefold().str.contains(low, regex=False)
                    | keep.deal_name.str.casefold().str.contains(low, regex=False)]
    if deal:
        keep = keep[keep.deal_name.str.casefold().str.contains(deal.casefold(), regex=False)]
    if year:
        keep = keep[keep.filing_year == str(year)]
    if asset_class:
        keep = keep[keep.asset_class.str.casefold() == str(asset_class).casefold()]
    return set(keep.accession)


# Opening a connection to the API costs about 10 seconds on this network, and
# ask.py runs one question per process, so it pays that every time. Questions
# repeat constantly during a demo or an evaluation sweep, so their vectors are
# kept on disk and a repeat never touches the API at all.
QUERY_CACHE = DATA / "vectors" / "queries.pkl"
_QUERIES = None


def query_cache():
    global _QUERIES
    if _QUERIES is None:
        try:
            with open(QUERY_CACHE, "rb") as fh:
                _QUERIES = pickle.load(fh)
        except Exception:
            _QUERIES = {}
    return _QUERIES


def embed_query(text, backend, model):
    """Put the question in the same space as the passages."""
    if backend == "tfidf":
        return model.transform([text])
    if backend == "openai":
        from embed import OPENAI_MODEL

        cache = query_cache()
        if text in cache:
            return cache[text]
        resp = client().embeddings.create(model=OPENAI_MODEL, input=[text])
        vec = np.array([resp.data[0].embedding], dtype="float32")
        cache[text] = vec
        QUERY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUERY_CACHE, "wb") as fh:
            pickle.dump(cache, fh)
        return vec
    raise ValueError(f"no query path for backend {backend!r}")


def search(question, backend=DEFAULT_BACKEND, issuer=None, year=None,
           asset_class=None, deal=None, top_k=10, kinds=("body", "glossary")):
    """Rank passages against a question, filtered by deal metadata first.

    Returns dicts carrying the passage, the deals it appears in, and enough to
    cite it: section title, prospectus page and the SEC url.
    """
    cached = load_cached(backend)
    if cached is None:
        raise FileNotFoundError(
            f"no vectors for backend {backend!r}. Run: python src/embed.py {backend}")

    shas, matrix, model = cached["shas"], cached["matrix"], cached["model"]
    _, _, where = load_passages()
    deals = load_deals()
    allowed = matching_accessions(deals, issuer, year, asset_class, deal)
    by_acc = {d.accession: d for d in deals.itertuples()}

    # Filter first: keep only passages that appear in a surviving deal and sit
    # in a section kind worth searching. Index listings and static pool tables
    # are excluded by default rather than dropped at chunk time.
    rows, keep_recs = [], []
    for i, sha in enumerate(shas):
        recs = [r for r in where[sha]
                if r["accession"] in allowed and r["section_kind"] in kinds]
        if recs:
            rows.append(i)
            keep_recs.append(recs)
    if not rows:
        return []

    scores = cosine_similarity(embed_query(question, backend, model),
                               matrix[rows]).ravel()
    order = np.argsort(-scores)[:top_k]

    out = []
    for rank in order:
        if scores[rank] <= 0:
            continue
        recs = keep_recs[rank]
        first = recs[0]
        out.append({
            "score": round(float(scores[rank]), 4),
            "text": first["text"],
            "section_title": first["section_title"],
            "n_deals": len(recs),
            "deals": [{
                "deal_name": by_acc[r["accession"]].deal_name,
                "filing_date": by_acc[r["accession"]].filing_date,
                "asset_class": by_acc[r["accession"]].asset_class,
                "page": r["page_start"],
                "doc_url": by_acc[r["accession"]].doc_url,
                "text_file": by_acc[r["accession"]].text_file,
                "char_start": r["char_start"],
                "char_end": r["char_end"],
            } for r in recs],
        })
    return out
