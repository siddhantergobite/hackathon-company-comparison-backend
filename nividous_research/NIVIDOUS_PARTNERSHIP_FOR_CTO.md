# Nividous partnership — what ErgoBite can deliver faster, and why

**Purpose:** As a Nividous partner, which work we can take, which platform pieces we use, and why that is weeks of work instead of building an automation stack from scratch.

---

## 1. What Nividous gives ErgoBite

Nividous does not simply give us one automation bot. It gives us a **ready-made automation platform**.

Instead of building:

- our own RPA engine
- our own bot infrastructure
- our own document extraction system
- our own OCR integrations
- our own workflow engine
- our own approval system
- our own scheduler
- our own monitoring dashboard
- our own credential vault
- our own audit and governance system

ErgoBite can focus on:

**understanding the client’s process, then configuring and building their solution on top of Nividous.**

That is the core value.

If a client says “automate invoices / KYC / onboarding / claims — and we need it in weeks, not 6–7 months,” we do not first spend months inventing that stack. We use what already exists.

| Component | Simple meaning | What ErgoBite uses it for |
|---|---|---|
| **Studio** | Build the automation | Create workflows and bot logic |
| **RPA Bots** | Do repetitive computer work | Work with ERP, Excel, websites, portals |
| **Smart Bots** | Understand documents and data | Invoice, PAN, Aadhaar, email, contracts |
| **LPA** | Connect people, bots and approvals | End-to-end business workflows |
| **Control Center** | Manage everything | Run, schedule and monitor 10–100 bots |

**LPA is not another bot.** It is the orchestrator. RPA does the clicks; Smart Bot reads the document; LPA decides the order and manages people.

Nividous also ships **ready-made intelligence** (document templates, pre-trained models, OCR options, GenAI functions). Those are listed in section 7 as they appear in Studio **7.5.1** community documentation. Treat the exact counts as **documented in that version**, and re-check against the partner licence we actually get before quoting them as a commercial guarantee.

**Timelines:** Nividous’s own Quick Start for one production bot is described as about **3–4 weeks**. A **2–3 week** delivery is a **possible** window for a **well-defined** process that stays on ready-made models (no custom training, no new infrastructure). SAP, Citrix, custom models, SSO, or unclear processes can still take months. We should not present weeks as a guarantee.

**What ErgoBite sells:** a working client solution.  
**What Nividous supplies:** the platform that solution sits on.

---

## 2. How the pieces work together (not five separate products)

```
Studio          →  build the automation
Smart Bot       →  understand the document / email / form
RPA Bot         →  perform actions in the client’s systems
LPA             →  manage approvals, exceptions, and people
Control Center  →  deploy, schedule, and monitor everything
```

**Example — vendor invoice (AP)**

1. An email arrives with a PDF. Smart Bot takes it in.  
2. The Invoice template pulls vendor, GST, line items, total — we do not train a new model first.  
3. Uncertain rows go to a person (Maker-Checker).  
4. LPA waits for AP manager approval.  
5. An RPA Bot posts the voucher into the ERP the client already uses.  
6. Control Center runs the job on schedule, holds ERP passwords, and shows success or fail.

ErgoBite’s job is to **configure** that chain for the client. Without Nividous, each step is usually a different product plus months of glue.

---

## 3. Studio — BUILD

**Simple meaning:** This is where we design the automation.

**What it does:** One design tool for RPA and LPA. Drag-and-drop workflows, recorders for web / desktop / SAP, ready libraries (Excel, email, PDF, and others), debug, version control. Engineers can also describe steps in plain language and get a first draft of a bot, then tighten it.

**Example work for ErgoBite**

1. Invoice / KYC / onboarding flows — first cut in days, not a custom engine.  
2. Excel, email, and PDF automations using shipped libraries.  
3. Web or desktop recording on the screens the client already uses (no API needed for a first version).  
4. Reusable pieces we keep and clone for the next client.  
5. Faster internal drafting of bot logic.

**Connection**

Studio builds → Smart Bot understands → RPA Bot acts → LPA manages approvals → Control Center runs it.

