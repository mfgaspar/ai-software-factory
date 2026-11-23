# Complete Requirements & Behaviour Specification
**Product:** Compose Build **Automate** (SDD Pipeline)  
**Schema Version:** `1.0` (`build_automated_version: ">=0.11.2"`)  
**Last Updated:** 2026-11-22  

---

## 1. System Overview & Surfaces

**Compose Build Automate** is an AI Software Factory platform structured into **2 core stages**:
1. **Stage 1 — Clarity (Screen 1, Optional — Enabled by Default):** Project metadata definition, AI spec brainstorming, and synthesis/approval of the 8 mandatory engineering artifacts. When enabled, users **cannot proceed forward** until Clarity is completed and approved; when disabled, users can skip directly to Backlog Sync & Stage 2.
2. **Stage 2 — Build Automate (Screen 3+):** Autonomous feature and bug execution via structured **Build Automated - SDD Pipeline** workflows, Coding Agents, and `clarify-gate` verification.

### 1.1 Supported Surfaces & Capability Boundaries
| Surface | Viewport | Primary Users | Included Capabilities | Explicitly Excluded |
| :--- | :--- | :--- | :--- | :--- |
| **Desktop Web App** | `1280px+` | Engineers, Tech Leads, Platform Admins | Full 3-step project wizard, optional Clarity stage, backlog sync, work item create/import, AI spec brainstorming, live streaming step logs, `clarify-gate` review, completion risk/verification evidence, and bi-directional Visual/YAML Workflow Builder. | — |
| **Mobile Companion** | `390px` | On-the-Go Reviewers & Tech Leads | Project switcher, 2×3 status summary, queue cards with active Coding Agent & stage progress, `clarify-gate` Q&A diff review, sticky `Approve & Plan` / `Reject (Abort)` controls, and completed-only risk/test summary. | Streaming step logs, Admin Visual/YAML Workflow Builder, project creation wizard, and work item authoring. |

---

## 2. Functional Requirements & Expected Behaviour

### FR-01: Stage 1 — Clarity, Project Metadata & AI Brainstorming (Step 1 of 3)
**Purpose:** Establish repository context and optionally synthesize & approve the 8 mandatory engineering documents before moving to Backlog Sync and Stage 2 (Build Automate).

- **FR-01.1 Project Metadata:**
  - Inputs: **Project Name**, **Repository Target** (`Existing URL` vs. `New Repo` toggle), **Stack Tags** (language/framework chips), and **Project Description**.
  - Behaviour: Toggling `Existing URL` / `New Repo` updates the repository target input mode while preserving project metadata.
- **FR-01.2 Optional Clarity Toggle & Forward Gating:**
  - **Enabled by Default:** Clarity is active by default when creating a project.
  - **Strict Gate When Enabled:** The forward action (**Continue to Backlog Sync →**) remains **disabled** until Clarity is both **Completed** (8/8 mandatory artifacts ready) and **Approved**.
  - **Skip When Disabled:** Disabling the Clarity toggle dims/collapses the brainstorming & artifacts workspace and **immediately enables** the forward action (**Skip Clarity & Continue →**) so teams can proceed with metadata alone.
- **FR-01.3 Split-Screen AI Brainstorming Agent:**
  - Displays conversational thread (`YOU` vs. `ARCHITECT AGENT`, e.g., `MODEL: o3-high`), inline artifact synthesis summaries, and clarifying questions.
  - Supports drag-and-drop attachment pills (`.md` specs, UI wireframes) with per-pill removal (`×`).
  - Actions: **Start Brainstorming** (triggers/continues agent synthesis) and **Approve Clarity** (marks Clarity completed & approved, unlocking **Continue to Backlog Sync**).
- **FR-01.4 Mandatory Artifacts Checklist & Document Drawer:**
  - Tracks 8 required engineering documents with live status badges (`Ready`, `Generating`, `Needs Review`, `Pending`) and completion counter (`N/8`):
    1. Product Requirements Document (PRD)
    2. Functional & Non-Functional Requirements (FR/NFR)
    3. UI/UX & State Flows
    4. System Architecture Document (SAD)
    5. API Contracts (OpenAPI / GraphQL)
    6. Database Schema & ERD
    7. Architecture Decision Records (ADRs)
    8. Environment & Setup Guide
  - Clicking **Preview** or **Edit** on any artifact opens the **Document Preview & Editor Drawer** in read-only preview or editable mode.

---

