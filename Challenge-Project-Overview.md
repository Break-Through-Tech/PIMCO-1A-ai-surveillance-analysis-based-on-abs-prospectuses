---

> ## Challenge Advisor: Update & Finalize Your Project Overview
>
> > 💡 **These grey text instructions are just for you, the team's Challenge Advisor; please delete them once you have completed the steps below.**
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
> ❌ Remember that this is a public repo. Do NOT include: Proprietary data, PII, API keys, credentials, or anything confidential.

## 📋 BTT Internal Evaluation Notes

| Check | Status | Notes |
|-------|--------|-------|
| Python Compatibility | 🟡 | While the tech stack is predominantly Python, tools like LangChain and LangGraph may introduce additional complexity that requires careful integration and understanding from students. |
| Data Readiness | 🟡 | The status of data readiness is unclear; the actual size and structure of the datasets have not been disclosed, which could lead to data preparation challenges that need to be assessed at the start of the project. |
| Resource Check | 🟢 | No specialized hardware or proprietary software issues are identified in the submission. The tools indicated are available for student access. |

**Student Fit Score:** 5/10  
**Technical Depth Score:** 7/10  
**Overall Recommendation:** REVISE

**Advisor Feedback Draft:**
The proposed project is intriguing with the potential for significant practical applications in the field of AI and finance. However, clarity on data size and structure is essential for a successful student experience. I recommend refining the project scope to better fit the student's current capabilities while allowing for incremental learning.

---

### Project Milestones

Use these milestones to guide your work. Your team will create a **GitHub Projects board** to track tasks within each milestone.

| Month | Milestone | Key Activities |
| :--- | :--- | :--- |
| September | Data Pipeline & Ingestion Setup | • Programmatically ingest ABS prospectuses and monthly servicing reports (424B / 10-D filings) from SEC EDGAR.<br>• Implement PDF layout parsing and text/table chunking pipelines.<br>• Extract baseline deal parameters (credit enhancement tiers, collateral pool attributes, trigger thresholds).<br>• Define evaluation benchmarks for extraction precision and metadata accuracy. |
| October | Core Surveillance & Performance Tracking | • Build RAG and structured LLM pipelines to monitor ongoing pool performance (delinquency rates, loss severity, prepayment speeds).<br>• Develop automated comparative logic to detect trigger breaches, credit rating changes, or structural risk shifts relative to original prospectus terms.<br>• Conduct prompt optimization, error analysis, and hallucination checks on financial figures. |
| November / December | Risk Alerting Dashboard & Deliverables | • Build an interactive Streamlit dashboard providing deal surveillance summaries, performance trend visualizations, and risk alerts.<br>• Integrate citation verification to map extracted surveillance metrics back to source prospectus pages/tables.<br>• Finalize clean, reproducible GitHub repository, technical documentation, and stakeholder presentation deck. |

### Stretch Goals
* **Automated Risk Escalation Flags:** Auto-generate priority alerts when key credit metrics breach predefined risk thresholds or covenant limits.
* **Multi-Quarter Historical Trend Tracking:** Aggregate sequential monthly servicing reports (10-D filings) to plot multi-period credit performance and delinquency trends over time.
* **Cross-Issuer Benchmarking Console:** Build an interactive comparison module in the Streamlit UI to benchmark deal performance across different asset classes and issuers (e.g., Auto vs. Equipment vs. Credit Card ABS).

> **Note for the team:** Please create a GitHub Projects board in this repository to break these milestones into weekly tasks. Go to the **Projects** tab → **New project** → Choose **Board** → Add columns for each month.

---

## 📊 Dataset

**Name and Source:** Real ABS prospectuses (Toyota TALNT, Verizon ABS, Sallie Mae SMB Trust) from SEC EDGAR 424B filings  
**Format:** PDF  
**Size:** unknown  
**Location:** [Link to dataset or instructions for accessing it]

### Key Details
- Real ABS prospectuses from SEC EDGAR 424B filings
- No known limitations or preprocessing needed
- [Link to data dictionary or documentation, if available]

# AI Due Diligence Agent for ABS Prospectuses

**Company / Org:** PIMCO  
**Challenge Advisor:** Simon Fan, [Email address]    
**AI Studio Coach:** Darshan Ugale, darshan.ugale@breakthroughtech.org       
**Program:** Break Through Tech AI Studio - Fall 2026

---

## 🏢 About PIMCO

PIMCO is a leading global investment management firm, specializing in fixed income and alternative investments. Our focus is on leveraging innovative technology and data analytics to optimize investments and manage risk effectively.

---

## 🎯 The Challenge

### Project Summary
Build a deep agentic AI system using LangChain and LangGraph that autonomously conducts structured due diligence on a publicly available ABS prospectus — breaking a DD checklist into subtasks, retrieving relevant evidence from the document, reasoning through each question, self-evaluating the sufficiency of its answers, and generating a comprehensive cited due diligence report.

### Success Criteria
Agent self-scores (Complete / Partial / Not Found + confidence float), Evaluation against 30 hand-crafted Q&A pairs, and stretch goal completeness score.

---

## 🛠️ Suggested Approach

**ML Problem Type:** NLP

**Recommended Libraries:**
- langchain
- langgraph
- openai
- faiss-cpu
- pdfplumber
- sec-edgar-downloader
- pydantic
- streamlit
- fpdf2
- pandas

**Evaluation Metrics:**
- Completeness score, confidence float metrics

---

## 📚 Resources to Get Started

The following resources will help your team understand the problem space and potential technical approaches for this project:

**Background Reading:**
- [Link to an article or blog post about the problem domain]
- [Link to an industry report or case study]

**Technical Tutorials:**
- [Link to a free tutorial on the ML technique(s) involved]
- [Link to documentation for a key library or tool]

**Code Examples:**
- [Link to a relevant GitHub repo]
- [Link to a sample implementation or starter code]

**Other:**
- [Links to any additional resources — e.g., papers, videos, podcasts, etc.]

*Feel free to explore beyond these, and share anything interesting you find with me!*

---

## 🤝 How We'll Work Together

**Check-ins:** During our biweekly 60-min AI Studio Lab Section meeting block (2nd and 4th week of every month)  
**Communication:** [e.g., Slack (Break Through Tech workspace) or email]  
**Response time:** [e.g., Within 48 hours on weekdays]  

**Recommended Tools:**
- **Coding:** [e.g., Google Colab, VS Code]
- **Collaboration:** [e.g., GitHub, Notion]
- **Virtual Meetings:** [e.g., Zoom, Google Meet]

---

## 🚀 Getting Started

1. **Review this overview document** and note any questions for our first meeting
2. **Begin reviewing the dataset** using the link above
3. **Read the GitHub Projects documentation** [here](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)

I'm excited to work with you!

---

## ❓ Questions?

Please bring any questions to our first meeting during the week of August 24th (Break Through Tech's Bridge to Studio - Session B).

---