**Time saved:** we do not write a designer, recorders, library pack, or debugger. A business analyst can produce a first cut; seniors take the hard parts.

---

## 4. RPA Bots — EXECUTE

**Simple meaning:** Digital workers that use a computer the way a person would — open apps, click, copy, paste, fill forms.

**Client problem:** “Our people type from Excel into our ERP every day.”

**Without Nividous:** ErgoBite may have to assemble a large automation infrastructure before that one process even starts.

**With Nividous:** we build the logic; the bot works on the **existing** Excel and ERP. The client often does **not** need to replace their software.

Two modes:

- **Attended** — works next to an employee. Example: a call-centre agent clicks “Get customer”; the bot opens three old screens and shows a summary. The person stays on the call.  
- **Unattended** — works alone. Example: 1,000 invoices at 10 pm, then a report. Control Center starts it.

**Projects this makes easier**

1. Excel → ERP  
2. Email → portal  
3. Legacy applications with no usable API  
4. SAP / desktop data entry after a document has been read  
5. Nightly reports (Excel → portal → email)

**Connection:** built in Studio, started after LPA approval when needed, calls Smart Bot to “read this PDF,” run and watched from Control Center.

**Time saved:** we do not build the robot runtime, app drivers, queues, or password vault. We automate the current environment instead of waiting for a core-system rewrite.

---

## 5. Smart Bots — UNDERSTAND

**Simple meaning:** RPA is good at click → copy → paste. Smart Bots help with **read → understand → extract → classify**.

This is one of the largest time savings for ErgoBite.

**Example work**

1. **Invoices** — vendor bills in many layouts.  
2. **PAN and Aadhaar** — India KYC, plus driving licence, passport, cheque.  
3. **Email mailroom** — attachments classified (invoice vs KYC vs contract) and split.  
4. **Resumes and contracts** — names, skills, dates, amounts.  
5. **Questions on a long PDF** — “What are the payment terms?” / summarise / compare two contracts / draft a reply email.

**Why pre-trained models save time — PAN / Aadhaar example**

*From scratch we might need to:* collect documents, label data, train a model, test accuracy, build extraction, deploy, then keep improving it.

*With a ready template we get closer to:* pick the model → give sample documents → set the fields → set “if confidence is low, send to a human” → pass results to ERP or LPA.

That is why invoice / PAN / Aadhaar / passport work can start from an **existing capability**, not a new AI research project.

**Connection:** Studio calls these capabilities; results go to RPA (type into SAP) or LPA (exception queue); models are switched on in Control Center.

**OCR (practical):** several engines are available (including Nividous, Tesseract, AWS, Google, Azure). Nividous’s own OCR is English-only in the docs — Hindi/regional needs another engine and should be priced in. Cheques: do not use Nividous OCR or AWS Textract (per their docs).

---

## 6. LPA — CONNECT PEOPLE, BOTS, AND APPROVALS

**Simple meaning:** LPA is **not** another RPA bot. It is the **orchestrator**.

- RPA Bot = does the work  
- Smart Bot = understands the information  
- LPA = decides the order and manages people and approvals  

**Employee onboarding example**

```
HR uploads documents
        ↓
Smart Bot reads the documents
        ↓
Manager approves
        ↓
LPA moves the workflow forward
        ↓
RPA Bot creates accounts / email
        ↓
Control Center monitors everything
```

**Other work:** loan or claims (upload → extract → core system → approve → letter); low-confidence Aadhaar waiting in a task list; “if AP has not approved in 24 hours, escalate.”

**Time saved:** building our own workflow engine, forms, task inbox, SLAs, and audit trail is typically months. After document templates, this is the next largest “do not rebuild” item.

---

## 7. Control Center — MANAGE AT SCALE

**Simple meaning:** one place to run and watch the digital workforce.

Imagine one company with:

- 20 invoice bots  
- 15 KYC bots  
- 25 report bots  
- 10 attended support bots  
- 30 other automations  

Without a centre, operations become guesswork.

Control Center helps answer:

