---
name: compose-implement
description: Implement the current feature by working through tasks.md phase by phase, checking off each task as it is done. Use after tasks (and ideally analyze).
argument-hint: "[scope, e.g. a phase or user story]"
---

# Implement the feature

Optional scope from the user (e.g. "only user story 1"):

```text
$ARGUMENTS
```

## Steps

1. Run `compose feature paths --json`. Read `tasks_file` and `plan_file` (both required —
   name the missing skill and stop if not). Read `data-model.md`, `contracts/`,
   `research_file` and `quickstart.md` in the feature folder when they exist, and the
   constitution at `constitution_file`.
2. **Checklists.** If `checklists_dir` has checklists, count unchecked items per file. If
   any are incomplete: in an interactive session, show the table and ask whether to
   continue; in a headless run (e.g. `COMPOSE_RUN_ID` is set), continue and mention it in
   the report.
3. **Project setup.** Make sure ignore files fit the stack in the plan (e.g. `.gitignore`
   entries for build output and dependencies). Add only what is missing.
4. Work through the tasks in phase order, within the requested scope:
   - respect dependencies; tasks marked `[P]` may be done in any order;
   - when tests are part of the tasks, write them first and see them fail;
   - follow the plan's structure and decisions, and the constitution;
   - after finishing each task, mark it `- [x]` in `tasks_file` immediately.
5. After each phase, run the project's tests and checks if it has them, and fix failures
   before moving on. If a task cannot be done, stop that line of work, leave it unchecked,
   and explain why — don't skip silently.
6. At the end, confirm every task in scope is checked, the tests pass, and the feature
   matches the spec's acceptance scenarios. Run the steps in `quickstart.md` if practical.

Do not commit, push or open pull requests unless the user asks; leave the changes in the
working tree.

## Report

Tasks completed (and any left, with reasons), tests run and their result, files changed,
and anything the user should check by hand.
