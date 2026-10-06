"""Task 3: build the deal index, one row per filing in the manifest.

Joins the manifest to the extracted text and derives the two fields the
manifest does not carry: the trust/deal name (the manifest holds the
*depositor*, which is not what an analyst searches by) and the asset class.

Two data problems from Task 1 are handled here rather than hidden:

1. The download script named files ENTITY_DATE_424H.htm, so same-day filings
   from one entity overwrote each other. 129 manifest rows produced 122 files.
   The seven overwritten filings (three Amex, four Verizon series) were
   re-downloaded from their doc_url on 2026-09-15 and saved with the accession
   appended, e.g. Verizon_ABS_II_LLC_2025-08-04_424H_0000929638-25-002866.htm,
   so local_name() looks for that name first. The collision handling below
   stays for any future re-download that collides again: where the survivor
   can be identified (the SGML <FILENAME> matches exactly one row's
   primary_doc) that row gets the text and its siblings are marked
   overwritten; Verizon filings all use primary_doc a424h.htm, so a collision
   there is marked ambiguous.
2. Bridgecrest filed one document under two CIKs sharing accession
   0001104659-26-003790, so rows are deduped on accession.

Usage:
    python src/build_index.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

DATA = Path("data")
TEXT = DATA / "text"
MANIFEST = DATA / "_manifest.csv"
OUT = DATA / "deal_index.csv"

UNSAFE_IN_FILENAME = re.compile(r"[^\w-]")
SGML_FILENAME = re.compile(r"<FILENAME>(.+)")
WORD = re.compile(r"[A-Za-z]{3,}")

# Phrases that separate the asset classes in this corpus. Counts are compared
# against each other, so a stray "mortgage loan" in an auto deal's risk factors
# cannot outvote 100 hits of "financed vehicle".
ASSET_CLASS_KEYWORDS = {
    "CMBS": ("mortgaged propert", "commercial mortgage"),
    "Device payment plans": ("device payment plan",),
    "Credit cards": ("credit card account", "credit card receivable"),
    "Auto lease": ("leased vehicle", "residual value"),
    "Motorcycle loan": ("financed motorcycle", "motorcycle contract"),
    "Auto loan": ("financed vehicle", "retail installment sale contract",
                  "automobile loan contract", "motor vehicle retail installment",
                  "retail installment contract"),
}
MIN_KEYWORD_HITS = 5


def local_name(entity_name, filing_date, form, accession=""):
    """Rebuild the on-disk filename the download script produced.

    Do not use the manifest's local_path, it has Windows backslashes and points
    at a data_v1 folder that does not exist. A file saved with the accession
    appended (the recovered same-day filings) takes precedence.
    """
    slug = UNSAFE_IN_FILENAME.sub("_", entity_name)
    base = f"{slug}_{filing_date}_{form}"
    if accession and (DATA / f"{base}_{accession}.htm").exists():
        return f"{base}_{accession}.htm"
    return f"{base}.htm"


def sgml_filename(path):
    """The original SEC filename recorded in the SGML header."""
    head = Path(path).read_text(encoding="utf-8", errors="replace")[:500]
    m = SGML_FILENAME.search(head)
    return m.group(1).strip() if m else ""


# The cover page always labels the trust "Issuing Entity", but its position
# relative to the name changes by generator: same line after the name (Amex,
# Toyota), the line below it (AmeriCredit, World Omni, Honda), or two lines
# below past a CIK parenthetical (Wells Fargo). So anchor on the label and
# search backwards for something shaped like a trust name.
ISSUING_ENTITY = re.compile(r"(?:as\s+)?Issuing Entity")

# A name is a run of capitalised words ending in "Trust", optionally with a
# series designator. The series can sit inside the name ("Honda Auto
# Receivables 2024-2 Owner Trust") or after it ("World Omni Select Auto Trust
# 2026-A"). "Trust" is spelled out case by case so the rest stays case
# sensitive, otherwise the pattern runs off into ordinary prose.
NAME_TOKEN = r"(?:[A-Z][\w'&.\u2011-]*|20\d\d[\u2011-][A-Za-z0-9]{1,6})"
TRUST_NAME = re.compile(
    r"((?:" + NAME_TOKEN + r"\s+){1,8}[Tt][Rr][Uu][Ss][Tt]"
    r"(?:\s+20\d\d[\u2011-][A-Za-z0-9]{1,6})?)"
)
PARENTHETICAL = re.compile(r"[(\[][^)\]]*[)\]]")
CIK_NEAR_LABEL = re.compile(r"(?:CIK|Central Index Key)[^0-9]{0,20}(\d{7,10})", re.I)

# Wells Fargo's CMBS conduit deals are named "BANK5 2025-5YR18" with no
# "Trust" anywhere, so fall back to a bare name plus series designator.
DEAL_FALLBACK = re.compile(r"^[A-Z][\w&.'‑ -]{2,60}\s+20\d\d[‑-][A-Za-z0-9]{1,8}$")
BOILERPLATE = re.compile(
    r"^(prospectus|subject to completion|the information|filed pursuant"
    r"|registration|this (?:preliminary )?prospectus)", re.I)


def _cover_label(text):
    """Position of the cover page's Issuing Entity label, or None."""
    m = ISSUING_ENTITY.search(text[:8000])
    return m.start() if m else None


