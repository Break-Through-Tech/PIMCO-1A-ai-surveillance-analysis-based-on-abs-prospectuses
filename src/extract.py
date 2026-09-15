"""Extract clean text from SEC 424H prospectus .htm files.

The files in data/ are HTML wrapped in SEC's SGML submission format. They come
from three different document generators. Most issuers stick to one, but AFS
SenSub, Ally, Bridgecrest and CarMax each switch between two over time, so this
strips the union of what they use for layout rather than branching per issuer.

    A  55 files  "<!-- Field: Page -->" comment markers
    B  42 files  repeated "Table of Contents" links, <hr> page breaks
    C  25 files  <hr> page breaks, no repeated TOC link

Parser note: use html.parser, not lxml. AmeriCredit, Santander and Amex filings
write smart quotes and dashes as Windows-1252 numeric refs (&#146;, &#151;).
lxml decodes those to raw C1 control characters, one per entity, between about
160 and 2,900 per file (1,115 in AmeriCredit 2024-1), which silently breaks any
search for words like "sponsor's". html.parser gets them right.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment

# Safety net for files that carry raw Windows-1252 bytes rather than entities.
CP1252 = {
    0x80: "\u20ac", 0x82: "\u201a", 0x83: "\u0192", 0x84: "\u201e",
    0x85: "\u2026", 0x86: "\u2020", 0x87: "\u2021", 0x88: "\u02c6",
    0x89: "\u2030", 0x8A: "\u0160", 0x8B: "\u2039", 0x8C: "\u0152",
    0x8E: "\u017d", 0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c",
    0x94: "\u201d", 0x95: "\u2022", 0x96: "\u2013", 0x97: "\u2014",
    0x98: "\u02dc", 0x99: "\u2122", 0x9A: "\u0161", 0x9B: "\u203a",
    0x9C: "\u0153", 0x9E: "\u017e", 0x9F: "\u0178",
}

# Tags that should end a line in the output.
BLOCK_TAGS = ("p", "div", "br", "hr", "tr", "table", "li",
              "h1", "h2", "h3", "h4", "h5", "h6", "center")

# Cells sit side by side on one line, so they need a space, not a line break.
CELL_TAGS = ("td", "th")

# Spaces used for layout: nbsp, en/em/figure/thin, narrow nbsp, tab.
LAYOUT_SPACE = re.compile("[\t\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]")

# Invisible characters some generators use as anchor text and padding: zero
# width space/non-joiner/joiner, word joiner, BOM, soft hyphen. Harley-Davidson
# emits about 20,000 per file. They never sit inside a word here, so they are
# deleted rather than turned into spaces.
ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

# Marks a real block boundary. Source files soft-wrap mid-sentence, so a raw
# newline in the HTML is not a line break and must not be treated as one.
BREAK = "\x00"

TEXT_OPEN = re.compile(r"<TEXT>", re.I)
TEXT_CLOSE = re.compile(r"</TEXT>", re.I)


def read_body(path):
    """Return the HTML inside the SGML <TEXT> wrapper.

    Without this the <TYPE>, <SEQUENCE> and <FILENAME> header values leak into
    the extracted text as a stray '424H 1 d679938d424h.htm 424H' at the top.

    A file that opens <TEXT> and never closes it was cut off in transfer. One
    Wells Fargo filing arrived at half its EDGAR size that way and still parsed
    into a healthy-looking document, so this is an error, not "use the rest".
    """
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    open_m = TEXT_OPEN.search(raw)
    close_m = TEXT_CLOSE.search(raw)
    if open_m and not close_m:
        raise ValueError(f"{path}: <TEXT> is never closed, the file is truncated")
    start = open_m.end() if open_m else 0
    end = close_m.start() if close_m else len(raw)
    return raw[start:end]


def extract_text(path):
    """Return cleaned plain text for one prospectus, one block per line."""
    soup = BeautifulSoup(read_body(path), "html.parser")

    # <title> is just "424H" and adds a stray first line.
    for tag in soup.find_all(["head", "title", "script", "style"]):
        tag.decompose()

    # World Omni and others use HTML comments as page markers, ~200 per file.
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Diagrams are .jpg with no useful alt text. Known coverage gap.
    for img in soup.find_all("img"):
        img.decompose()

    # AmeriCredit repeats a "Table of Contents" link on every page, ~173 times.
    # Harley-Davidson writes the same link as "TABLE OF CONTENTS" next to a
    # zero-width-space anchor, so compare case-insensitively after stripping.
    for anchor in soup.find_all("a"):
        label = ZERO_WIDTH.sub("", anchor.get_text(strip=True)).casefold()
        if label == "table of contents":
            anchor.decompose()

    # Tables hold more prose than numbers in these filings (risk factors,
    # credit enhancement), so flatten them into the text rather than dropping
    # or structuring them.
    for tag in soup.find_all(CELL_TAGS):
        tag.insert_after(" ")
    for tag in soup.find_all(BLOCK_TAGS):
        # Some generators (Toyota, BMW) wrap each cell's contents in <p>.
        # Breaking there would put every cell on its own line and lose the row.
        inside_cell = tag.find_parent(list(CELL_TAGS)) is not None
        tag.insert_after(" " if inside_cell else BREAK)

    # Join with no separator. AmeriCredit renders small caps by splitting words
    # across <small> tags, so "RISK FACTORS" is markup for "R" + "ISK F" +
    # "ACTORS". A separator here would turn every section heading into
    # "R ISK F ACTORS". Spacing comes from the tags handled above instead.
    text = soup.get_text("").translate(CP1252)
    text = ZERO_WIDTH.sub("", text)
    text = LAYOUT_SPACE.sub(" ", text)
    text = re.sub(r"[\r\n]+", " ", text)

    lines = (re.sub(r" {2,}", " ", line).strip() for line in text.split(BREAK))
    return "\n".join(line for line in lines if line)


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        out = Path(arg).with_suffix(".txt").name
        Path(out).write_text(extract_text(arg), encoding="utf-8")
        print(f"{arg} -> {out}")