### FR-02: Backlog Sync & AI Workflow Configuration (Steps 2 & 3)
**Purpose:** Bind an upstream issue tracker and configure default Coding Agents, LLM cognitive routing, and pipeline flags.

- **FR-02.1 Upstream Backlog Integration:**
  - Supports **Jira Cloud**, **Azure DevOps**, and **GitHub Issues** with connection status (`Connected`, `Connect`, `Synced`) and a **Project / Board** selector.
  - Preview table translates upstream items into Factory Tasks showing `Source Key`, `Translated Factory Task`, `Type` (`User Story`, `Feature`, `Bug`), `Assigned Workflow`, and per-row `Sync` checkbox.
- **FR-02.2 Dual-Pipeline & Coding Agent Configuration:**
  - **Build Automated - SDD Pipeline (`v1.1.0`):** `specify → clarify → plan → tasks → analyze → implement → converge (max 3)`.
  - **Bug Convergence Hotfix (`v1.0.4`):** `specify → plan → implement → converge-loop (max 3 cycles)`.
  - **Coding Agent (`integration`) Selector:** `auto (Project Default)`, `claude (Claude Code)`, `copilot (GitHub Copilot)`, `gemini (Gemini CLI)`, `opencode (OpenCode)`.
  - **Per-Stage LLM Bindings:** Independent selectors for `reasoning`, `plan`, and `code` roles.
  - **Pipeline Inputs (Booleans):** `with_constitution`, `with_checklist`, `skip_clarify`.

---

### FR-03: Project Dashboard & Work Item Queue
**Purpose:** Provide real-time visibility into autonomous factory runs, cost, and human-in-the-loop gates.

- **FR-03.1 Global Controls:**
  - Top bar includes **Project Switcher**, **Global Date Range** (`Last 7 days`, `Last 30 days`, `Custom range...`), **Admin: Workflow Builder** link, and **New Feature / Bug** CTA.
  - Displays **Total Factory Spend** for the selected window.
- **FR-03.2 6-State Status KPI Strip & Filter Tabs:**
  - Clickable KPI cards and matching filter tabs for: `Pending`, `Started`, `Stopped`, `Needs Attention`, `Completed`, `Buggy` (plus `All` tab).
  - Each KPI card displays total count and `Features · Bugs` breakdown.
- **FR-03.3 Work Item Queue Table & Row Actions:**
  - Search input filters rows live by Work Item ID or Title.
  - **+ New / Import** button navigates to Work Item Creation.
  - Columns: `Work Item`, `Type`, `Status`, `Workflow Stage` (with progress bar), `Est. Cost`, `Diff Metrics`, and state-specific `Action`:
    - `Needs Attention` → **Review Plan** (opens quick `clarify-gate` review modal with `Approve & Plan` / `Reject (Abort)`).
    - `Started` → **Pause**.
    - `Pending` → **Start**.
    - `Buggy` → **Relaunch**.
    - `Completed` → View / click-through to Execution Detail.

---

### FR-04: Work Item Creation & Upstream Import
**Purpose:** Allow engineers to author new Features/Bugs with AI assistance or import pre-triaged items from a configured upstream tracker.

- **FR-04.1 Work Item Type Routing:**
  - **Feature** toggle sets branch prefix `feat/` and binds **Build Automated - SDD Pipeline v1.1.0**.
  - **Bug** toggle sets branch prefix `fix/` and binds **Bug Convergence Hotfix v1.0.4**.
- **FR-04.2 AI-Assisted Authoring (`Title` & `inputs.spec`):**
  - **Title:** Includes **Enhance with AI** button to refine/clarify the work item title.
  - **Specification / Acceptance Criteria (`inputs.spec`):** Includes both **Brainstorm** toggle and **Enhance with AI** button.
  - **Inline Spec Brainstorming Agent:** Appears directly beneath `inputs.spec`, providing:
    - Agent prompt/guidance on failure modes, auth boundaries, and constraints.
    - Quick-insert constraint chips (e.g., `+ Edge cases & HTTP codes`, `+ DB & migration constraints`).
    - Follow-up text input + **Ask** button.
    - **Apply to Spec** button that writes/appends synthesized acceptance criteria directly into `inputs.spec`.
- **FR-04.3 Execution Parameters & Submission:**
  - Configurable **Coding Agent** override (`auto`, `claude`, `copilot`, `gemini`, `opencode`), **Priority** (`P0 — Critical`, `P1 — High`, `P2 — Normal`), and **Pipeline Inputs** (`with_constitution`, `with_checklist`, `skip_clarify`).
  - Dual actions: **Create & Queue** (adds as `Pending`) or **Create & Start Run** (adds and immediately starts `specify`).
