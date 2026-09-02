# Nividous Platform — Capability Research for ErgoBite

**Prepared:** 1 September 2026
**Prepared for:** ErgoBite (AI project delivery)
**Subject:** What Nividous actually sells, what agents/components exist, and how ErgoBite can build on it with low-code / no-code

> **Scope note:** This document is a **standalone research deliverable**. It has nothing to do with, and must not be merged into, the hackathon company-comparison project that shares this repository folder. It lives in `nividous_research/` deliberately.

> **Accuracy policy:** Every factual claim below was read directly from `nividous.com` or from the logged-in `community.nividous.com` portal (Learning, Knowledge Base, Download Resources, Forums, and the RoboHelp product documentation behind them) on 1 Sep 2026. Where I could not verify something, I say so explicitly in **Section 12 — What I could NOT verify**. Nothing here is inferred marketing filler.

---

## 1. How this research was done (so you can re-verify)

| Source | Access | What it gave us |
|---|---|---|
| `nividous.com` (public) | Open | Positioning, platform components, industry/function use cases, services model, Quick Start commercials |
| `community.nividous.com/learning/` | Logged in as `amol.a@ergobite.com` | 7 course tracks + full lesson-by-lesson curricula, durations, certification structure |
| `community.nividous.com/knowledge-base-2/` | Logged in | 39 KB troubleshooting articles + 11 full product documentation sets |
| `community.nividous.com/help-documents/...` | Logged in | The real product docs (Adobe RoboHelp). ~650 documented topics extracted across RPA, LPA, Control Center, Smart Bot and API help |
| `community.nividous.com/download-resources/` | Logged in | Installer + release-notes catalogue (Studio only) |
| `community.nividous.com/forums/` | Logged in | Forum taxonomy, topic/post counts, last-activity dates, tag cloud |
| Release Notes PDFs (7.5.1, 7.5.0, 7.0.1, 7.0.0, 6.1.0) | Downloaded | Authoritative feature list per version |

Raw evidence is preserved alongside this file: `toc/` (documentation trees), `pages/` (help topics), `public/` (nividous.com pages), `RN_*.pdf` (release notes), `*.links.txt` (link maps).

---

## 2. Executive summary — the five things that matter

1. **Nividous is not an "AI agent marketplace."** They do **not** publish a catalogue of named, downloadable pre-built agents (no "Invoice Agent", "HR Agent" you can install). What they sell is a **platform of four components** — Studio, RPA Bot, Smart Bot, Control Center — plus a **library of pre-trained ML models and out-of-the-box document templates** that function as ready-made intelligence. The "agent" language on the website is an architectural framing, not a product list.

2. **The real reusable inventory is substantial and specific**: 7 out-of-the-box document models (incl. Indian PAN and Aadhaar), 3 pre-trained text classifiers, 2 pre-trained NLP entity extractors, 4 pre-trained predictive models, ~10 zero-training GenAI functions, 5 selectable OCR engines, and ~20 automation libraries. **This is what you actually assemble solutions from.**

3. **There is a clear gap between marketing and shipped product.** The website talks about agentic orchestration, autonomous agents and a native LLM. The *shipped, documented, downloadable* product as of Studio **7.5.1 (patch dated 06 Aug 2025, published 31 Oct 2025)** is a mature RPA + BPMN low-code + IDP/AI platform with **GenAI features bolted in**. The learning portal has **no agentic-AI course at all**. Plan commercially against what ships, not the deck.

4. **Nividous's own delivery benchmark is 3–4 weeks**, not 1–2. Their fixed-price "Quick Start Guarantee" is: workshop 1–2 days → scoping 1–2 days → implementation 2–3 weeks → rollout 2–3 days. Section 10 covers how ErgoBite can realistically hit a 1–2 week client demand, and when to refuse it.

5. **The commercial route for ErgoBite is the Partner programme.** The community portal only lets you download **Studio**. Control Center, Bot and Smart Bot installers are not published there, and every component has a licence-renewal KB article — so nothing runs end-to-end without a Nividous licence agreement.

---

## 3. What Nividous sells — the four components

Source: `nividous.com/platform`, `nividous.com/platform/studio|rpa-bots|smart-bots|control-center`, plus product docs.

### 3.1 Studio — the build environment (low-code / no-code)
Drag-and-drop visual designer with a palette of **Process Elements** (Start, End, Connector, Condition, True/False Connector, For Loop, Subprocess) plus **Libraries** and **Reusable Libraries**.

Studio is built on Eclipse — the docs reference workspaces, perspectives, Project Explorer, `Studio.ini`, a workbench, and plugin JARs including `com.nividous.studio.sirius.ui` (Eclipse Sirius is the Eclipse modelling-editor framework). Useful to know because Eclipse conventions, memory tuning and plugin patching all apply.

Documented capabilities:
- Visual process designer, table/diagram dual view, auto-connect, diagram validation, styling/re-layout
- Variables: scalar, list, dictionary; built-in variables; scoping; refactor/rename
- Source control: **SVN and Git** integration
- Setup / Cleanup hooks that always run before and after a process
- Export/import of processes, resources and whole Studio projects
- Debugging, detailed execution logs, console/problems panes
- **GenAI RPA code generation** (see 4.6)
- Two perspectives in one IDE: **RPA** and **LPA**

