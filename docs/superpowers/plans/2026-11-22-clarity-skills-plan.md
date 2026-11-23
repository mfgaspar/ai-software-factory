# Clarity skills — Implementation Plan

Date: 2026-11-22
Design: [../specs/2026-11-22-clarity-skills-design.md](../specs/2026-11-22-clarity-skills-design.md)
Source being ported: [microsoft/clarity-agent](https://github.com/microsoft/clarity-agent) (MIT),
`processes/`, `thinkers/`, `src/clarity_agent/protocol/` (`initialize.py` templates,
`packet_status.py` graph/markers/routing, `thinker_registry.py` prerequisites).

## How to use this plan

Milestones are ordered by dependency. Each task lists the files it touches, what to build, the
tests that prove it, and when it's done. Every milestone ends green (`uv run pytest`,
`uv run ruff check`) and is committed on its own (`C<n>: …`).

**What can be tested deterministically.** Skills are prose, so unit tests check *structure*:
front matter, that skills reference the manifest and templates instead of inlining them, that
the manifest is internally consistent, that templates parse, and that the body-hash command
behaves. *Behaviour* (does `/clarity` actually run the flow, does the validator say the right
thing) is checked by live tests (`@pytest.mark.live`, skipped by default, cost money), which call
`claude -p` directly on fixture projects. They don't go through compose's runner, because clarity
is independent of compose workflows.

## Layout (target)

```text
src/compose/assets/
  skills/
    clarity/SKILL.md                       # orchestrator
    clarity-configure/SKILL.md
    clarity-validate/SKILL.md
    clarity-approve/SKILL.md
    clarity-problem/            SKILL.md, LICENSE.txt
    clarity-discovery-prototype/SKILL.md, LICENSE.txt
    clarity-discovery-research/ SKILL.md, LICENSE.txt
    clarity-solution/           SKILL.md, LICENSE.txt
    clarity-architecture/       SKILL.md, LICENSE.txt
    clarity-decision/           SKILL.md, LICENSE.txt
    clarity-message/            SKILL.md, LICENSE.txt
    clarity-failure-brainstorm/ SKILL.md, LICENSE.txt, thinkers/*.md (6)
    clarity-failure-analysis/   SKILL.md, LICENSE.txt
    clarity-failure-management/ SKILL.md, LICENSE.txt
    clarity-prd/ clarity-ux-flows/ clarity-api-contracts/ clarity-data-model/ clarity-setup-guide/
  templates/clarity/
    manifest.yml                           # installed with overwrite
    config.yml                             # starter project config (clarity-configure copies it)
    summary.md notes.md observations.md
    goal/{problem,stakeholders,requirements,open-questions,resolved-questions}.md
    product/{prd,ux-flows}.md
    solution/{solution,architecture,solution-summary}.md
    contracts/{api.md,openapi.yaml}
    data/data-model.md
    failures/failures.md  failures/brainstorm/thinker.md
    decisions/{index.md,adr.md}
    ops/setup-guide.md
tests/unit/test_clarity_assets.py          # new
tests/live/test_clarity_live.py            # new
tests/fixtures/clarity/                    # fixture projects for live tests
```

---

## C0 — Installer and test scaffolding

**T0.1 Install clarity skills.** `src/compose/engines/claude/install.py` `_planned()`: include
skill folders starting with `compose` **or** `clarity`, overwrite on. In the templates loop, mark
`clarity/manifest.yml` overwrite=True. All other templates stay add-only. Update the docstring.
Tests (`tests/unit/test_claude_install.py`): the fixture assets gain a `clarity-validate` skill
and a `templates/clarity/manifest.yml` plus `templates/clarity/goal/problem.md`. Assert that both
skill families install into a repo and into a run worktree. Assert that a changed `manifest.yml`
is rewritten on reinstall while a locally edited `goal/problem.md` template is not. Assert that
the git-exclude handling covers the clarity skill paths, as it already does for compose skills.
Done: the existing install tests plus the new ones are green.

**T0.2 Asset test scaffolding.** `tests/unit/test_assets.py`:
- Add `CLARITY_SKILLS` (all 19 names) to `test_all_skills_are_shipped`. While milestones are in
  flight, keep a `CLARITY_PENDING` set that the test subtracts, and empty it in C7.
