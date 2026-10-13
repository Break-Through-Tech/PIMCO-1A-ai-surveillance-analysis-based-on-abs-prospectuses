"""Prove the chunks are sound before anything gets embedded.

Runs against the written data/chunks/*.jsonl, not an in-memory rerun.

The failure worth guarding against is the quiet one: 86,000 chunks that look
reasonable and silently drop a third of every document. So check A compares
line by line against the source, and check G replays Milestone 1's keyword
search as ground truth.

Usage:
    python src/validate_chunks.py
"""

import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from chunk import chunk_text, find_toc, page_map
from search import search_prospectuses

DATA = Path("data")
INDEX = DATA / "deal_index.csv"
CHUNKS = DATA / "chunks"

BARE_INT = re.compile(r"(?m)^\d{1,4}$")
TOC_SHAPED = re.compile(r"^(?=(?:[^0-9]*[0-9]){1,4}[^0-9]*$)"
                        r"[A-Za-z][^0-9]{4,}\s+(?:\d{1,3}|[ivxlcdm]{1,7})$")
SPACES = re.compile(r"\s+")
MIN_RECALL = 0.90


def load(deal):
    """Source text and its chunk records."""
    path = Path(deal.text_file)
    source = path.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in
            (CHUNKS / (path.stem + ".jsonl")).read_text(encoding="utf-8").splitlines()]
    return source, rows


def check(name, failures, detail=""):
    status = "PASS" if not failures else "FAIL"
    print(f"[{status}] {name}: {len(failures)} problem(s){detail}")
    for item in failures[:5]:
        print(f"        {item}")
    return not failures


def main():
    deals = pd.read_csv(INDEX, dtype=str).fillna("")
    results = []

    # A. Coverage. Every line that should have survived is inside some chunk.
    bad = []
    for deal in deals.itertuples():
        source, rows = load(deal)
        lines = source.split("\n")
        toc = set(find_toc(lines))
        _, footers, _ = page_map(lines)
        covered = set()
        for row in rows:
            covered.update(range(row["line_start"], row["line_end"] + 1))
        want = {i for i, line in enumerate(lines)
                if line.strip() and i not in footers and i not in toc}
        missing = sorted(want - covered)
        if missing:
            bad.append(f"{Path(deal.text_file).stem[:40]}: {len(missing)} lines, "
                       f"first {lines[missing[0]][:50]!r}")
    results.append(check("A coverage, no source line dropped", bad))

    # B. Span round trip. A citation has to point at the text it quotes.
    bad = []
    for deal in deals.itertuples():
        source, rows = load(deal)
        text_lines = source.split("\n")
        toc = set(find_toc(text_lines))
        _, footers, _ = page_map(text_lines)
        for row in rows:
            # The chunk is the span with footers and contents lines removed and
            # paragraphs broken by a page break rejoined, so compare against
            # that reconstruction rather than the raw slice.
            kept = [text_lines[i].strip()
                    for i in range(row["line_start"], row["line_end"] + 1)
                    if text_lines[i].strip() and i not in footers and i not in toc]
            span = SPACES.sub(" ", " ".join(kept))
            for line in row["text"].split("\n"):
                probe = SPACES.sub(" ", line).strip()[:80]
                if probe and probe not in span:
                    bad.append(f"{row['chunk_id']}: {probe[:50]!r} not in its span")
                    break
    results.append(check("B span round trip, citations resolve", bad))

    # C and D come straight off the report the driver already wrote.
    report = pd.read_csv(DATA / "chunk_index.csv")
    agree, disagree = report.page_agree.sum(), report.page_disagree.sum()
    rate = agree / max(agree + disagree, 1)
    bad = [] if rate >= 0.99 else [f"page agreement {rate:.3%}"]
    results.append(check("C page cross validation", bad,
                         f", footer vs TOC agree {rate:.2%}"))

    low = report[report.heading_recall < MIN_RECALL]
    bad = [f"{Path(r.text_file).stem[:40]}: {r.heading_recall}" for r in low.itertuples()]
    results.append(check("D heading recall per file", bad,
                         f", min {report.heading_recall.min():.3f}"))

    # E. A bare integer in prose means footer stripping missed a page. Tables
    # legitimately carry them, so only prose-dense chunks count.
    bad = []
    for deal in deals.itertuples():
        _, rows = load(deal)
        for row in rows:
            if (row["section_kind"] == "body" and row["word_share"] > 0.6
                    and BARE_INT.search(row["text"])):
                bad.append(f"{row['chunk_id']} p{row['page_start']} "
                           f"ws={row['word_share']}")
    results.append(check("E no page footer left in prose", bad))

    # F. A contents or index listing left tagged as prose would be embedded as
    # if it were substance. chunk.py tags these from content, so this asserts
    # the tagging held rather than re-deriving it.
    bad = []
    for deal in deals.itertuples():
        _, rows = load(deal)
        for row in rows:
            if row["section_kind"] != "index" and row["toc_share"] > 0.6:
                bad.append(f"{row['chunk_id']}: toc_share {row['toc_share']} "
                           f"but tagged {row['section_kind']}")
    results.append(check("F listings tagged, not left as prose", bad))

    # G. Milestone 1's keyword search as ground truth. If search.py can find a
    # phrase in a document and no chunk of that document contains it, chunking
    # lost retrievable content.
    bad = []
    for query in ("custodian", "commingl", "true sale", "physical possession"):
        hits = search_prospectuses(query, use_regex=True, top_k=8)
        for hit in hits.itertuples():
            row = deals[deals.doc_url == hit.doc_url]
            if row.empty:
                continue
            _, rows = load(next(row.itertuples()))
            blob = "\n".join(r["text"] for r in rows).casefold()
            if not re.search(query, blob):
                bad.append(f"{query!r} found by search.py but absent from "
                           f"{hit.deal_name[:40]} chunks")
    results.append(check("G keyword search answers survive chunking", bad))

    # I. Determinism, so a cached embedding set stays valid.
    bad = []
    for deal in list(deals.itertuples())[:6]:
        source, rows = load(deal)
        again = chunk_text(source, deal.accession)
        if [r["text_sha1"] for r in rows] != [r["text_sha1"] for r in again]:
            bad.append(f"{Path(deal.text_file).stem[:40]} differs on rerun")
    results.append(check("I deterministic across runs", bad))

    # H. Someone has to read the output. The extremes are where breakage lives.
    print("\n" + "=" * 78)
    print("H human spot read, 6 samples. Read these.")
    random.seed(0)
    sample = random.sample(list(deals.itertuples()), 4)
    picks = []
    for deal in sample:
        _, rows = load(deal)
        picks.append(random.choice(rows))
    widest = []
    for deal in deals.itertuples():
        _, rows = load(deal)
        widest.extend(rows)
    picks.append(max(widest, key=lambda r: r["n_chars"]))
    picks.append(min(widest, key=lambda r: r["word_share"]))
    for row in picks:
        body = row["text"].replace("\n", " ")[:200]
        print(f"\n  {row['chunk_id']}  p{row['page_start']}-{row['page_end']}  "
              f"{row['n_chars']}c  ws={row['word_share']}  [{row['section_kind']}]")
        print(f"  section: {row['section_title'][:70]!r}")
        print(f"  {body}")

    print("\n" + "=" * 78)
    passed = sum(results)
    print(f"VALIDATION: {passed}/{len(results)} checks passed")
    if passed < len(results):
        print("Do not embed until these are resolved.")


if __name__ == "__main__":
    main()
