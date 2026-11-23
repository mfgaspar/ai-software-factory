# Using the clarity documents in compose

Read this when the repository has a `.clarity/` folder. Without one, ignore it.

**Clarity** works at the application level. It holds the **why** (problem, users, goals), the
**rules** (non-functional requirements, constraints, standards, product principles, UX
standards, API conventions, data rules) and the application's **how** (solution, architecture,
tech stack, ADRs, environments). **compose** works one feature at a time. It defines the
**what** (the spec's user stories and `FR-###`), then the feature's **how** (its plan,
contracts, data, tasks), always inside clarity's rules. compose never redefines a clarity rule.

## Which documents count

`compose feature paths --json` returns a `clarity` entry: `null` when there's no `.clarity/`
folder, or `{dir, guide, documents}`, where `documents` maps each path (relative to
`.clarity/`) to its declared `status`. Without a feature, read the same `status` field from each
document's front matter. Then:

- `complete`: **binding**. Follow it, and cite it.
- `draft`: **a hint**. Use it, but mark what you take from it as an assumption ("per draft
  architecture"). Don't treat it as settled.
- `n/a`: doesn't apply. Skip it.
- ADRs (`decisions/ADR-*.md`): only `accepted` ones are binding. `proposed` and `reconsider`
  ones are hints. Ignore `superseded` and `rejected` ones.

The status is what the document declares. It's not a full check: `/clarity-validate` gives that.

## What each step reads

| Step | Reads from `.clarity/` | Uses it to |
|---|---|---|
| constitution | `goal/requirements.md` (NFR, CON, STD), `product/prd.md` (product principles), accepted ADRs, `failures/failures.md` (mitigations that apply everywhere), `product/ux-standards.md`, `contracts/api.md`, `data/data-model.md`, `ops/setup-guide.md` | Turn rules into checkable principles. Each principle cites its source in brackets, e.g. `[STD-002]`, `[ADR-003]`. |
| specify | `goal/problem.md`, `goal/stakeholders.md`, `product/prd.md` (goals `G-###`, scope boundaries, principles), `goal/requirements.md`, the `## Feature ideas` in `notes.md` | Pick the actors and the goal the feature serves. Stay within the scope boundaries. Don't ask what these already answer. Functional requirements stay technology-agnostic. |
| plan | `solution/architecture.md`, accepted ADRs, `contracts/api.md`, `data/data-model.md`, `product/ux-standards.md`, `ops/setup-guide.md`, `goal/requirements.md`, `failures/failures.md` | Take the stack and components from the architecture and ADRs: don't research what an ADR settled. The feature's contracts follow the API conventions and extend any published `spec`. Its data extends the core entities and follows the data rules. Its screens follow the UX standards. |
| tasks | `failures/failures.md`, `goal/requirements.md` (STD), `ops/setup-guide.md` | Add a task for each failure mitigation that touches this feature, the tests the standards require, and any setup or configuration step. |
| analyze | all of the above | Check that the spec cites the goal it serves, the plan breaks no NFR, standard or accepted ADR, and the tasks cover the mitigations. |

## The constitution

In a clarity repo, the constitution is generated: `/compose-constitution from-clarity`
regenerates the whole file from the documents in the constitution row above, and compose
stamps its first line with the clarity fingerprint it came from. Hand edits are overwritten by
the next clarity run; change the clarity documents instead.

## Citing

- **Spec:** under the feature's summary, add a `Serves:` line with the goals (`G-###`) and the
  rules that apply (`NFR-###`, `CON-###`, `STD-###`). The spec's own `FR-###` are numbered per
  feature and never reuse clarity IDs.
- **Plan:** extend the constitution check with a **Clarity check**: one row for each applicable
  NFR, constraint, standard, accepted ADR and convention document, saying how the plan complies.

## Conflicts

compose never edits `.clarity/`.

- **A feature needs to break a clarity rule** (a binding document or accepted ADR): in an
  interactive session, say so and ask whether to change the feature or revisit the rule with
  `/clarity`. In a headless run (`COMPOSE_RUN_ID` is set), keep the feature within the rule
  where you can. Where you can't, record the conflict under the spec's Assumptions or the
  plan's Complexity tracking as `Clarity conflict: <rule> — <why>`.
- **The plan needs a new application-level decision** (a new datastore, framework or
  external service): make the decision for this feature in `research.md` and mark it
  `Proposed ADR`. Suggest `/clarity-decision` to record it for the whole application.
