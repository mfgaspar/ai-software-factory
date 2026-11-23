# Tasks: [FEATURE TITLE]

**Input**: design documents in `specs/[NNN-short-name]/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md,
contracts/, quickstart.md

## Format: `- [ ] [ID] [P?] [Story?] Description with file path`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: the user story the task belongs to (US1, US2, …)
- Every task names the exact file(s) it touches.

## Phase 1: setup

- [ ] T001 Create the project structure described in plan.md
- [ ] T002 [P] Configure linting and formatting

## Phase 2: foundations (blocks every user story)

- [ ] T003 [shared infrastructure every story needs, with file path]

**Checkpoint**: foundations ready; user stories can start.

## Phase 3: user story 1 — [title] (P1) 🎯 MVP

**Goal**: [what this story delivers]
**Independent test**: [how to check it on its own]

- [ ] T004 [P] [US1] Test for [behavior] in tests/[path]
- [ ] T005 [US1] Implement [component] in src/[path]

**Checkpoint**: user story 1 works and is testable on its own.

## Phase 4: user story 2 — [title] (P2)

- [ ] T006 [P] [US2] …

## Final phase: polish

- [ ] T0XX [P] Documentation updates
- [ ] T0XX Run quickstart.md end to end

## Dependencies and order

- Setup → foundations → user stories in priority order (or in parallel) → polish.
- Within a story: tests before implementation, models before services, services before
  endpoints or UI.