- **FR-04.4 Import from Configured Upstream:**
  - Displays the already-configured upstream board (e.g., `Jira · BILLING-ENG`), **Refresh** button, issue search, multi-select checkboxes, mapped `Feature`/`Bug` badge, assigned Coding Agent, and bound workflow.
  - **Import Selected (N) to Queue** updates dynamically with selection count and enqueues selected items.

---

### FR-05: Execution Monitoring & Streaming Step Logs (Desktop)
**Purpose:** Track stage-by-stage progress, inspect live agent output, and audit execution events.

- **FR-05.1 Execution Header & State Bar:**
  - Displays Status badge (`Completed`, `Running`, `Needs Attention`, `Aborted`), Gate badge (`HITL Gate Passed`), Git branch (`feat/...` or `fix/...`), `TOTAL COST`, and `TOTAL DIFF`.
- **FR-05.2 Interactive Pipeline Stepper:**
  - Displays 5 stage groups (`1. specify & clarify`, `2. plan & tasks`, `3. analyze`, `4. implement`, `5. converge-loop`) with model, Coding Agent, duration, and cost.
  - **Streaming Step Log Panel (Desktop Only):**
    - Automatically opens when a step is actively **Running** or when the user clicks any step card.
    - Displays `LIVE · STREAMING` indicator, active step command (`build-automated.<step>`), model, Coding Agent, **Pause Stream** / **Resume** toggle, **Close** button, and dark terminal output.
- **FR-05.3 Traceability JSON Drawer:**
  - Slide-over drawer showing timestamped JSON events (`ts`, `step`, `model`, `cost`, `type`, `options`, `on_reject`, `status`).

---

### FR-06: Human-in-the-Loop (`clarify-gate`) & Needs Attention
**Purpose:** Enforce human sign-off on specification ambiguities before planning and implementation begin.

- **FR-06.1 Gate Semantics:**
  - `clarify-gate` is the **only** human-in-the-loop gate (`type: gate`, `options: [approve, reject]`, `on_reject: abort`).
  - `plan` (`build-automated.plan`) is **not** a gate and executes automatically once `clarify-gate` is approved (or immediately if `skip_clarify` is `true`).
- **FR-06.2 Needs Attention Review Experience:**
  - Highlights `2. clarify-gate` in the stepper with `on_reject: abort` badge.
  - Displays **Clarifications & Proposed Resolutions** cards (`Q1`, `Q2`, `Q3` with `RESOLVED` status), dark-canvas `# build-automated.clarify Q&A Diff`, and an optional **Clarification Override or Abort Reason** textarea.
  - **Approve & Plan** transitions status to `Running · plan` and triggers `build-automated.plan`.
  - **Reject (Abort)** halts the run cleanly (`Aborted`) per `on_reject: abort`.

---

### FR-07: Post-Completion Verification & Risk Metrics
**Purpose:** Present objective verification proof and merge risk only after implementation and convergence finish.

- **FR-07.1 Strict Completion-Only Visibility Rule:**
  - **Merge Danger Score** (0–100 score, risk tier, conflict/migration summary) and **Blast Radius** (impacted service count, downstream consumers, modified file tree) **MUST only be visible when execution status is `Completed`**.
  - During `Running`, `Started`, or `Needs Attention`, risk assessment widgets are hidden on both Desktop and Mobile, and the evidence column expands to full width on Desktop.
- **FR-07.2 Verification Evidence:**
  - **Test Execution Matrix:** Pass/fail counts across `Unit Tests`, `Integration`, `E2E Tests`, and `Security / Lint`.
  - **Proof of Work & Evidences:** Expandable terminal logs (migration + CI test output) and API response snapshots.

---

### FR-08: Admin Visual Workflow Builder & YAML Sync (`schema_version: "1.0"`)
**Purpose:** Enable platform engineers to author, inspect, and publish declarative SDD pipelines.

- **FR-08.1 Bi-Directional Editor Modes:**
  - Header mode toggle: **Visual Builder**, **Split View** (default), and **YAML Editor**, plus workflow selector and **Save & Publish**.
  - Quick-add palette: `+ Input`, `+ if Block`, `+ Build Automated Step`, `+ gate`, `+ do-while`.
