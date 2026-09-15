"""Task 2: extract clean text for every prospectus in data/ into data/text/.

Usage:
    python src/run_extract.py
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract import extract_text

DATA = Path("data")
OUT = DATA / "text"

# Things that should never survive extraction.
C1_CONTROL = re.compile("[\u0080-\u009f]")
LAYOUT_SPACE = re.compile("[\t\u00a0\u2000-\u200a\u202f\u205f\u3000]")
ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
# A real table of contents shows up a handful of times. Dozens means the
# per-page navigation links were not stripped.
TOC = re.compile(r"table of contents", re.I)
WORD = re.compile(r"[A-Za-z]{3,}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA.glob("*.htm"))
    print(f"extracting {len(files)} files -> {OUT}/")

    failures, flagged, total_words = [], [], 0
    start = time.time()

    for i, path in enumerate(files, 1):
        try:
            text = extract_text(path)
        except Exception as exc:
            failures.append((path.name, f"{type(exc).__name__}: {exc}"))
            continue

        words = len(WORD.findall(text))
        total_words += words

        problems = []
        if C1_CONTROL.search(text):
            problems.append("c1-control-chars")
        if LAYOUT_SPACE.search(text):
            problems.append("layout-whitespace")
        if ZERO_WIDTH.search(text):
            problems.append("zero-width-chars")
        if len(TOC.findall(text)) > 10:
            problems.append(f"{len(TOC.findall(text))}-table-of-contents")
        if words < 5000:
            problems.append(f"only-{words}-words")
        if problems:
            flagged.append((path.name, ",".join(problems)))

        (OUT / (path.stem + ".txt")).write_text(text, encoding="utf-8")
        if i % 20 == 0 or i == len(files):
            print(f"  {i}/{len(files)}")

    print(f"\ndone in {time.time() - start:.0f}s, {total_words:,} words total")
    print(f"failures: {len(failures)}  flagged: {len(flagged)}")
    for name, why in failures + flagged:
        print(f"  {name}: {why}")


if __name__ == "__main__":
    main()
