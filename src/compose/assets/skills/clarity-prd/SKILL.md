---
name: clarity-prd
description: Write or revise the product brief (.clarity/product/prd.md) from the problem, stakeholders, requirements and solution - overview, personas, goals with G-### IDs and metrics, scope boundaries and checkable product principles. It lists no features; each feature is specified with compose and cites these goals. Use when the project needs a product brief, or when /clarity reaches the product stage.
argument-hint: "[focus, extra sources or notes for the product brief]"
---

# Product brief

Focus, extra sources or notes from the user:

```text
$ARGUMENTS
```

The product brief turns what the team already agreed (the problem, the people, the rules, the
chosen solution) into a product: who it is for, what it should achieve, where its boundaries
are, and the principles every feature follows. It lists no features: each feature is
specified on its own with compose (`compose-specify`) and cites the goals here. Its value is
in the joins: every goal traces to a success criterion, every principle is checkable.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-prd]`, then remove them.
   - The `depends_on` documents: `.clarity/goal/problem.md`, `.clarity/goal/stakeholders.md`,
     `.clarity/goal/requirements.md`, `.clarity/solution/solution.md`. Also skim
     `.clarity/goal/open-questions.md` and `.clarity/decisions/`.
   - The document's front matter `sources`, plus anything in the arguments. An existing PRD,
     pitch or roadmap is a good seed; reuse its wording where it is still right.
   - The repo, lightly: the README tells you what the product already is.
2. **Create the file if needed.** If `.clarity/product/prd.md` doesn't exist, copy
   `.compose/templates/clarity/product/prd.md` there, then fill its sections. Keep
   `status: draft` while working, and save a rough draft early.
3. **Draft each section from what you read.**
   - **Overview**: one paragraph; the product, its users, the problem it solves (from the
     problem statement, in product terms).
   - **Users and personas**: the primary and secondary personas, drawn from the stakeholders
     who use the product. Give each a goal and a pain point; skip stakeholders who never touch
     it.
   - **Goals and metrics**: each goal gets a stable `G-###` ID that feature specifications
     cite, maps to a success criterion in the problem document, and has a measure, a
     baseline where known, and a target. A goal with no success criterion is either a
     missing criterion (raise it) or not a goal. Never renumber an existing ID.
   - **Scope boundaries**: the areas features may cover, and what no feature should do. Use
     the problem's scope; name what was deliberately left out so nobody assumes it.
   - **Product principles**: the product rules every feature follows (for example "never
     lose a user's draft"). Each one must be checkable in a review; drop or sharpen any that
     isn't.
4. **Check traceability** and show the result to the user:
   - success criteria no goal covers, and goals not tied to a success criterion;
   - principles that conflict with an NFR, constraint or standard.
   If a source lists features, screens or functional behaviour, don't copy it here: note it in
   `.clarity/notes.md` under `## Feature ideas` for `compose-specify`.
5. **Ask only about the gaps** that remain: missing targets, vague principles, conflicts
   between sources and the requirements. Never re-ask what the documents already answer. Move
   quickly through what's obvious.
6. **Finish** (see below).

## Not applicable

A product brief rarely doesn't fit, but it can: a one-off internal migration, a research
spike, a library with no product owner. If the evidence points that way, propose N/A and say
why (for example, "no end users in the stakeholders; the only goal is a data move"). Only on
the user's agreement set `status: n/a` and a `reason:`. Never decide N/A alone.

## Questions

Ask a person only what a person must answer: their intent and priorities, facts only they
hold (real users, numbers, deadlines, owners), a trade-off the material leaves open that is
theirs to own, a conflict the sources can't settle, and confirmations. Anything you can work
out from the sources, the code, the other `.clarity/` documents, earlier answers or
established practice, decide yourself: write it, mark it as inferred with where it came
from, and name it in your summary so the person can correct it. `/clarity` sets this out in
**Ask a person only what needs a person**.

## Unattended

`/clarity` runs this skill unattended in its `auto`, `draft` and `apply` phases, and passes
`auto`. Work the same way whenever `COMPOSE_RUN_ID` is set or no person is present. Ask
nothing. Draft from the sources, the code and the other documents, drafts included. Fill
what you can work out yourself (see **Questions**), marked as inferred, and leave a
`[TBD — <what's missing or conflicting>]` note only for what a person must answer, in the
section it belongs to,
and propose any N/A only as a note. Never set `status: complete` or `n/a`, and never write
`reviewed` hashes. Return the draft and its list of gaps: `/clarity` turns them into
questions for a person.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]`, the bracketed prompts and the
  example goal line) from the sections you filled. Keep HTML comments only where they help.
- Notable product choices (dropping a persona, narrowing the scope) deserve an ADR: record one
  with the `clarity-decision` skill, or tell the user one should be recorded.
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

- Write for people and LLMs alike: short, concrete, no filler.
- The test of a goal: someone can collect its measure and tell whether the target was
  met. The test of a principle: a reviewer can say whether a feature breaks it. Sharpen
  or drop what fails. A line that would fit any product is filler.
- Goals and principles, not features. What a user can do is defined per feature with compose.
- Don't invent rules here. A new NFR, constraint or standard goes into
  `.clarity/goal/requirements.md` with an ID first (tell the user).
- Talk about the product, not about files or front matter.
