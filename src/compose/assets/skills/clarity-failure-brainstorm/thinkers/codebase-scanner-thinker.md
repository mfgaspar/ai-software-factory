---
name: codebase-scanner-thinker
display_name: Codebase Scanner
modes: [quick, deep]
prerequisites:
  required: [goal/problem.md]
  recommended: [goal/stakeholders.md, solution/architecture.md]
tags: [architecture, codebase, scanning, reconnaissance]
description: "Repository scanning: API routes, configs, auth patterns, secrets, AI integrations, infrastructure"
---
# Codebase scanner thinker

Scan the repository for what the system actually is (components, data flows, trust
boundaries, attack surface) and record the concerns it reveals. This needs direct read and
search access to the code; without it, skip this thinker and rely on the architecture
document.

## Approach

1. Identify the stack from package manifests (`package.json`, `pyproject.toml`,
   `requirements.txt`, `pom.xml`, `go.mod`…) and the directory layout. Adapt every search to
   that stack.
2. If `.clarity/solution/architecture.md` exists, treat it as the intended design and check
   it against the code. Discrepancies are findings.
3. Search for these signals:
   - **API routes**: route definitions, handlers, controllers, API docs.
   - **Config**: environment files, settings modules, feature flags.
   - **LLM / AI**: model API calls, embedding pipelines, agent frameworks, prompt templates.
   - **Database and storage**: connection strings, ORM models, migrations, query builders.
   - **Auth**: middleware, sessions, token handling, identity providers.
   - **Network**: port bindings, CORS, proxies, load balancers, firewall rules.
   - **Secrets**: vault references, secret managers, credential stores, hard-coded secrets.
     Never copy a secret value into your output; cite the file and line.
   - **CI/CD**: pipelines, Dockerfiles, infrastructure as code, deploy scripts.

## What to produce

Write raw failures to `.clarity/failures/brainstorm/<thinker-name>.md` (use the exact output
path you were given) in the format of the manifest's `helpers.thinker_output` template,
`.compose/templates/clarity/failures/brainstorm/thinker.md`. Before the entries, add a short
**Scan summary**: languages and frameworks; components found (type and trust zone); main data
flows (protocol and sensitivity); auth, secrets handling and AI integrations; discrepancies
with the architecture document; open questions the code can't answer.

Each raw failure describes the concern and its potential harm in one to three sentences and
cites the file or pattern that raised it. Put discrepancies with the architecture document,
and anything else a project document should say, in a **Suggestions** section at the end,
each naming its target document.

Adapted from microsoft/clarity-agent (thinkers/codebase-scanner-thinker.md), MIT License; see
LICENSE.txt in the skill folder.