- `test_templates`: list only top-level *files* (skip the `clarity/` directory) so the existing
  assertion still holds.
- Make sure `test_skill_frontmatter` applies to clarity skills too: `name` matches the folder, a
  description of 40–400 characters, and `$ARGUMENTS` in the body.

New `tests/unit/test_clarity_assets.py` (it grows through C1–C7), with a helper
`load_manifest()` and `body_hash(path)` that runs the manifest's `hash_command` via `subprocess`.
Done: green with no clarity skills yet (everything pending).

---

## C1 — Manifest, starter config, templates

**T1.1 `manifest.yml`.** Fields per the design: `placeholder_markers` (clarity-agent's
`TEMPLATE_MARKERS` from `packet_status.py`, plus `[TBD]`), `hash_command`, `walk_order`, `stages`,
`never_na` (problem, requirements), and `documents:` with `path`, `template`, `mandatory`,
`allow_na`, `required_sections`, `depends_on`, `produced_by`. All 15 mandatory documents follow the
design table. Notes, observations and resolved-questions are listed as `mandatory: false` with no
validation. Stages in order: goal → solution → failures → architecture+ADRs → product →
contracts/data/setup → summaries.

**T1.2 Templates.** One per manifest document, each starting with the design's front matter
(`status: draft`, `reason: ""`, `depends_on` equal to the manifest's, empty `reviewed`, `sources`,
`approvals`). Bodies:
- Ported from `initialize.py` `TEMPLATES`: summary, problem (with Why This Matters, Success
  Criteria), stakeholders, open-questions, resolved-questions, solution, architecture,
  solution-summary, failures, notes, observations.
- Extended: requirements gets `## Functional requirements` (`FR-001 …`, each with *Stakeholder*
  and *Acceptance*) and `## Non-functional requirements` (`NFR-001 …`, with category and measure).
  Architecture becomes a SAD outline: Context, Components, Data flows, Deployment, Cross-cutting
  concerns, and a Threat model with a fenced `mermaid` placeholder.
- New: prd (Overview, Users and personas, Goals and metrics, Scope / out of scope, Features
  mapped to FR IDs, Release criteria). ux-flows (Screens, User journeys, State diagrams with a
  `stateDiagram-v2` block). contracts/api.md (front matter `spec: contracts/openapi.yaml`,
  Overview, Auth, Errors, Versioning) plus a minimal `openapi.yaml` stub (`openapi: 3.1.0`, a
  placeholder `info.title: "[TBD]"`). data-model (Entities, Tables, `erDiagram` block,
  Migrations, Retention). setup-guide (Prerequisites, Environments, Local setup, Configuration,
  Secrets handling, Troubleshooting). decisions/index.md (ADR table). decisions/adr.md (ADR-NNN
  template with Context, Options, Decision, Consequences; ADR front matter `status: proposed`).
  failures/brainstorm/thinker.md (raw-output format for thinkers).
- open-questions template documents the per-question fields: `status`, `strategy`, `blocking`.

**T1.3 Starter `config.yml`.** Every key from the design (`mandatory.add/remove`,
`not_applicable`, `documents`, `approvals`, `stale_fails: false`), all commented out with
one-line explanations.

Tests (`test_clarity_assets.py`):
- The manifest loads, every `template` exists, every `depends_on` and stage entry names a manifest
  path, every stage path appears exactly once, `walk_order` is a permutation of the validated
  documents, and `never_na` documents have `allow_na: false`.
- Every template's front matter parses, has `status: draft`, and has `depends_on` equal to the
  manifest's.
- Every template contains at least one placeholder marker. Every `required_sections` heading
  appears in its template.
- `openapi.yaml` and the starter `config.yml` are valid YAML, and every path the config's
  commented example names exists in the manifest.
- **Body hash:** for a template, changing only the front matter leaves `body_hash` unchanged,
  changing one body character changes it, and a `---` horizontal rule inside the body is hashed
  (not treated as front matter). This runs the real `hash_command`.
- `produced_by` names are in `CLARITY_SKILLS`. Don't check that the skill exists yet; C7 does.

