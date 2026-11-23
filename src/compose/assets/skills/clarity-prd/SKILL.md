---
name: clarity-prd
description: Write or revise the product requirements document (.clarity/product/prd.md) from the problem, stakeholders, requirements and solution. Every feature cites the FR/NFR IDs it delivers, and gaps in coverage are flagged. Use when the project needs a PRD, or when /clarity reaches the product stage.
argument-hint: "[focus, extra sources or notes for the PRD]"
---

# Product requirements document

Focus, extra sources or notes from the user:

```text
$ARGUMENTS
```

The PRD turns what the team already agreed (the problem, the people, the requirements, the
chosen solution) into a product: who it is for, what it lets them do, what ships first, and
how anyone will know it worked. It adds little that is new. Its value is in the joins: every
feature traces to a requirement, every goal to a success criterion.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-prd]`, then remove them.
   - The `depends_on` documents: `.clarity/goal/problem.md`, `.clarity/goal/stakeholders.md`,
     `.clarity/goal/requirements.md`, `.clarity/solution/solution.md`. Also skim
     `.clarity/goal/open-questions.md` and `.clarity/decisions/`.
   - The PRD's front matter `sources`, plus anything in the arguments. An existing PRD, pitch
     or roadmap is the best seed; reuse its wording where it is still right.
   - The repo, lightly: the README and any feature list tell you what already exists.
2. **Create the file if needed.** If `.clarity/product/prd.md` doesn't exist, copy
   `.compose/templates/clarity/product/prd.md` there, then fill its sections. Keep
   `status: draft` while working, and save a rough draft early.
3. **Draft each section from what you read.**
   - **Overview**: one paragraph; the product, its users, the problem it solves (from the
     problem statement, in product terms).
   - **Users and personas**: the primary and secondary personas, drawn from the stakeholders
     who use the product. Give each a goal and a pain point; skip stakeholders who never touch
     it.
   - **Goals and metrics**: each goal maps to a success criterion in the problem document and
     has a measure, a baseline where known, and a target. A goal with no success criterion is
     either a missing criterion (raise it) or not a goal.
   - **Scope**: in this release and not in this release. Use the problem's scope and the
     solution's phasing; name what was deliberately left out so nobody assumes it.
   - **Features**: one entry per user-visible capability, citing the FR-### and NFR-### IDs it
     delivers. Prioritise (must / should / could) when the release can't hold everything.
   - **Release criteria**: what must be true to ship: the must-have features, the NFR targets
     that gate release, and any launch, support or compliance conditions.
4. **Check traceability** and show the result to the user:
   - requirements no feature delivers (each needs a feature, a later release, or a note that
     it is non-product, such as an internal constraint);
   - features that cite no requirement (scope creep, or a missing requirement; ask which);
   - goals not tied to a success criterion.
5. **Ask only about the gaps** that remain: missing targets, unclear priorities, conflicts
   between sources and the requirements. Never re-ask what the documents already answer. Move
   quickly through what's obvious.
6. **Finish** (see below).

## Not applicable

A PRD rarely doesn't fit, but it can: a one-off internal migration, a research spike, a
library with no product owner. If the evidence points that way, propose N/A and say why (for
example, "no end users in the stakeholders; the only requirement is a data move"). Only on the
user's agreement set `status: n/a` and a `reason:`. Never decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]`, the bracketed prompts and the
  example feature line) from the sections you filled. Keep HTML comments only where they help.
- Notable product choices (dropping a persona, deferring a must-have requirement) deserve an
  ADR: record one with the `clarity-decision` skill, or tell the user one should be recorded.
- If you changed another document that is already `complete` (for example, adding a missing
  success criterion to the problem), leave its `status` and `reviewed` alone, and tell the
  user which documents you touched.
- **When `/clarity` called you**: don't mark anything complete. Return the draft and the list
  of open gaps.
- **When run directly**: show a short summary and the open gaps, and ask the user to confirm.
  On a clear yes, set `status: complete` and write `reviewed.hash` (this document's body hash)
  and `reviewed.deps` (the body hash of each `depends_on` document). A body hash is the output
  of the manifest's `hash_command` with `FILE` replaced by the quoted path; never compute it
  any other way. Then suggest `/clarity` to continue.

## Rules

- Write for people and LLMs alike: short, concrete, no filler. A feature is what a user can
  do, not how it is built.
- Don't invent requirements in the PRD. A new need goes into `.clarity/goal/requirements.md`
  with an ID first (tell the user), then the feature cites it.
- Talk about the product, not about files or front matter.
