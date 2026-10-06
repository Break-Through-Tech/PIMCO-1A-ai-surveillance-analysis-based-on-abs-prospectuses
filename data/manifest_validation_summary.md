# Manifest validation summary

## Inventory

- Manifest rows: 129 — filing records expected by the inventory.
- Unique accessions: 128 — one fewer than the row count, so an accession is repeated.
- Unique local paths: 122 — several rows point to the same stored filename.
- Prospectus-like files in `data/`: 122 — actual local `.htm`, `.html`, or `.pdf` documents.
- Unique issuers: 16 — distinct `entity_name` values represented.
- Filing date range: 2024-02-01 to 2026-08-12 — earliest through latest valid manifest date.

### Why 129 manifest rows correspond to 122 local files

The two totals measure different things. The manifest contains 129 filing records, but
several records use the same issuer-and-date-based `local_path`. As a result, the manifest
rows collapse to 122 distinct paths: a net difference of 7 files.

| Shared local path | Manifest rows using path | Unique file | Net difference |
|---|---:|---:|---:|
| `data/Verizon_ABS_II_LLC_2025-08-04_424H.htm` | 4 | 1 | 3 |
| `data/Verizon_ABS_II_LLC_2025-07-22_424H.htm` | 2 | 1 | 1 |
| `data/AMERICAN_EXPRESS_CREDIT_ACCOUNT_MASTER_TRUST_2025-07-10_424H.htm` | 2 | 1 | 1 |
| `data/AMERICAN_EXPRESS_CREDIT_ACCOUNT_MASTER_TRUST_2025-05-01_424H.htm` | 2 | 1 | 1 |
| `data/AMERICAN_EXPRESS_CREDIT_ACCOUNT_MASTER_TRUST_2024-04-11_424H.htm` | 2 | 1 | 1 |
| **Total across collision groups** | **12** | **5** | **7** |

Therefore, `129 manifest rows - 7 duplicate-path overlap = 122 unique local paths`.
The 12 duplicate-path findings reported below are row-level flags: every row in a
collision group is flagged. They do not mean that many files are missing. Because distinct
SEC accessions sometimes point to the same stored path, one filing may have overwritten
another during downloading; identifying the stored document requires content or SEC-source verification.

## Findings

- Total report entries: 143 — row-level findings, not necessarily distinct underlying problems.
- Automatically fixed: 129 — corrections written to `_manifest_clean.csv`.
- Human review required: 14 — ambiguous items the script deliberately leaves unresolved.
- `duplicate` on `accession`: 2 — the same accession appears on two rows; verify whether this is a valid shared filing relationship or incorrect metadata.
- `duplicate` on `local_path`: 12 — multiple rows point to the same stored filename; verify each document-to-accession mapping.
- `noncanonical_path` on `local_path`: 129 — the files exist, and their corrected portable paths are already in the clean manifest.

## Issue-type key

| Issue type | Meaning | Normal response |
|---|---|---|
| `noncanonical_path` | A file exists, but the manifest path is not the chosen portable `data/filename` form. | Automatically normalize it in the clean manifest. |
| `missing_file` | A manifest row points to a filename not found in `data/`. | Locate the file, correct the row, or document its absence. |
| `unreferenced_file` | A prospectus-like file exists in `data/` but no manifest row references it. | Research it, then add a row or document its exclusion. |
| `invalid_format` | A date, CIK, or accession does not follow the required format. | Correct it using authoritative filing metadata. |
| `invalid_url` | A URL is not shaped like an SEC EDGAR archive URL. | Replace it using the filing's SEC index page. |
| `invalid_value` | A controlled field such as `downloaded` contains an unsupported value. | Normalize it when the correct value is deterministic. |
| `metadata_mismatch` | Two related fields disagree. | Correct the deterministic field or investigate the source. |
| `missing_value` | Required metadata is blank. | Populate it from an authoritative source. |
| `duplicate` | An accession or local path occurs in multiple manifest rows. | Review the affected rows; do not delete automatically. |

`implemented_fix` records changes already written to `_manifest_clean.csv`.
`suggested_fix` is retained for acceptance criteria and is used only when human review is still required.