def find_deal_name(text):
    """Return the issuing entity (trust) name from the cover page.

    Matched line by line, nearest to the label first. Collapsing the lines into
    one window makes the pattern run backwards through neighbouring capitalised
    boilerplate and return "Asset Backed Notes Honda Auto Receivables 2024-2
    Owner Trust".
    """
    pos = _cover_label(text)
    if pos is None:
        return ""
    lines = text[:pos].split("\n")
    # lines[-1] is whatever precedes the label on its own line, which is where
    # Toyota and Amex put the name. Then walk back up the cover page.
    for line in [lines[-1]] + list(reversed(lines[-8:-1])):
        line = PARENTHETICAL.sub(" ", line).strip(" ​­")
        if not line:
            continue
        found = TRUST_NAME.findall(line)
        if found:
            return re.sub(r"\s+", " ", found[-1]).strip()
        if BOILERPLATE.match(line):
            continue
        if DEAL_FALLBACK.match(line):
            return re.sub(r"\s+", " ", line).strip()
    return ""


SERIES = re.compile(r"\bSeries\s+(20\d\d[‑-][A-Za-z0-9]{1,4})\b", re.I)


def find_series(text):
    """Series designator from the cover page.

    Owner trusts carry the series in the deal name ("... Trust 2024-1"), but
    master trusts do not: all 6 Verizon and all 5 Amex filings share one trust
    name and are told apart only by series. Verizon also files supplementary
    prospectuses for later classes of an existing series, so the series year
    can predate the filing year.
    """
    m = SERIES.search(text[:8000])
    return m.group(1) if m else ""


def find_issuing_cik(text):
    """Cover pages carry the issuing entity CIK. The manifest only has the
    depositor CIK, so this is the better deal-level key. The CIK sits either
    just before the label (Wells Fargo, Amex) or just after it (most others)."""
    pos = _cover_label(text)
    if pos is None:
        return ""
    m = CIK_NEAR_LABEL.search(text[max(0, pos - 300):pos + 150])
    return m.group(1) if m else ""


def find_asset_class(text):
    low = text.lower()
    scores = {
        label: sum(low.count(k) for k in keys)
        for label, keys in ASSET_CLASS_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return (best if scores[best] >= MIN_KEYWORD_HITS else "Unknown"), scores


def resolve_collisions(df):
    """Decide which manifest row owns each file when several map to one name."""
    owner, note = {}, {}
    for name, group in df.groupby("local_name"):
        rows = list(group.itertuples())
        if len(rows) == 1:
            owner[rows[0].accession] = True
            continue
        actual = sgml_filename(DATA / name)
        matches = [r for r in rows if r.primary_doc == actual]
        winner = matches[0] if matches else rows[0]
        for r in rows:
            owner[r.accession] = r.accession == winner.accession
            if r.accession != winner.accession:
                note[r.accession] = "overwritten_by_same_day_filing"
        if len(matches) > 1:
            note[winner.accession] = "ambiguous_same_day_filing"
    return owner, note


def main():
    df = pd.read_csv(MANIFEST, dtype=str).fillna("")
    before = len(df)
    df = df.drop_duplicates(subset="accession", keep="first").copy()
    df["local_name"] = [local_name(r.entity_name, r.filing_date, r.form, r.accession)
                        for r in df.itertuples()]
    print(f"manifest rows {before} -> {len(df)} after dedupe on accession")

    owner, note = resolve_collisions(df)

    rows = []
    for r in df.itertuples():
        txt = TEXT / (Path(r.local_name).stem + ".txt")
        has_text = owner.get(r.accession, False) and txt.exists()
        if has_text:
            status = "ok"
        elif (DATA / r.local_name).exists():
            # The .htm is there but run_extract wrote no text for it, which
            # happens when extract.py rejects a truncated file.
            status = "no_text_file"
        else:
            status = "no_local_file"
        row = dict(
            accession=r.accession,
            deal_name="",
            series="",
            issuing_entity_cik="",
            depositor_name=r.entity_name.strip().rstrip("."),
            depositor_cik=r.cik,
            asset_class="",
            form=r.form,
            filing_date=r.filing_date,
            filing_year=r.filing_date[:4],
            doc_url=r.doc_url,
            local_file="",
            text_file="",
            word_count=0,
            status=note.get(r.accession, status),
        )
        if has_text:
            text = txt.read_text(encoding="utf-8")
            row.update(
                deal_name=find_deal_name(text),
                series=find_series(text),
                issuing_entity_cik=find_issuing_cik(text),
                asset_class=find_asset_class(text)[0],
                local_file=f"data/{r.local_name}",
                text_file=f"data/text/{txt.name}",
                word_count=len(WORD.findall(text)),
            )
        rows.append(row)

    out = pd.DataFrame(rows).sort_values(["depositor_name", "filing_date"])
    out.to_csv(OUT, index=False, encoding="utf-8")

    withtext = out.word_count > 0
    print(f"wrote {OUT}  rows={len(out)}")
    print(f"  rows with text:      {withtext.sum()}")
    print(f"  deal_name found:     {(out.deal_name != '').sum()} / {withtext.sum()}")
    print(f"  issuing cik found:   {(out.issuing_entity_cik != '').sum()} / {withtext.sum()}")
    print(f"  series found:        {(out.series != '').sum()} / {withtext.sum()}")
    ident = (out[withtext].deal_name + " " + out[withtext].series).str.strip()
    print(f"  distinct deal+series: {ident.nunique()} / {withtext.sum()}")
    print("\nstatus:")
    print(out.status.value_counts().to_string())
    print("\nasset classes:")
    print(out[withtext].asset_class.value_counts().to_string())


if __name__ == "__main__":
    main()
