---
name: compose-analyze
description: Read-only consistency check of the current feature's spec, plan and tasks against each other and the constitution; reports gaps, contradictions and coverage. Use before implementing.
argument-hint: "[areas to focus on]"
---

# Analyze consistency (read-only)

Optional focus:

```text
$ARGUMENTS
```

**Do not modify any file.** This skill only reports.

## Steps

1. Run `compose feature paths --json`. Read `spec_file`, `plan_file` and `tasks_file` (all
   three required — if one is missing, name the skill that creates it and stop) and the
   constitution at `constitution_file` if it exists. When the JSON's `clarity` is not
   null, also read the guide at `clarity.guide` and the clarity documents it lists.
2. Build an inventory: requirements (`FR-…`) and success criteria from the spec, user
   stories with their acceptance scenarios, the plan's decisions and structure, and every
   task with the requirement or story it serves.
3. Look for:
   - **Duplication** — requirements that say the same thing.
   - **Ambiguity** — vague adjectives without measures ("fast", "secure"), leftover
     placeholders and `[NEEDS CLARIFICATION]` markers.
   - **Underspecification** — requirements with no measurable outcome, stories without
     acceptance scenarios, tasks referring to things defined nowhere.
   - **Constitution conflicts** — anything violating a MUST principle. These are always
     critical.
   - **Clarity conflicts** (only with `.clarity/`): the plan breaks a binding NFR,
     constraint, standard or accepted ADR, or drifts from the API, data or UX conventions.
     These are critical, like constitution conflicts. Also flag a spec with no `Serves`
     goal, and failure mitigations that touch the feature but have no task.
   - **Coverage gaps** — requirements with no task, tasks tied to no requirement or story,
     non-functional requirements with no task.
   - **Inconsistency** — terminology drift, entities in the plan missing from the spec (or
     the reverse), task order contradicting dependencies, conflicting technology choices.
4. Rate each finding: CRITICAL (constitution violation, or a core requirement with no
   coverage), HIGH (conflict or ambiguity that would change what is built), MEDIUM, LOW.
   Report at most 50 findings, most severe first.

## Report

A findings table (ID, category, severity, location, summary, recommendation); a coverage
table (requirement → tasks); constitution issues; and metrics (requirements, tasks,
coverage percentage, critical count). End with next actions: fix CRITICAL issues before
`/compose-implement`, and say which skill to rerun for each. Offer to suggest concrete edits,
but don't apply them.
