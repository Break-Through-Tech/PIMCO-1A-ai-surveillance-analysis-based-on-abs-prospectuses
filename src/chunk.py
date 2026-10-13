"""Split extracted prospectus text into passages for embedding-based retrieval.

Input is a file from data/text/, produced by extract.py: one document block per
line. Chunks follow the document's own sections rather than fixed windows,
since a 424H answers a question like "where are collections deposited" in one
provision.

Each filing states its structure twice, in the table of contents and in the
page footers, and the two agree for 99.9% of headings. Matching on that
agreement is what lets a repeated subhead like "General" (9 occurrences in one
Harley file) resolve to the right one.

Three things that look reasonable and are wrong here:

    Capitalisation is not a heading test. AFS SenSub is all caps in the TOC and
    title case in the body, CarMax and Verizon are the inverse, BMW uses both
    in one file.

    Not every bare integer is a footer. One AmeriCredit file has 236 of them
    and only 148 are pages, the rest being a pool factor table's month column.

    Packing by line count would vary 50x. Median line is 63 chars but 10.9% of
    lines exceed 500 and hold 56.7% of the text.
"""

import hashlib
import re

TARGET_CHARS = 1800
# Carried as whole blocks, so only 47.6% of in-section boundaries get any.
# Boundaries fall between whole blocks anyway, so this is insurance.
OVERLAP_CHARS = 200
STUB_CHARS = 200

# Wells Fargo tables of contents run past line 600. A 500 line window drops 2
# to 62 headings in 6 of their 10 files.
TOC_SCAN_LINES = 1500
TOC_GAP_LINES = 10
TOC_MIN_ENTRIES = 8

# Length alone is the wrong guard, World Omni glues "SUMMARY OF TERMS" (16
# chars) onto its paragraph. Page agreement in find_headings does the work.
MIN_PREFIX_TITLE = 12

CURLY = str.maketrans("‘’“”‐‑–—", "''\"\"----")
NOT_PLAIN = re.compile(r"[^a-z0-9 ]")
SPACES = re.compile(r" {2,}")

# Dot leaders survive some generators as runs of periods or spaced periods.
LEADERS = re.compile(r"[.\u00b7\u2026]{2,}\s*$|(?:\.\s){3,}")

BARE_INT = re.compile(r"^\d{1,4}$")
# Annex pages label themselves: A-1, S-I-19, A-II-7, D-2-22.
ANNEX_PAGE = re.compile(r"^[A-Z]{1,2}(?:-[A-Z0-9]{1,4}){1,3}$")
ROMAN = re.compile(r"^[ivxlcdm]{1,7}$", re.I)

ANNEX_PREFIX = re.compile(r"^(?:annex|appendix|schedule|exhibit)\s+[a-z0-9-]{1,6}\s+", re.I)


def normalize(line):
    """Comparison form for matching a TOC title to a body heading.

    Case is deliberately destroyed rather than tested. Issuers disagree about
    which of the two copies is capitalised, and BMW disagrees with itself.
    """
    out = line.translate(CURLY).casefold()
    out = NOT_PLAIN.sub(" ", out)
    return SPACES.sub(" ", out).strip()


def toc_entry(line):
    """Split a table of contents line into (title, page token), or None.

    Page tokens come in three shapes in this corpus: arabic (RISK FACTORS 20),
    lowercase roman (NOTICE TO INVESTORS: UNITED KINGDOM ii) and annex-style
    (ANNEX B CLEARANCE ... B-1).
    """
    text = LEADERS.sub(" ", line).strip()
    if " " not in text:
        return None

    title, _, page = text.rpartition(" ")
    title = title.strip(" .\u00b7")
    if not title or len(title) > 150:
        return None

    if page.isdigit():
        # Cover pages are full of prose ending in a year: "February ___, 2024".
        # Real pages top out at 630 (Wells Fargo).
        if not 1 <= int(page) <= 999:
            return None
    elif not (ROMAN.match(page) or ANNEX_PAGE.match(page)):
        return None

    # A title has to contain letters, or "(2) Plus accrued interest, 2024" gets in.
    if not re.search(r"[A-Za-z]{2}", title):
        return None

    return title, page


