"""Ask a question against the prospectus corpus and see the supporting passages.

Usage:
    python src/ask.py "where are collections initially deposited?"
    python src/ask.py "are the files custodied in paper form?" --issuer Toyota
    python src/ask.py "is the collateral free and clear of liens?" --year 2025 -k 3
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from embed import DEFAULT_BACKEND
from semantic_search import search

WIDTH = 78


def wrap(text, indent="  "):
    for para in text.split("\n"):
        para = para.strip()
        while len(para) > WIDTH:
            cut = para.rfind(" ", 0, WIDTH)
            if cut <= 0:
                break
            print(indent + para[:cut])
            para = para[cut + 1:]
        if para:
            print(indent + para)


def label(deal):
    """Deal name with its series. All 10 Verizon filings share one name."""
    name = deal["deal_name"]
    series = deal.get("series", "")
    return f"{name} {series}".strip() if series and series not in name else name


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--issuer", help="issuer or deal name, e.g. Toyota")
    ap.add_argument("--year", help="filing year, e.g. 2025")
    ap.add_argument("--asset-class", help="e.g. 'Auto loan', CMBS")
    ap.add_argument("-k", type=int, default=5, help="passages to return")
    ap.add_argument("--backend", default=DEFAULT_BACKEND)
    args = ap.parse_args()

    hits = search(args.question, backend=args.backend, issuer=args.issuer,
                  year=args.year, asset_class=args.asset_class, top_k=args.k)

    print(f"\nQ: {args.question}")
    filters = [f for f in (args.issuer, args.year, args.asset_class) if f]
    if filters:
        print(f"   filtered to: {', '.join(filters)}")
    if not hits:
        print("\nNothing matched. Try loosening the filters.")
        return

    for n, hit in enumerate(hits, 1):
        print("\n" + "=" * WIDTH)
        lead = hit["deals"][0]
        print(f"[{n}] {label(lead)}  p{lead['page']}   score {hit['score']}")
        print(f"    {hit['section_title'][:66]}")
        if hit["n_deals"] > 1:
            others = ", ".join(label(d) for d in hit["deals"][1:4])
            more = f" +{hit['n_deals'] - 4} more" if hit["n_deals"] > 4 else ""
            print(f"    also in {hit['n_deals'] - 1} other deal(s): {others}{more}")
        print("-" * WIDTH)
        wrap(hit["text"][:900])
        print(f"\n    {lead['doc_url']}")


if __name__ == "__main__":
    main()
