---
name: compose-converge
description: After implementing, check the code against the current feature's spec, plan, tasks and constitution, and append whatever is still missing to tasks.md as a new Convergence phase for implement to finish. Changes nothing else.
argument-hint: "[areas to focus on]"
---

# Converge code with the spec

Optional focus from the user:

```text
$ARGUMENTS
```

The spec, plan and tasks say what the feature must do; this skill finds where the code
does not do it yet and turns each gap into a task. Run it after `/compose-implement`, then
implement again until it reports the feature converged.

**The only file you may change is `tasks_file`, and only by appending.** Never edit the
spec, plan or any code, and never rewrite, renumber, reorder or delete an existing task
(earlier Convergence phases included). Fixing the gaps is `/compose-implement`'s job. If
nothing is missing, leave `tasks_file` exactly as it is.

This is about the code as it is now, not about history: don't diff branches or read git
log.

## Steps

1. Run `compose feature paths --json`. Read `spec_file`, `plan_file` and `tasks_file`; if
   one is missing, name the skill that creates it (`/compose-specify`, `/compose-plan`,
   `/compose-tasks`) and stop. Read the constitution at `constitution_file` if it exists
   and has been filled in; skip constitution checks if it is still the starter template.
2. **What is intended.** List, each with a short reference you can cite:
   - requirements (`FR-…`) and success criteria (`SC-…`) that need code to be met
     (leave out business outcomes measured after launch);
   - each user story's acceptance scenarios (`US1/AC2`) and the spec's edge cases;
   - the plan's decisions that the code must reflect: stack, structure, data model,
     contracts, and the files it says will be created or changed;
   - the constitution's MUST and SHOULD principles that apply to code;
   - every task, checked or not. A checked box is a claim, not proof.
3. **Where to look.** Start from the files the plan and tasks name, and search the code
   for the concepts each requirement describes. Stay within what the feature covers.
4. **Assess.** For each intended item, check what the code actually does now (read it; run
   the tests if the project has them and you are allowed to). Record a finding only where
   there is a gap, as one of:
   - **missing** — no code for it at all;
   - **partial** — it exists but doesn't fully meet the requirement, scenario or decision;
   - **contradicts** — the code conflicts with the intent or a constitution MUST;
   - **unrequested** — code the spec, plan and tasks don't call for (you still don't
     delete it; the task is to review it, then justify or remove it).
   With little or no code yet, the whole scope is *missing*: report it, don't fail.
5. **Severity.**
   - CRITICAL: breaks a constitution MUST, or a missing/contradicting piece that stops a
     P1 story from working at all.
   - HIGH: a missing or partial core requirement or acceptance scenario.
   - MEDIUM: a partial secondary requirement, or unrequested code with no clear reason.
   - LOW: small gaps, polish, harmless unrequested code.
6. **Show the findings before writing anything:** a table of ID, gap type, severity,
   reference, evidence (file or area) and the remaining work, then counts: items checked
   by kind, findings by gap type and by severity.
7. **Append, or report converged.**
   - With findings: find the highest task number (`T…`) and the highest phase number in
     `tasks_file`. At the very end of the file add one section `## Phase N: Convergence`
     (N = highest phase + 1) with one unchecked task per finding, CRITICAL first, then by
     severity, numbered on from the highest task:

     ```markdown
     - [ ] T043 Validate the email format on sign-up per FR-004 (partial)
     ```

     Each line names its reference and gap type. Add a new phase even if an earlier
     Convergence phase exists.
   - With no findings: don't touch `tasks_file`.

## Report

End with exactly one of these lines, on its own, so a workflow can tell the outcome:

- `CONVERGED: the code meets the spec, plan and tasks.` — and suggest reviewing the
  changes and opening a pull request.
- `TASKS APPENDED: <n> in Phase <N>: Convergence` — and suggest `/compose-implement` to do
  them, then `/compose-converge` again.
