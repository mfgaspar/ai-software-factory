---
name: compose-checklist
description: Generate a requirements-quality checklist for the current feature (checklists/<topic>.md), testing whether the spec is complete, clear and consistent for a given concern such as security or UX.
argument-hint: "<topic, e.g. security, ux, api, release>"
---

# Generate a requirements checklist

The checklist topic and any focus:

```text
$ARGUMENTS
```

A checklist is a **unit test for the requirements**: each item asks whether the spec says
something completely, clearly and consistently. It never tests the implementation.

- Good: "Are rate limits specified for every public endpoint? [Completeness, Spec §FR-012]"
- Good: "Is 'fast' quantified with a measurable threshold? [Clarity, Spec §SC-002]"
- Wrong: "Verify the endpoint returns 429" — that tests code.

## Steps

1. Run `compose feature paths --json`. Read `spec_file` (required), and `plan_file` and
   `tasks_file` if they exist.
2. Decide the topic from the input (default: general requirements quality). In an
   interactive session, if the topic is unclear, ask up to three short questions (scope,
   depth, audience); otherwise choose sensible defaults and say which.
3. Write items grouped by quality dimension: completeness, clarity, consistency,
   measurability, scenario coverage (primary, alternate, error, recovery), edge cases,
   non-functional requirements, dependencies and assumptions.
4. Each item is a question, numbered `CHK001` onward, ending with its dimension and a
   reference to the spec section — or `[Gap]` when the spec says nothing. At least 80% of
   items must reference the spec or mark a gap. Merge near-duplicates; keep it under
   about 40 items.
5. Use the template `checklist.md` in `templates_dir`. Write to
   `checklists_dir/<topic>.md` (e.g. `security.md`). If that file exists, append new items
   continuing the numbering instead of replacing it.

## Report

The checklist path, the item count, the focus areas, and any spec gaps that stood out.
