# Issue 1: Validate the SEC ABS Prospectus Manifest

## Purpose

This task prepares the repository's SEC asset-backed securities (ABS) prospectuses for later search, NLP, and retrieval-augmented generation (RAG). The project needs a trustworthy inventory connecting each SEC filing record to its locally stored prospectus.

The validation script treats:

- `data/_manifest.csv` as the **expected inventory** of filings and metadata.
- The `.htm`, `.html`, and `.pdf` files directly inside `data/` as the **actual local inventory**.

It reconciles these inventories, validates the manifest's formats and internal relationships, and writes a clean manifest plus two reports. It does **not** download documents, contact the SEC, or read the contents of the prospectus HTML files.

## What the manifest is

`data/_manifest.csv` is a catalog. Each row is expected to describe one SEC filing.

| Field | Meaning |
|---|---|
| `entity_name` | SEC entity or issuer name associated with the filing. |
| `cik` | Central Index Key used by the SEC to identify an entity. |
| `form` | SEC form type, such as `424H`. |
| `filing_date` | Date recorded for the filing. |
| `accession` | EDGAR submission identifier. |
| `primary_doc` | Original filename of the primary document on the SEC site. |
| `doc_url` | Direct SEC archive URL for the primary document. |
| `index_url` | SEC filing-detail/index page. |
| `local_path` | Workspace-relative path to the downloaded local copy. |
| `downloaded` | Whether the corresponding local file is present. |

The manifest was already present when this task began. The repository does not contain provenance documentation or the collection code that created it, so its exact origin cannot be proven from this checkout. Based on its EDGAR fields and generated local filenames, it was likely created by an earlier SEC EDGAR collection/download process. This is an inference, not a confirmed fact.

## Where the validation rules come from

The immediate requirements come from the Challenge Project Overview and Issue 1 acceptance criteria. The SEC-specific formats are consistent with official EDGAR documentation:

- The SEC Submissions API addresses entities using a 10-digit, zero-padded CIK (`CIK##########.json`). See [EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
- EDGAR accession numbers use a 10-digit submitter CIK, two-digit year, and six-digit sequence: `##########-##-######`. See the [SEC explanation of login CIKs and accession numbers](https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/understand-select-set-default-login-cik).
- Filing files are stored under archive locations shaped like `/Archives/edgar/data/{cik}/{accession-without-dashes}/`. See [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
- `YYYY-MM-DD` and workspace-relative forward-slash paths are project conventions. They make dates unambiguous and paths portable across operating systems.

The validator checks syntax and consistency. Passing a check does not prove that a value is factually correct. For example, it confirms that a CIK has ten digits but does not search the prospectus or contact the SEC to prove that it is the correct CIK.

## What the script does

`scripts/validate_manifest.py` uses only Python's standard library.

### 1. Read the expected inventory

The script opens `data/_manifest.csv`, confirms that required columns exist, and reads every row as text. This preserves leading zeroes in CIKs and accessions.

### 2. Read the actual inventory

It scans `data/` for `.htm`, `.html`, and `.pdf` files. It ignores CSVs, Markdown reports, and `.gitkeep`.

### 3. Validate each row

For each manifest row, the script:

1. Extracts the filename from `local_path` and looks for it in `data/`.
2. Reports `missing_file` when it cannot find the file.
3. Reports `noncanonical_path` when the file exists but the path is not in portable `data/filename` form.
4. Requires `filing_date` to be a real `YYYY-MM-DD` date.
5. Requires `cik` to contain exactly ten digits.
6. Requires `accession` to follow `##########-##-######`.
7. Checks that both URLs are syntactically shaped like HTTPS SEC EDGAR archive URLs.
8. Compares `primary_doc` with the filename at the end of `doc_url`.
9. Compares `downloaded` with actual local-file presence.
10. Records accessions and paths for duplicate detection.

`primary_doc` is not compared with the renamed local filename. For example, the SEC may call a document `taot2026-c_424h.htm`, while the local copy is named `TOYOTA_AUTO_FINANCE_RECEIVABLES_LLC_2026-07-08_424H.htm`. The correct internal comparison is `primary_doc` versus the filename in `doc_url`.

### 4. Check in the opposite direction

The script checks every local prospectus against the manifest. A file with no referencing row becomes an `unreferenced_file` finding.

Do not add such a file blindly. First decide whether it is a legitimate prospectus, a duplicate, intentionally excluded, or referenced by an incorrect path. If it is a legitimate missing record, obtain authoritative metadata and add a row.

### 5. Separate automatic fixes from human decisions

The script implements only deterministic corrections:

- Normalize a present file's path to `data/filename`.
- Align `downloaded` with actual file presence.

It never automatically deletes duplicates, invents metadata, renames colliding files, or decides which ambiguous row is correct.

## Example: validating one row

A Toyota row contains:

```text
filing_date: 2026-07-08
cik: 0001131131
accession: 0000929638-26-002565
primary_doc: taot2026-c_424h.htm
doc_url: .../taot2026-c_424h.htm
local_path: ./data_v1\TOYOTA_AUTO_FINANCE_RECEIVABLES_LLC_2026-07-08_424H.htm
downloaded: True
```

The script finds the Toyota filename in `data/`, so the file exists and `downloaded=True` agrees. Its date, CIK, accession, URLs, and `primary_doc` relationship pass. The only finding is that `./data_v1\...` is not the selected path format. The clean output implements:

```text
data/TOYOTA_AUTO_FINANCE_RECEIVABLES_LLC_2026-07-08_424H.htm
```

## Issue-type key

| Issue type | Meaning | Required response |
|---|---|---|
| `noncanonical_path` | A file exists, but the manifest path is not portable `data/filename` form. | Automatically normalize it in the clean manifest. |
| `missing_file` | A row references a filename not found in `data/`. | Locate it, correct the row, or document its absence. |
| `unreferenced_file` | A prospectus file exists but no row references it. | Research it, then add a row or document its exclusion. |
| `invalid_format` | A date, CIK, or accession has the wrong format. | Correct it using authoritative metadata. |
| `invalid_url` | A URL is not shaped like an SEC archive URL. | Obtain the correct SEC filing link. |
| `invalid_value` | A controlled field has an unsupported value. | Normalize it when deterministic. |
| `metadata_mismatch` | Two related fields disagree. | Correct the deterministic field or investigate. |
| `missing_value` | Required metadata is blank. | Populate it from an authoritative source. |
| `duplicate` | An accession or path occurs in multiple rows. | Review the rows; never delete automatically. |

Report action columns:

- `resolution_status`: either `automatically_fixed` or `human_review_required`.
- `implemented_fix`: a deterministic correction already written to `_manifest_clean.csv`.
- `suggested_fix`: the next action when human judgment is required. It is also retained to meet the acceptance criteria.

## Understanding duplicates

Duplicate checks operate on fields in the manifest CSV, not duplicated text inside HTML files.

The accession `0001104659-26-003790` occurs in two rows associated with different Bridgecrest entities. This may be a shared filing relationship, duplicated metadata, or an incorrect field. Both rows are flagged for review rather than deleted.

A duplicate local path means multiple filing rows point to one stored filename. Four Verizon accessions, for example, point to `Verizon_ABS_II_LLC_2025-08-04_424H.htm`. The existing entity/date/form naming scheme cannot distinguish multiple same-day filings. They may need unique accession-based filenames, but their correct document mappings must be verified first.

## Generated outputs

1. `data/_manifest_clean.csv` — a complete copy with deterministic corrections implemented; the original remains unchanged.
2. `data/manifest_validation_report.csv` — one row per finding with its status and implemented or suggested action.
3. `data/manifest_validation_summary.md` — annotated totals, issue counts, and an issue-type key.

## Current results

- **Manifest rows: 129** — expected filing records.
- **Unique accessions: 128** — one accession appears in two rows and needs review.
- **Unique local paths: 122** — several records share stored filenames.
- **Prospectus-like files: 122** — actual local documents.
- **Unique issuers: 16** — distinct `entity_name` values.
- **Date range: 2024-02-01 to 2026-08-12** — earliest through latest valid manifest dates.
- **Automatically fixed: 129** — all original paths used old `./data_v1\...` notation; normalized paths are in `_manifest_clean.csv`.
- **Human review required: 14** — 12 row-level duplicate-path and 2 row-level duplicate-accession findings, not necessarily 14 separate root causes.
- **Missing files: 0** — every referenced basename has a local file.
- **Unreferenced files: 0** — every local prospectus is referenced by at least one row.
- **Invalid core metadata found: 0** — dates, CIK and accession formats, URL syntax, primary-document relationships, and download flags passed the implemented checks.

## How to run

From the repository root:

```powershell
python scripts/validate_manifest.py
```

Or with the repository's Windows environment:

```powershell
.\.venv\Scripts\python.exe scripts\validate_manifest.py
```

Expected output:

```text
Compared 129 manifest rows with 122 prospectus files.
Wrote cleaned manifest: data\_manifest_clean.csv
Wrote 143 report entries: data\manifest_validation_report.csv
Wrote summary: data\manifest_validation_summary.md
```

## Limitations and next step

This local structural validator does not parse prospectus text, make live SEC requests, prove that a local file contains the filing described by its row, resolve shared filing relationships, or recover documents possibly overwritten by filename collisions.

The next human-review step is to investigate duplicate groups using SEC filing index pages. After confirming which document belongs to each accession, distinct filings can receive unique filenames and updated paths.

## Recap

> I built a standard-library Python validator that compares the expected SEC filing inventory in `_manifest.csv` with the actual prospectus files in `data/`. It validates metadata formats and relationships, detects missing and unrepresented files, and identifies duplicate accessions and file mappings. It safely normalizes deterministic path problems into `_manifest_clean.csv` while preserving ambiguous cases for human review. It also produces a detailed CSV report and an annotated Markdown summary so the dataset is understandable and reproducible before entering the NLP and RAG pipeline.