- Which bots are running?  
- Which bot failed, and why?  
- When is the next job?  
- Who has access?  
- Which passwords should the bot use?  
- How many transactions succeeded?  
- Which version is live? (and roll back if needed)

**Why this matters to ErgoBite:** not only build. After go-live we can offer **support, monitoring, and maintenance** (AMC) — recurring work, not only a one-time project.

**Connection:** everything designed in Studio **runs here**.

---

## 8. Ready-made intelligence — where the most time can disappear

This is worth highlighting: for suitable projects we **start from an existing capability**, not from zero AI.

**Document templates (no training first)**  
Invoice · PAN · Aadhaar · Cheque · Driving licence · Passport · Generic (forms/tables)

Client gives sample invoices → we pick Invoice → map fields (invoice no., GSTIN, amount) → set “below our confidence level → human.” A first extraction **demo is possible in the same week** on a clean, well-defined sample set — not a promise for every client or every messy archive.

**Pre-trained models**  
Classification (e.g. sentiment, spam) · entity recognition (e.g. resume fields) · prediction (e.g. assist fraud/claims — always with a human gate, not a replacement for the client’s risk policy)

**GenAI functions (we pass the document; prompts are already set)**  
Summarise · translate · classify · extract · **document query** · **document comparison** · email generation

Examples: “What is the termination clause?” on a 40-page contract; compare two vendor MSAs; summarise an inspection PDF, then RPA files it.

**Document factory (ingestion)**  
Scan/upload or email in → classify → split packs → extract → human review if needed → start RPA or LPA. That is production mailroom, not “we built OCR once.”

**Studio libraries** (Excel, web, desktop, email, SAP, PDF, and others) mean common system work is not written from zero either.

*The inventory above matches what we read in 7.5.1 community docs (including seven document models, several classifiers/predictors, about ten GenAI functions, and multiple OCR engines). Confirm the same list on the licensed environment before treating any number as a contractual commitment.*

---

## 9. From scratch vs using Nividous

| From scratch | Using Nividous |
|---|---|
| Build the automation infrastructure | Use the existing platform |
| Build document AI | Start from available models / templates |
| Build workflow management | Use LPA |
| Build bot management | Use Control Center |
| Build monitoring and governance | Use existing platform capabilities |
| Build every integration layer | Use Studio libraries where they fit |
| Months before the platform is ready | Focus earlier on the **client’s** process |

**Other benefits**

- Automate the **current** UI instead of waiting for a system replacement.  
- Show a document demo early; train a custom model later only if needed.  
- Control Center supports a managed-service story.  
- We can put an ErgoBite screen in front if the client should not live in Nividous (their APIs allow this).  
- PAN + Aadhaar templates are a practical India differentiator vs generic global RPA.

**What we still own:** process discovery, exceptions, testing, ERP field mapping, security reviews, and saying no when the job is SAP/Citrix/custom ML — that is **not** a two-week job.

---

## 10. What we should accept vs push back

**Easier fit:** invoice AP, India KYC packs, email+attachment mailroom, Excel/MIS unattended bots, attended helpdesk assist, contract Q&A/summarise, HR resume first pass, simple approvals.

**Longer — say so up front:** custom document models, Citrix/SAP-heavy work, new SSO/environments, and “fully agentic” autonomous agents as marketed. What we can actually deliver today is RPA + Smart Bot + LPA + GenAI as they ship.

**Partnership:** the community portal currently lets us download **Studio**. Control Center, Bot, and Smart Bot need a **licence / partner agreement**. RPA and IDP training on the portal is free — two engineers should still get certified.

---

## 11. Simply saying

Nividous can help ErgoBite reduce development effort because the **base automation platform is already available**. We use **Studio** to build, **RPA Bots** to perform work, **Smart Bots** to understand data and documents, **LPA** to manage the complete workflow, and **Control Center** to deploy and manage everything. Ready-made document models, ML capabilities, OCR options, and GenAI functions can further reduce custom development on **suitable, well-defined** client projects — so we spend our time on the client’s process, not on rebuilding a platform.