### 3.2 RPA Bot — execution
- **Attended Bots** — sit on an employee workstation, invoked on demand (front-office assist)
- **Unattended Bots** — scheduled, self-start/stop, physical or virtual environments, high-volume transactional

Documented automation surfaces: desktop, web, image-based, **Citrix / virtual environments**, Excel, Word, PDF, email, database, XML, SAP, mobile/tablet, screen & web scraping, anchor-based (change-resilient) element location.

### 3.3 Smart Bot — the AI layer
Native CV, NLP, Predictive Analysis and GenAI. This is where the genuinely reusable "intelligence" lives. Full inventory in Section 4.

Explicit positioning from the docs: *"This automation is achievable without the need for data scientists or specialized expertise, and it operates independently of expensive third-party components."*

### 3.4 Control Center — orchestration and governance
Web portal. Documented modules (from the CC help tree, 171 topics):
- **RPA**: process repository, draft-process versioning + authorisation, schedules, robot monitoring, executed-process filtering, **audit logs**, **Vault** (passwords + variables), RPA dashboard, queue management
- **LPA**: business processes, instances, **My Tasks** (assignment, filtering, follow-up/due dates, comments), JSP-customisable task forms, reports (slice-and-dice / table / card widgets), business dashboards
- **Smart Bot**: full model lifecycle (add → manage → deploy → configure), classification, extraction, predictive, GenAI, text summarisation, clustering
- **Document Processor**: the IDP pipeline builder
- **Document Repository**
- **BRMS**: business rules upload/deploy/manage + API integration

Platform-level: role-based dashboards, fine-grained access control, credential vaults per division, clustering, release management (activate/rollback a process version in one click), RESTful APIs.

---

## 4. The actual "agent" inventory — what you get out of the box

This is the section you asked for. Below is the **complete, verified list** of pre-built intelligence available in the platform.

### 4.1 How Nividous defines an "agent"
From `nividous.com/platform`, a Nividous Agent = three layers:
1. **Deterministic automation layer** — interacts with any system
2. **Intelligence layer** — understands context, decides, using your chosen LLM or the native Nividous-LLM
3. **Governance layer** — Control Center defines what the agent is authorised to do

They market **three capability tiers**, all governed by the same Control Center:
| Tier | What it is | Real product equivalent |
|---|---|---|
| Deterministic | High-volume rules-based | RPA Bot processes |
| AI-assisted | Judgment, classification, document understanding | RPA + Smart Bot models |
| Fully agentic | Autonomous, goal-oriented, cross-system | Positioned; not documented in the community product docs |

### 4.2 Out-of-the-box document models (Computer Vision, "Domain Specific")
Zero training needed. Select the model, pick the fields, save the template.

| Model | Notes |
|---|---|
| **Invoice** | Trained on diverse invoice types; supports tax types, line items, advanced metadata, structured + tabular; built for AP workflows |
| **PAN** | Indian PAN card |
| **Aadhaar** | Indian Aadhaar |
| **Cheque** | Bank cheque (note: Nividous OCR and AWS Textract are *not* supported for cheques) |
| **Driving License** | |
| **Passport** | |
| **Generic** | Form + table field extraction, "Extract full table" option, multi-value fields |

Template-level options: skew/orientation correction, multiple-field extraction, OCR engine selection, edge detection (PAN / Aadhaar / Cheque / DL / Passport).

### 4.3 Pre-trained text classifiers
| Model | Trained on | Output |
|---|---|---|
| **SentimentAnalysis** | Sentiment140 (1.6M tweets) | positive / negative |
| **NewsClassifier** | BBC full-text dataset | business, political, sport, entertainment, technology |
| **SpamSMSClassifier** | UCI SMS Spam Collection (5,574 msgs) | ham / spam |

### 4.4 Pre-trained NLP entity extractors
| Model | Extracts |
|---|---|
| **Resume Parser** | Skills, Degree, Graduation Year, Location, Email, Designation, Years of Experience, Name, College Name, Companies Worked |
| **Generic** (spaCy `en_core_web_sm`) | PERSON, NORP, FAC, ORG, GPE, LOC, PRODUCT, EVENT, WORK_OF_ART, LAW, LANGUAGE, DATE, TIME, PERCENT, MONEY, QUANTITY, ORDINAL, CARDINAL |

### 4.5 Pre-trained predictive models
| Model | Predicts |
|---|---|
| **Loan Credit Fraud Propensity** | Default propensity from ~16 application parameters (income, loan amount/term, credit history, property area, KYC required, etc.) |
| **Credit Card Fraud Detection** | Fraudulent transaction probability |
| **Insurance Claim Prediction** | Health-insurance claim probability (age, gender, BMI, dependents, smoking, region, charges) |
| **Mobile Money Transaction Fraud Detection** | Fraud probability across cash-in / cash-out / debit / payment / transfer |

### 4.6 Generative AI — zero-training functions
System prompts are **pre-configured by Nividous**; the user only supplies input. Available in Control Center → Smart Bot → Generative AI, and via API.

| Function | Typical use |
|---|---|
| Sentiment Analysis | Customer feedback triage |
| Text Summarization | Meeting minutes, long reports |
| Grammar Correction | Outbound comms QA |
| Translation | Manuals, multilingual support |
| Document Comparison | Contract redlines / version diff |
| Document Query | "What are the payment terms?" against a contract |
| Email Generation | Follow-ups, acknowledgements |
| Classification | Support-ticket routing |
| Data Extraction | Invoice fields from scans |
| Auto Annotation (API) | Bootstrapping training datasets |