Done: green. All templates read sensibly on their own.

---

## C2 — `clarity-validate`

**T2.1 SKILL.md.** Steps, in order:
1. Load the effective manifest. That is `.compose/templates/clarity/manifest.yml`, plus
   `.clarity/config.yml` with the design's merge rules: add/remove, never-removable documents,
   `not_applicable`, custom `documents`, `approvals` globs, and `stale_fails`. Report config errors
   as FAIL.
2. For each validated document in walk order, compute its state using exactly the design's checks
   (missing, n/a / invalid-n/a, draft, edited, stale, blocked, unapproved, complete). Use the
   manifest's `hash_command` for every hash.
3. Apply the special rules: decisions (an index plus at least one ADR, or N/A; ADRs that are
   `proposed` or `reconsider` count as blocked), open-questions (unresolved with `blocking: true`
   counts as blocked), and contracts (the `spec:` file exists and parses).
4. Output a table (document, state, detail), a "decisions to recheck" section, and the next skill
   or approver for each gap. Then the last line, exactly `CLARITY: PASS` or
   `CLARITY: FAIL (<n> incomplete)`.
5. It writes nothing. `$ARGUMENTS` may restrict the check to named documents.

The skill describes the state rules in its own prose and reads markers, sections and paths from
the manifest. It never copies template text.

Tests: front matter. The body references `manifest.yml`, `config.yml`, `hash_command`, and both
literal result lines. Each state name appears in the body. The body contains no template heading
blocks (the generic "no template inlined" check, which is written here and applied to every
clarity skill from now on).

Done: green. Running `/clarity-validate` by hand on a scratch project with one complete and one
draft document gives the expected table.

---

## C3 — `clarity-configure` and `clarity-approve`

