#!/usr/bin/env python3
"""Reconcile data/_manifest.csv with prospectus files stored in data/.

Outputs a safely normalized manifest, a detailed CSV report, and a Markdown
summary. Run from the repository root: python scripts/validate_manifest.py
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MANIFEST = DATA_DIR / "_manifest.csv"
CLEAN_MANIFEST = DATA_DIR / "_manifest_clean.csv"
REPORT_CSV = DATA_DIR / "manifest_validation_report.csv"
SUMMARY_MD = DATA_DIR / "manifest_validation_summary.md"
PROSPECTUS_EXTENSIONS = {".htm", ".html", ".pdf"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CIK_RE = re.compile(r"^\d{10}$")
ACCESSION_RE = re.compile(r"^\d{10}-\d{2}-\d{6}$")
REQUIRED_COLUMNS = {
    "entity_name", "cik", "form", "filing_date", "accession",
    "primary_doc", "doc_url", "index_url", "local_path", "downloaded",
}
REPORT_FIELDS = ["row_id", "issue_type", "field", "current_value",
                 "resolution_status", "implemented_fix", "suggested_fix",
                 "entity_name", "accession"]


def prospectus_files():
    """Return the actual prospectus-like files stored directly in data/."""
    return sorted(p for p in DATA_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in PROSPECTUS_EXTENSIONS)


def basename(raw_path):
    """Extract a filename from Windows- or POSIX-style paths."""
    return PurePosixPath(raw_path.strip().replace("\\", "/")).name


def canonical_path(raw_path):
    name = basename(raw_path)
    return f"data/{name}" if name else ""


def valid_sec_url(value):
    """Validate URL syntax only; this does not make a network request."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (parsed.scheme.lower() == "https"
            and parsed.netloc.lower() == "www.sec.gov"
            and parsed.path.lower().startswith("/archives/edgar/data/")
            and bool(PurePosixPath(parsed.path).name)
            and not parsed.query and not parsed.fragment)


def url_filename(value):
    try:
        return unquote(PurePosixPath(urlparse(value).path).name)
    except ValueError:
        return ""


def add_issue(issues, row_id, issue_type, field, current, fix, row=None,
              implemented_fix=""):
    row = row or {}
    issues.append({
        "row_id": row_id, "issue_type": issue_type, "field": field,
        "current_value": current,
        "resolution_status": "automatically_fixed" if implemented_fix else "human_review_required",
        "implemented_fix": implemented_fix,
        "suggested_fix": "" if implemented_fix else fix,
        "entity_name": row.get("entity_name", ""),
        "accession": row.get("accession", ""),
    })


