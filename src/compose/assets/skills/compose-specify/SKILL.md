---
name: compose-specify
description: Turn a feature description into a specification (specs/NNN-name/spec.md) on its own feature branch. Use to start a new feature from a plain-language description.
argument-hint: "<what the feature should do>"
---

# Write the feature specification

The feature description:

```text
$ARGUMENTS
```

If the description is empty, stop and ask the user what the feature should do.

## Steps

1. **Create or locate the feature.** Run:

   ```bash
   compose feature new --json "<the feature description>"
   ```

   Add `--name <short-name>` when a 2–4 word short name is obvious and better than the
   default. The JSON gives `name`, `branch`, `feature_dir`, `spec_file`, `templates_dir`
   and `created`. Inside a compose workflow run this returns the run's feature and creates
   nothing, which is expected. Use these paths for everything below; never invent them.
2. Load `spec.md` from `templates_dir` and keep its section order and headings.
   **Project memory.** Read the constitution at `constitution_file` if it exists. When it
   is a memory index (its first line is `<!-- memory-index: … -->`), read the guide at
   `.compose/templates/compose/clarity.md` and open the files the index lists for the
   `specify` step. They give the actors, the goals (`G-###`) the feature can serve, the
   scope boundaries and the rules that apply. Fill **Serves** with those IDs. Don't ask
   about anything they already answer. If the description names a goal or an item in the
   memory file `feature-ideas.md`, start from it. A feature outside the product's scope
   boundaries is a conflict, and the guide says how to handle it. The spec's own `FR-###`
   start at `FR-001` and never reuse the foundation's IDs.
3. Understand the description: actors, actions, data, constraints, and what success looks
   like. Fill the template:
   - **User stories** in priority order. Each must be independently valuable and testable,
     with Given/When/Then acceptance scenarios.
   - **Functional requirements**, each specific and testable (`FR-001` …).
   - **Key entities** when the feature involves data.
   - **Success criteria**: measurable and technology-agnostic (time, rate, count,
     satisfaction), never "the API responds in 200 ms using Redis".
   - **Edge cases, assumptions and out of scope.**
4. Say what and why, never how: no languages, frameworks, APIs, database names or code.
   Write for a business reader.
5. **Unknowns.** Make an informed guess where a reasonable default exists and record it under
   Assumptions. Use `[NEEDS CLARIFICATION: question]` only where the answer changes the
   scope, security or user experience significantly and no default is reasonable — at most
   three markers, the most important first.
6. Write the result to `spec_file`.
7. **Check the quality** of what you wrote and fix what fails (up to three passes):
   - no implementation details; every requirement is testable and unambiguous;
   - success criteria are measurable and technology-agnostic;
   - every user story has acceptance scenarios; edge cases and scope are stated.
   Save this checklist as `checklists/requirements.md` in the feature folder, with each item
   checked or annotated with what is still missing.
8. If clarification markers remain, list each question with two or three suggested answers
   and what each implies. When someone can answer (an interactive session), ask them, then
   update the spec. When no one can answer (a headless run, e.g. `COMPOSE_RUN_ID` is set),
   leave the markers in place for the clarify step.

## Report

The feature name and branch, the spec path, the checklist result, open questions, and the
suggested next step (`/compose-clarify` if questions remain, otherwise `/compose-plan`).
