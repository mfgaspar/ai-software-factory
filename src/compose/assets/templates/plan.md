# Implementation plan: [FEATURE TITLE]

**Feature**: `[NNN-short-name]` | **Date**: [DATE] | **Spec**: [link to spec.md]

## Summary

[The primary requirement and the chosen technical approach, in a few sentences.]

## Technical context

<!-- Replace each value with the project's actual choice, or NEEDS CLARIFICATION. -->

- **Language / version**: [e.g. Python 3.12]
- **Primary dependencies**: [e.g. FastAPI]
- **Storage**: [e.g. PostgreSQL, files, N/A]
- **Testing**: [e.g. pytest]
- **Target platform**: [e.g. Linux server, iOS 18]
- **Project type**: [single project, web app (frontend + backend), mobile + API, library]
- **Performance goals**: [domain-specific, e.g. 500 req/s]
- **Constraints**: [e.g. p95 < 200 ms, offline-capable]
- **Scale / scope**: [e.g. 10k users, 40 screens]

## Constitution check

*Gate: must pass before research, and again after the design.*

| Principle | How this plan complies | Status |
|---|---|---|
| [principle from the constitution] | [evidence] | PASS / VIOLATION |

## Project structure

### Documentation (this feature)

```text
specs/[NNN-short-name]/
├── spec.md          # what and why
├── plan.md          # this file
├── research.md      # decisions and alternatives (phase 0)
├── data-model.md    # entities (phase 1)
├── quickstart.md    # how to try it end to end (phase 1)
├── contracts/       # interface definitions (phase 1)
└── tasks.md         # created by the tasks skill
```

### Source code (repository)

```text
[the real directory layout this feature touches or adds]
```

**Structure decision**: [why this layout]

## Phase 0: research

[Each open question from the technical context, with the decision, the rationale and the
alternatives considered — written to research.md.]

## Phase 1: design

[Entities in data-model.md, interfaces in contracts/, the end-to-end check in quickstart.md.]

## Complexity tracking

*Only when the constitution check has violations that are justified.*

| Violation | Why it is needed | Simpler alternative rejected because |
|---|---|---|
| | | |
