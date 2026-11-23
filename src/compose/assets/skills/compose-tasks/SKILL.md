---
name: compose-tasks
description: Break the current feature's plan into an ordered, dependency-aware task list (tasks.md) grouped by user story. Use after planning, before implementing.
argument-hint: "[extra guidance, e.g. include tests]"
---

# Generate the task list

Guidance from the user (may be empty):

```text
$ARGUMENTS
```

## Steps

1. Run `compose feature paths --json`. Read `plan_file` and `spec_file` (both required — if
   either is missing, say which skill to run first). Read whichever exist of
   `research_file`, `data-model.md`, `contracts/` and `quickstart.md` in the feature folder,
   and the template `tasks.md` in `templates_dir`.
   When the JSON's `clarity` is not null, also read the guide at `clarity.guide` (`.compose/templates/compose/clarity.md`),
   `.clarity/failures/failures.md`, the standards in `.clarity/goal/requirements.md` and
   `.clarity/ops/setup-guide.md`.
2. Take the user stories and their priorities from the spec, and the stack, structure and
   components from the plan.
3. Write tasks in phases:
   1. **Setup** — project structure and tooling the feature needs.
   2. **Foundations** — what every user story depends on. Nothing story-specific here.
   3. **One phase per user story**, in priority order. Each phase has its goal, its
      independent test, and the tasks to finish that story alone: tests (only when the
      spec, plan or user asks for tests, or the constitution requires them) before code,
      then models, services, interfaces and integration.
   4. **Polish** — documentation, cross-cutting improvements, running the quickstart.
4. Every task follows exactly: `- [ ] T001 [P] [US1] Description with exact file path`.
   - IDs run in order (`T001`, `T002`, …).
   - `[P]` only when the task touches different files from, and doesn't depend on, any
     unfinished task.
   - `[USn]` on user-story phase tasks only.
   With `.clarity/`, add tasks for each failure mitigation that touches this feature, for
   the tests the standards (`STD-###`) require (even when the spec didn't ask for tests),
   and for any setup or configuration the feature needs. Cite the source in the
   description, e.g. `(mitigates failures/<name>.md)`.
5. After the phases, describe the dependencies between phases and stories, what can run in
   parallel, and the MVP (usually user story 1 alone).
6. Write `tasks_file`.

## Report

The task count in total and per story, the parallel opportunities, the MVP scope, and the
suggested next step (`/compose-analyze` then `/compose-implement`).
