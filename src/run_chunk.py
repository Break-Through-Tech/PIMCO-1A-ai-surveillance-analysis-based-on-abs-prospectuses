"""Task 1 of Milestone 2: chunk every prospectus in the deal index.

Reads data/deal_index.csv, writes one JSONL file per document into
data/chunks/, and a per-document quality table to data/chunk_index.csv.

Usage:
    python src/run_chunk.py
"""

import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from chunk import (TARGET_CHARS, chunk_text, find_headings, find_toc,
                   page_map, toc_entry)

DATA = Path("data")
TEXT = DATA / "text"
INDEX = DATA / "deal_index.csv"
OUT = DATA / "chunks"
REPORT = DATA / "chunk_index.csv"

BARE_INT = re.compile(r"(?m)^\d{1,4}$")

# Floors, not targets. The measured corpus sits well clear of each one, so a
# trip means something changed rather than something was always marginal.
MIN_RECALL = 0.90
MIN_PAGES = 50
MAX_DISAGREE = 5
MAX_OUT_OF_ORDER = 5
MAX_PREFIX_SHARE = 0.20
MAX_STUB_SHARE = 0.05
MIN_CHUNKS = 100


def measure(lines):
    """Heading and page quality for one document, before any chunking."""
    toc = find_toc(lines)
    pages, footers, body_end = page_map(lines)
    headings = find_headings(lines, set(toc), pages)

    declared = sum(1 for i in toc if toc_entry(lines[i]))
    recall = len(headings) / declared if declared else 0.0
    prefix = sum(1 for h in headings if h[3] == "prefix")
    out_of_order = sum(1 for a, b in zip(headings, headings[1:]) if b[0] <= a[0])

    agree = disagree = 0
    for line, _, toc_page, _ in headings:
        got = pages.get(line, "")
        if toc_page.isdigit() and got.isdigit():
            if abs(int(got) - int(toc_page)) <= 1:
                agree += 1
            else:
                disagree += 1

    return {
        "n_toc_entries": declared,
        "n_headings": len(headings),
        "heading_recall": round(recall, 3),
        "n_prefix": prefix,
        "n_out_of_order": out_of_order,
        "page_agree": agree,
        "page_disagree": disagree,
        "n_pages": len(footers),
        "body_end_line": body_end,
    }


