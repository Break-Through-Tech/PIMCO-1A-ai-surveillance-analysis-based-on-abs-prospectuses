---

> ## Challenge Advisor: Update & Finalize Your Project Overview
>
> > **Note —** **These grey text instructions are just for you, the team's Challenge Advisor; please delete them once you have completed the steps below.**
>
> We've pre-populated this Challenge Project Overview page — which is what will be shared with your Break Through Tech student team in August — using the details from your submission form. You should have received an email inviting you to join this repo as a Collaborator, enabling you to add files and make edits.
> 
> In order for your project to be finalized and assigned to a team, please:
> 1. **Review all sections below** and update or expand any content as needed, making sure to address the SME Feedback in the section immediately below. Look for square brackets to find the places below that require additional inputs from you (e.g., "About [Company / Org Name]").
> 2. **Add your dataset** to the [data folder](data) in this repo.
> 3. **Close the Issue assigned to you in this repo** to let us know that you have made your edits and the overview page is ready for final review. You can do this by going to the _Issues_ tab in the top left section of the menu above, add a comment that says "CA review complete", and click the button to Close the Issue. 
>
> If you're unfamiliar with how to edit a page like this in GitHub, check out [this tutorial](https://ubc-lib-geo.github.io/gis-workshop-waml-template/content/handson/edit-readme.html) for a quick overview (start with step 2 and only edit this page), and [this guide](https://ubc-lib-geo.github.io/gis-workshop-waml-template/content/markdown.html) on how to use Markdown to compose text.
>
>
> **Important —** Remember that this is a public repo. Do NOT include: Proprietary data, PII, API keys, credentials, or anything confidential.

## BTT Internal Evaluation Notes

| Check | Status | Notes |
|-------|--------|-------|
| Python Compatibility | Green | Pure-Python stack (pandas, pypdf, an LLM/embedding client, numpy, scikit-learn, Streamlit). The heavier agent framework has been moved to an optional stretch goal, so the core project stays within reach of students with introductory CS/ML background. |
| Data Readiness | Green | Dataset is now specified: ≤100 SEC EDGAR 424B ABS prospectuses, ≤1 GB, PDF/text, with clear preprocessing notes (text extraction, per-deal organization, table/scan noise). |
| Resource Check | Green | No specialized hardware or proprietary software issues are identified in the submission. The tools indicated are available for student access. |

**Student Fit Score:** 8/10  
**Technical Depth Score:** 7/10  
**Overall Recommendation:** REVISED (to be determined by BTT)

**Advisor Feedback Draft:**
The project offers a practical, well-scoped introduction to retrieval-augmented Q&A over real-world financial documents. The scope has been staged into three tiers — (1) data collection + parsing + metadata filtering, (2) embedding-based semantic Q&A, and (3) an optional agentic layer as a stretch goal — so every team can reach a meaningful deliverable while stronger teams still have room to grow. Dataset size and format are specified, and the evaluation approach (retrieval precision + LLM-as-judge) is appropriate for the student level.

---

# AI Surveillance Analysis based on ABS Prospectuses

**Company / Org:** PIMCO  
**Challenge Advisor:** Simon Fan — _email intentionally left blank (will not be published on this public repo; please do not add it)._  
**AI Studio Coach:** Darshan Ugale, darshan.ugale@breakthroughtech.org  
**Program:** Break Through Tech AI Studio - Fall 2026

---

## About PIMCO

PIMCO is a leading global investment management firm, specializing in fixed income and alternative investments. Our focus is on leveraging innovative technology and data analytics to optimize investments and manage risk effectively.

---

## The Challenge

### Project Summary
Build a **question-answering assistant over a library of SEC ABS prospectuses**. A user asks a plain-English question — for example, *"Which deals appear to use paper (physical) custody?"* — and the system searches the document collection and returns the most relevant deals along with the supporting text snippets.

The project is intentionally **staged from simple to advanced** so that every team reaches a working deliverable:
- **Start simple:** keyword / regular-expression search plus metadata filtering over parsed documents.
- **Then add semantics:** embedding-based retrieval so the assistant can match meaning, not just exact words, and let an LLM summarize the answer with citations.
- **Stretch goal (optional):** a small multi-step "agent" that plans, retrieves, reasons, and reports.

Think of it as a lightweight, student-friendly version of a document-surveillance tool: the goal is learning the full retrieval-augmented Q&A workflow on real financial documents, not building a production system.

### Success Criteria
1. Meet the key deliverables and milestones described below (reaching Milestone 1 alone is already a solid result).
2. On a small held-out set of ~15–20 test questions, the assistant returns the relevant deal(s) among its top results and shows the supporting text/source for each answer.

### Project Milestones

The deliverables are staged so each milestone builds on the previous one. **Finishing Milestone 1 counts as success; Milestones 2–3 raise the ceiling.**

