---
name: compose-constitution
description: Create or amend the project constitution (.compose/memory/constitution.md), the principles every compose feature plan is checked against. Use when setting up a project's principles or changing them.
argument-hint: "[principles or changes to make]"
---

# Create or amend the project constitution

The user's input (may be empty):

```text
$ARGUMENTS
```

## Steps

1. The constitution lives at `.compose/memory/constitution.md` in the repository root
   (`compose feature paths --json` also reports it as `constitution_file` when a feature
   is active).
2. Load it. If it doesn't exist yet, start from `.compose/templates/constitution.md`; if
   that is missing too, create the file with the sections: core principles, constraints,
   development workflow, governance.
3. Collect values for every `[PLACEHOLDER]`:
   - from the user's input first;
   - then from the repository itself (README, docs, existing code conventions, CI);
   - for anything still unknown, choose a sensible default and list it under
     "Assumptions" in your final report. Do not leave a placeholder unresolved unless the
     user explicitly asked to keep it; mark any you keep as `TODO(<name>): reason`.
4. Write principles as rules: each is a short name, then MUST/SHOULD statements that can
   be checked in a review, then one line of rationale. Remove vague words ("robust",
   "clean") unless they are made concrete.
5. Version the document with semantic versioning:
   - MAJOR — a principle removed or redefined incompatibly;
   - MINOR — a principle or section added, or guidance materially expanded;
   - PATCH — wording and clarifications.
   Keep `Ratified` as the original adoption date; set `Last amended` to today (ISO date).
6. Check the templates in `.compose/templates/` (`plan.md`, `spec.md`, `tasks.md`) still fit
   the principles (for example, a new testing principle should be reflected in the plan's
   constitution check). Update them only where they now contradict the constitution.
7. At the top of the constitution, add or replace an HTML comment with a sync report: old →
   new version, principles added/changed/removed, templates updated, open TODOs.
8. Save the file.

## Report

Tell the user the new version and why it was bumped, what changed, which templates were
touched, and any assumptions or TODOs. Suggest a commit message such as
`docs: amend constitution to vX.Y.Z (<summary>)`.