def find_toc(lines):
    """Line indices of the first dense table of contents block.

    First, not densest: Wells Fargo repeats its whole TOC on the back cover.
    The gap tolerance matters in the other direction, because AmeriCredit
    interrupts its own TOC with a bare "Page" column header.
    """
    hits = [i for i, line in enumerate(lines[:TOC_SCAN_LINES]) if toc_entry(line)]
    if not hits:
        return []

    block = [hits[0]]
    for prev, cur in zip(hits, hits[1:]):
        if cur - prev > TOC_GAP_LINES:
            if len(block) >= TOC_MIN_ENTRIES:
                return block
            block = []
        block.append(cur)
    return block if len(block) >= TOC_MIN_ENTRIES else []


# Extraction occasionally drops a footer, which splits the sequence. Strict +1
# kept one run and leaked the rest into prose (CarMax pages 12 and 34). A small
# step tolerates that without admitting pool table rows, which also climb by 1
# but sit densely in one place.
MAX_PAGE_STEP = 3
CHAIN_WINDOW = 80


def _page_chain(values):
    """Longest chain of bare integers that reads like a page sequence.

    values is (line index, integer) in line order. A chain steps forward in
    both line index and value, by no more than MAX_PAGE_STEP in value.
    """
    if not values:
        return []
    best = [1] * len(values)
    prev = [-1] * len(values)
    for i in range(len(values)):
        for j in range(max(0, i - CHAIN_WINDOW), i):
            if 1 <= values[i][1] - values[j][1] <= MAX_PAGE_STEP and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    end = max(range(len(values)), key=lambda i: best[i])
    chain = []
    while end != -1:
        chain.append(values[end])
        end = prev[end]
    return chain[::-1]


def page_map(lines):
    """Return (pages, footers, body_end).

    pages maps a line index to the page label that line sits on, as a string
    because annex pages are "A-II-7". footers is the set of line indices that
    are page markers and must be dropped. body_end is the last line of the
    arabic run, which is also the annex boundary: in every issuer sampled the
    last body footer is immediately followed by the annex heading.
    """
    ints = [(i, int(line)) for i, line in enumerate(lines) if BARE_INT.match(line.strip())]
    run = _page_chain(ints)
    if not run:
        return {}, set(), len(lines) - 1

    footers = {i for i, _ in run}
    labels = [(i, str(n)) for i, n in run]
    body_end = run[-1][0]

    for i in range(body_end + 1, len(lines)):
        if ANNEX_PAGE.match(lines[i].strip()):
            footers.add(i)
            labels.append((i, lines[i].strip()))

    # A footer closes its page, so a line belongs to the first footer at or
    # after it. Verified: line 74 is "i" and the TOC above it is page i.
    pages = {}
    cursor = 0
    for i in range(len(lines)):
        while cursor < len(labels) and labels[cursor][0] < i:
            cursor += 1
        if cursor < len(labels):
            pages[i] = labels[cursor][1]
    return pages, footers, body_end


def _page_num(label):
    """Arabic page as an int, or None for roman and annex labels."""
    return int(label) if label and label.isdigit() else None


def find_headings(lines, toc_idx, pages):
    """Locate each contents title in the body, as (line, title, page, how).

    Matching is constrained by page agreement rather than a forward cursor. A
    cursor alone collapses on the issuers that glue a subhead onto its
    paragraph, where one early miss pushes it past everything else.
    """
    by_norm = {}
    for i, line in enumerate(lines):
        if i in toc_idx or toc_entry(line):
            continue
        by_norm.setdefault(normalize(line), []).append(i)

    norm_lines = {i: normalize(lines[i]) for i in range(len(lines))}

    found = []
    cursor = 0
    for i in toc_idx:
        entry = toc_entry(lines[i])
        if not entry:
            continue
        title, page = entry
        want = _page_num(page)

        key = normalize(title)
        cands = [(j, "exact") for j in by_norm.get(key, [])]

        # "ANNEX A STATIC POOL INFORMATION" is one TOC line but two body lines.
        if not cands:
            stripped = normalize(ANNEX_PREFIX.sub("", title))
            if stripped and stripped != key:
                cands = [(j, "exact") for j in by_norm.get(stripped, [])]

        # Some issuers run the subhead and its paragraph together. World Omni
        # does it to its whole summary section in the 2026 filings.
        if not cands and len(title) >= MIN_PREFIX_TITLE:
            cands = [(j, "prefix") for j, text in norm_lines.items()
                     if j not in toc_idx and text.startswith(key + " ")]

        if want is not None:
            agree = [c for c in cands
                     if (_page_num(pages.get(c[0], "")) or -99) in (want - 1, want, want + 1)]
            if agree:
                cands = agree

        if not cands:
            continue

        ahead = [c for c in cands if c[0] >= cursor]
        pool = ahead or cands
        pool.sort(key=lambda c: (c[1] != "exact", c[0]))
        line, how = pool[0]
        found.append((line, title, page, how))
        cursor = line + 1

    found.sort(key=lambda h: h[0])
    return found


