# Clarity skills — design

Date: 2026-11-22
Status: approved 2026-11-22

## Intent

[microsoft/clarity-agent](https://github.com/microsoft/clarity-agent) is a thinking partner. It
pushes a project through problem → stakeholders → requirements → solution → failure analysis →
architecture → decisions, and writes each result to a Markdown file in `.clarity-protocol/`. Its
conversational guidance is already Markdown (11 process guides, 6 "thinker" guides). The rest is
Python glue: it creates templates, detects placeholder text, keeps a dependency graph with
content hashes for staleness, routes to the next process, runs thinkers through mailbox folders,
tracks decision triggers, builds review packets, and serves an MCP server.

We want the same work done **through skills only**. Skills are less deterministic than code, but
they are portable, readable, and need no runtime. On top of clarity-agent's document set we add the
software-delivery documents a team needs before building: PRD, FR/NFR, UI/UX and state flows,
system architecture document, API contracts, database schema and ERD, ADRs, and an environment and
setup guide. One skill validates that every mandatory document is complete.

## Goals

- A `clarity-*` skill family that reproduces clarity-agent's processes and thinkers, plus skills
  for the added software documents.
- Document templates live as separate files, **never inline in a SKILL.md**.
- One command, `/clarity`, runs the whole process end to end: configure → draft from supplied
  documents → work through every document → approvals → validation.
- A `clarity-validate` skill reports, for every mandatory document, one of: complete, N/A (with
  reason), draft/placeholder, missing, blocked, unapproved, or stale/edited, and gives an overall
  PASS/FAIL.
- Any document can be marked **not applicable** with a reason, unless the manifest forbids it.
- State lives in the documents themselves (front matter), one shipped manifest and one project
  config. No `config.json` and no scripts. The only exact computation is a content fingerprint
  from a documented one-line `git hash-object` command (see Front matter).

## Non-goals

- No tie-in to the `compose-*` skills or compose workflows. These skills are independent: they do
  not call `compose` CLI commands, and compose skills don't call them.
- No Python, no helper scripts, no MCP server, no CLI command.
- No Word (.docx) review packets.
- No desktop/web UI, LLM-provider setup, or the clarity installer/updater.

## Anti-goals

- Templates copied into SKILL.md bodies (the user's explicit constraint).
- A validator that says PASS while a document still has placeholder text, or that accepts N/A
  with no reason.
- Exposing the machinery to the user ("the dependency graph says…"). Like clarity-agent, the
  skills hold a conversation and keep the files quietly up to date.
- Software-only framing in the early processes. Problem and solution work stays domain-neutral, as
  in clarity-agent. The software documents simply go N/A when they don't apply.

## Constraints

- Skills ship from this repo next to the compose skills, in `src/compose/assets/skills/clarity*/`.
  They're installed by the existing installer (`src/compose/engines/claude/install.py`), which
  copies skills to `<project>/.claude/skills/` and templates to `<project>/.compose/templates/`.
  **The user's decision: install all skills, compose and clarity, everywhere the installer runs**
  (repo setup and every workflow worktree). That takes one installer change: `_planned()` currently
  copies only folders whose names start with `compose`, and it must also include `clarity`. The
  installer tests are updated to match.
- `manifest.yml` is installed with **overwrite on**, like a skill, so upgrades keep it in step with
  the skills. The document templates stay add-only, so local edits survive. *(My call.)*
- Templates go in `src/compose/assets/templates/clarity/`, so they install to
  `.compose/templates/clarity/`. *(My call: it reuses the installer unchanged. Moving to a
  `.clarity/` home later is just a path change in the manifest and skills.)*
- clarity-agent is MIT-licensed (Microsoft). Skills that adapt its process or thinker text carry
  attribution, and a `LICENSE.txt` with the MIT notice ships in the adapted skill folders, the same
  way `compose-find-skills/LICENSE.txt` does today.
- Existing asset tests (`tests/unit/test_assets.py`) list every shipped skill, so the new skills
  must be registered there.

## Approaches considered

**A. The documents carry their own state (chosen).** Every protocol document has YAML front
matter (`status`, `reason`, `depends_on`). A manifest lists the mandatory documents, their
required sections, their dependency order, and which skill produces each one. `clarity-validate`
reads the manifest plus the front matter. It treats a document as stale when a dependency's
content no longer matches what it was when the document was confirmed. This uses only skills and data, and the state sits where
reviewers already look. The trade-off: the checks rest on the model following the instructions
exactly, so they're consistent but not byte-for-byte deterministic.

**B. A plus a small validation script.** This makes the presence, placeholder and N/A checks exact,
but reintroduces code, which is what we're moving away from. Rejected.

**C. A central `config.json` like clarity-agent's.** This is closest to the original, but every
skill must keep it in sync by hand, and a skills-only port would drift fastest there. Rejected.

The user picked **A**.

## Protocol directory

`.clarity/` at the project root *(the user's decision; clarity-agent uses `.clarity-protocol/`,
and its standalone `Clarity Protocol/` variant is dropped)*.

```text
.clarity/
├── summary.md                  # general-audience narrative
├── notes.md                    # shared memory, [for: <phase>] tags (not validated)
├── observations.md             # analysis provenance (not validated)
├── goal/
│   ├── problem.md
│   ├── stakeholders.md
│   ├── requirements.md         # FR-### and NFR-### sections
│   ├── open-questions.md
│   └── resolved-questions.md   # not validated
├── product/
│   ├── prd.md
│   └── ux-flows.md             # screens, journeys, Mermaid state diagrams
├── solution/
│   ├── solution.md
│   ├── architecture.md         # the System Architecture Document (SAD)
│   └── solution-summary.md
├── contracts/
│   ├── api.md                  # narrative + pointer to the machine-readable spec
│   └── openapi.yaml | schema.graphql
├── data/
│   └── data-model.md           # schema tables + Mermaid erDiagram
├── failures/
│   ├── failures.md
│   └── brainstorm/<thinker>.md # raw thinker output (replaces mailboxes)
├── decisions/
│   ├── index.md                # ADR list with status
│   └── ADR-NNN-<slug>.md
└── ops/
    └── setup-guide.md          # environments, prerequisites, local setup, config, secrets handling
```

### Project config: choosing the mandatory set (the user's decision)

The shipped manifest is overwritten on every install, so projects customize through their own
file, `.clarity/config.yml`. The project owns and commits it, and installs never touch it.
The file is written by the **`clarity-configure`** skill, which is **the first step of every
`/clarity` run** (the user's decision). It's a short conversation:

- It reads the shipped manifest, any existing `config.yml`, and a quick scan of the supplied
  documents and repo. From these it *proposes* a configuration: which documents are mandatory,
  which look N/A and why (for example, "no UI found: mark ux-flows N/A?"), any custom documents
  the user mentions, and who approves what.
- The user corrects it in their own words. Short-cuts like
  `/clarity mandatory: PRD, API, setup guide only` are applied directly.
- It writes `config.yml`, shows the result, and moves on once the user confirms it.
- On later runs, when a `config.yml` already exists, it only asks "keep the same setup?" and
  skips the conversation unless the user wants changes or the shipped manifest gained documents
  since the last run.
- In `auto` mode it writes the proposal with every inferred N/A left commented out (N/A needs a
  person) and no approvers, and moves on.

It can also be run on its own (`/clarity-configure`) at any time to change the setup.

```yaml
mandatory:
  add:    [ops/runbook.md]          # optional or custom documents made required
  remove: [product/ux-flows.md]     # never required in this project
not_applicable:                     # decided up front; /clarity won't ask
  data/data-model.md: "Stateless service, no persistence"
documents:                          # project-specific documents
  ops/runbook.md:
    template: .clarity/templates/runbook.md
    required_sections: [Alerts, Rollback]
    depends_on: [solution/architecture.md]
    produced_by: clarity            # the orchestrator drafts it from the template and sources
    walk_after: ops/setup-guide.md
stale_fails: false
```

Rules:

- The **effective manifest** is the shipped manifest with `config.yml` applied on top. Both
  `/clarity` and `clarity-validate` use only the effective manifest, and the validator report says
  which config it applied.
- `remove` can't remove `goal/problem.md` or `goal/requirements.md`. The validator reports that as
  a config error.
- `not_applicable` entries count as N/A with that reason, the same as `status: n/a` in the
  document. If they conflict, the document's own front matter wins, and the report flags the
  mismatch.
- Custom `documents` need a template that exists, plus valid `depends_on` paths, and their
  templates follow the same front-matter rules. With no dedicated skill, `/clarity` drafts them
  itself from the template, the sources and their dependencies. `produced_by` may name any shipped
  skill instead.
- An invalid `config.yml` (bad YAML, unknown path, missing template) makes the validator FAIL with
  the specific error. It never silently ignores the config.

### Approvals (the user's decision: keep it simple)

Approvals are an optional, recorded sign-off. They're an honor system, not proof of identity. A
project turns them on by listing approvers per document in `config.yml`:

```yaml
approvals:
  product/prd.md: [Ana Silva]
  solution/architecture.md: [Rui Costa]
  decisions/*: [Rui Costa]          # glob: every ADR
```

- Documents not listed need no approval, which is the default, so nothing changes for projects
  that don't use approvals.
- The new `clarity-approve <document>` skill asks who is approving, checks that the name is on that
  document's list, and appends `{by, at: <date>, hash: <body hash>}` to the document's `approvals:`
  front matter. It refuses on a `draft` document, and on a complete document that is stale or
  edited (see Front matter), because the approver would be signing something not yet re-confirmed.
- An approval counts only while the document's body hash still equals its `hash`. Any edit means
  it must be approved again. This works the same whether or not anything has been committed.
- **Approvals are the last step of `/clarity`** (the user's decision). They come only after every
  mandatory document is complete or N/A and nothing is blocked. The orchestrator lists the
  documents needing sign-off and who they're waiting on, then invokes `clarity-approve` for each
  one. The approver must be the person in the conversation and must confirm by name. The
  orchestrator never fills in an approver itself. Approvers who aren't present are left pending.
  The final validator report names them, and they can run `/clarity-approve` later.
- In `auto` mode the approval step is skipped entirely, and pending approvals are only reported.
- No roles, no git authorship, no PR integration for now. *(Possible later step: map approvals to
  PR reviews.)*

### Front matter (every validated document)

```yaml
---
status: draft          # draft | complete | n/a
reason: ""             # required, non-empty, when status is n/a
depends_on:            # copied from the manifest at creation; skills may add to it
  - goal/problem.md
reviewed:              # written when the user confirms; empty while draft
  hash: ""             # this document's body hash at confirmation
  deps: {}             # {path: body hash} of each depends_on document at confirmation
sources: []            # user-supplied documents/URLs this content was inferred from
approvals: []          # [{by, at, hash}], written only by clarity-approve
---
```

**Body hash.** This is the fingerprint of everything after the front matter. Every skill computes
it with the same documented command, which is stored once in the manifest as `hash_command`:

```bash
awk 'n>=2; /^---$/ && n<2 {n++}' <file> | git hash-object --stdin
```

This is clarity-agent's own baseline model (`packet_status --record` stores the content hashes of a
document and its dependencies). It's kept as a single shell command, not a script. *(My call,
replacing my earlier commit-based `reviewed_at`. Thinking through the full flow showed that
commit-based checks break whenever `.clarity/` isn't committed between steps, which is the normal
case in one `/clarity` session. An approval given before a commit would be invalid right after it.
Content hashes don't care about commits, and they don't need a git repo, only the `git` binary.)*

- **Confirming** a document (by the user, in a stage batch) sets `status: complete` and writes
  `reviewed.hash` and `reviewed.deps`. Re-confirming with no changes just rewrites them, which is
  how a stale document clears without a meaningless edit. The failures ↔ architecture cycle clears
  once both are confirmed.
- **Stale**: a dependency's current body hash differs from `reviewed.deps`.
- **Edited**: the document's own body hash differs from `reviewed.hash`. Someone changed it after
  confirmation, by hand or through another skill. It needs re-confirming, and its approvals are void.

Templates ship with `status: draft` and bracketed placeholders (`[TBD]`, `[To be determined…]`).
A skill sets `status: complete` only after the user confirms the content, and removes every
placeholder when it does.

## The manifest

`src/compose/assets/templates/clarity/manifest.yml` is the single source of truth that both the
skills and the validator read. For each document it gives:

- `path` (relative to `.clarity/`), and `template` (relative to the templates dir)
- `mandatory: true|false`
- `allow_na: true|false`. *(My call: `false` only for `goal/problem.md` and `goal/requirements.md`,
  since every project has a problem and criteria. Everything else may be N/A.)*
- `required_sections`: the headings that must exist and be non-empty
- `depends_on`: the upstream documents
- `produced_by`: the skill that writes it
- `placeholder_markers`: a shared list (clarity-agent's markers plus `[TBD]`)
- `walk_order`: the global order used for routing and the report
- `stages`: the confirmation batches (see Pace), each a list of paths
- `hash_command`: the body-hash command above

Mandatory documents, in walk order:

| # | Document | Origin | Depends on | Produced by |
|---|---|---|---|---|
| 1 | goal/problem.md | clarity | — | clarity-problem |
| 2 | goal/stakeholders.md | clarity | 1 | clarity-problem |
| 3 | goal/requirements.md (FR/NFR) | clarity, extended | 1, 2 | clarity-problem |
| 4 | goal/open-questions.md | clarity | 1 | clarity-problem |
| 5 | solution/solution.md | clarity | 1, 3, 4 | clarity-solution |
| 6 | failures/failures.md | clarity | 5, 7 | clarity-failure-analysis / -management |
| 7 | solution/architecture.md (SAD) | clarity, extended | 5, 6 | clarity-architecture |
| 8 | decisions/ (ADRs) | clarity, reshaped | cross-cutting | clarity-decision |
| 9 | product/prd.md | new | 1, 2, 3, 5 | clarity-prd |
| 10 | product/ux-flows.md | new | 9, 3 | clarity-ux-flows |
| 11 | contracts/api.md + spec file | new | 7, 3 | clarity-api-contracts |
| 12 | data/data-model.md | new | 7, 3 | clarity-data-model |
| 13 | ops/setup-guide.md | new | 7, 11, 12 | clarity-setup-guide |
| 14 | solution/solution-summary.md | clarity | 5, 7 | clarity-solution / -architecture |
| 15 | summary.md | clarity | 1, 2, 5 | clarity-message |

The failures ↔ architecture cycle is kept from clarity-agent and broken the same way: failures come
first in the walk.

**Open questions and ADRs (the user's decision: block on blockers).** Each question in
`goal/open-questions.md` carries `status` (`open | investigating | resolved`), `strategy`
(`thinking | research | prototyping`), and `blocking: true|false`. The project can PASS with open
questions, but FAILs while any unresolved question has `blocking: true`. It also FAILs while any
ADR is `proposed` or `reconsider`.

`decisions/` counts as complete when `index.md` has `status: complete` and lists at least one ADR,
or when `index.md` is `n/a` with a reason. Each ADR has its own front matter: `status` of
`proposed | accepted | superseded | reconsider`, plus `depends_on`, which lists the documents the
decision rests on. ADR front matter replaces clarity-agent's decision triggers.

`contracts/api.md` names its spec file in front matter (`spec: contracts/openapi.yaml`). The
validator checks that the file exists and is well-formed YAML/GraphQL by reading it, unless
`api.md` is N/A.

## Skills

There are 19 skills. Each has a SKILL.md with frontmatter (`name`, `description`,
`argument-hint`), like the compose skills. Process text is adapted from the matching clarity-agent
guide, with its tool calls replaced by plain file reads and writes.

| Skill | Source in clarity-agent | Writes |
|---|---|---|
| `clarity` | clarity-agent.md (entry point) | orchestrator: sets up `.clarity/`, ingests supplied documents, invokes every other skill in order, ends with validation |
| `clarity-problem` | problem-clarification.md | problem, stakeholders, requirements, open-questions |
| `clarity-discovery-prototype` | discovery-prototype.md | resolved-questions, open-questions |
| `clarity-discovery-research` | discovery-research.md | resolved-questions, open-questions |
| `clarity-solution` | solution-brainstorming.md | solution, solution-summary |
| `clarity-architecture` | architecture-design.md | architecture (SAD, with Mermaid threat-model diagram), solution-summary |
| `clarity-failure-brainstorm` | failure-brainstorming.md + 6 thinkers | failures/brainstorm/*.md |
| `clarity-failure-analysis` | failure-analysis.md, failure-reasoning-guidelines.md | failures.md, observations.md |
| `clarity-failure-management` | failure-management.md | failures.md (plans); may update solution/architecture |
| `clarity-decision` | decision-guidance.md | decisions/ADR-*.md, decisions/index.md |
| `clarity-message` | message-clarification.md | summary.md (+ optional messaging.md) |
| `clarity-prd` | new | product/prd.md |
| `clarity-ux-flows` | new | product/ux-flows.md |
| `clarity-api-contracts` | new | contracts/api.md + spec |
| `clarity-data-model` | new | data/data-model.md |
| `clarity-setup-guide` | new | ops/setup-guide.md |
| `clarity-validate` | packet_status.py logic | nothing (report only) |
| `clarity-approve` | new | the document's `approvals:` front matter |
| `clarity-configure` | new | `.clarity/config.yml` (first step of `/clarity`) |

Shared behaviours, written once in each skill's own text rather than in a shared runtime:

- Read `notes.md` at the start; add or consume `[for: <phase>]` items.
- Save as you go: write rough drafts early, keep `status: draft` until the user confirms.
- Any skill whose document doesn't fit the project offers to mark it N/A, asks the user for the
  reason, and records it.
- Before asking anything, read the document's `sources` and the other protocol documents, and ask
  only about gaps and conflicts.
- When finished, hand back to `clarity`, which re-assesses and continues automatically. When a
  skill is called directly, it suggests the next step instead.
- Domain-neutral language up to the solution. Software framing only in the new product,
  contract, data and setup skills.

### One skill drives everything (`clarity`)

**The user's requirement: the user never has to call the skills one by one.** `clarity` is the
orchestrator. It works through the whole chain itself and invokes each producing skill in walk
order. After each one finishes, it re-assesses and moves to the next, until `clarity-validate`
reports PASS or the user stops. The other skills can still be called directly to rework one
document, but nothing requires it.

```text
/clarity [docs or paths…] [auto]
  ├─ 0. assess    read .clarity/ (if any), config.yml, notes.md; run the validate rules silently
  ├─ 1. inputs    read every supplied document + scan the repo, once; list what each informs
  ├─ 2. configure clarity-configure → mandatory set, N/A, custom docs, approvers → config.yml
  ├─ 3. scaffold  create only the effective manifest's documents from templates (skip existing)
  ├─ 4. infer     draft every document the inputs inform (status: draft, sources: […])
  ├─ 5. stages    for each stage in order, until all its documents are complete or N/A:
  │                 run each document's skill (asks only about gaps/conflicts), then
  │                 one batch confirmation for the stage → complete + reviewed hashes
  │                 goal → solution → failures (brainstorm→analysis→management)
  │                 → architecture + ADRs → product → contracts/data/setup → summaries
  ├─ 6. recheck   one pass over stale/edited documents: re-confirm or revise
  ├─ 7. approve   clarity-approve per document needing sign-off (last; skipped in auto)
  └─ 8. validate  clarity-validate → table + CLARITY: PASS | FAIL, and what's left, for whom
```

Why this order (from walking the whole flow):

- **Inputs before configure.** `clarity-configure` can only propose a sensible mandatory set and
  N/A list once it knows what material exists. Inputs are read once and reused by every later
  step, so nothing is read twice.
- **Configure before scaffold.** Creating every template first and then marking half of them N/A
  is noise. Only the effective manifest's documents are created, custom ones included, and N/A
  ones get a stub with `status: n/a` and the reason.
- **Infer before stages.** Drafting everything up front means each stage's conversation starts
  from a draft and asks only about gaps. It also shows conflicts across documents early (for
  example, a PRD that contradicts the code).
- **Approvals after recheck.** An approval binds to a content hash, so anything that could still
  change a document has to happen first.

### Resuming, re-runs and loops

- **Resumable by design.** All state is on disk, so a long run can stop at any point (the user
  leaves, the session ends, the context fills up) and `/clarity` picks up at the first unfinished
  stage. Each stage ends by saving, then gives a one-line "done: X, next: Y" so a fresh session can
  continue. The orchestrator relies on the files, not on conversation memory.
- **Re-runs with new sources.** New material can update `draft` documents freely. For a
  `complete` document, the orchestrator shows a short summary of what the new source would change
  and asks. If accepted, the document goes back to draft and is re-confirmed in its stage. It never
  overwrites confirmed content silently.
- **Downstream skills changing upstream documents.** `clarity-failure-management` may revise the
  solution or architecture, and any skill may record an ADR. When a skill edits a `complete`
  document, the document becomes *edited* and is picked up by step 6. It is not re-run in a loop.
- **No endless loops.** Step 6 runs once per `/clarity` run. Anything that turns stale again during
  it is reported, not re-processed. A stage whose skill was run twice in one run without
  completing is reported as "needs the user" and the run moves on.
- **Discovery work stays disposable.** `clarity-discovery-prototype` builds in
  `.clarity/prototypes/<question>/`, which is never imported by product code. Only the findings
  are recorded, in `goal/resolved-questions.md`. Research findings go to the same place.
- **Using it as a gate.** Because the validator's last line is exact, a team can gate on it, for
  example `claude -p "/clarity-validate"` in CI and check for `CLARITY: PASS`. It's not
  byte-for-byte deterministic (Approach A's trade-off), so treat it as a review gate, not a
  compiler.

**Inferring from supplied documents (the user's requirement).** The user may hand over existing
material: files or folders in the repo, pasted text, or URLs (the same fetch-safety rules as the
compose skills). It might be a PRD, an RFC, meeting notes, an existing architecture doc, an OpenAPI
file, a SQL schema, or a README. `clarity` reads all of it first, before asking anything. It also
reads the repo's code when there is some, the way clarity-agent "articulates what's already there".

- Each source is mapped to the protocol documents it informs. One source can feed several
  documents. For example, a PRD feeds problem, stakeholders, requirements and prd.md.
- Each informed document is drafted from the sources and keeps `status: draft`. Its front matter
  gains `sources: [<path or URL>, …]`, so the origin of the content stays traceable.
- Machine-readable sources are reused rather than retyped. An existing OpenAPI/GraphQL file
  becomes the `spec:` of `contracts/api.md` (referenced in place, or copied if it lives outside the
  repo). A SQL/ORM schema seeds `data/data-model.md` and its ERD.
- Where sources disagree, or are silent on a required section, the draft records the gap as a
  placeholder plus a one-line note saying what's missing or conflicting. Then each skill's
  conversation asks *only* about those gaps and conflicts. It doesn't re-ask what the documents
  already answer.
- A document the sources show doesn't apply (for example, no UI anywhere) gets *proposed* as N/A,
  with the inferred reason. The user confirms it.

**Pace.** Following clarity-agent's "move quickly through what's obvious", the orchestrator
confirms in batches by stage rather than per document: goal, then solution, then failures, then
architecture and ADRs, then product, contracts, data and setup, then summaries. Each batch shows a
short summary of what was drafted or inferred, lists the open gaps, and asks what's wrong or
missing. Confirmed documents get `status: complete` and their `reviewed` hashes.

**`auto` mode** *(my call)*. For an unattended run, or when the user says "just draft
everything", `clarity … auto` skips the confirmations. It infers and drafts every document, marks
nothing `complete`, and ends with the validator report, which lists what needs a human. Nothing in
auto mode marks a document `complete` or `n/a`. A person must confirm those.

### Routing details

Inside a stage, the orchestrator uses the same rules as `clarity-validate` to pick the next
document in walk order that is missing, draft or blocked. It invokes that document's `produced_by`
skill and tells the user in a plain sentence what it is working on. Blocking open questions route
by their strategy field (prototyping → discovery-prototype, research → discovery-research,
thinking → problem) inside the goal stage, before solution work starts. Non-blocking questions
don't stop the flow. ADRs in `proposed` or `reconsider` status route to `clarity-decision` in the
architecture + ADRs stage. The routing rules live in the manifest plus the orchestrator's text.
Step 0 applies the validate rules silently to assess, and step 8 invokes `clarity-validate` for the
final report.

### Thinkers (`clarity-failure-brainstorm`)

The six thinker guides (general, security, security-catalog, human-factors, adversarial-analysis,
codebase-scanner) are reference files in `clarity-failure-brainstorm/thinkers/`. They are
instructions, not document templates, so they stay inside the skill folder. Each keeps
clarity-agent's front matter, including `prerequisites.required`, which the skill checks before it
runs a thinker. The skill dispatches each eligible thinker as a parallel subagent where the host
supports subagents, and sequentially otherwise. Each thinker writes only its own
`failures/brainstorm/<thinker>.md` file. That file-per-thinker layout replaces clarity-agent's
mailbox and keeps parallel writes safe. The codebase-scanner thinker runs only when the project has
code. Human contributions go to `failures/brainstorm/human-<n>.md`. `clarity-failure-analysis`
consumes those files and records which ones it absorbed in `observations.md`, so it can run again
on new input.

## Validation (`clarity-validate`)

Inputs: the effective manifest (the shipped `.compose/templates/clarity/manifest.yml` with `.clarity/config.yml` applied on top) and `.clarity/`.
`$ARGUMENTS` may name a subset of documents.

Checks for each mandatory document, in walk order:

1. **missing**: the file isn't there.
2. **n/a**: `status: n/a`. Valid only if `reason` is non-empty and `allow_na` is true. Otherwise it
   is reported as **invalid-n/a**.
3. **draft**: `status: draft`, *or* any placeholder marker appears, *or* a required section is
   missing or empty, even if the front matter says `complete`. Each specific gap is listed.
4. **edited** (failure): `status: complete` but the body hash differs from `reviewed.hash`.
   Confirmed content changed without being re-confirmed.
   **stale** (warning, failure only with `stale_fails: true`): a dependency's body hash differs
   from `reviewed.deps`. The changed dependencies are named. ADRs whose `depends_on` documents
   changed are listed in a "decisions to recheck" section.
5. **blocked** (failure): an unresolved open question with `blocking: true`, or an ADR in
   `proposed` or `reconsider` status. Each one is named.
6. **unapproved** (failure): the document is complete, but an approver listed in `config.yml` has
   no valid approval, either because none was recorded or because the content changed since.
   Missing approvers are named.
7. **complete**: none of the above.

Output: a table in chat (document, state, detail) and a final line that is exactly
`CLARITY: PASS` or `CLARITY: FAIL (<n> incomplete)`. PASS means every mandatory document is
complete or validly N/A, not edited, not blocked, and approved where the config requires it.
Stale items are reported but don't fail by default. *(My call: an upstream tweak shouldn't fail a
project whose downstream content is still right. Set `stale_fails: true` in `config.yml` to make
it strict.)* The skill writes nothing and edits nothing. For each gap it names the producing
skill, or the approver who still has to sign.

## Tests and docs

- Installer tests: clarity skills are planned and installed alongside the compose skills (repo and
  worktree), the manifest is overwritten on reinstall, and templates are not.
- `tests/unit/test_assets.py`: register the clarity skills, either in a new `CLARITY_SKILLS` list
  or under `OTHER_SKILLS`, and make sure the existing frontmatter and `compose <command>` reference
  checks pass. The clarity skills reference no `compose` commands.
- A test that the shipped `config.yml` starter (used by `clarity-configure`) is valid YAML, and that every path it mentions exists in the manifest.
- A new test reads `manifest.yml` and checks that every `template` file exists, every
  `produced_by` names a shipped skill, every `depends_on` names a manifest path, every template's
  front matter has `status: draft` with matching `depends_on`, and no SKILL.md body contains a
  template's contents. That last check enforces "templates outside skills": no template's heading
  block appears verbatim in any SKILL.md.
- A test that each thinker file under `clarity-failure-brainstorm/thinkers/` has valid front
  matter.
- README and `docs/` get a short "Clarity skills" section: what they are, the document set, how
  N/A works, and how to run `clarity-validate`.

## Left to the builder

- The exact wording of each SKILL.md and template, adapted from clarity-agent's guides and kept
  concise.
- The section headings for the new templates (PRD, UX flows, API, data model, setup guide), using
  common industry structure.
- Whether the mapping test from template to SKILL.md uses heading blocks or another overlap
  heuristic.
- The manifest's exact YAML shape, within the fields listed above.

## Amendment 2026-11-23 — clarity is why, rules and how; compose is what

Decided with the user after the first build:

- **Split.** Clarity holds the application-level why (problem, users, goals), rules (NFR,
  constraints, standards, product principles, UX standards, API conventions, data rules) and
  how (solution, architecture, stack, ADRs, environments). compose holds each feature's what
  (`compose-specify`: user stories, `FR-###`) and that feature's how (`compose-plan`,
  `compose-tasks`), inside clarity's rules.
- **Reframed documents.** `goal/requirements.md` keeps only NFR, CON and STD items. `product/prd.md`
  becomes a product brief (goals `G-###`, scope boundaries, principles, with no features).
  `product/ux-flows.md` becomes `product/ux-standards.md` (skill `clarity-ux-standards`).
  `contracts/api.md` becomes API conventions, with `spec:` optional and only for an existing
  published contract; the `openapi.yaml` stub is removed. `data/data-model.md` becomes core
  entities and data rules. Feature-level content found in sources goes to
  `## Feature ideas` in `notes.md`.
- **compose follows clarity.** `compose feature paths --json` adds `clarity`, the declared
  status of each document, read from front matter. A shared guide,
  `templates/compose/clarity.md`, says what constitution, specify, clarify, plan, tasks and
  analyze take from which document. Complete documents are binding, drafts are hints, n/a
  documents are skipped, and only accepted ADRs bind. compose never edits `.clarity/`.
- **compose templates** moved to `templates/compose/`, next to `templates/clarity/`.