def flags_for(stats, chunks):
    """Reasons this document should be looked at before anything is embedded."""
    out = []
    sizes = [c["n_chars"] for c in chunks]

    if not stats["n_toc_entries"]:
        out.append("no-toc")
    if stats["heading_recall"] < MIN_RECALL:
        out.append(f"heading-recall-{stats['heading_recall']}")
    if stats["n_pages"] < MIN_PAGES:
        out.append(f"only-{stats['n_pages']}-pages")
    if stats["page_disagree"] > MAX_DISAGREE:
        out.append(f"page-disagree-{stats['page_disagree']}")
    if stats["n_out_of_order"] > MAX_OUT_OF_ORDER:
        out.append(f"heading-order-{stats['n_out_of_order']}")
    if stats["n_headings"] and stats["n_prefix"] / stats["n_headings"] > MAX_PREFIX_SHARE:
        out.append(f"prefix-matched-{stats['n_prefix']}")
    if not chunks:
        return out + ["no-chunks"]
    if len(chunks) < MIN_CHUNKS:
        out.append(f"only-{len(chunks)}-chunks")

    oversize = sum(1 for s in sizes if s > TARGET_CHARS * 1.25)
    if oversize:
        out.append(f"oversize-chunk-{oversize}")
    stubs = sum(1 for s in sizes if s < 200)
    if stubs / len(chunks) > MAX_STUB_SHARE:
        out.append(f"stub-chunks-{round(100 * stubs / len(chunks))}%")

    # A bare integer surviving into prose means footer stripping missed a page.
    # Tables and index listings carry them legitimately, so this matches the
    # threshold validate_chunks.py check E uses, or the two would disagree.
    leaks = sum(1 for c in chunks
                if c["section_kind"] == "body" and c["word_share"] > 0.6
                and BARE_INT.search(c["text"]))
    if leaks:
        out.append(f"footer-leak-{leaks}")
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    deals = pd.read_csv(INDEX, dtype=str).fillna("")
    print(f"chunking {len(deals)} deals -> {OUT}/")

    # 129 text files against 128 index rows. The orphan is the Bridgecrest
    # document filed under two CIKs, which build_index.py drops by deduping on
    # accession. Named here so nobody later "fixes" the gap with a glob.
    on_disk = {p.name for p in TEXT.glob("*.txt")}
    referenced = {Path(t).name for t in deals.text_file if t}
    orphans = sorted(on_disk - referenced)

    rows, failures, total_chunks = [], [], 0
    seen_sha = set()
    start = time.time()

    for n, deal in enumerate(deals.itertuples(), 1):
        path = Path(deal.text_file)
        if not path.exists():
            failures.append((deal.accession, f"missing {path}"))
            continue
        try:
            source = path.read_text(encoding="utf-8")
            lines = source.split("\n")
            stats = measure(lines)
            chunks = chunk_text(source, deal.accession)
        except Exception as exc:
            failures.append((deal.accession, f"{type(exc).__name__}: {exc}"))
            continue

        with open(OUT / (path.stem + ".jsonl"), "w", encoding="utf-8") as fh:
            for chunk in chunks:
                fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        total_chunks += len(chunks)
        seen_sha.update(c["text_sha1"] for c in chunks)
        kinds = {}
        for chunk in chunks:
            kinds[chunk["section_kind"]] = kinds.get(chunk["section_kind"], 0) + 1

        rows.append(dict(
            accession=deal.accession,
            text_file=deal.text_file,
            chunk_file=f"data/chunks/{path.stem}.jsonl",
            n_chunks=len(chunks),
            n_sections=len({c["section_seq"] for c in chunks}),
            max_chunk_chars=max((c["n_chars"] for c in chunks), default=0),
            distinct_sha1=len({c["text_sha1"] for c in chunks}),
            body=kinds.get("body", 0),
            static_pool=kinds.get("static_pool", 0),
            glossary=kinds.get("glossary", 0),
            index=kinds.get("index", 0),
            mortgage_loans=kinds.get("mortgage_loans", 0),
            other=len(chunks) - sum(kinds.get(k, 0) for k in
                                    ("body", "static_pool", "glossary", "index",
                                     "mortgage_loans")),
            flags=",".join(flags_for(stats, chunks)),
            **stats,
        ))
        if n % 20 == 0 or n == len(deals):
            print(f"  {n}/{len(deals)}")

    report = pd.DataFrame(rows)
    report.to_csv(REPORT, index=False, encoding="utf-8")

    print(f"\ndone in {time.time() - start:.0f}s")
    print(f"wrote {REPORT}  rows={len(report)}")
    print(f"  chunks:          {total_chunks:,}")
    print(f"  distinct text:   {len(seen_sha):,} "
          f"({100 * len(seen_sha) / max(total_chunks, 1):.1f}% of chunks)")
    print(f"  heading recall:  min {report.heading_recall.min():.3f}  "
          f"median {report.heading_recall.median():.3f}")
    agree, disagree = report.page_agree.sum(), report.page_disagree.sum()
    print(f"  page agreement:  {agree:,} / {agree + disagree:,} "
          f"({100 * agree / max(agree + disagree, 1):.2f}%)")

    print("\nchunks by section kind:")
    for kind in ("body", "static_pool", "glossary", "index", "mortgage_loans", "other"):
        print(f"  {kind:<16} {report[kind].sum():>8,}")

    print(f"\norphan text files not in the deal index: {len(orphans)}")
    for name in orphans:
        print(f"  {name}")

    flagged = report[report["flags"] != ""]
    print(f"\nfailures: {len(failures)}  flagged: {len(flagged)}")
    for accession, why in failures:
        print(f"  {accession}: {why}")
    for row in flagged.itertuples():
        print(f"  {Path(row.text_file).stem[:52]}: {getattr(row, '_asdict')()['flags']}")


if __name__ == "__main__":
    main()