# Enumerated definitions arrive as one giant line whose clauses are separated
# by semicolons, so semicolons split as well as sentence enders.
SENTENCE = re.compile(r"(?<=[.;:])\s+")
WORD3 = re.compile(r"[A-Za-z]{3,}")
# A contents or back-of-book index entry is a title and exactly one page
# number. The bound on digit count is what keeps amortization table rows
# ("Closing Date 100 100 100 100") from matching.
TOC_LINE = re.compile(r"^(?=(?:[^0-9]*[0-9]){1,4}[^0-9]*$)"
                      r"[A-Za-z][^0-9]{4,}\s+(?:\d{1,3}|[ivxlcdm]{1,7})$")
CLOSERS = ".;:?!\"')\u201d\u2019"

# Checked in order: "Index of Defined Terms" must not be read as a glossary.
SECTION_KINDS = (
    ("index", ("index of defined terms", "index of terms")),
    ("static_pool", ("static pool",)),
    ("glossary", ("glossary", "defined terms")),
    ("clearance", ("clearance settlement", "settlement and tax")),
    ("mortgage_loans", ("characteristics of the mortgage loans",
                        "mortgage loan representations")),
    ("portfolio", ("trust portfolio",)),
)


def word_share(text):
    """Share of characters sitting in 3+ letter words.

    Separates numeric tables from prose: an AmeriCredit static pool table
    scores 0.02 and a CarMax one 0.17, against 0.77 for risk factor prose.
    """
    if not text:
        return 0.0
    return sum(len(m.group()) for m in WORD3.finditer(text)) / len(text)


def _kind_for(kind, listing, page):
    """Final tag, letting the chunk's own page and content override its section."""
    if listing > 0.6:
        return "index"
    if kind == "body" and page and not page.isdigit():
        return "annex_other"
    return kind


