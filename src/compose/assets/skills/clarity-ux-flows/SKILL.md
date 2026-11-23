---
name: clarity-ux-flows
description: Write or revise the UI/UX and state flows document (.clarity/product/ux-flows.md) - screens, user journeys with error and empty states, and a Mermaid stateDiagram-v2 per key entity or screen - inferring from UI code when present. Use for any product with a user interface, or when /clarity reaches the product stage.
argument-hint: "[focus, extra sources such as wireframes or notes]"
---

# UI/UX and state flows

Focus, extra sources or notes from the user:

```text
$ARGUMENTS
```

This document shows how people move through the product: the surfaces they see, the journeys
they take from entry to outcome, and the states the important things pass through. It is the
bridge between the PRD's features and what gets built, and the place where missing error,
empty and loading cases surface before they become bugs.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-ux-flows]`, then remove them.
   - The `depends_on` documents: `.clarity/product/prd.md` (personas and features) and
     `.clarity/goal/requirements.md` (FR IDs, usability and accessibility NFRs). Also
     `.clarity/solution/architecture.md` if it exists, for which clients there are.
   - The document's front matter `sources` and anything in the arguments: wireframes, design
     files, screenshots, user research.
   - **UI code, when present.** Routes and router config, page and screen components,
     navigation menus, forms and their validation, and status enums or state machines in
     the code. These give you the real screen list and the real states; prefer them to
     guesses.
2. **Create the file if needed.** If `.clarity/product/ux-flows.md` doesn't exist, copy
   `.compose/templates/clarity/product/ux-flows.md` there, then fill its sections. Keep
   `status: draft` and save a rough draft early.
3. **Draft each section.**
   - **Screens**: each screen or surface (page, dialog, email, notification, CLI command),
     its purpose, the persona who uses it, and the main actions. Note the empty, loading and
     error state of each one.
   - **User journeys**: one per main PRD feature or persona goal, step by step from entry to
     outcome, naming the screens passed through. Include the unhappy paths: invalid input,
     no permission, nothing found, network or service failure, and how the user recovers.
     Cite the FR IDs each journey serves.
   - **State flows**: a Mermaid `stateDiagram-v2` for each key entity (an order, a document,
     an account) or stateful screen (a multi-step form). Every state should be reachable and
     every non-final state should have a way out. Keep the diagram names and states in the
     product's vocabulary. If the code has a status enum, the diagram must match it.
4. **Check coverage** and show the user:
   - PRD features with no journey, and screens no journey reaches;
   - journeys with no error path; states with no exit or no entry;
   - differences between the code and the PRD (a screen the PRD doesn't mention, a feature
     with no screen).
5. **Ask only about the gaps** that remain. Never re-ask what the PRD, sources or code
   already answer. Move quickly through what's obvious.
6. **Finish** (see below).

## Not applicable

Propose N/A when the project has no user interface at all: no UI code, no UI requirements,
no human-facing surface (for example, a batch job or a service called only by other
services). State the evidence. **Ask first about CLI-only tools**: a command line is still an
interface, and multi-step commands, prompts and error output often deserve journeys and state
flows. Only on the user's agreement set `status: n/a` and a `reason:`. Never decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]`, the bracketed prompts and the
  template's example diagram states) from the sections you filled.
- Notable UX choices (dropping a platform, a navigation model that rules out a feature)
  deserve an ADR: record one with the `clarity-decision` skill, or tell the user.
- If you changed another document that is already `complete` (for example, a PRD feature
  that needed splitting), leave its `status` and `reviewed` alone and tell the user which
  documents you touched.
- **When `/clarity` called you**: don't mark anything complete. Return the draft and the list
  of open gaps.
- **When run directly**: show a short summary and the open gaps, and ask the user to confirm.
  On a clear yes, set `status: complete` and write `reviewed.hash` (this document's body hash)
  and `reviewed.deps` (the body hash of each `depends_on` document). A body hash is the output
  of the manifest's `hash_command` with `FILE` replaced by the quoted path; never compute it
  any other way. Then suggest `/clarity` to continue.

## Rules

- Describe what the user sees and does, not visual design details nobody has decided.
- Diagrams must be valid Mermaid; keep each one small enough to read.
- Accessibility NFRs apply to every screen; mention where they change a flow.
- Talk about the product, not about files or front matter.