**Model choice:** native **Nividous-LLM** or integrated **OpenAI GPT** (docs cite TurboGPT 3.5, GPT-4o, GPT-4o mini). The public site additionally claims support for Gemini and Claude plus on-prem **vLLM** and **MCP server integrations** — see Section 12, this is website-only and not in the shipped docs.

**Plus, in Studio:** *Generating RPA Code through GenAI* — write process steps in natural language, get a Nividous RPA script back as a resource file, import it as a subprocess. Disabled by default; enable via `-Dstudio.genai.enable=true` in `Studio.ini` and point Studio at a Smart Bot URL with an `apiadmin` account.

### 4.7 Data extraction methods (choose per document type)
1. **Guided** — user-guided template
2. **Custom Model** — train your own on your dataset (6.5 and 7.0 dataset formats)
3. **Out of the Box (Domain)** — the 7 models above
4. **GenAI based (VLM)** — vision-language model extraction, template-driven
5. **NLP Model Extraction** — NER, pre-trained or custom
6. **Search Based Extraction** — keyword/pattern driven, no training
7. **Digital Extraction** (API) — native-digital documents
8. **CV Template Extraction** (API)

Post-processing: **Adapters** and **Templates**. Human review: **Maker-Checker screen** with confidence thresholds — anything below your benchmark is flagged for review.

### 4.8 Classification methods
Text Classification · Image Classification · Search-Based Classification · ID Card Classification (API) · GenAI Classification

### 4.9 Other Smart Bot capabilities
Text Summarization · Text Clustering · Predictive Analysis · Guidelines-driven dataset preparation · model export/import/migration between environments

### 4.10 IDP / Document Processor pipeline steps
Build a per-project pipeline from these steps:
`Crop Individual Pages` → `Straighten Pages` → `Classify Document` → `Split Files into Logical Documents` → `Extract Information` → `Integrate with Other Processes` → `Custom Step`

Sources: file upload, **email attachments**, cloud storage. Output can **trigger an RPA or LPA process**. Supports scheduling and bulk multi-page documents.

