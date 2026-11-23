---
name: compose-clarify
description: Find and resolve the most important ambiguities in the current feature's spec, recording the answers in spec.md. Use after specifying and before planning.
argument-hint: "[areas to focus on]"
---

# Clarify the specification

Optional focus from the user:

```text
$ARGUMENTS
```

## Steps

1. Run `compose feature paths --json` and read `spec_file`. If the spec doesn't exist, stop
   and tell the user to run `/compose-specify` first.
2. Scan the spec for ambiguity in each area, rating it clear, partial or missing:
   scope and goals; users and roles; data and entities; interaction flows and states;
   non-functional qualities (performance, scale, reliability, security, privacy,
   accessibility); integrations and dependencies; edge cases and failure handling;
   constraints and trade-offs; terminology; completion signals; existing
   `[NEEDS CLARIFICATION]` markers.
   When the paths JSON has a non-null `clarity`, read the guide at `clarity.guide`. An area
   the binding clarity documents already settle (users, non-functional qualities,
   constraints, conventions) counts as clear: cite the document instead of asking.
3. Pick at most **five** questions whose answers would change the architecture, the data
   model, the tasks, the tests or compliance. Skip anything trivial or better decided
   during planning. Order them by impact.
4. Each question must be answerable with one choice from two to five options, or a short
   phrase. For each, give your recommended answer and why.
5. **Asking.** In an interactive session, ask one question at a time, show the options and
   your recommendation, and accept "yes" or "recommended" as taking it. Stop early when
   the user says they are done.
   In a headless run (no one can answer, e.g. `COMPOSE_RUN_ID` is set), take your
   recommended answer for each question and mark it as an assumption.
6. After each answer, update the spec right away:
   - add or extend a `## Clarifications` section with a `### Session YYYY-MM-DD` heading
     and a bullet `- Q: <question> → A: <answer>` (note "assumed" when you chose it);
   - change the affected section (requirements, entities, scenarios, success criteria,
     edge cases) so the spec no longer contradicts itself; replace resolved
     `[NEEDS CLARIFICATION]` markers.
7. Save `spec_file` after every change, keeping the template's headings.

## Report

How many questions were asked and answered, the sections changed, a table of each area's
status (resolved, deferred, clear, still open), and the suggested next step
(`/compose-plan`, or `/compose-clarify` again if important gaps remain).
