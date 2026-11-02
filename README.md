# SEC ABS Prospectus Manifest Validation

## Manifest Validation

This component validates the relationship between:

- The expected SEC filing records listed in `data/_manifest.csv`.
- The actual prospectus documents stored in `data/`.

This validation is an important first step toward building a question-answering and surveillance tool over SEC asset-backed securities (ABS) prospectuses. Before the documents can be searched or used in a retrieval-augmented generation (RAG) system, each filing record must be reliably connected to the correct local document.

## Validation Process

The Python validator:

- Confirms that all required manifest columns exist.
- Scans `data/` for HTML and PDF prospectuses.
- Checks whether every manifest record points to an existing local file.
- Checks whether every local prospectus is referenced by the manifest.
- Validates the formats and relationships of the metadata in each column, including filing dates, CIKs, accession numbers, SEC URLs, document names, local paths, and download statuses.
- Detects duplicate accessions and records that point to the same local filename.
- Automatically fixes safe, deterministic problems that do not require human judgment.
- Leaves ambiguous findings unchanged and marks them for human review.
- Produces a cleaned manifest, a detailed CSV validation report, and a readable Markdown summary.

The validator does not automatically delete or merge duplicate records. A repeated accession or shared filename may represent incorrect metadata, a legitimate filing relationship, or a document that was overwritten during downloading. These cases must be verified using authoritative SEC filing pages before they can be safely changed.

## Main Results

Each **filing record** is one row in the manifest describing an expected SEC submission. An **accession number** is the SEC identifier for a submission, so the number of unique accessions shows how many distinct submission identifiers appear in the manifest. A **local prospectus file** is an HTML or PDF document currently stored in `data/`, while an **issuer** is the company or entity associated with a filing. These totals measure different parts of the collection, so they are not expected to be identical.

- **129 filing records:** The manifest contains 129 rows representing expected filings.
- **128 unique accessions:** One accession number appears in two different rows and requires review.
- **122 local prospectus files:** There are 122 HTML or PDF prospectus documents stored in `data/`.
- **16 issuers:** The collection represents 16 distinct entities.
- **No missing files:** Every filename referenced by the manifest exists locally.
- **No unreferenced files:** Every local prospectus is referenced by at least one manifest row.
- **129 paths safely normalized:** Every original path used the old Windows-style `./data_v1/filename` location and notation. The cleaned manifest now uses portable paths in the form `data/filename`.
- **14 row-level duplicate findings require review:** These consist of 12 duplicate-path flags and two duplicate-accession flags.

The difference between 129 filing records and 122 local files is primarily caused by multiple records pointing to the same stored filename. The 14 findings are row-level flags, not necessarily 14 separate underlying problems. For example, both rows in a duplicated pair are reported so that every affected record is visible.

## Blockers

- **Twelve duplicate-path flags:** Multiple filing records point to the same local filename. The affected documents must be checked against their SEC filing pages to determine the correct file-to-accession mappings.
- **Two duplicate-accession flags:** The same accession appears in two manifest rows. This may be a legitimate shared filing relationship or incorrect metadata, so the rows were intentionally left unchanged.
- These findings require external verification and cannot be resolved safely from the local filenames and manifest alone.
- The project overview refers to `424B` filings, while the current manifest records use `424H`. The intended filing scope should be confirmed with the project advisor.

The affected mappings should be resolved before the cleaned manifest is treated as the final authoritative input for document parsing and retrieval.

## Usage

From the repository root, run:

```bash
python scripts/validate_manifest.py
```

The validator uses only the Python standard library. It regenerates the cleaned manifest, detailed validation report, and Markdown summary listed below.

## Generated Files

- `scripts/validate_manifest.py` - reproducible validation script.
- `data/_manifest_clean.csv` - cleaned manifest containing deterministic corrections.
- `data/manifest_validation_report.csv` - detailed audit trail of every finding and action.
- `data/manifest_validation_summary.md` - readable summary of the inventory and validation results.
- `Issue1.md` - complete methodology, validation rules, limitations, and usage instructions.


---

## Chunking Passages for Semantic Retrieval