**T3.1 `clarity-configure`.**
- Inputs: the shipped manifest, the existing `config.yml`, and the inputs summary from the
  orchestrator (or a quick scan when it's run alone).
- It proposes a config, with N/A candidates and the evidence for each, then takes the user's
  corrections. It applies short-cuts like `mandatory: PRD, API only`.
- It writes `.clarity/config.yml` starting from the starter template and shows it. It moves on
  once the user confirms.
- On a re-run: "keep the same setup?", unless the shipped manifest has documents the config
  doesn't mention.
- In `auto` mode: write the proposal with inferred N/As left commented out and no approvers.
- It validates its own output against the design's config rules before saving.

**T3.2 `clarity-approve`.**
- Arguments: a document path or glob, or nothing to mean every document pending approval.
- For each document: it refuses if the document is draft, stale or edited. It asks who is
  approving and checks that the name is on that document's list. It requires an explicit
  "I approve <document>" from that person. Then it appends `{by, at, hash}` using `hash_command`.
- It never approves on behalf of someone who isn't present, and it never runs in `auto` mode.

Tests: front matter. Both skills reference `config.yml` and `hash_command`. Approve mentions the
refusal cases (draft, stale, edited) and that `auto` never approves.

Done: green.

---

## C4 — Ported process skills

For each skill, adapt the matching clarity-agent guide. Keep its conversational method, steps,
pitfalls and success indicators. Replace its tool calls with plain file reads and writes, and
replace `packet_status --record` with "on the user's confirmation, set `status: complete` and
write `reviewed.hash` / `reviewed.deps` with `hash_command`". Each skill also carries the design's
shared behaviours: read `notes.md`, read `sources` and other documents first, ask only about gaps,
offer N/A with a reason, and hand back to `clarity`. Each folder gets `LICENSE.txt` (MIT,
Microsoft) and a one-line attribution in SKILL.md that names `LICENSE.txt`.

| Task | Skill | Source guide | Writes |
|---|---|---|---|
| T4.1 | clarity-problem | problem-clarification.md (incl. discovery check) | goal/* (FR/NFR format, question fields) |
| T4.2 | clarity-discovery-prototype | discovery-prototype.md | `.clarity/prototypes/<q>/`, resolved-questions |
| T4.3 | clarity-discovery-research | discovery-research.md | resolved-questions, open-questions |
| T4.4 | clarity-solution | solution-brainstorming.md | solution, solution-summary |
| T4.5 | clarity-architecture | architecture-design.md + snippet's threat-model rule | SAD sections, mermaid threat model, solution-summary |
| T4.6 | clarity-decision | decision-guidance.md | ADR-NNN from `decisions/adr.md`, index.md |
| T4.7 | clarity-message | message-clarification.md | summary.md (+ messaging.md) |

Tests: front matter. `LICENSE.txt` contains "MIT License" and "Microsoft Corporation", and SKILL.md
mentions it (mirrors `test_adopted_skill_keeps_its_license`). Each skill names its template paths
under `.compose/templates/clarity/` and inlines none of them. Prototype names
`.clarity/prototypes/`.

Done: green. Each skill reads like a self-contained guide.

---

## C5 — Failure trio and thinkers

**T5.1 Thinkers.** Copy the six `thinkers/*.md` into `clarity-failure-brainstorm/thinkers/` with
their front matter kept (`name`, `prerequisites.required/recommended`, `modes`, `description`).
Rewrite `prerequisites` paths for the new layout and replace any tool calls with "write to
`failures/brainstorm/<name>.md` using the thinker template".

**T5.2 `clarity-failure-brainstorm`.** Read context. Select thinkers whose required
prerequisites are complete; codebase-scanner only when the project has code. Dispatch one
subagent per thinker in parallel where subagents are available, otherwise run them in sequence.
Each subagent writes only its own file. Then invite human contributions into
`brainstorm/human-<n>.md`. Ported from failure-brainstorming.md.

**T5.3 `clarity-failure-analysis`.** Group the raw files into failure modes with chains and
intervention points, using failure-analysis.md and failure-reasoning-guidelines.md. Record the
files it absorbed in `observations.md` so re-runs only process new files.

**T5.4 `clarity-failure-management`.** Write management plans into `failures.md`, from
failure-management.md. When plans change the solution or architecture, edit those documents.
That edit puts them in the *edited* state, and the orchestrator's recheck step picks them up.
Record notable choices with `clarity-decision`.

Tests: each thinker's front matter parses, has `name` matching its file and a `prerequisites`
block, and its paths exist in the manifest. The brainstorm skill names all six thinkers and the
`brainstorm/` path. License checks as in C4.

Done: green.

---

## C6 — New software-document skills

`clarity-prd`, `clarity-ux-flows`, `clarity-api-contracts`, `clarity-data-model`,
`clarity-setup-guide`. Each one:
- Reads its upstream documents and `sources`, plus the repo's code where it's relevant: routes and
  handlers for the API, models and migrations for data, the build and env files for setup.
- Drafts from its template and asks only about gaps, then confirms.
- Offers N/A with the evidence (for example "no UI code or UI requirements found").
- Keeps traceability: PRD features and API operations cite FR/NFR IDs, and data entities cite the
  requirements that need them.
- API contracts: reuse an existing OpenAPI or GraphQL file as `spec:` (reference it in place, or
  copy it if it's outside the repo), or write `contracts/openapi.yaml` from the stub.
- Data model: a schema table per entity plus a mermaid `erDiagram`. Seed it from SQL or ORM
  sources when they exist.
- Setup guide: never write secret values, only where they come from.

Tests: front matter. Each skill names its template and output path. API names the `spec:` field,
data names `erDiagram`, UX names `stateDiagram`, and setup contains the no-secrets rule.

Done: green.

---

## C7 — The orchestrator `clarity`

**T7.1 SKILL.md** implementing the design's steps 0–8, ported in spirit from clarity-agent.md
(conversation first, no machinery talk, save as you go):
- Arguments: supplied documents, paths or URLs; an optional `auto`; optional config short-cuts,
  which go to configure.
- Step 1 (inputs) uses compose's URL-fetch safety rules, copied in prose. Build an inputs summary
  that maps each source to the documents it informs. Reuse it in steps 2 and 4.
- Steps 2–3: invoke `clarity-configure`, then scaffold only the effective documents. N/A
  documents get a stub with `status: n/a` and the reason.
- Step 4: draft everything the inputs inform, with `sources:` filled in.
- Step 5: stages in manifest order. Inside a stage, invoke each `produced_by` skill for missing,
  draft or blocked documents. Blocking questions route by strategy before solution work starts.
  Then do one batch confirmation per stage, which writes `complete` plus the `reviewed` hashes.
  The orchestrator itself drafts custom documents that have `produced_by: clarity`.
- Step 6: a single recheck pass over stale and edited documents.
- Step 7: invoke `clarity-approve` for pending documents. Skip this in `auto`.
- Step 8: invoke `clarity-validate`.
- Resume, re-run and loop rules from the design: resume at the first unfinished stage, never
  silently overwrite complete documents, a one-line "done: X, next: Y" after each stage, and a
  stage that fails twice gets reported as "needs the user".
- `auto` never sets `complete` or `n/a` and never approves.

**T7.2 Finalize asset tests.** Empty `CLARITY_PENDING`. Every manifest `produced_by` now names a
shipped skill, and the orchestrator names every other clarity skill, every step, and `auto`.

Done: `uv run pytest` green with all 19 skills shipped.

---

## C8 — Live end-to-end

`tests/live/test_clarity_live.py`, marked live. It skips when `check()` reports problems, like the
existing live tests. Each test copies a fixture into a tmp git repo, installs the assets with
`install()`, and runs `claude -p "<prompt>" --output-format json` with a small model and a cost cap.

| Test | Fixture | Prompt | Assert |
|---|---|---|---|
| validate: complete | `fixtures/clarity/complete/` (hand-written, hashes precomputed by the test using `body_hash`) | `/clarity-validate` | last line `CLARITY: PASS` |
| validate: edited | same, one body edited after hashing | `/clarity-validate` | `FAIL`, names the edited document |
| validate: stale is a warning | same, one dependency edited | `/clarity-validate` | `PASS`, names the stale document; with `stale_fails: true` it gives `FAIL` |
| validate: N/A and approvals | complete + `config.yml` with an N/A and a required approver | `/clarity-validate` | `FAIL`, names the missing approver; after the approval entry is written with the right hash, `PASS` |
| orchestrator auto | `fixtures/clarity/sources/` (a short PRD + a small OpenAPI file) | `/clarity docs/prd.md api/openapi.yaml auto` | `.clarity/config.yml` exists; prd/problem/requirements drafted with `sources:`; `contracts/api.md` `spec:` points at the given OpenAPI; no document is `complete`; output ends with `CLARITY: FAIL` |

The fixtures' hashes are computed by the test at setup time, so they can't drift from the
template. The interactive flow (configure conversation, stage confirmations, approvals in person)
can't be scripted with `-p`. It's checked once by hand, and the walkthrough is recorded in the PR
description.

Done: `uv run pytest -m live tests/live/test_clarity_live.py` passes.

---

## C9 — Docs

- `README.md`: a short "Clarity skills" section. What they're for, `/clarity` as the one entry
  point, the document set, N/A, `config.yml`, approvals, `/clarity-validate` with the PASS/FAIL
  line, and the clarity-agent attribution.
- `docs/clarity.md` (new): the full flow (steps 0–8), the front-matter reference, the config
  reference, the validator states, and the CI usage example. Link to it from the README.
  `tests/unit/test_release_docs.py` checks the relative links.
- Make sure `test_no_references_to_the_old_project_anywhere` still passes. Ported text must not
  mention it.

Done: green. The docs match the shipped behaviour.

---

## Suggested order and parallelism

C0 → C1 → C2 come first, in sequence: C2's rules are the contract every later skill follows. After
that, C3, C4, C5 and C6 touch separate skill folders and can be built in parallel, with
`test_clarity_assets.py` as the only shared file (add tests at the end of the file). C7 needs
C2–C6. C8 needs C7. C9 can start after C7.

## Definition of done

- 19 `clarity-*` skills and `templates/clarity/` ship and install alongside the compose skills
  (repo and worktree), with the manifest refreshed on upgrade.
- No template content inside any SKILL.md (enforced by test).
- `/clarity` alone takes a project from nothing (or from supplied documents) to a validated
  `.clarity/` folder, resumably, with approvals last.
- `/clarity-validate` gives the right PASS/FAIL on the live fixtures.
- `uv run pytest`, `uv run ruff check` and the clarity live suite are green, and the docs are
  updated.
