---
name: clarity-data-model
description: Write or revise the data model (.clarity/data/data-model.md) - entities citing the requirements that need them, a schema table per entity, a Mermaid erDiagram, migrations and retention - seeded from SQL, ORM models or migrations when present. Use when the project stores data, or when /clarity reaches the technical stage.
argument-hint: "[focus, schema files or extra sources]"
---

# Data model

Focus, schema files or extra sources from the user:

```text
$ARGUMENTS
```

The data model says what the system remembers, how the pieces relate, how the structure
changes over time and when data is deleted. Each entity exists because a requirement needs
it; nothing is stored just in case.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-data-model]`, then remove them.
   - The `depends_on` documents: `.clarity/solution/architecture.md` (data stores, which
     component owns what) and `.clarity/goal/requirements.md` (FR IDs; privacy, retention,
     compliance and performance NFRs). Also `.clarity/contracts/api.md` and its spec, and
     `.clarity/product/ux-flows.md`, when they exist: their payloads and state diagrams name
     entities and statuses.
   - The document's front matter `sources` and anything in the arguments.
   - **The repo.** SQL schema and DDL files, migration folders, ORM models and entity
     classes, document-store schemas, seed data. These seed the draft: reuse table, column
     and type names exactly as the code has them.
2. **Create the file if needed.** If `.clarity/data/data-model.md` doesn't exist, copy
   `.compose/templates/clarity/data/data-model.md` there, then fill its sections. Keep
   `status: draft` and save a rough draft early.
3. **Draft each section.**
   - **Entities**: each entity, what it represents in the domain, which component owns it,
     and the FR/NFR IDs that need it. Mark personal or sensitive data.
   - **Schema**: one table per entity listing columns (or fields), types, constraints (keys,
     uniqueness, nullability, defaults, checks) and notes. Name the indexes that matter for
     the access patterns in the requirements.
   - **Entity relationship diagram**: a Mermaid `erDiagram` with every entity and its
     relationships and cardinalities. It must match the schema tables.
   - **Migrations**: the tool and where migrations live, how they run in each environment,
     how to roll back, and how to change a column without downtime when that matters.
   - **Retention**: per entity or data class, how long it is kept, why, and how it is
     deleted or anonymised. Tie each rule to the compliance and privacy NFRs; where none
     exist, say so and ask.
4. **Check consistency** and show the user: requirements that imply stored data with no
   entity, entities that no requirement needs, mismatches with the code or the API payloads,
   statuses that differ from the state diagrams, and sensitive data with no retention rule.
5. **Ask only about the gaps** that remain. Never re-ask what the documents, sources or code
   already answer.
6. **Finish** (see below).

## Not applicable

Propose N/A when the system is stateless with no persistence of its own: no database, no
files it keeps, no durable queues or caches whose loss would matter. State the evidence (for
example, "a pure transformation service; no data store in the architecture, no models or
migrations in the code"). Data held only by a third-party service may still need entities
and retention here; ask. Only on the user's agreement set `status: n/a` and a `reason:`.
Never decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]`, the bracketed prompts, the
  template's example table row and example diagram) from the sections you filled.
- Notable choices (the type of store, denormalising for speed, soft versus hard deletes)
  deserve an ADR: record one with the `clarity-decision` skill, or tell the user.
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

- Never copy real records from seed files or dumps into the document; describe their shape.
- The code and migrations are the truth for what exists; the document may describe planned
  changes, labelled as such.
- Diagrams must be valid Mermaid.
- Talk about the data, not about files or front matter.