### 4.11 LPA (low-code BPM) building blocks
LPA is BPMN 2.0 based (the docs' vocabulary — Java delegates, execution/task listeners, expression language, Spin functions, call activities — indicates a Camunda-lineage engine).

**Task types:** User Task · Script Task · Service Task · Send Task · Receive Task · **RPA Task** (calls a deployed RPA process with input/output parameters)

**Events:** Start, None, Message (start/boundary, correlation, Message API), Timer (start/boundary, timezone handling), Error (start/end/boundary, catch-and-rethrow), Cancel & Compensation, Conditional, Link, Terminate

**Gateways:** Exclusive (XOR), Parallel, Inclusive, Event-based, conditional/default sequence flows

**Subprocesses:** Embedded, Call Activity, Event Subprocess, Transaction Subprocess

**Also:** Business Objects (entity-to-DB mapping, auto-generated forms), form customisation with sections/fields, multi-instance (parallel) processing, connectors (HTTP, SOAP), web services (consume + expose), BRMS business rules, document variables with multi-file support.

---

## 5. The automation library catalogue (Studio)

Verified from the docs, the 7.5.0/7.5.1 release notes, KB articles and the forum tag cloud. Default palette on a new process is `BuiltIn`, `Desktop2`, `Web`.

| Library | Purpose |
|---|---|
| **BuiltIn** | Core actions, logging, control (`Run Action If`) |
| **Desktop2** (Desktop1 legacy, migration path documented) | Desktop application automation |
| **Web** | Browser automation; Web Recorder on Chrome Manifest V3 |
| **Image Recognition** | Image/pixel-based automation; Citrix & virtual environments |
| **Excel / ExcelLibrary2** | Excel automation incl. complex formula setting |
| **PDF** | PDF automation, `Create Pdf From Html` |
| **Email** | Email automation with **OAuth** support |
| **Database** | DB connectivity and operations |
| **SAP** | SAP automation (SAP Recorder) |
| **SFTP** | File transfer, mask-based search/download |
| **XML** | XML automation |
| **Json** | Added in 7.5.0 |
| **Queue** | Added in 7.5.0, with Queue Framework integration |
| **Vault** | Retrieve credentials/variables from Control Center |
| **Util** | Utilities incl. encrypt/decrypt |
| **Subprocess** | Compose and reuse processes |
| **NLP** | Smart Bot NLP inferencing from RPA — see below |
| **CV** | Smart Bot computer-vision from RPA |
| **GenAI** | Added in 7.5.0 |
| **Document Processor** | IDP pipeline invocation |
| **Mobile automation** | Mobile/tablet activity (KYC, OTP handling, field workforce) |
| **Custom / External** | Bring your own; **Python libraries integrate directly** |
| **Reusable Libraries** | Project-level and Common-Resources shared components |

**NLP Library actions (documented in detail):** `Classify`, `Recognize Entities`, `Prediction Data`, `Get ROI Text`, `Fuzzy Search`. Batch mode supported for classification and entity recognition. A `Text Summarization` action was added to the NLP Library in **7.5.1**.

**Note on lineage:** the docs state Nividous RPA is *"inspired from the Robot Framework"* and uses auto-generated Robot Framework scripts with post-processing. That matters — your Python-fluent engineers will be productive fast.

### OCR engines (selectable per template)
| Engine | Notes |
|---|---|
| **Nividous OCR** | Own trained models. **English only.** Not usable for bank cheques. |
| **Tesseract** | Open source; multi-language via `.traineddata` in `smartbot_data/cv/tessdata` + `sb_config_ocr_lang_list.yaml` |
| **AWS Textract** | Digital, scanned, handwritten. Not usable for Guided templates or cheques. Needs AWS credentials. |
| **Google OCR** | Needs GCP credentials |
| **Azure OCR** | Needs Azure credentials |

---

## 6. Integration surface (APIs)

Two documented API families (v2 / 7.5):

**Control Center APIs** — Get/Upload Template JSON, template name lists, model lists (text classifier, image classifier, search-based classifier, NLP extraction, search-based extraction, predictive analysis), and RPA Process APIs: Get All Processes, Get Process Details, Create Process, Upload Draft Process, Get Active Draft Process(es), Get Draft Process Detail, Download Draft Process.

**Smart Bot APIs** — Token generation (separate tokens for Training Server and Application Server); Classification (text / image / search-based / ID card); Extraction (NLP, search-based, digital, CV template); Predictive Analysis; Text Analysis (GET-ROI, sorted ROI, clustering, summarization); Pre-processing (ID edge detection, orientation detection); Adapter; Utilities (assisted OCR, delete/purge transaction data, pre-signed URL); Model management (load, unload, metadata, import, export, delete, deploy, undeploy, list deployed); and the full Generative AI API set.

**Practical read:** the Smart Bot AI layer is fully headless-accessible. ErgoBite can wrap it behind its own product UI without ever showing a client the Nividous console.

---

## 7. The community portal — exactly what's in there and what's usable

### 7.1 Learning (`/learning/`) — 7 live tracks, 2 placeholders
All free, with quizzes, timed exercises, a hands-on exam and a course certificate.

| Track | Version | Structure | Stated duration |
|---|---|---|---|
| **RPA Essentials** | 7.5 (Jul-2025) and 7.0 (Aug-2021) | 17 sections / 18 lessons | 2 weeks |
| **RPA Advanced** | 7.5 and 7.0 | 15 sections / 15 lessons | 2 weeks |
| **RPA Administration** | — | 15 sections / 17 lessons | 20 hours |
| **LPA Essentials** | 7.5 and 7.0 | 12 sections / 17 lessons (22 items) | Lifetime access |
| **LPA Advanced** | 7.5 and 7.0 | 16 sections / 15 lessons | Lifetime access |
| **Smart Bot Essential** | 7.0 | 12 sections / 14 lessons | 40 hours |
| **Intelligent Document Processing** | 7.5 (Jul-2025) | 7 sections / 9 lessons | 1 week |
| *2 × "Coming Soon"* | — | one under RPA, one under Low-Code | — |

**Curriculum detail (this is your skills ladder):**

- **RPA Essentials 7.5** — Intro to RPA → Nividous platform → install/setup → first process → deep dive → decision statements → loops → collections → file handling & OS ops → string handling → **Quiz 1** → Exercise 1.1 (2 days) → reusability → Excel/PDF/Email automation → error handling → process deployment → **Quiz 2** → Exercise 1.2 (2 days) → **Hands-On Exam (3 days)**
- **RPA Advanced 7.5** — recorders intro → desktop automation + recorder → web automation + recorder → **web scraping** → image automation + recorder → **Citrix & virtual environment (IR automation)** → Quiz 1 → Exercise → **Python library integration** → **custom library creation/management** → database automation → web services & APIs (REST + SOAP) → XML automation → Quiz 2 → Exercise → Hands-On Exam
- **RPA Administration** — process lifecycle → CC setup → Bot setup → user management → **access control** → exercise+solution → Quiz 1 → deployment & scheduling → process monitoring & bot administration → **Vault** → best practices → exercise+solution → Quiz 2 → survey → **Course Certificate** (instructor: admin)
- **LPA Essentials 7.5** — Intro to LPA → **BPMN 2.0 notations** → install Studio/Control Center/Bot → user management → Business Objects → first LPA process → tasks → more on LPA process → Quiz 1 → Exercise 1.1 → gateways → events → **subprocess & call activity** → **form customization** → **RPA Task (LPA↔RPA integration)** → Quiz 2 → Exercise 1.2 → Hands-On Exam (instructor: Jyoti Hunka)
- **LPA Advanced 7.5** — task assignment → process communication → **delegates** → **listeners** → multi-instance processing → dynamic data retrieval → document extraction → Quiz 1 → Exercise → **custom views & portlets** → **BRMS** → reports & dashboards → **web service API** → Quiz 2 → Exercise → Hands-On Exam
- **Smart Bot Essential 7.0** — intro → install/setup → **Smart Bot RPA libraries** → text/image/search-based classification → Exercise → Quiz 1 → CV template-based recognition → datasets & models → NLP entity recognition → search-based entity recognition → predictive analysis → Exercise → Quiz 2 (instructor: Chetan Sindhi)
- **IDP 7.5** — additional configuration settings → best practices → intro to IDP → **server master config** → **project master config** → **pipeline settings config** → execution & notifications → Quiz → Exercise → Hands-On Exam

### 7.2 Knowledge Base (`/knowledge-base-2/`)
Two layers.

**(a) Full product documentation — 11 sets, ~650 topics.** These are the crown jewels. Extracted trees are in `toc/`:

| Doc set | Topics |
|---|---|
| Nividous LPA Help | 212 |
| Control Center Help | 171 |
| Nividous RPA Help | 92 |
| API Help (CC + Smart Bot v2) | 73 |
| Bot Installation Help | 29 |
| CC Installation Help | 25 |
| Studio Installation Help | 15 |
| Infrastructure Help | 14 |
| RPA Quick Start | 11 |
| LPA Quick Start | 11 |
| Best Practices | (article set) |

**Infrastructure Help** covers on-premises (Development / UAT / Production environment sizing) and cloud (**AWS, Google Cloud, Microsoft Azure**).

**(b) 39 troubleshooting articles.** The genuinely useful ones for a delivery team:

*Studio:* Not able to launch Studio · Best practices in process designing · External library in Studio · Rearranging process diagrams · Using upgraded library versions · **How to handle captcha** · Image Recognition Library loading issues · **Citrix Automation** · **Web automation driver crash on long runs (1–6 hrs)** · **How to create a Custom Library** · Process history in Source Editor · Web Recorder vs Chrome >115 · Licences · Screenshot errors in unattended mode · Delay in process execution · IMAP config · `PDFInfoNotInstalledError`

*Control Center:* **LDAP over SSL** · Synchronising LDAP users · Multi-bot issues · **SSL certificate configuration** · Licences · **Multi-user creation at a time** · Concurrent user bifurcation LPA vs non-LPA

*Bot:* AutoItLibrary startup failure · **Project structure for Bot without Control Center** · Licences · Screenshot errors · Delay in execution · **Script to unblock files and executables** · Memory leak from dependent library in DP · IMAP config · `PDFInfoNotInstalledError`

*Smart Bot:* **EncryptText utility** · **How to decide which classification method to use** · How Sentiment Analysis model is useful · Licences

### 7.3 Download Resources (`/download-resources/`) — **Studio only**
| Build | Release notes | Date |
|---|---|---|
| Nividous Studio **7.5.1 Patch** | Yes | March 2025 listing; PDF says released 31/10/2025, patch dated 06/08/2025 |
| Nividous Studio Setup **7.5.0.138** | Yes | Sept 2024 listing; build dated 25/11/2024 |
| Nividous Studio 7.0.1 Patch | Yes | Nov 2023 |
| Nividous Studio Setup 7.0.0.7739 | Yes | March 2023 |
| Nividous Studio Setup 6.1.0.5985 | Yes | April 2022 |
| Nividous Studio Setup 6.0.0.4524 | Yes | August 2021 |

**No Control Center, Bot or Smart Bot installers are published here.** Each download has a separate licence file. This is the single biggest practical constraint on ErgoBite building anything end-to-end without a commercial agreement.

**Key 7.5.0 features (from the release notes, verbatim gist):** GenAI library added to Studio · **ability to generate RPA code using Generative AI** · Queue Library + Queue Framework integrated · Json Library added · Email Library OAuth support · data-driven test automation · HTTPS deployment from Studio · downloadable deployment zips · explicit library loading · Web Recorder upgraded to Chrome Manifest V3. LPA side: downloadable LPA deployment zip · custom data types on variables · migration support from earlier Studio versions · multi-document Document variables · per-process version tracking · custom code in pre/post listeners.
**7.5.1 adds:** NLP Library token-generation timeout + retry config, and a **Text Summarization action in the NLP Library**.

### 7.4 Forums (`/forums/`) — **be realistic about these**
Structure is good; activity is not.

| Public forum | Topics | Posts | Last post |
|---|---|---|---|
| Studio | 114 | 238 | ~5 years 2 months ago |
| Control Center | 16 | 25 | ~5 years 2 months ago |
| Bot | 16 | 30 | ~4 years 11 months ago |
| Smart Bot | 10 | 20 | ~5 years 2 months ago |

There are parallel **Internal** forums (Studio Internal 58/81, last post ~10 months ago; Control Center Internal 22/29; Bot Internal 7/12; Smart Bot Internal 2/1) which are more recent but are Nividous-staff-facing.

Sub-forum taxonomy (useful as a checklist of what the platform can do): Process Designing · Variables and Arguments · Library and Actions · Data Manipulation · Desktop Automation · PDF Automation · Excel Automation · Web Automation · Email Automation · Database Automation · Image Automation · Recorders · Reusable Components · Custom and External Library · Exception Handling · Installation and Troubleshooting.

Tag cloud: Adding Subprocess, Bot, Control Center, Custom Library, Database Connection, Database Library, Debug, Desktop automation, Excel Automation, Excel Library, Exception Handling, Export Project, If Condition, Image Recognition, Loop, OCR, Pdf Automation, Process Deployment, Process Execution, Recorder, Regex, RPA, SAP Automation, SAP Library, Scheduler, SMTP, Studio, Variables, Vault Library, Web Library, Web Recorder, Xpath.

**Verdict:** treat the forum as a searchable archive, not a support channel. Real support goes through `support@nividous.com` (the portal's Contact Support form) or your partner/account manager.

---

## 8. Basic → Intermediate → Advanced: the real service tiers

Nividous doesn't publish tiers, so here is the tiering that falls naturally out of the platform, the training curricula and the delivery effort. **This is the framework I'd recommend ErgoBite adopt for scoping and pricing.**

### Tier 1 — Basic (no-code, zero model training)
*Skills: RPA Essentials + IDP course. 1 person. Days, not weeks.*

- OOTB document extraction: Invoice, PAN, Aadhaar, Cheque, Driving Licence, Passport, Generic
- All 10 GenAI functions (summarise, translate, compare, query, classify, extract, sentiment, grammar, email gen, auto-annotate)
- The 3 pre-trained classifiers, 2 pre-trained NER models, 4 pre-trained predictors
- Excel / PDF / Email / file-and-folder RPA
- Scheduled unattended runs, Vault-managed credentials, CC dashboards
- Search-Based Extraction and Search-Based Classification (keyword/pattern rules, no training)

### Tier 2 — Intermediate (low-code, some configuration and training)
*Skills: RPA Advanced + LPA Essentials + Smart Bot Essential. 2–3 people. 2–4 weeks.*

- Web + desktop automation with recorders; web scraping
- Database automation, REST/SOAP web services, XML/JSON
- **Custom CV templates** (Guided or Custom Model) and **custom NLP/classifier models** trained on client data
- Multi-step **Document Processor pipelines** (crop → straighten → classify → split → extract → trigger downstream)
- **LPA workflows**: user tasks with custom forms, gateways, timers, RPA Tasks, Business Objects mapped to a DB
- Maker-Checker human-in-the-loop with confidence thresholds
- Queue Framework for high-volume work distribution
- Reports and business dashboards in Control Center

### Tier 3 — Advanced (pro-code, enterprise)
*Skills: LPA Advanced + RPA Administration + Java/Python. 3–5 people. 6+ weeks.*

- Citrix / virtual-desktop and SAP automation
- **Custom Studio libraries** and Python library integration
- LPA **Java delegates, execution/task listeners, expression language, Spin functions**, custom portlets and views
- **BRMS** rule authoring, deployment and API integration
- Multi-instance / parallel processing, transaction and event subprocesses, compensation handling
- Multi-environment architecture (Dev/UAT/Prod), clustering, LDAP-over-SSL, SSL certs, RBAC design
- Cloud deployment on AWS / GCP / Azure, or on-prem
- CI-style release management with process versioning and one-click rollback

---

## 9. Where Nividous already has proven demand (your sales map)

Straight from their solutions pages — these are the use-case lists Nividous itself publishes, i.e. the conversations their clients are already having.

**Banking & Finance:** loan processing · account opening · trade finance · compliance · account reconciliation · automated mailers · monthly account reviews · credit card requests · credit underwriting · retail credit assessment · retail fraud detection · regulatory reporting

**Insurance:** customer onboarding · underwriting · complex document automation · policy creation & issuance · claims processing · commission payouts · customer service email automation · financial statement automation · compliance reporting · premium reconciliation · **GenAI-based early claim detection** · fraud detection · automated validation of death certifications

**Healthcare:** claims management · patient assistance · data migration · vendor management · fraud prevention · overpayment reconciliation · data cleansing · customer complaints · drug registration · patient registration · reporting · administration

**Healthcare RCM (5-step model they sell):** eligibility verification → medical coding & claim prep → claim submission across insurer portals → dispute management → claim reconciliation

**Manufacturing:** order processing · BOM processing · product distribution · transportation & delivery · supplier master management · invoice processing · dispute management · credit management · customer billing · journal entries · product/service accounting · statutory compliance

**Life Sciences:** clinical trials · compliance handling · data analysis · regulatory compliance · drug discovery & development · pharmacovigilance · quote-to-cash · patient registration · drug registration · QA · data management & reporting · performance reporting

**Logistics & Supply Chain:** manual data entry · multi-source data collection · information centralisation · shipment scheduling & tracking · freight bill payment · invoice generation & collection · payment dispute resolution · proof-of-delivery capture · load closeout · customer onboarding · appointment scheduling · automated email scanning

**Finance & Accounting (cross-industry):** O2C/AR · P2P/AP · record-to-report · FP&A · tax filing & compliance · fixed asset accounting · budgeting & forecasting · bank reconciliation · expense management · cash flow management · audit preparation · risk management

**HR:** employment history verification · onboarding · payroll · leave & attendance · performance management · expense claims · talent & training · employee records · engagement surveys · self-service portals · MIS/reporting · exit management · final settlements · helpdesk · tax management

**IT / Service Desk:** helpdesk & service requests · ticket creation & remediation · knowledge base management · vendor on/offboarding · IT asset tracking · incident management · SLA tracking · data migration · updates & backups · status reporting · task routing & alerts · security & data auditing · cost tracking · KPI reporting · channel integration

**Contact Centre:** virtual assistants & chatbots · transactional automation · scheduled/triggered customer comms · customer data management · CRM integration · service requests & scheduling · call-centre/email/core-system integration · predictive dialling · speech analytics · QA monitoring · customer behaviour prediction · transcription summaries · abandonment prevention · forecasting & scheduling · live-agent guidance · workflow automation

---

## 10. The "client wants it in 1–2 weeks" question

You asked this directly. Here's the honest answer.

**Nividous's own guarantee is 3–4 weeks** for one trained bot in production, at fixed price, including a 1-year platform subscription. Their breakdown:

| Phase | Duration | What happens |
|---|---|---|
| Workshop | 1–2 days | Identify eligible processes, demo, build the business case |
| Scoping | 1–2 days | Keystroke-level process documentation: activities, exceptions, business rules, I/O fields, trigger values; project plan + sign-off |
| Implementation | 2–3 weeks | Workflow design, Dev/Test/Prod environment setup, agile build |
| Roll-out | 2–3 days | Exception capture with UAT, hypercare during production migration, knowledge transfer |

### What ErgoBite can genuinely deliver in 1–2 weeks
Only if **all** of these hold: environments already exist and are licensed, the process is single-system or document-centric, and you stay inside Tier 1.

Realistic 1–2 week deliverables:
- Invoice / PAN / Aadhaar / cheque / passport / DL extraction with Maker-Checker review — **OOTB models, zero training**
- Any GenAI function wired into a workflow (summarise, translate, compare, query, classify, generate email) — **zero training**
- Email-attachment intake → classify → extract → push to a system of record, using the Document Processor pipeline
- A scheduled Excel/PDF/report-generation unattended bot
- Sentiment or spam classification on an existing text feed using the pre-trained models

### What will **not** fit in 1–2 weeks — push back
- Custom CV or NLP model training (dataset collection, annotation, training, tuning, validation)
- Citrix / virtual-desktop or SAP automation
- Multi-system LPA workflows with custom forms, delegates, listeners or BRMS rules
- Anything requiring new infrastructure, LDAP/SSO, SSL, or a Dev/UAT/Prod build-out
- Anything where the client hasn't already documented the process at keystroke level

### The three levers that actually buy you speed
1. **Reuse over rebuild.** Nividous's own services page says their consultants *"leverage a vast library of reusable Nividous artifacts."* ErgoBite should build the same thing — an internal accelerator library (Section 11).
2. **Pre-trained first, custom later.** Ship the OOTB model in week 1, train the custom model in the background, swap it in during hypercare. The client sees value on day 7.
3. **Escalate to Nividous when the clock is the risk.** For a hard 1–2 week deadline on a Tier-2/Tier-3 scope, the correct move is to co-deliver with Nividous Professional Services under their Quick Start guarantee rather than take the delivery risk yourself.

---

## 11. Recommendations for ErgoBite

### 11.1 Commercial posture
1. **Apply to the Nividous Global Partner programme** (`nividous.com/company/partners`). Without it you cannot download or licence Control Center, Bot or Smart Bot, and you cannot resell. Everything below depends on this.
2. **Position ErgoBite as the AI/agent build layer on top of Nividous**, not as a Nividous reseller. Nividous provides governed execution; ErgoBite provides domain solutions, the client-facing product surface, and the LLM/agent design work. Their Smart Bot APIs are fully headless, so you can front the whole thing with your own UI.
3. **Target their weakest published area: Indian mid-market document + compliance workloads.** They already ship PAN, Aadhaar and Cheque models — nobody else's OOTB catalogue has those. That's a defensible wedge for ErgoBite.

### 11.2 Capability build — the 60-day plan
| Weeks | Action |
|---|---|
| 1–2 | 2 engineers complete **RPA Essentials 7.5** + **IDP 7.5** (free, certified). Install Studio 7.5.1 from the portal. |
| 3–4 | 1 engineer completes **LPA Essentials 7.5**; 1 completes **Smart Bot Essential**. Secure a Nividous partner sandbox with Control Center + Smart Bot. |
| 5–6 | Complete **RPA Advanced 7.5** and **RPA Administration**. Build the first accelerator (below). |
| 7–8 | **LPA Advanced 7.5**. Package two demo solutions. Run the Nividous "Agentic AI Enterprise Readiness Assessment" to get in front of their team. |

Total cost of the training: zero. Total certified engineers: 2–4. That's the cheapest capability build available to you.

### 11.3 The accelerator library to build (this is the profit lever)
Every one of these is assembled from verified platform features, is reusable across clients, and shortens delivery from weeks to days.

| Accelerator | Built from | Sells to |
|---|---|---|
| **AP Invoice Agent** | OOTB Invoice model + Document Processor pipeline + Maker-Checker + LPA approval workflow + ERP posting via RPA | Manufacturing, logistics, any mid-market |
| **India KYC Agent** | OOTB PAN + Aadhaar + DL + Passport models + edge detection + search-based validation + LPA exception queue | BFSI, insurance, fintech |
| **Cheque & Bank Reconciliation Agent** | OOTB Cheque model (Tesseract/Google/Azure OCR — *not* Nividous OCR) + Excel/DB libraries + reconciliation rules in BRMS | Banking, NBFC, accounting firms |
| **Contract Intelligence Agent** | GenAI Document Query + Document Comparison + Summarization + Generic NER | Legal, procurement, compliance |
| **Support Triage Agent** | GenAI Classification + Sentiment Analysis + Email Generation + LPA routing with SLA timers | Contact centre, IT service desk |
| **Resume Screening Agent** | Pre-trained Resume Parser + custom classifier + LPA shortlisting workflow with human tasks | HR, staffing |
| **Claims Fraud Agent** | Pre-trained Insurance Claim Prediction + Credit Card / Mobile Money fraud predictors + Maker-Checker | Insurance, fintech |
| **Regulatory Report Agent** | Web + Database libraries + Text Summarization + scheduled unattended bots + CC dashboards | BFSI, life sciences |
| **NL → Automation Bootstrapper** | Studio GenAI RPA code generation + your own prompt library | Internal — cuts your own build time |

### 11.4 Where low-code / no-code genuinely helps ErgoBite
- **Studio's visual designer + recorders** mean a business analyst, not a developer, can produce a first-cut process. Your senior engineers only touch the hard 20%.
- **LPA gives you BPMN workflow + auto-generated forms + task inbox for free.** Building that stack yourself (workflow engine, form builder, task queue, SLA timers, audit log) is months of work. This is the single largest time saving on the platform.
- **Pre-trained models and GenAI functions remove the ML project entirely** for a large class of use cases. No dataset, no annotation, no training run.
- **Control Center gives you scheduling, credential vaulting, RBAC, audit trails, dashboards and one-click rollback** out of the box — the "boring" enterprise requirements that normally eat 30–40% of a project.
- **GenAI RPA code generation** turns a natural-language process description into a Nividous subprocess you can edit. Use it internally to accelerate your own builds even when the client never hears about it.

### 11.5 Things to watch
- **English-only native OCR.** For Hindi/Gujarati/Marathi documents you must configure Tesseract with the right `.traineddata`, or pay for Google/Azure/AWS OCR. Price this in.
- **Smart Bot Essential course is still on 7.0** while RPA/LPA/IDP are on 7.5. Expect UI drift in that training.
- **Studio GenAI is off by default** and needs a manual JAR patch plus an `apiadmin` Smart Bot account. Budget setup time.
- **Dormant public forums.** Don't promise clients a community support fallback.
- **No agentic-AI training or documentation exists** in the portal. If a client buys on the "agentic" pitch, make sure the contracted scope is written against RPA/LPA/Smart Bot/IDP capabilities that actually ship today.

---

## 12. What I could NOT verify (stated plainly)

1. **Pricing.** No pricing is published anywhere on the public site or the community portal. Quick Start is described as "fixed price" with "conditions apply" — the number is not disclosed.
2. **A named catalogue of pre-built agents.** It does not exist. Anyone claiming Nividous ships "X ready-made agents" is describing the model/template inventory in Section 4, or is making it up.
3. **Gemini, Claude, vLLM and MCP server support.** Claimed on the `nividous.com` homepage. **Not present** in the 7.5 product documentation, which names only Nividous-LLM and OpenAI (TurboGPT 3.5, GPT-4o, GPT-4o mini). Confirm directly with Nividous before you quote it to a client.
4. **The "fully agentic" tier.** Marketed on the platform page. No documentation, no course, no release-note feature corresponds to it in the community portal. Treat as roadmap until Nividous demonstrates otherwise.
5. **The full action-level reference for each library.** Nividous ships Library Documentation *inside Studio only* (Help → Library Documentation), not on the web. You'll get the exhaustive action list after installing Studio 7.5.1.
6. **SOC 2 certification.** Claimed on the homepage; the certificate itself was not available to review.
7. **Non-Studio installers.** Control Center, Bot and Smart Bot are not on the download page. Availability presumably comes with a licence/partner agreement — confirm with Nividous.
8. **The webinar video content.** I read page copy and transcripts where published; I did not watch gated video recordings.

---

## 13. Immediate next steps

1. **Decide the partnership question.** Everything else is blocked on Global Partner status and a sandbox with Control Center + Smart Bot.
2. **Start the free training this week.** Two engineers on RPA Essentials 7.5 + IDP 7.5 costs nothing and takes ~2 weeks. There is no reason to wait for the commercial conversation.
3. **Install Studio 7.5.1** from the portal and pull the in-Studio Library Documentation — that closes the last gap in Section 12.
4. **Send Nividous a written question list** covering: pricing model, non-Studio installer access, the Gemini/Claude/vLLM/MCP claim, the agentic tier roadmap, and partner margin structure.
5. **Pick two accelerators from 11.3** — I'd suggest **India KYC Agent** and **AP Invoice Agent** — and build them against the sandbox. They're the fastest path to a demo that closes deals.

---

## Appendix — source URLs

**Public**
- `https://nividous.com/platform` · `/platform/studio` · `/platform/rpa-bots` · `/platform/smart-bots` · `/platform/control-center`
- `https://nividous.com/automation/agentic-ai` · `/automation/intelligent-automation` · `/automation/intelligent-document-processing` · `/automation/rpa` · `/automation/hyperautomation`
- `https://nividous.com/services` · `https://nividous.com/solutions/quick-start-program`
- `https://nividous.com/solutions/industry/{finance-and-banking,insurance,healthcare,manufacturing,life-sciences,logistics-and-supply-chain,optical-practices}-automation`
- `https://nividous.com/solutions/function/{finance-and-accounting,healthcare-revenue-cycle-management,it,hr,contact-center,automation-across-business-functions}`
- `https://nividous.com/company/partners`

**Community portal (login required)**
- `https://community.nividous.com/learning/`
- `https://community.nividous.com/knowledge-base-2/` and `/knowledge-base-detail/`
- `https://community.nividous.com/download-resources/`
- `https://community.nividous.com/forums/` and `/nividous-forum/`
- Documentation root: `https://community.nividous.com/help-documents/{Nividous-RPA-Help,Nividous-LPA-Help,CC-Help,API-Help,RPA-Quick-Start,LPA-Quick-Start,Studio-Installation-Help,CC-Installation-Help,Bot-Installation-Help,Infrastructure-Help}/`
- Release notes: `https://community.nividous.com/downloads/ReleaseNotes_NividousStudio{6.0.0,6.1.0,7.0.0,7.0.1,7.5.0,7.5.1}.pdf`
