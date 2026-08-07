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

# AI Surveillance Analysis based on ABS Prospectuses

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
Build a deep agentic AI system using Openai-agents-sdk, or LangChain and LangGraph that autonomously search or scan the library of available ABS prospectus (downloadable from SEC website https://efts.sec.gov/EFTS/hits) — in order to identity potential risk defined by atypical or non-standard practice of clauses. E.g., user may search "is any ABS deal using the paper custody?", the agent is expected to search the document library, and list all the deals that using (or highly likely) using the paper custody.

### Success Criteria
1. Meet the key deliverables and millstones described below
2. The AI agent has decent performance (e.g., 70-80% user can get satisfying answers from the Bot)

### Project Milestones

Below is the key deliverables:
1. Data schema creation: downloading a good set of ABS deals' prospectus from the SEC, and prepare the indexing data schema (September)
2. AI Agent using openai-agents-sdk or LangChain and LangGraph: Multi-node state graph: Planner → Retriever/AI Searching → Reasoner → Evaluator → Reporter (October)
3. Build the user interface (testing and fine tuning the AI agent) (November)

> **Note for the team:** Please create a GitHub Projects board in this repository to break these milestones into weekly tasks. Go to the **Projects** tab → **New project** → Choose **Board** → Add columns for each month.

---

## 📊 Dataset

**Name and Source:** Real ABS prospectuses from SEC EDGAR 424B filings  
**Format:** Text, PDF   
**Size:** Less than or equal to 1 GB
**Location:** https://www.sec.gov/search-filings or https://www.sec.gov/edgar/search/

### Key Details
- [Brief description of what's in the data]
- [Any known limitations or preprocessing needed]
- [Link to data dictionary or documentation, if available]

---

## 🛠️ Suggested Approach

**ML Problem Type:** Large Language Models (LLMs) / Generative AI

**Recommended Libraries:**
- [e.g., pandas, scikit-learn, TensorFlow, Hugging Face]

**Evaluation Metrics:**
- [e.g., Accuracy, Precision/Recall, RMSE, BLEU score]

---

## 📚 Resources to Get Started

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

## 🤝 How We'll Work Together

**Official check-ins:** During our biweekly 45-minute AI Studio Lab Section meeting block (2nd and 4th week of every month)

 **Other ways to reach out to me with questions:** 
* [e.g., Your team's channel within Break Through Tech’s Discord space]
* [e.g., Email; please copy your teammates and AI Studio Coach]
* [e.g., Request a team check-in on Zoom]
* [Note: I will aim to respond within 48 hours. Please reach out to your AI Studio Coach with urgent questions.]

> 💡 **Challenge Advisor: Please update the above based on your availability and preference. If you are not able to answer questions or meet with fellows outside of the biweekly Lab Section check-ins, simply write in "N/A (only available during the official check-in times)"**

**Recommended free coding / collaboration tools**
* […]
* […]

---

## 🚀 Getting Started

1. **Review this overview document** and note any questions for our first meeting
2. **Begin reviewing the dataset** using the link above
3. **Read the GitHub Projects documentation** [here](https://docs.github.com/en/issues/planning-and-tracking-with-projects/learning-about-projects/about-projects)

I’m excited to work with you!

---

## ❓ Questions?

Please bring any questions to our first meeting during the week of August 24th (Break Through Tech’s Bridge to Studio - Session C). 