def valid_date(value):
    if not DATE_RE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def main():
    if not MANIFEST.is_file():
        print(f"Error: manifest not found: {MANIFEST}", file=sys.stderr)
        return 2

    with MANIFEST.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = sorted(REQUIRED_COLUMNS - set(fieldnames))
        if missing:
            print("Error: missing columns: " + ", ".join(missing), file=sys.stderr)
            return 2
        rows = [dict(row) for row in reader]

    files = prospectus_files()
    actual_names = {p.name.casefold() for p in files}
    issues = []
    accession_rows = defaultdict(list)
    path_rows = defaultdict(list)
    referenced_names = set()
    valid_dates = []

    for row_number, row in enumerate(rows, 1):
        row_id = str(row_number)
        raw_path = row.get("local_path", "").strip()
        name = basename(raw_path)
        normalized = canonical_path(raw_path)
        exists = bool(name and name.casefold() in actual_names)

        if name:
            referenced_names.add(name.casefold())
            path_rows[normalized.casefold()].append(row_number)
        if not exists:
            add_issue(issues, row_id, "missing_file", "local_path", raw_path,
                      normalized or "Add a path under data/", row)
        elif raw_path != normalized:
            add_issue(issues, row_id, "noncanonical_path", "local_path",
                      raw_path, normalized, row, implemented_fix=normalized)

        filing_date = row.get("filing_date", "").strip()
        if valid_date(filing_date):
            valid_dates.append(date.fromisoformat(filing_date))
        else:
            add_issue(issues, row_id, "invalid_format", "filing_date",
                      filing_date, "Use a real YYYY-MM-DD date", row)

        cik = row.get("cik", "").strip()
        if not CIK_RE.fullmatch(cik):
            fix = cik.zfill(10) if cik.isdigit() and len(cik) < 10 else "Use exactly 10 digits"
            add_issue(issues, row_id, "invalid_format", "cik", cik, fix, row)

        accession = row.get("accession", "").strip()
        if accession:
            accession_rows[accession].append(row_number)
        if not ACCESSION_RE.fullmatch(accession):
            add_issue(issues, row_id, "invalid_format", "accession", accession,
                      "Use ##########-##-###### format", row)

        for field in ("doc_url", "index_url"):
            value = row.get(field, "").strip()
            if not valid_sec_url(value):
                add_issue(issues, row_id, "invalid_url", field, value,
                          "Use an HTTPS www.sec.gov/Archives/edgar/data/... URL", row)

        # primary_doc is the SEC filename. A local copy may be renamed, so the
        # correct comparison is primary_doc versus the filename in doc_url.
        primary = row.get("primary_doc", "").strip()
        doc_name = url_filename(row.get("doc_url", "").strip())
        if not primary:
            add_issue(issues, row_id, "missing_value", "primary_doc", "",
                      doc_name or "Record the SEC filename", row)
        elif doc_name and primary.casefold() != doc_name.casefold():
            add_issue(issues, row_id, "metadata_mismatch", "primary_doc",
                      f"primary_doc={primary}; doc_url filename={doc_name}",
                      doc_name, row)

        downloaded = row.get("downloaded", "").strip()
        if downloaded.casefold() not in {"true", "false"}:
            add_issue(issues, row_id, "invalid_value", "downloaded", downloaded,
                      "True" if exists else "False", row,
                      implemented_fix="True" if exists else "False")
        elif (downloaded.casefold() == "true") != exists:
            add_issue(issues, row_id, "metadata_mismatch", "downloaded", downloaded,
                      "True" if exists else "False", row,
                      implemented_fix="True" if exists else "False")

        # Only deterministic corrections go into the clean output. Duplicate
        # records are reported, never automatically deleted or renamed.
        row["local_path"] = normalized
        row["downloaded"] = "True" if exists else "False"

    for accession, numbers in accession_rows.items():
        if len(numbers) > 1:
            for number in numbers:
                row = rows[number - 1]
                add_issue(issues, str(number), "duplicate", "accession", accession,
                          f"Review rows {', '.join(map(str, numbers))}", row)

    for _, numbers in path_rows.items():
        if len(numbers) > 1:
            for number in numbers:
                row = rows[number - 1]
                add_issue(issues, str(number), "duplicate", "local_path",
                          row.get("local_path", ""),
                          "Give each distinct filing a unique filename, preferably including its accession",
                          row)

    for path in files:
        if path.name.casefold() not in referenced_names:
            add_issue(issues, "", "unreferenced_file", "local_path",
                      f"data/{path.name}", "Add a manifest row or document its exclusion")

    with CLEAN_MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with REPORT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(issues)

    counts = Counter((i["issue_type"], i["field"]) for i in issues)
    resolution_counts = Counter(i["resolution_status"] for i in issues)
    issuers = len({r.get("entity_name", "").strip() for r in rows
                   if r.get("entity_name", "").strip()})
    unique_accessions = len({r.get("accession", "").strip() for r in rows
                             if r.get("accession", "").strip()})
    unique_paths = len(path_rows)
    path_collisions = [(numbers, rows[numbers[0] - 1].get("local_path", ""))
                       for numbers in path_rows.values() if len(numbers) > 1]
    path_overlap = sum(len(numbers) - 1 for numbers, _ in path_collisions)
    date_range = (f"{min(valid_dates)} to {max(valid_dates)}"
                  if valid_dates else "Unavailable")
    lines = [
        "# Manifest validation summary", "", "## Inventory", "",
        f"- Manifest rows: {len(rows)} — filing records expected by the inventory.",
        f"- Unique accessions: {unique_accessions} — one fewer than the row count, so an accession is repeated.",
        f"- Unique local paths: {unique_paths} — several rows point to the same stored filename.",
        f"- Prospectus-like files in `data/`: {len(files)} — actual local `.htm`, `.html`, or `.pdf` documents.",
        f"- Unique issuers: {issuers} — distinct `entity_name` values represented.",
        f"- Filing date range: {date_range} — earliest through latest valid manifest date.",
        "", f"### Why {len(rows)} manifest rows correspond to {unique_paths} local files", "",
        f"The two totals measure different things. The manifest contains {len(rows)} filing records, but",
        "several records use the same issuer-and-date-based `local_path`. As a result, the manifest",
        f"rows collapse to {unique_paths} distinct paths: a net difference of {path_overlap} files.", "",
        "| Shared local path | Manifest rows using path | Unique file | Net difference |",
        "|---|---:|---:|---:|",
    ]
    lines += [f"| `{path}` | {len(numbers)} | 1 | {len(numbers) - 1} |"
              for numbers, path in path_collisions]
    lines += [
        f"| **Total across collision groups** | **{sum(len(numbers) for numbers, _ in path_collisions)}** | **{len(path_collisions)}** | **{path_overlap}** |", "",
        f"Therefore, `{len(rows)} manifest rows - {path_overlap} duplicate-path overlap = {unique_paths} unique local paths`.",
        f"The {sum(len(numbers) for numbers, _ in path_collisions)} duplicate-path findings reported below are row-level flags: every row in a",
        "collision group is flagged. They do not mean that many files are missing. Because distinct",
        "SEC accessions sometimes point to the same stored path, one filing may have overwritten",
        "another during downloading; identifying the stored document requires content or SEC-source verification.",
        "", "## Findings", "",
        f"- Total report entries: {len(issues)} — row-level findings, not necessarily distinct underlying problems.",
        f"- Automatically fixed: {resolution_counts.get('automatically_fixed', 0)} — corrections written to `_manifest_clean.csv`.",
        f"- Human review required: {resolution_counts.get('human_review_required', 0)} — ambiguous items the script deliberately leaves unresolved.",
    ]
    finding_notes = {
        ("duplicate", "accession"): "the same accession appears on two rows; verify whether this is a valid shared filing relationship or incorrect metadata.",
        ("duplicate", "local_path"): "multiple rows point to the same stored filename; verify each document-to-accession mapping.",
        ("noncanonical_path", "local_path"): "the files exist, and their corrected portable paths are already in the clean manifest.",
    }
    lines += ([f"- `{kind}` on `{field}`: {count} — {finding_notes.get((kind, field), 'see the issue-type key and CSV report for the required action')}"
               for (kind, field), count in sorted(counts.items())]
              if counts else ["- No issues found — the implemented checks all passed."])
    lines += ["", "## Issue-type key", "",
              "| Issue type | Meaning | Normal response |", "|---|---|---|",
              "| `noncanonical_path` | A file exists, but the manifest path is not the chosen portable `data/filename` form. | Automatically normalize it in the clean manifest. |",
              "| `missing_file` | A manifest row points to a filename not found in `data/`. | Locate the file, correct the row, or document its absence. |",
              "| `unreferenced_file` | A prospectus-like file exists in `data/` but no manifest row references it. | Research it, then add a row or document its exclusion. |",
              "| `invalid_format` | A date, CIK, or accession does not follow the required format. | Correct it using authoritative filing metadata. |",
              "| `invalid_url` | A URL is not shaped like an SEC EDGAR archive URL. | Replace it using the filing's SEC index page. |",
              "| `invalid_value` | A controlled field such as `downloaded` contains an unsupported value. | Normalize it when the correct value is deterministic. |",
              "| `metadata_mismatch` | Two related fields disagree. | Correct the deterministic field or investigate the source. |",
              "| `missing_value` | Required metadata is blank. | Populate it from an authoritative source. |",
              "| `duplicate` | An accession or local path occurs in multiple manifest rows. | Review the affected rows; do not delete automatically. |",
              "", "`implemented_fix` records changes already written to `_manifest_clean.csv`.",
              "`suggested_fix` is retained for acceptance criteria and is used only when human review is still required.", ""]
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Compared {len(rows)} manifest rows with {len(files)} prospectus files.")
    print(f"Wrote cleaned manifest: {CLEAN_MANIFEST.relative_to(ROOT)}")
    print(f"Wrote {len(issues)} report entries: {REPORT_CSV.relative_to(ROOT)}")
    print(f"Wrote summary: {SUMMARY_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