- **FR-08.2 Connected Execution Graph:**
  - Renders sequential and conditional edges explicitly:
    - `type: if` (`{{ inputs.with_constitution }}`) → `constitution-run` (`build-automated.constitution`)
    - `specify` (`build-automated.specify`)
    - `type: if` (`{{ inputs.skip_clarify == false }}`) → `clarify-run` (`build-automated.clarify`) → `clarify-gate` (`type: gate`, `on_reject: abort`)
    - `plan` (`build-automated.plan`)
    - `type: if` (`{{ inputs.with_checklist }}`) → `checklist-run` (`build-automated.checklist`)
    - `tasks` → `analyze` (`continue_on_error: true`) → `implement` (`build-automated.implement`)
    - `type: do-while` (`id: converge-loop`, `max_iterations: 3`) → `converge` → `implement-remaining`
- **FR-08.3 Step Inspector & Schema:**
  - Selecting any node populates the **Step Inspector** with `Coding Agent (integration)`, `model`, and step parameters.
  - Canonical YAML root keys: `schema_version: "1.0"`, `workflow`, `requires` (`build_automated_version: ">=0.11.2"`, `integrations.any: [claude, copilot, gemini, opencode]`), `inputs` (8 typed inputs), and `steps`.

---

### FR-09: Mobile Companion App
**Purpose:** Let reviewers monitor queue health and resolve `clarify-gate` approvals from mobile devices.

- **FR-09.1 Mobile Project Dashboard:**
  - Header with Project Switcher and date filter (no Admin Builder link).
  - Compact 2×3 status grid (`Pending`, `Started`, `Stopped`, `Needs Attn`, `Completed`, `Buggy`).
  - Work item cards showing ID, Type, active **Coding Agent** (`agent: claude|copilot|gemini`), Status badge, Stage progress, Cost/Diff, and primary action (`Review Clarifications`, `Pause Run`, `Relaunch`).
- **FR-09.2 Mobile Feature Detail & Approval:**
  - Contextual back header (`CB-142` + Status badge), active **Coding Agent**, Cost, `build-automated.clarify` Q&A Diff preview, and vertical **Build Automated - SDD Timeline**.
  - Sticky bottom action bar (`Reject (Abort)` / `Approve & Plan`) visible when at `clarify-gate`.
  - **Merge Danger**, **Blast Radius**, **Diff**, and **Verification Summary** badges appear only when status is `Completed`. No streaming log terminal is rendered on mobile.

---

## 3. Screen-to-Screen Interaction & Navigation Architecture

### 3.1 Visual Navigation Map

```
DESKOP FLOW
===========
[1. Project Creation & Metadata Wizard (Stage 1: Clarity — Optional)]
   │  "Continue to Backlog Sync" (requires Clarity Completed & Approved, OR Clarity Disabled)
   ▼
[2. Backlog Sync & AI Workflow Config] ◄──("Back to Brainstorm")──┘
   │  "Launch Project Factory"
   ▼
[3. Project Dashboard & Work Item Queue] ◄──────────────────────────┐
   │                                                                │
   ├── "+ New / Import" or "New Feature / Bug"                      │
   │      └──▶ [3b. Create & Import Work Item] ──("Back to Queue" / Submit)─┘
   │
   ├── "Admin: Workflow Builder" (Global Header Link)
   │      └──▶ [5. Admin Visual Workflow Builder & YAML Sync] ──("Compose Build" Logo)─┘
   │
   ├── Row Click (Completed / Started) or "Inspect"
   │      └──▶ [4. Feature Execution Detail & Verification] ──(Breadcrumb: Project)─┘
   │
   └── Row Click (Needs Attention) or "Review Plan"
          ├── Quick Modal: Clarify Gate Overlay (Approve & Plan / Reject)
          └── Full View: [4b. Execution Needs Attention — Clarify Gate]
                            ├── "Approve & Plan" ──▶ [4. Execution Detail (Running: plan)]
                            └── "Reject (Abort)" ──▶ [3. Queue / Aborted State]

MOBILE FLOW (390px)
===================
[Mobile: Project Dashboard]
   │  Tap Work Item Card / "Review Clarifications"
   ▼
[Mobile: Feature Detail & Approval] ◄──("← CB-142" Back Header)──┘
   └── Sticky Footer ("Approve & Plan" / "Reject (Abort)")
```

### 3.2 Complete Screen Transition Matrix

