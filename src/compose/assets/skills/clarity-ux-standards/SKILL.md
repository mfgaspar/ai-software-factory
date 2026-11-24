---
name: clarity-ux-standards
description: Write or revise the UX standards (.clarity/product/ux-standards.md) - surfaces and navigation, interaction patterns, accessibility and localization, design system, and state conventions with a Mermaid stateDiagram-v2 - the rules every screen follows, inferred from UI code when present. Use for any product with a user interface, or when /clarity reaches the product stage.
argument-hint: "[focus, extra sources such as a design system, style guide or notes]"
---

# UX standards

Focus, extra sources or notes from the user:

```text
$ARGUMENTS
```

This document sets the interaction rules every screen and surface follows: what kinds of
surfaces exist, how users move between areas, the patterns features reuse, the accessibility
level to meet, the design system, and how states are named and shown. It describes no
individual screens or journeys: each feature's specification and plan (compose) defines
those, and follows these standards.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-ux-standards]`, then remove them.
   - The `depends_on` documents: `.clarity/product/prd.md` (personas, product principles) and
     `.clarity/goal/requirements.md` (usability, accessibility and localization NFRs,
     standards). Also `.clarity/solution/architecture.md` if it exists, for which clients
     there are.
   - The document's front matter `sources` and anything in the arguments: design system,
     style guide, brand or content guidelines, user research.
   - **UI code, when present.** Router and navigation config, shared components and the
     component library, form and validation helpers, empty, loading and error components,
     i18n setup, theme tokens, and status enums or state machines. These show the patterns
     already in use; prefer them to guesses.
2. **Create the file if needed.** If `.clarity/product/ux-standards.md` doesn't exist, copy
   `.compose/templates/clarity/product/ux-standards.md` there, then fill its sections. Keep
   `status: draft` and save a rough draft early.
3. **Draft each section.**
   - **Surfaces and navigation**: the kinds of surfaces (web, mobile, CLI, email,
     notifications) and the navigation model between areas. Name areas, not screens.
   - **Interaction patterns**: the rules features reuse: forms and validation, confirming
     destructive actions, empty, loading and error states, notifications, undo. Write each
     as a checkable rule.
   - **Accessibility and localization**: the level to meet (for example WCAG 2.2 AA),
     supported languages, date, number and currency formats. Tie them to the NFRs.
   - **Design system**: the component library, visual tokens, and content style (tone,
     terminology).
   - **State conventions**: how the states of user-facing entities are named, shown and
     changed. Add a Mermaid `stateDiagram-v2` for each core entity with a lifecycle (an
     order, a document, an account). Every state should be reachable and every non-final
     state should have a way out. If the code has a status enum, the diagram must match it.
4. **Check consistency** and show the user:
   - accessibility or usability NFRs no standard covers;
   - patterns the code uses that differ from what the document says;
   - states with no exit or no entry.
   If sources or code describe individual screens or journeys, don't copy them here: note them
   in `.clarity/notes.md` under `## Feature ideas` for `compose-specify`.
5. **Ask only about the gaps** that remain. Never re-ask what the PRD, sources or code
   already answer. Move quickly through what's obvious.
6. **Finish** (see below).

## Not applicable

Propose N/A when the project has no user interface at all: no UI code, no UI requirements,
no human-facing surface (for example, a batch job or a service called only by other
services). State the evidence. **Ask first about CLI-only tools**: a command line is still an
interface, and its prompts, output and error messages often deserve standards. Only on the
user's agreement set `status: n/a` and a `reason:`. Never decide N/A alone.

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
  template's example diagram states) from the sections you filled.
- Notable UX choices (dropping a platform, a navigation model, an accessibility level)
  deserve an ADR: record one with the `clarity-decision` skill, or tell the user.
- If you changed another document that is already `complete` (for example, a missing
  accessibility NFR), leave its `status` and `reviewed` alone and tell the user which
  documents you touched.
- **When `/clarity` called you**: don't mark anything complete. Return the draft and the list
  of open gaps.
- **When run directly**: show a short summary and the open gaps, and ask the user to confirm.
  On a clear yes, set `status: complete` and write `reviewed.hash` (this document's body hash)
  and `reviewed.deps` (the body hash of each `depends_on` document). A body hash is the output
  of the manifest's `hash_command` with `FILE` replaced by the quoted path; never compute it
  any other way. Then suggest `/clarity` to continue.

## Rules

- The test of a rule: two people building different features from it would do the same
  thing. Sharpen any rule that fails it, or ask. A rule that would fit any project is
  filler.
- Write rules, not screens. A standard applies to every feature; a screen belongs to one.
- Don't invent visual details nobody has decided.
- Diagrams must be valid Mermaid; keep each one small enough to read.
- Talk about the product, not about files or front matter.