def toc_share(text):
    """Share of lines shaped like a contents entry.

    Issuers put these listings in places the contents-block detector does not
    reach: Harley's back-of-book index carries no heading of its own, and
    Wells Fargo prints a second risk factor listing on page 4. Measuring the
    chunk itself catches both without guessing at headings.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 5:
        return 0.0
    return sum(1 for l in lines if TOC_LINE.match(l)) / len(lines)


def section_kind(title, start, body_end):
    """Coarse content class, used to filter at embed time rather than here."""
    low = normalize(title)
    # "Index of Principal Terms" and "Index of Defined Terms" are the same
    # back-of-book listing under different issuer house styles.
    if low == "index" or low.startswith("index of"):
        return "index"
    for kind, keys in SECTION_KINDS:
        if any(k in low for k in keys):
            return kind
    return "body" if start <= body_end else "annex_other"


def units(lines, lo, hi, drop):
    """Text blocks for lines [lo, hi), as (text, first_line, last_line).

    Footers interrupt a paragraph mid sentence in 30.8% of page breaks, so a
    block whose predecessor had something dropped between them and which
    starts lowercase is rejoined rather than started fresh.
    """
    out = []
    for i in range(lo, hi):
        if i in drop:
            continue
        text = lines[i].strip()
        if not text:
            continue
        if out:
            prev, first, last = out[-1]
            if last < i - 1 and prev[-1:] not in CLOSERS and text[:1].islower():
                out[-1] = (prev + " " + text, first, i)
                continue
        out.append((text, i, i))
    return out


def split_long(unit):
    """Break a single line that exceeds the budget on its own.

    3,337 lines in the corpus exceed 2,000 characters; the worst is a 6,508
    character "Eligible Investments" definition. The pieces keep the original
    line span, so a citation still says truthfully which line this came from.
    """
    text, first, last = unit
    if len(text) <= TARGET_CHARS:
        return [unit]
    out, buf = [], ""
    for part in SENTENCE.split(text):
        if buf and len(buf) + 1 + len(part) > TARGET_CHARS:
            out.append((buf, first, last))
            buf = part
        else:
            buf = (buf + " " + part).strip()
    if buf:
        out.append((buf, first, last))
    return out


def pack(items):
    """Greedy fill to TARGET_CHARS, carrying whole blocks back as overlap."""
    packed, buf, size = [], [], 0
    for item in items:
        if buf and size + len(item[0]) + 1 > TARGET_CHARS:
            packed.append(buf)
            tail, taken = [], 0
            for prev in reversed(buf):
                if taken + len(prev[0]) > OVERLAP_CHARS:
                    break
                tail.insert(0, prev)
                taken += len(prev[0])
            buf, size = list(tail), taken
        buf.append(item)
        size += len(item[0]) + 1
    if buf:
        packed.append(buf)
    return packed


def sections(lines, headings, body_end):
    """(start, end, title, toc_page) spans, with stub sections merged forward.

    A section under STUB_CHARS is nearly always a parent heading sitting
    directly on top of its first child, so merging it into what follows fixes
    the size and buys one level of breadcrumb at the same time.
    """
    spans = []
    if not headings or headings[0][0] > 0:
        spans.append((0, headings[0][0] if headings else len(lines), "", ""))
    for n, (line, title, page, _) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        spans.append((line, end, title, page))

    out, carry = [], None
    for start, end, title, page in spans:
        if carry:
            start = carry[0]
            title = f"{carry[1]} > {title}" if title else carry[1]
            page = carry[2] or page
            carry = None
        if title and sum(len(lines[i]) for i in range(start, end)) < STUB_CHARS:
            carry = (start, title, page)
            continue
        out.append((start, end, title, page))
    if carry:
        out.append((carry[0], len(lines), carry[1], carry[2]))
    return out



def chunk_text(text, accession):
    """Split one prospectus into passage records."""
    lines = text.split("\n")
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    toc = find_toc(lines)
    pages, footers, body_end = page_map(lines)
    headings = find_headings(lines, set(toc), pages)
    drop = footers | set(toc)

    records, seq = [], 0
    for section_seq, (start, end, title, toc_page) in enumerate(sections(lines, headings, body_end)):
        blocks = []
        for unit in units(lines, start, end, drop):
            blocks.extend(split_long(unit))
        kind = section_kind(title, start, body_end)

        for group in pack(blocks):
            body = "\n".join(b[0] for b in group)
            listing = toc_share(body)
            first, last = group[0][1], group[-1][2]
            records.append({
                "chunk_id": f"{accession}-{seq:05d}",
                "accession": accession,
                "chunk_seq": seq,
                "section_seq": section_seq,
                "section_title": title,
                # A chunk sitting on an annex page is annex content whatever
                # its section started as: Harley's static pool tables fall
                # under a body heading that began before the annex boundary.
                "section_kind": _kind_for(kind, listing, pages.get(first, "")),
                "toc_share": round(listing, 3),
                "page_start": pages.get(first, ""),
                "page_end": pages.get(last, ""),
                "toc_page": toc_page,
                "line_start": first,
                "line_end": last,
                "char_start": offsets[first],
                "char_end": offsets[last] + len(lines[last]),
                "n_chars": len(body),
                "word_share": round(word_share(body), 3),
                "text_sha1": hashlib.sha1(normalize(body).encode("utf-8")).hexdigest(),
                "text": body,
            })
            seq += 1
    return records


if __name__ == "__main__":
    import sys
    from pathlib import Path

    for arg in sys.argv[1:]:
        recs = chunk_text(Path(arg).read_text(encoding="utf-8"), "SAMPLE")
        print(f"{arg}: {len(recs)} chunks")
        for r in recs[:3]:
            head = r["text"][:160].replace("\n", " ")
            print(f"  [{r['section_kind']}] p{r['page_start']} {r['section_title'][:40]!r}")
            print(f"    {head}")
