---
status: draft
reason: ""
depends_on:
  - solution/architecture.md
  - goal/requirements.md
reviewed:
  hash: ""
  deps: {}
sources: []
approvals: []
spec: ""
---

# API conventions

The rules every interface of this application follows. Feature endpoints are not listed here:
each feature's plan defines its own contracts (`compose-plan`) following these conventions.
When the application already has a published API that features must keep, the `spec` field
above names its machine-readable contract (OpenAPI or GraphQL); otherwise leave it empty.

## Overview

[To be determined. Who calls the application's interfaces, and the style (REST, GraphQL,
gRPC, events, CLI).]

## Authentication

[TBD — how callers authenticate, and how permissions are expressed and checked.]

## Conventions

[TBD — naming, resource and URL shape, pagination, filtering, idempotency, timestamps and IDs.]

## Errors

[TBD — the error format every interface returns, and the common error cases.]

## Versioning

[TBD — how contracts change without breaking callers, and the deprecation policy.]