| Source Screen | Trigger / UI Control | Condition | Target Screen / Overlay | Data & State Passed |
| :--- | :--- | :--- | :--- | :--- |
| **1. Project Creation Wizard** | `Preview` / `Edit` on Mandatory Artifact | Any of 8 artifacts | **Document Preview & Editor Drawer** (in-screen) | Document ID, Title, Status, Mode (`preview` \| `edit`) |
| **1. Project Creation Wizard** | `Continue to Backlog Sync` / `Skip Clarity & Continue` | Clarity Completed & Approved (8/8), **or** `Enable Clarity` unchecked | **2. Backlog Sync & AI Workflow Config** | `project_name`, `repo_target`, `stack_tags`, `clarity_enabled`, and 8 finalized `.md` specs (if Clarity enabled) |
| **1. Project Creation Wizard** | `Save & Exit` | Any time | **3. Project Dashboard** | Draft project state saved |
| **2. Backlog Sync & Config** | `Back to Brainstorm` | Any time | **1. Project Creation Wizard** | Current backlog & workflow selections preserved |
| **2. Backlog Sync & Config** | `Launch Project Factory` | Valid config & >=1 tracker or manual setup | **3. Project Dashboard** | Selected upstream board, imported work items, default Coding Agents (`integration`), model bindings (`reasoning`, `plan`, `code`), pipeline flags |
| **3. Project Dashboard** | `New Feature / Bug` or `+ New / Import` | Any time | **3b. Create & Import Work Item** | Active `project_id`, configured upstream tracker (e.g., `Jira · BILLING-ENG`), project default Coding Agent |
| **3. Project Dashboard** | `Admin: Workflow Builder` (Header) | Admin/Engineer role | **5. Admin Visual Workflow Builder** | Active `workflow_id` (`pipeline` or `bug-hotfix`) |
| **3. Project Dashboard** | `Review Plan` button | Row status = `Needs Attention` | **Clarify Gate Quick-Action Modal** (or **4b. Execution Needs Attention**) | `work_item_id`, `title`, `build-automated.clarify` Q&A diff |
| **3. Project Dashboard** | Row Title link or `Inspect` button | Status = `Started` or `Completed` | **4. Feature Execution Detail** | `work_item_id`, `execution_id`, current step state |
| **3. Project Dashboard** | Row Title link | Status = `Needs Attention` | **4b. Execution Needs Attention** | `work_item_id`, `clarify-gate` Q&A payload |
| **3b. Create & Import Work Item** | `Create & Start Run` / `Create & Queue` / `Import Selected (N)` | Valid Title & `inputs.spec` (or >=1 checked upstream issue) | **3. Project Dashboard** (or **4. Execution Detail** on immediate start) | New `CB-*` item(s), branch prefix (`feat/` or `fix/`), bound workflow, `inputs.spec`, Coding Agent, priority, boolean flags |
| **3b. Create & Import Work Item** | `Back to Queue` or Project Breadcrumb | Any time | **3. Project Dashboard** | Discards unsaved draft or returns to queue |
| **4. Feature Execution Detail** | Click any Pipeline Step Card | Desktop only | **Streaming Step Log Panel** (in-screen) | `step_id`, `build-automated.<step>`, `model`, `coding_agent`, live/historical log stream |
| **4. Feature Execution Detail** | `View Traceability JSON` (Header) | Any time | **Traceability JSON Drawer** (in-screen) | Full timestamped event array for `execution_id` |
| **4. Feature Execution Detail** | `Approve & Plan` (in Gate Banner) | `in_progress` at `clarify-gate` | **4. Feature Execution Detail** (`Running` → `Completed`) | Resumes pipeline at `build-automated.plan` |
| **4. Feature Execution Detail** | Project Breadcrumb (`billing-engine-v2`) | Any time | **3. Project Dashboard** | Returns to active project queue |
| **4b. Execution Needs Attention** | `Approve & Plan` | At `clarify-gate` | **4. Feature Execution Detail** (`Running: plan`) | Approval decision + optional clarification override text |
| **4b. Execution Needs Attention** | `Reject (Abort)` | At `clarify-gate` | **3. Project Dashboard** (status: `Aborted`) | `on_reject: abort` + optional abort reason |
| **5. Admin Workflow Builder** | `Compose Build` Logo (Header) | Any time | **3. Project Dashboard** | Returns to project queue |
| **5. Admin Workflow Builder** | `Save & Publish` | Valid `schema_version: "1.0"` YAML | **5. Admin Workflow Builder** (persisted to **2** & **3b**) | Updated workflow definition available to project config and work item creation |
| **Mobile: Project Dashboard** | Tap Work Item Card / `Review Clarifications` | Any item | **Mobile: Feature Detail & Approval** | `work_item_id`, `coding_agent`, current stage, `clarify-gate` diff |
| **Mobile: Feature Detail** | `← CB-142` Back Header | Any time | **Mobile: Project Dashboard** | Returns to mobile queue |
| **Mobile: Feature Detail** | `Approve & Plan` / `Reject (Abort)` | At `clarify-gate` | **Mobile: Feature Detail** (updates state) / **Mobile Dashboard** | Gate decision synced to backend execution |

