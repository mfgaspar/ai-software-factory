---
name: clarity-api-contracts
description: Write or revise the API conventions (.clarity/contracts/api.md) - callers, authentication, conventions, errors and versioning - inferred from route handlers or an existing OpenAPI or GraphQL contract, named in the optional spec field. Feature endpoints come from each feature's plan. Use when the project exposes an API, or when /clarity reaches the technical stage.
argument-hint: "[focus, existing spec path, or extra sources]"
---

# API conventions

Focus, an existing spec, or extra sources from the user:

```text
$ARGUMENTS
```

This document sets the rules every interface of the application follows: who calls it, how
callers authenticate, the shape of resources and URLs, the error format and how contracts
change. It lists no feature endpoints: each feature's plan (`compose-plan`) defines its own
contracts following these conventions. When the application already has a published API that
features must keep, the front matter `spec:` names its machine-readable contract.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-api-contracts]`, then remove
     them.
   - The `depends_on` documents: `.clarity/solution/architecture.md` (components, clients,
     trust boundaries) and `.clarity/goal/requirements.md` (security and performance NFRs,
     constraints, standards). Also `.clarity/data/data-model.md` when it exists, for
     identifier and timestamp rules.
   - The document's front matter `sources` and anything in the arguments.
   - **The repo.** Look for an existing spec (`openapi.*`, `swagger.*`, `*.graphql`,
     `schema.gql`, AsyncAPI files) and for route handlers, middleware, error handlers and
     request/response models. Code is the truth about the conventions in use today.
2. **Create the file if needed.** If `.clarity/contracts/api.md` doesn't exist, copy
   `.compose/templates/clarity/contracts/api.md` there. Keep `status: draft` and save early.
3. **Settle `spec:`**. It is optional; leave it empty (`""`) unless a published contract
   already exists.
   - **A spec exists in the repo**: set `spec:` to its path relative to the repo root. Don't
     copy it; one source of truth.
   - **A spec exists outside the repo** (a URL or a supplied file): copy it into
     `.clarity/contracts/` and set `spec:` to the copy (for example `contracts/openapi.yaml`).
     Add the origin to `sources`.
   - **No spec**: leave `spec:` empty. Never create a spec stub and never invent endpoints.
   - A spec you name must exist and be well-formed: valid YAML or JSON with an `openapi` key,
     or a GraphQL schema with at least one type.
4. **Draft api.md.** Infer each section from the spec and the code when they exist.
   - **Overview**: callers, style (REST, GraphQL, gRPC, events, CLI), base URL per
     environment, and a pointer to the spec when there is one.
   - **Authentication**: how callers prove who they are, what scopes or roles exist, and how
     permissions are checked. Tie it to the security NFRs and the architecture's trust
     boundaries.
   - **Conventions**: naming, resource and URL shape, pagination, filtering, idempotency,
     rate limits, timestamps and IDs. Write each as a rule a feature plan can follow.
   - **Errors**: one error format, the status codes or error types used, and the common
     cases.
   - **Versioning**: what counts as a breaking change (removing or renaming a field or
     operation, tightening validation, changing a type or meaning), how versions are
     expressed (URL, header, schema evolution), how deprecations are announced and how long
     old versions live.
5. **Check consistency** and show the user: places where the code or spec breaks the
   conventions, and NFRs (security, performance) no convention covers. If sources list
   feature endpoints, don't copy them here: note them in `.clarity/notes.md` under
   `## Feature ideas` for `compose-specify`.
6. **Ask only about the gaps** that remain. Never re-ask what the documents, spec or code
   already answer.
7. **Finish** (see below).

## Not applicable

Propose N/A when the project has no API surface: nothing calls it over a network or
messaging boundary, and nothing it exposes is meant for other programs (for example, a
desktop tool with no integrations, or a static site). State the evidence, such as "no route
handlers, no spec, no integration requirements". A library's public interface or a CLI is not
normally an API here; ask the user. Only on the user's agreement set `status: n/a` and a
`reason:`. Never decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]` and the bracketed prompts) from
  the sections you filled.
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

- Conventions, not endpoints. Feature endpoints come from each feature's plan.
- Never put real credentials, tokens or keys in examples; use obvious stand-ins.
- Don't change an existing spec in the repo: other code may depend on it.
- Talk about the API, not about files or front matter.
