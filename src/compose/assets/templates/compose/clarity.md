# Using the project memory in compose

Read this when the constitution (`.compose/memory/constitution.md`) is a **memory index**:
its first line is `<!-- memory-index: … -->`. When it isn't, the constitution is a plain
list of principles: follow it as written and ignore this guide.

The project's foundation is written and approved with **clarity**, at the application
level. It holds the **why** (problem, users, goals), the **rules** (non-functional
requirements, constraints, standards, product principles, UX standards, API conventions,
data rules) and the application's **how** (solution, architecture, tech stack, ADRs,
environments). compose publishes it to `.compose/memory/`, one file per document, with the
approved text unchanged. **compose** works one feature at a time. It defines the **what**
(the spec's user stories and `FR-###`), then the feature's **how** (its plan, contracts,
data, tasks), always inside the foundation's rules. A feature never redefines one.

`.compose/memory/` is the only place to read the foundation. Don't open `.clarity/`: that is
where it is drafted, and it may hold work nobody has confirmed.

## Which files to open

The index has one row per file: what it **holds**, when to **read** it, and its
**standing**. Paths in the table are relative to `.compose/memory/`.

1. Read the index at every step.
2. Open every file whose Read column says **always at** and names your step.
3. Open any other file whose **when** is true of this feature. When you can't tell, open it.
4. When a spec, plan or task cites an ID (`NFR-004`, `ADR-002`), the Holds column says
   which file defines it. Open that file before you rely on the ID.

Open nothing else: the point of the index is to load only what the step needs.

Each skill reads as one step:

| Skill | Step |
|---|---|
| `compose-specify` | specify |
| `compose-clarify` | clarify |
| `compose-plan` | plan |
| `compose-tasks` | tasks |
| `compose-implement`, `compose-converge`, `compose-bug-fix` | implement |
| `compose-analyze` | analyze |

## Standing

- `binding`: confirmed. Follow it, and cite it.
- `draft`: **a hint**. Use it, but mark what you take from it as an assumption ("per draft
  architecture"). Don't treat it as settled.
- `ideas`: suggestions for features. Not rules.

Only accepted ADRs are published, so every ADR in memory is binding. A document listed
under **Not applicable** doesn't exist for this project: don't look for it.

## What each step uses it for

| Step | Uses the files it opens to |
|---|---|
| specify, clarify | Pick the actors and the goal (`G-###`) the feature serves. Stay within the scope boundaries. Don't ask what these files already answer. Functional requirements stay technology-agnostic. Start from an item in `feature-ideas.md` when the description names one. |
| plan | Take the stack and components from the architecture and ADRs: don't research what an ADR settled. The feature's contracts follow the API conventions and extend any published spec the index names. Its data extends the core entities and follows the data rules. Its screens follow the UX standards. |
| tasks | Add a task for each failure mitigation that touches this feature, the tests the standards require, and any setup or configuration step. |
| implement | Write code that keeps the binding rules: non-functional requirements, constraints, standards and accepted ADRs. |
| analyze | Check that the spec cites the goal it serves, the plan breaks no NFR, standard or accepted ADR, and the tasks cover the mitigations. Analyze opens every file. |

## The binding rules

There are no principles written out in the index. Wherever a skill checks "the
constitution's principles", check the **binding rules** instead: every `NFR-###`,
`CON-###` and `STD-###`, every product principle, and every accepted ADR, in the binding
files your step opens. A MUST in one of them is a constitution MUST.

## Citing

- **Spec:** under the feature's summary, add a `Serves:` line with the goals (`G-###`) and the
  rules that apply (`NFR-###`, `CON-###`, `STD-###`). The spec's own `FR-###` are numbered per
  feature and never reuse the foundation's IDs.
- **Plan:** extend the constitution check with a **Clarity check**: one row for each applicable
  NFR, constraint, standard, accepted ADR and convention file, saying how the plan complies.

## Conflicts

compose never edits `.compose/memory/` or `.clarity/`. The memory files are generated:
a change belongs in the clarity documents, made with `/clarity`, and compose publishes
them again.

- **A feature needs to break a binding rule** (a binding file or accepted ADR): in an
  interactive session, say so and ask whether to change the feature or revisit the rule with
  `/clarity`. In a headless run (`COMPOSE_RUN_ID` is set), keep the feature within the rule
  where you can. Where you can't, record the conflict under the spec's Assumptions or the
  plan's Complexity tracking as `Clarity conflict: <rule> — <why>`.
- **The plan needs a new application-level decision** (a new datastore, framework or
  external service): make the decision for this feature in `research.md` and mark it
  `Proposed ADR`. Suggest `/clarity-decision` to record it for the whole application.