### 3.3 End-to-End User Journeys

1. **New Project Onboarding Journey:**
   `1. Project Creation Wizard` (Project Metadata + **Stage 1: Clarity** enabled by default → AI Brainstorming + 8 Mandatory Artifacts → *Approve Clarity*, or disable Clarity to skip) → *Continue to Backlog Sync* → `2. Backlog Sync & AI Workflow Config` (Connect Jira/ADO/GitHub + Select Coding Agent & Models) → *Launch Project Factory* → `3. Project Dashboard` (**Stage 2: Build Automate**).
2. **Work Item Authoring & Spec Brainstorming Journey:**
   `3. Project Dashboard` → *+ New / Import* → `3b. Create & Import Work Item` (Choose Feature/Bug, *Enhance with AI* on Title/Spec, use *Spec Brainstorming Agent* + *Apply to Spec*, or check upstream Jira issues) → *Create & Start Run* → `4. Feature Execution Detail` (live streaming logs).
3. **Human-in-the-Loop (`clarify-gate`) Resolution Journey:**
   `3. Project Dashboard` (`Needs Attention` row) → *Review Plan* (quick modal) or click-through to `4b. Execution Needs Attention` → inspect `build-automated.clarify` Q&A diff → *Approve & Plan* → advances to `build-automated.plan` in `4. Feature Execution Detail`.
4. **Post-Completion Verification Journey:**
   Once `converge-loop` succeeds in `4. Feature Execution Detail`, status transitions to `Completed` → **Test Execution Matrix**, **Proof of Work**, **Merge Danger Score**, and **Blast Radius** unlock → engineer inspects **Traceability JSON Drawer**.
5. **Admin Pipeline Customization Journey:**
   Global Header *Admin: Workflow Builder* → `5. Admin Visual Workflow Builder` → edit connected graph / step Coding Agent / YAML → *Save & Publish* → immediately reflected in `2. Backlog Sync` and `3b. Create & Import Work Item`.
6. **Mobile On-the-Go Approval Journey:**
   `Mobile: Project Dashboard` (check active `agent: claude|copilot|gemini` and `Needs Attn` badge) → tap *Review Clarifications* → `Mobile: Feature Detail & Approval` → review Q&A diff → tap sticky *Approve & Plan* or *Reject (Abort)*.

---

## 4. State Machine & Behavioural Rules

```
[Pending] ──(Start)──▶ [Started: specify]
                           │
        ┌──────────────────┴──────────────────┐
        ▼ (skip_clarify: false)               ▼ (skip_clarify: true)
[Needs Attention: clarify-gate]        [Started: plan → implement → converge]
   │                       │                  │
   ├─(Reject / Abort)──▶ [Aborted]            ├─(Converged ≤ 3)──▶ [Completed]
   │                                          ├─(Max cycles fail)──▶ [Buggy]
   └─(Approve & Plan)─────────────────────────┘
```

- **Pause / Resume:** `Started` runs can be paused (`Stopped`) and resumed.
- **Relaunch:** `Buggy` runs can be relaunched from the queue or detail view.
- **Deterministic Loop Bound:** `converge-loop` is strictly capped at `max_iterations: 3`.

---

## 5. Non-Functional Requirements

- **Terminology Consistency:** All pipeline commands and identifiers use `Build Automated` (`build-automated.*`, `Build Automated - SDD Pipeline`, `build_automated_version`).
- **Visual & Typographic System:** Warm paper ground (`#f7f6f1`), crisp card surfaces (`#ffffff`), primary ink (`#0e0e14`), dark code/terminal canvas (`#06111f`), 1px hairline borders, zero drop shadows, **Archivo** for headings/prose, and **JetBrains Mono** for UI chrome, metrics, and code/YAML.
- **Accessibility & Responsiveness:** WCAG AA contrast across all semantic status tints, visible keyboard focus rings, `tabular-nums` alignment on all counters/costs/diffs, and clean single-column layout at `390px` mobile without horizontal overflow.
- **Auditability:** Every pipeline step, model binding, Coding Agent selection, and `clarify-gate` decision is recorded in the Traceability JSON event stream.