1. **Milestone 1 — Data collection, parsing & metadata filtering (September).** Download a set of ABS prospectuses (424B filings) from SEC EDGAR, extract the text from the PDFs, and build a simple index table (deal name / ticker / filing / extracted text). Support basic keyword or regular-expression search and filtering by metadata (e.g., year, deal type). *Reaching this milestone already meets the bar.*
2. **Milestone 2 — Embedding-based semantic Q&A (October).** Add vector embeddings (e.g., `text-embedding-3-small`) and similarity search so users can ask natural-language questions, then have an LLM produce a short answer with citations back to the source deals.
3. **Milestone 3 — Simple user interface + evaluation (November).** Wrap the assistant in a lightweight UI (e.g., Streamlit or Gradio) and evaluate it against the test-question set.
4. **Stretch / bonus (optional, for teams that finish early).** Build a small multi-step agent (plan → retrieve → reason → report) — e.g. using the OpenAI Agents SDK — add an automatic answer-quality checker, or support cross-deal summarization. This is entirely optional and not required for a successful project.

> **Note for the team:** Please create a GitHub Projects board in this repository to break these milestones into weekly tasks. Go to the **Projects** tab → **New project** → Choose **Board** → Add columns for each month.

---

## Dataset

**Name and Source:** Real ABS prospectuses from SEC EDGAR 424B filings  
**Format:** Text, PDF   
**Size:** ≤ 1 GB (roughly 50–100 filings is plenty to start)  
**Location:** https://www.sec.gov/search-filings or https://www.sec.gov/edgar/search/

### Key Details
- Publicly available offering documents (prospectuses) for asset-backed securities (ABS) deals — long, text-heavy PDFs describing deal structure, collateral, servicing, custody, and legal terms.
- Preprocessing needed: extract text from PDFs (some filings are scanned or contain tables, which can add noise), then organize the text per deal for indexing and search.
- Data is free and public via SEC EDGAR full-text search; no login, credentials, or proprietary data are required.

---

## Suggested Approach

**ML Problem Type:** Large Language Models (LLMs) / Retrieval-Augmented Generation (RAG)

> The examples below are just starting points — teams are free to pick equivalent tools. Any LLM provider works (e.g. OpenAI, or OpenRouter, which offers many models including some free tiers).

**Recommended Libraries:**
- `pandas`, `numpy` — data handling and the index table
- `pypdf` / `PyPDF2` — PDF text extraction
- `sec-edgar-downloader` (or plain `requests`) — pulling filings from EDGAR
- An LLM / embedding client — e.g. `openai`, or any other provider (OpenRouter gives access to many models, including some free tiers). Embeddings such as `text-embedding-3-small` plus LLM answers.
- `scikit-learn` — simple similarity / nearest-neighbor search
- `streamlit` or `gradio` — the Milestone 3 user interface
- *(Optional, stretch goal only:* an agent framework such as the OpenAI Agents SDK — not needed for the core project.)

**Evaluation Metrics:**
- **Retrieval precision / recall @ k** — does the correct deal appear in the top-k results for each test question?
- **LLM-as-judge** — use an LLM to rate whether each generated answer is correct and well-supported by the cited source.
- Light manual spot-checks — confirm answers point to the right deal and text.

---

## Resources to Get Started

The following resources will help your team understand the problem space and potential technical approaches for this project:

**Background Reading:**
- [e.g., Link to an article or blog post about the problem domain]
- [e.g., Link to an industry report or case study]

**Technical Tutorials:**
- [e.g., Link to a free tutorial on the ML technique(s) involved]
- [e.g., Link to documentation for a key library or tool]

**Code Examples:**
- [e.g., Link to a relevant GitHub repo]
- [e.g., Link to a sample implementation or starter code]

**Other:**
- [Links to any additional resources — e.g., papers, videos, podcasts, etc.]

*Feel free to explore beyond these, and share anything interesting you find with me!*

---

## How We'll Work Together

**Official check-ins:** During our biweekly 45-minute AI Studio Lab Section meeting block (2nd and 4th week of every month)

 **Other ways to reach out to me with questions:** 
* N/A — I'm available during the official biweekly Lab Section check-ins. For anything urgent or in between sessions, please reach out to the AI Studio Coach first.

**Recommended free coding / collaboration tools**
* GitHub (code, issues, and the project board)
* OpenRouter (access to many LLMs, including some free tiers)
---

## Getting Started

1. **Review this overview document** and note any questions for our first meeting
2. **Begin reviewing the dataset** using the link above
3. **Read the GitHub Projects documentation** [here](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)

I’m excited to work with you!

---

## Questions?

Please bring any questions to our first meeting during the week of August 24th (Break Through Tech’s Bridge to Studio - Session C). 
