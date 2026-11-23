---
name: clarity-api-contracts
description: Write or revise the API contracts (.clarity/contracts/api.md plus the machine-readable spec named in its spec field), reusing an existing OpenAPI or GraphQL schema or writing one from route handlers and requirements. Operations cite FR IDs. Use when the project exposes an API, or when /clarity reaches the technical stage.
argument-hint: "[focus, existing spec path, or extra sources]"
---

# API contracts

Focus, an existing spec, or extra sources from the user:

```text
$ARGUMENTS
```

The contract is what other teams and clients build against. `api.md` explains it to people:
who calls it, how they authenticate, what each operation is for, how errors look and how it
changes over time. The spec file is the exact, machine-readable version that tools and code
generators use. The two must agree.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `spec_template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-api-contracts]`, then remove
     them.
   - The `depends_on` documents: `.clarity/solution/architecture.md` (components, clients,
     trust boundaries) and `.clarity/goal/requirements.md` (FR IDs, security and performance
     NFRs). Also `.clarity/product/ux-flows.md` and `.clarity/data/data-model.md` when they
     exist: screens need operations, operations move entities.
   - The document's front matter `sources` and anything in the arguments.
   - **The repo.** Look for an existing spec (`openapi.*`, `swagger.*`, `*.graphql`,
     `schema.gql`, AsyncAPI files) and for route handlers, controllers, resolvers, router
     tables and request/response models. Code is the truth about what exists today.
2. **Create the file if needed.** If `.clarity/contracts/api.md` doesn't exist, copy
   `.compose/templates/clarity/contracts/api.md` there. Keep `status: draft` and save early.
3. **Settle the spec file**, and set the front matter `spec:` to its path:
   - **A spec exists in the repo**: reference it in place. Set `spec:` to its path relative to
     the repo root. Don't copy it; one source of truth.
   - **A spec exists outside the repo** (a URL or a supplied file): copy it into
     `.clarity/contracts/` and set `spec:` to the copy (for example
     `contracts/openapi.yaml`). Add the origin to `sources`.
   - **No spec**: copy the manifest's `helpers.openapi` stub
     (`.compose/templates/clarity/contracts/openapi.yaml`) to `.clarity/contracts/openapi.yaml`
     and fill it in, from route handlers when there is code, otherwise from the requirements
     and flows. Use GraphQL instead (`contracts/schema.graphql`) if that is the project's
     style.
   - When you write or edit a spec, it must be well-formed: valid YAML or JSON with an
     `openapi` key, or a GraphQL schema with at least one type. Re-read it after writing and
     check it parses. Replace the stub's `[TBD]` title and description.
4. **Draft api.md.**
   - **Overview**: callers, style (REST, GraphQL, events), base URL per environment, and a
     pointer to the spec.
   - **Authentication**: how callers prove who they are, what scopes or roles exist, and which
     operations need which. Tie it to the security NFRs and the architecture's trust
     boundaries.
   - **Operations**: the main operations grouped by resource, each with a one-line purpose
     and the FR IDs it serves. Leave field-level detail to the spec. Note idempotency,
     pagination and rate limits where they matter.
   - **Errors**: one error format, the status codes or error types used, and the main cases
     per operation group.
   - **Versioning**: how the contract changes without breaking callers. State what counts
     as a breaking change (removing or renaming a field or operation, tightening validation,
     changing a type or meaning). Say how versions are expressed (URL, header, schema
     evolution), how deprecations are announced and how long old versions live.
5. **Check traceability** and show the user: FRs that need an operation but have none,
   operations that serve no requirement, and differences between code, spec and api.md.
6. **Ask only about the gaps** that remain. Never re-ask what the documents, spec or code
   already answer.
7. **Finish** (see below).

## Not applicable

Propose N/A when the project has no API surface: nothing calls it over a network or
messaging boundary, and nothing it exposes is meant for other programs (for example, a
desktop tool with no integrations, or a static site). State the evidence, such as "no route
handlers, no spec, no integration requirements". A library's public interface or a CLI is not
normally an API contract here; ask the user. Only on the user's agreement set `status: n/a`
and a `reason:`. Never decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]`, the bracketed prompts and the
  example operation line) from api.md and from the spec you wrote.
- Notable choices (REST vs GraphQL, the versioning scheme, the auth model) deserve an ADR:
  record one with the `clarity-decision` skill, or tell the user.
- If you changed another document that is already `complete` (for example, the architecture
  for a missing gateway), leave its `status` and `reviewed` alone and tell the user which
  documents you touched.
- **When `/clarity` called you**: don't mark anything complete. Return the draft and the list
  of open gaps.
- **When run directly**: show a short summary and the open gaps, and ask the user to confirm.
  On a clear yes, set `status: complete` and write `reviewed.hash` (this document's body hash)
  and `reviewed.deps` (the body hash of each `depends_on` document). A body hash is the output
  of the manifest's `hash_command` with `FILE` replaced by the quoted path; never compute it
  any other way. Then suggest `/clarity` to continue.

## Rules

- Never put real credentials, tokens or keys in examples; use obvious stand-ins.
- Don't change an existing spec in the repo without telling the user: other code may depend
  on it.
- Keep api.md short; the spec carries the detail.
- Talk about the API, not about files or front matter.
