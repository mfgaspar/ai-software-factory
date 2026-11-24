# Clarity and build

compose is a software factory with two steps:

1. **`compose clarity`, the foundation.** It settles the application's **why**, its **rules**
   and its **how** once: the problem, stakeholders, non-functional requirements, constraints
   and standards, open questions, solution, failure analysis, architecture, ADRs, product
   brief, UX standards, API conventions, domain model and data rules, setup guide and
   summaries, in `.clarity/`. This is where people are involved: they answer questions,
   confirm the foundation and approve it.
2. **`compose build`, delivery.** It specifies and builds features autonomously, one at a
   time, inside that foundation.

```bash
compose clarity docs/            # draft from your documents, then answer what's still open
compose clarity status           # documents, verdict, questions, whether a build can start
compose build "Wishlist for signed-in users"
```

Clarity never holds the **what** of a feature: functional requirements, feature lists,
screens, endpoints or feature tables. compose defines those one feature at a time
(`/compose-specify`, then `/compose-plan`), inside clarity's rules. See
[How compose uses clarity](#how-compose-uses-clarity).

The work itself is done by the clarity skills, Claude Code skills adapted from
[microsoft/clarity-agent](https://github.com/microsoft/clarity-agent) (MIT): plain Markdown
instructions plus data files, with no runtime. compose orchestrates them as tracked runs; it
doesn't reimplement them. They also work by hand in Claude Code (see
[The clarity skills by hand](#the-clarity-skills-by-hand)). compose installs them alongside its
own skills, with `compose init` and in every run's worktree.

## compose clarity

```bash
compose clarity [SOURCES...] [--mode mixed|auto|interactive] [-d] [--json]
```

Sources are paths or URLs (documents, folders, issues), passed to `/clarity` as given. A
clarity run is a run like any other: it shows in `compose status`, `compose trace` and
`compose cost`, and through the [HTTP API](api.md). There is one active clarity run per repo,
paused ones included: starting another is refused until you answer it, or
`compose abort <run>`. Every clarity command takes `--repo`; the [CLI reference](cli.md#clarity-and-build)
lists all options.

### Modes

| Mode | What happens | People |
|---|---|---|
| `mixed` (default) | drafts everything unattended, then asks only what is still open, in rounds, most important first, and applies the answers | answer the questions |
| `auto` | drafts everything from the sources and asks nothing. The verdict is always FAIL; its questions stay in the questions file for a later mixed run or `compose clarity answer` | none |
| `interactive` | starts Claude Code (or Copilot, when `defaults.engine` is `copilot`) in the clarity worktree with `/clarity <sources> interactive`, attached to your terminal (the stage-by-stage conversation). When the session ends, compose runs `clarity-validate` as a tracked run | the whole conversation |

`interactive` needs a terminal and can't be detached; the API offers `mixed` and `auto` only.

In every mode the skills ask a person only what a person must answer: intent and priorities,
facts only you hold (real users, numbers, deadlines, owners), trade-offs that are yours to own,
conflicts the sources can't settle, and confirmations or approvals. Whatever they can work out
from the sources, the code, the other documents or established practice, they write down
themselves, marked as inferred, and list in the review question so you can correct it.

### How mixed works

A `mixed` run is the built-in `clarity` workflow:

1. **draft** (`/clarity <sources> draft`): reads every source and the code once, proposes the
   setup (`.clarity/config.yml`: which documents are mandatory, which don't apply, who
   approves), scaffolds and drafts every document, and writes questions for what it can't
   settle. Only **mandatory** documents raise questions; gaps in the others stay as
   placeholder notes.
2. **Rounds**, at most 4: the `questions` step asks the pending questions, then **apply**
   (`/clarity apply`) applies the answers and raises the next ones. The loop repeats while
   questions other than approvals are pending. The questions come in this order:
   - **setup**: confirm or correct the proposed mandatory set, N/A list and approvers;
   - **gap** and **conflict**: what stops a mandatory document from being completed,
     unresolved blocking open questions, and decisions (ADRs) still to be made. Your answer
     to a decision question accepts the ADR in your name;
   - **review**: once nothing else is pending, one summary of the whole foundation, answered
     `confirm` or with corrections. `confirm` marks every mandatory document complete (or
     n/a with its reason);
   - **approval**: after a confirmed review, one per configured approver.
3. **memory**: compose publishes the documents to `.compose/memory/` and writes its index,
   stamped with the clarity fingerprint (see [The published memory](#the-published-memory)).
   No model is involved.
4. **validate** (`/clarity-validate`); compose records the verdict, commits, and on PASS merges
   (see [The clarity branch](#the-clarity-branch)).

On a terminal in the foreground, compose asks each question there: it shows the question,
its details as bullets, the numbered options and the recommendation. You answer with a
number, your own words (any question but an approval), or Enter for the recommendation.
compose sends a desktop notification when it starts asking. Otherwise (`-d`, `--no-interactive`,
the API) the run **pauses** at the questions step until they're answered.

Approvals never hold a run. A run doesn't wait for an absent approver: when only approvals are
pending, the loop ends, and the run validates (FAIL, unapproved) and commits. The approver
answers later with `compose clarity answer`, and the next `compose clarity` applies the
approval and validates again.

### The questions file

`.clarity/questions.yml`, in the clarity worktree, is how the unattended phases talk to
people. Skills write the questions; compose writes only `answer`, `answered_by` and
`answered_at`. It's a companion file: created from a template, never validated, and not part
of the fingerprint.

```yaml
questions:
  - id: Q-007                      # stable, never reused
    round: 2                       # the draft/apply pass that raised it
    kind: gap                      # setup | gap | conflict | review | approval
    document: product/prd.md       # null for setup questions
    question: "The PRD says 3 user roles; the code has 2. Which is right?"
    details:                       # optional: supporting points, shown as bullets
      - "prd.md lists admin, editor and viewer."
      - "The code only checks admin and viewer."
    options: ["3 roles (PRD)", "2 roles (code)"]   # may be empty: free text
    recommended: "3 roles (PRD)"   # may be null
    free_text: true                # false: the answer must be one of the options
    approver: null                 # approval questions only: who must answer
    answer: null
    answered_by: null
    answered_at: null              # ISO date-time
```

- A question is **pending** while `answer` is null and it isn't marked `obsolete: true`.
- **Rounds carry over**: a new pass numbers its round after the highest in the file. `draft`
  keeps older pending questions that still apply and marks the rest obsolete, so the
  questions of an auto run are asked by the next mixed run.
- **Text values are quoted**, as above. compose reads the file with YAML 1.2 booleans, so an
  unquoted `No` or `yes` stays text, and numbers in `options` become text. When an unquoted
  list split an option at its commas, and `recommended` names the whole option, compose joins
  it back together.
- **Answers are checked**: with `free_text: false` the answer must be one of `options`.
  Setup, gap, conflict and review questions are free text. Approval questions take `approve`
  or `reject`, and only from their `approver`. A batch of answers is recorded all or nothing.
- The skills may add their own keys (`applied`, `hashes`); compose keeps them.

### Answering

Answers are repo-level: they're written into the questions file whether or not a run is
waiting. When a clarity run is paused on questions and nothing it asked is pending any more
(approvals aside), recording the answer resumes it. Otherwise the next `compose clarity` run
applies the answers.

- **CLI:**

  ```bash
  compose clarity questions                       # id, kind, document, options, recommendation
  compose clarity answer Q-007 "3 roles (PRD)"    # --by defaults to your git user name
  compose clarity answer Q-012 approve --by "Ana Silva"
  ```

  `--no-resume` records without resuming; `-d` resumes in the background.
- **API:** `GET /repos/{repo}/clarity/questions`, then
  `POST /repos/{repo}/clarity/answers` with `{"answers": {"Q-007": "3 roles (PRD)"}, "by":
  "Rui"}`. A paused run also lists what it waits for under `waiting.questions` in
  `GET /runs/{run}`. See [api.md](api.md).
- **Claude Code:** `/clarity` (or `/clarity mixed`) in your own checkout drafts, asks the
  pending questions in the conversation, records the answers in the file, and applies them,
  until nothing is pending.

### The clarity branch

Clarity runs work in a dedicated worktree, `~/.compose/worktrees/<repo>/clarity`, on a branch
named `clarity` (config `clarity.branch` in `~/.compose/config.yml`), created from the default
branch the first time.

- **Before a run**, compose merges the default branch into `clarity`. A conflict refuses the
  run, naming the files, and leaves the branch untouched.
- **Commits.** Whenever a clarity or clarity-validate run pauses, completes, fails or is
  aborted after changing `.clarity/` or `.compose/memory/`, compose commits those paths only, on
  the clarity branch, as `clarity: <mode> run <run id>`. It never commits anything else.
- **Auto-merge on PASS.** When a run records PASS, compose fast-forwards the local default
  branch to `clarity`. If the default branch moved during the run, it's merged into `clarity`
  first; a conflict, or a PASS that no longer holds on the merged content, merges nothing.
  When the default branch is checked out (usually your own checkout), compose fast-forwards it
  there, but only if that checkout has no uncommitted changes under `.clarity/` or
  `.compose/memory/`. Otherwise the run reports **PASS — merge pending** with the reason.
- **`compose clarity merge`** (`POST /repos/{repo}/clarity/merge`) retries the merge with the
  same rules, once you've cleaned up. It exits 1 (409) while the merge is still pending.
- **No push.** Push the default branch yourself when ready.

Builds branch from the default branch, so they only ever see a foundation that passed.

### Verdict and fingerprint

- The **clarity fingerprint** is a hash over the files under `.clarity/`, leaving out
  `verdict.yml`, `questions.yml`, `failures/brainstorm/` and `prototypes/`. It's the same for
  a branch and a worktree with the same content.
- After `/clarity-validate`, compose reads its last line (`CLARITY: PASS` or
  `CLARITY: FAIL (<n> incomplete)`; anything else counts as FAIL) and records
  `.clarity/verdict.yml`: `{result, incomplete, fingerprint, run_id, at}`. A verdict is
  **current** while its fingerprint matches the documents.
- `compose clarity validate` (`POST /repos/{repo}/clarity/validate`) runs `/clarity-validate`
  as a tracked run, records the verdict and, on PASS, publishes the memory files, commits
  and merges. It exits 1 on FAIL.
- `compose clarity status` shows all of it without a model call: each document's status, the
  verdict and whether it's current, the pending questions, whether the constitution is
  current, the active run, and whether `compose build` would start.

### The published memory

`.clarity/` is where the foundation is drafted and approved. Feature work never reads it.
After a clarity run, compose publishes the foundation to `.compose/memory/`, and that folder
is the only place the `compose-*` skills read:

- **One file per document**, at the same path (`.compose/memory/goal/requirements.md`). The
  text is the approved document, unchanged; only the clarity bookkeeping at the top is
  replaced by a one-line "generated" comment. Documents marked n/a aren't published, and
  only accepted ADRs are.
- **`feature-ideas.md`**, from the `## Feature ideas` section of the clarity notes.
- **A published API spec**, when `contracts/api.md` names one that lives under `.clarity/`.
- **The index**, `.compose/memory/constitution.md`. It has one row per file: what the file
  holds (with the rule IDs in it), when to read it, and its standing.

```text
<!-- memory-index: <fingerprint> -->
# Project memory

| File | Holds | Read | Standing |
|---|---|---|---|
| goal/requirements.md | The rules every feature must meet… IDs: NFR-001…NFR-014. | always at: specify, clarify, plan, tasks, implement, analyze | binding |
| product/ux-standards.md | UI rules… | always at: analyze; when: the feature has a user interface | binding |
```

A feature step reads the index, opens the files that name it under **always at**, and opens
the others only when their **when** fits the feature. `binding` files (complete documents,
accepted ADRs) are rules; `draft` files are hints.

What each row says comes from the shipped manifest. A custom document declares its own in
`.clarity/config.yml`:

```yaml
documents:
  ops/runbook.md:
    # template, required_sections, depends_on … as before
    memory:
      summary: "Alerts, on-call steps and how to roll back a release."
      read_at: [tasks, analyze]        # specify, clarify, plan, tasks, implement, analyze
      read_when: "the feature changes how the application is deployed or operated"
```

Publishing is plain copying: it costs nothing and the same documents always give the same
files. The folder is generated, so don't edit it: change the clarity documents and run
`compose clarity validate`. compose removes the files it published earlier and no longer
produces, and leaves alone anything else you keep in the folder.

**Upgrading.** A repo whose constitution was written by an earlier compose (its first line
is `<!-- generated-from-clarity: … -->`) has no memory files. `compose build` refuses there
with "The constitution is out of date with clarity"; one `compose clarity validate` run
publishes the memory and clears it.

## compose build

```bash
compose build "Wishlist for signed-in users" [--workflow id] [-i k=v ...] [--feature NNN-name] [-d] [--auto-approve]
```

`compose build` (`POST /repos/{repo}/builds`) runs the default workflow (`defaults.workflow`,
`automated` unless you change it) on a new feature, with the description as its spec (`compose run` is the same without the shortcut: you name the
workflow and give every input yourself with `-i`). First
comes the **pre-run check**, which `compose run` and `POST /repos/{repo}/runs` also apply to
every feature run. It reads the **local default branch**, the one feature worktrees branch
from, not your checkout. A repo has **started clarity** when its default branch has
`.clarity/`, or a `clarity` branch exists.

| Situation | Result |
|---|---|
| Clarity not started | Starts, with a warning: building on a guessed constitution. Run `compose clarity` for a confirmed foundation |
| Started, `.clarity/` not on the default branch | Refuses: clarity is in progress on branch `clarity`. Fix: `compose clarity`; or, when the branch has a current PASS that wasn't merged, `compose clarity merge` |
| No verdict, FAIL, or a verdict for other content than the default branch's | Refuses: the foundation doesn't pass (or changed since it was validated). Fix: `compose clarity validate` |
| The constitution's stamp isn't the default branch's fingerprint | Refuses: the constitution is out of date with clarity. Fix: `compose clarity validate` |
| All current and PASS | Starts |

`--auto-approve` (`-y`) approves gates and hook confirmations automatically, so a build can
run unattended (also with `-d`). It takes `approve`, or `install` at the skills gate (the first
option that isn't `reject`), and prints a `✓ auto-approved` line for each. A gate with no
`reject` option still waits, and clarity questions still wait for their approver.

A refusal happens before any run exists: exit 1 on the CLI, 409 from the API with
`problems: [{message, fix}]`. When the local default branch is behind its upstream (as far as
git already knows), the message says to pull first: clarity merged on the remote reaches
builds only after a pull. Warnings go to stderr on the CLI, and under `warnings` in JSON and
API responses.

**Without clarity**, builds work as before: the warning says the foundation is a guessed
constitution, and if the default branch has none, the workflow's constitution step creates one
unattended.

## The clarity skills by hand

```text
/clarity                                  # mixed: draft, ask what's open here, apply
/clarity docs/prd.md docs/rfc.md          # or from documents you already have
/clarity https://github.com/org/repo/issues/12 mandatory: PRD, API, setup guide only
/clarity docs/ interactive                # the stage-by-stage conversation
/clarity docs/ auto                       # draft everything unattended, confirm later
/clarity-validate                         # check; last line is CLARITY: PASS or FAIL
/clarity-approve product/prd.md           # an approver signs off
```

`/clarity` is the only command you need. It calls the other skills itself, in order. You can
also run any of them on its own to rework one document. Run by hand in your own checkout,
nothing is tracked or committed: you commit yourself, and the [pre-run check](#compose-build)
then reads what you merged into the default branch.

## The flow

This is the whole process, as `/clarity interactive` walks through it with you. `draft` and
`apply` run the same steps unattended, raising questions instead of asking them.

| Step | What happens |
|---|---|
| 0. Assess | Reads `.clarity/` and works out where things stand. Resumes at the first unfinished step. |
| 1. Inputs | Reads every supplied document, folder or URL, and scans the code, **once**. Writes an inputs summary (what each source informs, and any conflicts) to `.clarity/notes.md`. |
| 2. Configure | `clarity-configure` agrees with you which documents are mandatory, which don't apply and why, any custom documents, and who approves what. The result is `.clarity/config.yml`. |
| 3. Scaffold | Creates only the documents this project needs, from the templates. Documents you removed from the mandatory set are not created. |
| 4. Infer | Drafts every document your inputs inform. Existing OpenAPI/GraphQL files and database schemas are reused, not retyped. Gaps and conflicts are left as notes to ask about. |
| 5. Stages | goal → solution → failures → architecture + ADRs → product → technical → summaries. Each stage runs its skills, which ask only about gaps, and then you confirm the whole stage at once. |
| 6. Recheck | One pass over documents that went stale or were edited, to re-confirm or revise them. |
| 7. Approve | Sign-offs, always last. Only the approver in the conversation can approve, for their own name. |
| 8. Validate | `clarity-validate` prints the report and `CLARITY: PASS` or `CLARITY: FAIL (n incomplete)`. |

Everything is saved as it goes. If you stop at any point, the next `/clarity` picks up where
you left off. New material on a re-run updates drafts freely. For confirmed documents,
`/clarity` shows what would change and asks first.

`auto` runs steps 0–4 and the drafting part of step 5 without questions. It never marks
anything complete or N/A, and never approves, so its report always fails. The report lists
what needs a person.

## The documents

| Document | Skill | Notes |
|---|---|---|
| `goal/problem.md` | clarity-problem | Can't be N/A or removed |
| `goal/stakeholders.md` | clarity-problem | |
| `goal/requirements.md` | clarity-problem | Non-functional requirements `NFR-###`, constraints `CON-###`, standards `STD-###`. No functional requirements. Can't be N/A or removed |
| `goal/open-questions.md` | clarity-problem | Each question has Status, Strategy, **Blocking** |
| `solution/solution.md` | clarity-solution | |
| `failures/failures.md` | clarity-failure-brainstorm → -analysis → -management | Six "thinkers" brainstorm in parallel |
| `failures/fmea.md` | clarity-fmea | Optional. An FMEA worksheet built from the failure documents: function, failure mode, effect, cause, current controls, severity and recommended action per row. Add it with `mandatory.add` |
| `solution/architecture.md` | clarity-architecture | System architecture document, with a mermaid threat model |
| `decisions/index.md` + `ADR-NNN-*.md` | clarity-decision | One file per decision |
| `product/prd.md` | clarity-prd | Product brief: users, goals `G-###`, scope boundaries, product principles. No features |
| `product/ux-standards.md` | clarity-ux-standards | Navigation, interaction patterns, accessibility, design system, state conventions. No screens |
| `contracts/api.md` | clarity-api-contracts | API conventions. An optional `spec:` names a published OpenAPI/GraphQL contract the app must keep |
| `data/data-model.md` | clarity-data-model | Core entities (`erDiagram`) and data rules. No feature tables |
| `ops/setup-guide.md` | clarity-setup-guide | Never contains secret values |
| `solution/solution-summary.md` | clarity-architecture | |
| `summary.md` | clarity-message | |

Blocking open questions are investigated with `clarity-discovery-prototype` (in
`.clarity/prototypes/`, disposable), `clarity-discovery-research` or `clarity-problem`,
depending on their strategy. `notes.md`, `observations.md` and `goal/resolved-questions.md` are
kept alongside but not validated.

The templates live outside the skills, in `.compose/templates/clarity/`, next to
`manifest.yml`, which lists every document with its required sections, dependencies and
producing skill. Installs refresh the manifest. Templates are only added when missing, so local
edits to them survive.

## Front matter

Every document starts with:

| Field | Meaning |
|---|---|
| `status` | `draft`, `complete` (after your confirmation) or `n/a` |
| `reason` | Why it's N/A. Required when `status: n/a` |
| `depends_on` | The upstream documents |
| `reviewed.hash` | Fingerprint of the body when it was confirmed |
| `reviewed.deps` | Fingerprints of the upstream documents at that moment |
| `sources` | The supplied documents or URLs its content came from |
| `approvals` | `{by, at, hash}` entries, written only by `clarity-approve` |

A fingerprint is the git blob hash of the text after the front matter:

```bash
awk 'n>=2; /^---$/ && n<2 {n++}' .clarity/product/prd.md | git hash-object --stdin
```

Because only the body is hashed, confirming or approving a document never changes its
fingerprint. Nothing needs committing for the checks to work.

## Project config

`.clarity/config.yml` belongs to the project: commit it, and installs never touch it.
`clarity-configure` writes it, and every key is optional:

```yaml
setup: dynamic                   # or static; see below
mandatory:
  add: [ops/runbook.md]
  remove: [product/ux-standards.md]
not_applicable:
  data/data-model.md: "Stateless service, no persistence"
documents:                       # project-specific documents
  ops/runbook.md:
    template: .clarity/templates/runbook.md
    required_sections: [Alerts, Rollback]
    depends_on: [solution/architecture.md]
    produced_by: clarity         # /clarity drafts it itself
    walk_after: ops/setup-guide.md
approvals:
  product/prd.md: [Ana Silva]
  decisions/*: [Rui Costa]       # every ADR
stale_fails: false
```

### FMEA

`failures/fmea.md` is the one optional shipped document: a Failure Mode and Effects
Analysis worksheet, for regulated or safety-related work and audits that expect the classic
table. It is left out unless the config adds it:

```yaml
mandatory:
  add: [failures/fmea.md]
fmea:
  scores: false                  # true adds S, O, D and the risk priority number
```

`clarity-fmea` builds it from the analysed failure modes and their management plans, one
row per failure mode and cause (`FM-001`, …), each linking its failure document. It adds
nothing the failure documents don't say; when they change, the worksheet is regenerated.
Scores are off by default, because the failure skills don't rank by severity times
likelihood. With `scores: true`, each row is scored 1–10 for severity, occurrence and
detection, and a person confirms the occurrence and detection scores.

### Setup mode

`setup` says how the list of required documents is decided:

- `dynamic` (the default, also with no file): `/clarity` asks a person first. The setup
  question lists every document, included or left out, and the person confirms or changes
  the list. A brief that names the documents only shapes the proposal; it never counts as
  the answer. The agreed list is written to the file, so later runs ask again only when
  compose ships a new document.
- `static`: `/clarity` asks nothing about the setup and follows the file as written. Use it
  when the list is decided up front, or in a pipeline with nobody to answer.

The file starts as a commented starter with an example for every key, including the full
list of shipped documents; `clarity-configure` keeps those comments when it edits the file.

## Validation

`/clarity-validate` reads only. For each mandatory document it reports the first state that
applies:

| State | Fails? | Meaning |
|---|---|---|
| missing | yes | No file |
| n/a | no | Not applicable, with a reason. **invalid-n/a** (no reason, or a document that can't be N/A) fails |
| draft | yes | `status: draft`, placeholder text left, or a required section missing or empty |
| edited | yes | Complete, but the body changed after it was confirmed |
| blocked | yes | An unresolved open question marked Blocking: yes, or an ADR that is `proposed` or `reconsider` |
| unapproved | yes | A configured approver hasn't approved the current content |
| complete | no | None of the above |
| stale | warning | An upstream document changed after this one was confirmed. Fails with `stale_fails: true` |

The last line is always `CLARITY: PASS` or `CLARITY: FAIL (<n> incomplete)`, so you can gate
on it:

```bash
claude -p "/clarity-validate" | tail -n 1 | grep -qx 'CLARITY: PASS'
```

The checks are applied by the model following the skill's rules, consistently but not byte
for byte, so treat this as a review gate rather than a compiler.

## Approvals

Approvals are a recorded sign-off. They're an honor system, not proof of identity. List
approvers per document under `approvals` in the config. `clarity-approve` asks who is
approving, checks the name against the list, requires an explicit "I approve …", and records
the name, the date and the document's current fingerprint. Any later edit voids that approval.
Drafts, edited documents and stale documents can't be approved.

## How compose uses clarity

When a repo has a clarity foundation, the compose skills follow its published memory. They
read the index, and the shared guide `.compose/templates/compose/clarity.md` says how:

| compose step | Takes from the memory files |
|---|---|
| `/compose-constitution` | Nothing: the constitution is the generated index, and the skill leaves it alone. |
| `/compose-specify`, `/compose-clarify` | Actors, goals and scope boundaries. The spec's `Serves:` line cites goals and rules, and it doesn't ask what clarity answers. Its own `FR-###` are per feature. |
| `/compose-plan` | Stack and components from the architecture and accepted ADRs, which aren't researched again. Contracts, data and screens follow the conventions. A **Clarity check** table sits next to the constitution check. |
| `/compose-tasks` | Tasks for failure mitigations touching the feature, tests the standards require, and setup steps. |
| `/compose-implement`, `/compose-converge`, `/compose-bug-fix` | The binding rules (requirements, constraints, standards, accepted ADRs) the code must keep. |
| `/compose-analyze` | Reads every file. Flags breaking a binding rule or accepted ADR as critical. |

`complete` documents and `accepted` ADRs are binding, drafts are hints, and `n/a` documents are
skipped. compose never edits `.clarity/`. A conflict is raised (or, in a headless run, recorded
as `Clarity conflict:`), and a new application-wide decision is proposed for
`/clarity-decision`.