Milestone 2 Task 1. Splits each prospectus into passages so they can be
embedded, since a due diligence question is answered by one provision rather
than a whole filing.

Chunks follow the document's own sections rather than fixed windows. Each
filing states its structure twice, in the table of contents and in the page
footers, and the two agree for 99.9% of headings. That gives every chunk a real
prospectus page number for citation. Passages are packed to an 1800 character
budget.

### Usage

```
python src/run_chunk.py        # writes data/chunks/ and data/chunk_index.csv
python src/validate_chunks.py  # 8 checks, must pass before embedding
```

`data/chunks/` is gitignored, 154MB. `data/chunk_index.csv` is committed and
carries per document quality metrics, so a reviewer can see the state of all
128 documents without regenerating anything.

### Chunk records

One JSON object per line in `data/chunks/<document>.jsonl`:

| field | meaning |
|---|---|
| `chunk_id`, `accession` | unique id, and the deal key that joins to `deal_index.csv` |
| `section_title`, `section_kind` | the heading this passage sits under, and a coarse content class |
| `page_start`, `page_end`, `toc_page` | prospectus page, for citation |
| `line_start`, `line_end`, `char_start`, `char_end` | offsets into `data/text/`, so a passage can be checked against the source |
| `word_share`, `toc_share` | prose versus table, and prose versus listing |
| `text_sha1` | half the corpus is boilerplate repeated across filings |
| `text` | the passage |

Deal name, asset class and SEC URL are not copied in. They live in
`data/deal_index.csv` and join on `accession`.

`section_kind` and `word_share` are hints for filtering at embed time. Nothing
is dropped during chunking, because re-chunking takes under a minute and
re-embedding costs money.

## Retrieval Evaluation

Milestone 2 Task 2. `data/evaluation_questions.jsonl` contains a small gold set
of natural-language questions, expected deal accessions, and supporting quotes.
The evaluation checks the first five returned passages, before removing
repeated deals. It reports correct-deal recall separately from supporting-passage
recall. A supporting passage must contain an annotated quote from the expected
accession, ignoring capitalization and whitespace. At least one annotated quote
per expected deal must match for the question to pass. This does not judge
unannotated paraphrases; review those manually and add verified alternate quotes.

After extracting and chunking the documents, run the evaluator with the
retrieval function provided by Task 3:

```
python src/run_extract.py
python src/run_chunk.py
python src/evaluate_retrieval.py --retriever semantic_search:search
```

The retrieval function must accept `query` and `top_k` arguments and return
ranked records with non-empty `text` and either `accession` or a `deals` list
containing accessions. The team search uses grouped `deals`: a passage shared
by many deals counts as one result rank, and all its deals are checked.
Only the question is sent to retrieval. The evaluator requests five passages by
default (`--top-k` changes this). It verifies gold quotes against stored chunks
before evaluation. `data/retrieval_evaluation.csv` contains separate deal and
passage scores, missing evidence, and returned passage text, IDs and ranks.
`passed_at_k` now means supporting evidence was found for every expected deal;
`deal_passed_at_k` is the separate deal-only check. Missing result text is
an interface error rather than an ordinary retrieval miss. `--candidate-k` was
removed because scoring no longer collects distinct deals from 100 passages.
`src/validate_search.py` remains a separate keyword-search smoke test.

Run evaluator tests with `python -m unittest discover -s tests -v`.

Local baseline (no API key; not an embedding-model quality result):

```powershell
python src/embed.py tfidf
python src/evaluate_retrieval.py --backend tfidf --output data/retrieval_evaluation_tfidf.csv
```

For OpenAI semantic search, build or obtain matching OpenAI vectors, configure
`OPENAI_API_KEY` locally, and run `python src/evaluate_retrieval.py`.
Embedding and uncached queries use the API. Never commit API keys.
The teammate's `validate_retrieval.py` checks search mechanics and citations;
this evaluator complements it with annotated expected-deal and evidence scores.


### Results

86,219 chunks across 128 deals, 43,027 distinct. Heading recall median 0.992,
minimum 0.929. All 8 validation checks pass, including a replay of Milestone 1
keyword search confirming nothing findable before chunking became unfindable
after.
