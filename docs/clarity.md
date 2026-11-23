# Clarity skills

The clarity skills settle an application's **why**, its **rules** and its **how** before
features are built. They produce a reviewed set of documents in `.clarity/`: the problem,
stakeholders, non-functional requirements, constraints and standards, open questions,
solution, failure analysis, architecture, ADRs, product brief, UX standards, API conventions,
domain model and data rules, setup guide and summaries. Then they check that every mandatory
document is complete.

Clarity never holds the **what** of a feature: functional requirements, feature lists,
screens, endpoints or feature tables. compose defines those one feature at a time
(`/compose-specify`, then `/compose-plan`), inside clarity's rules. See
[How compose uses clarity](#how-compose-uses-clarity).

They're adapted from [microsoft/clarity-agent](https://github.com/microsoft/clarity-agent)
(MIT), which does the same with Python code. Here the same work runs through Claude Code
skills: plain Markdown instructions plus data files, with no runtime. The skills are
independent of the compose workflows: they don't call compose commands, and workflows don't
call them. compose installs them alongside its own skills, with `compose init` and in every
workflow worktree.

## Quick start

```text
/clarity                                  # start from a conversation
/clarity docs/prd.md docs/rfc.md          # or from documents you already have
/clarity https://github.com/org/repo/issues/12 mandatory: PRD, API, setup guide only
/clarity docs/ auto                       # draft everything unattended, confirm later
/clarity-validate                         # check; last line is CLARITY: PASS or FAIL
/clarity-approve product/prd.md           # an approver signs off
```

`/clarity` is the only command you need. It calls the other skills itself, in order. You can
also run any of them on its own to rework one document.

## The flow

| Step | What happens |
|---|---|
| 0. Assess | Reads `.clarity/` and works out where things stand. Resumes at the first unfinished step. |
| 1. Inputs | Reads every supplied document, folder or URL, and scans the code, **once**. Writes an inputs summary (what each source informs, and any conflicts) to `.clarity/notes.md`. |
| 2. Configure | `clarity-configure` agrees with you which documents are mandatory, which don't apply and why, any custom documents, and who approves what. The result is `.clarity/config.yml`. |
| 3. Scaffold | Creates only the documents this project needs, from the templates. |
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

When a repo has `.clarity/`, the compose skills follow it. `compose feature paths --json`
reports each document's declared status under `clarity`, and the shared guide
`.compose/templates/compose/clarity.md` says what each step reads:

| compose step | Takes from clarity |
|---|---|
| `/compose-constitution` | Derives the principles from the NFRs, constraints, standards, product principles, accepted ADRs, application-wide failure mitigations and conventions, citing each source (`[STD-002]`). Re-run it after clarity changes. |
| `/compose-specify`, `/compose-clarify` | Actors, goals and scope boundaries. The spec's `Serves:` line cites goals and rules, and it doesn't ask what clarity answers. Its own `FR-###` are per feature. |
| `/compose-plan` | Stack and components from the architecture and accepted ADRs, which aren't researched again. Contracts, data and screens follow the conventions. A **Clarity check** table sits next to the constitution check. |
| `/compose-tasks` | Tasks for failure mitigations touching the feature, tests the standards require, and setup steps. |
| `/compose-analyze` | Flags breaking a binding rule or accepted ADR as critical. |

`complete` documents and `accepted` ADRs are binding, drafts are hints, and `n/a` documents are
skipped. compose never edits `.clarity/`. A conflict is raised (or, in a headless run, recorded
as `Clarity conflict:`), and a new application-wide decision is proposed for
`/clarity-decision`.
