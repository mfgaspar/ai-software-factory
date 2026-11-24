---
name: compose-plan
description: Produce the technical implementation plan for the current feature (plan.md, research.md, data-model.md, contracts/, quickstart.md), checked against the project constitution.
argument-hint: "[technical direction, e.g. stack or constraints]"
---

# Plan the implementation

Technical direction from the user (may be empty):

```text
$ARGUMENTS
```

## Steps

1. Run `compose feature paths --json`. Read `spec_file` (required — if it is missing, stop
   and tell the user to run `/compose-specify`), the constitution at `constitution_file`
   if it exists, and the plan template `plan.md` in `templates_dir`.
   When the constitution is a memory index (its first line is `<!-- memory-index: … -->`),
   also read the guide at `.compose/templates/compose/clarity.md` and open the files the
   index lists for the `plan` step, and those whose "when" fits this feature. These are the
   application's architecture, stack, accepted ADRs and conventions.
2. If the spec still has `[NEEDS CLARIFICATION]` markers on things that change the design,
   say so; in an interactive session suggest `/compose-clarify` first, otherwise proceed and
   state your assumptions.
3. Write `plan_file` from the template:
   - **Technical context**: language, dependencies, storage, testing, platform, project
     type, performance goals, constraints, scale. Follow the user's direction and the
     repository's existing choices; mark real unknowns `NEEDS CLARIFICATION`.
   - **Constitution check**: one row per principle with how the plan complies (with a
     memory index, the Clarity check below takes its place). A
     violation must be justified in "Complexity tracking", or the plan changed to remove
     it. Do not continue past an unjustified violation.
   - **Clarity check** (only with a memory index): one row per applicable NFR, constraint,
     standard, accepted ADR and convention file, from the binding files you opened. A
     violation is treated like a constitution violation. Technical context comes from the
     architecture and accepted ADRs. Don't pick a different stack. A conflict is handled
     as the guide says.
4. **Phase 0 — research.** For every unknown and every key technology choice, decide and
   record in `research_file`: the decision, the rationale, the alternatives considered.
   Don't re-research what an accepted ADR settled: cite it. A new application-level
   decision is marked `Proposed ADR`, and the report suggests `/clarity-decision`.
   Look at the existing code to stay consistent with it. Resolve every
   `NEEDS CLARIFICATION` in the technical context.
5. **Phase 1 — design**, in the feature folder:
   - `data-model.md`: entities, fields, relationships, validation rules, state changes;
   - `contracts/`: the interfaces the feature exposes (API endpoints, CLI commands, events,
     public functions), one file per interface, in the format that fits the project;
   - with a memory index: the data model extends the core entities in the memory file
     `data/data-model.md` and follows its data rules. Contracts follow the conventions in
     `contracts/api.md` and extend the published spec its index row names, if any, without
     breaking it. Screens and flows follow `product/ux-standards.md`. Skip a file the
     index lists as not applicable;
   - `quickstart.md`: how to run and check the feature end to end.
   Skip a file only when it clearly doesn't apply, and say why in the plan.
6. Fill in the project structure with the real directories, and re-run the constitution
   check against the design.
7. Save all files. Use paths relative to the repository root inside documents.

## Report

The plan path and every file created, the key decisions, the constitution check result,
and the suggested next step (`/compose-tasks`).
