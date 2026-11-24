---
name: clarity-data-model
description: Write or revise the domain model and data rules (.clarity/data/data-model.md) - the core entities the whole application shares, a Mermaid erDiagram of them, data rules, migrations and retention - seeded from SQL, ORM models or migrations when present. Feature tables are not listed here; each feature's plan adds them. Use when the project stores data, or when /clarity reaches the technical stage.
argument-hint: "[focus, schema files or extra sources]"
---

# Domain model and data rules

Focus, schema files or extra sources from the user:

```text
$ARGUMENTS
```

This document names the few core entities most features touch, how they relate, and the
rules all data follows: storage, naming, identifiers, personal data, migrations and
retention. It lists no feature tables or fields: each feature's plan (`compose-plan`) adds
those, following these rules.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-data-model]`, then remove them.
   - The `depends_on` documents: `.clarity/solution/architecture.md` (data stores, which
     component owns what) and `.clarity/goal/requirements.md` (privacy, retention,
     compliance and performance NFRs, constraints, standards). Also
     `.clarity/contracts/api.md` and `.clarity/product/ux-standards.md` when they exist: their
     ID, timestamp and state conventions must agree with the data rules.
   - The document's front matter `sources` and anything in the arguments.
   - **The repo.** SQL schema and DDL files, migration folders, ORM models and entity
     classes, document-store schemas. These seed the core entities (reuse names exactly as
     the code has them) and show the data rules in use: ID types, timestamp columns, soft
     delete flags, audit fields, naming style.
2. **Create the file if needed.** If `.clarity/data/data-model.md` doesn't exist, copy
   `.compose/templates/clarity/data/data-model.md` there, then fill its sections. Keep
   `status: draft` and save a rough draft early.
3. **Draft each section.**
   - **Core entities**: only the entities most features share (a user, an account, an
     organisation, an order). For each, what it represents, which component owns it, and
     whether it holds personal or sensitive data. Keep fields out; feature plans add them.
   - **Entity relationship diagram**: a Mermaid `erDiagram` of the core entities with their
     relationships and cardinalities.
   - **Data rules**: storage choice per kind of data, naming, identifiers, timestamps and
     time zones, soft or hard delete, personal data handling, auditing. Write each as a rule
     a feature plan can follow.
   - **Migrations**: the tool and where migrations live, how they run in each environment,
     how to roll back, and the rules a migration must follow (for example, no downtime
     column changes).
   - **Retention**: per data class, how long it is kept, why, and how it is deleted or
     anonymised. Tie each rule to the compliance and privacy NFRs; where none exist, say so
     and ask.
4. **Check consistency** and show the user: privacy, retention or compliance NFRs no rule
   covers, places where the code breaks the rules, conflicts with the API or UX state
   conventions, and sensitive data with no retention rule. Feature tables found in the code
   are not listed here.
5. **Ask only about the gaps** that remain. Never re-ask what the documents, sources or code
   already answer.
6. **Finish** (see below).

## Not applicable

Propose N/A when the system is stateless with no persistence of its own: no database, no
files it keeps, no durable queues or caches whose loss would matter. State the evidence (for
example, "a pure transformation service; no data store in the architecture, no models or
migrations in the code"). Data held only by a third-party service may still need rules and
retention here; ask. Only on the user's agreement set `status: n/a` and a `reason:`. Never
decide N/A alone.

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
  template's example diagram) from the sections you filled.
- Notable choices (the type of store, soft versus hard deletes, the ID scheme) deserve an
  ADR: record one with the `clarity-decision` skill, or tell the user.
- If you changed another document that is already `complete` (for example, the architecture
  for a new store), leave its `status` and `reviewed` alone and tell the user which documents
  you touched.
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
- Core entities and rules, not schemas. Feature tables come from each feature's plan.
- Never copy real records from seed files or dumps into the document; describe their shape.
- The code and migrations are the truth for what exists; the document may describe planned
  changes, labelled as such.
- Diagrams must be valid Mermaid.
- Talk about the data, not about files or front matter.
