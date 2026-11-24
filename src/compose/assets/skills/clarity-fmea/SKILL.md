---
name: clarity-fmea
description: Build or refresh the optional Failure Mode and Effects Analysis worksheet (.clarity/failures/fmea.md) from the analysed failure modes and their management plans, one row per failure mode and cause, with optional 1-10 scores and risk priority numbers. Use after failure management, when a project must show an FMEA, or when the failure documents change.
argument-hint: "[scope, or 'scores' to add the scored columns]"
---

# Failure Mode and Effects Analysis (FMEA)

Scope or options from the user:

```text
$ARGUMENTS
```

The FMEA worksheet is a **view over the failure documents**, for people who need the
classic table: auditors, safety and quality reviewers, and teams in regulated work. The
thinking is already done in `.clarity/failures/`: this skill lays it out as a worksheet and
adds nothing the failure documents don't support. When the two disagree, the failure
documents are right and the worksheet is regenerated.

The document is optional. It is part of a project only when `.clarity/config.yml` lists
`failures/fmea.md` under `mandatory.add`. When it doesn't and the user ran this skill
directly, offer to add it (through `clarity-configure`), and go on only if they agree.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/config.yml`: `fmea.scores` (default `false`). The argument `scores` turns the
     scored columns on for this run; tell the user to set `fmea.scores: true` to keep them.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-fmea]`, then remove them.
   - `.clarity/failures/failures.md` and every `failure-NN-*.md` it links: the summary, the
     failure chain, the observations (severity), the intervention points and the management
     plan of each.
   - `.clarity/solution/solution.md` and `.clarity/solution/architecture.md`, when they
     exist, for the functions and components the rows name. Without them, take the
     functions from `.clarity/goal/problem.md`.
   - The existing `.clarity/failures/fmea.md`, to keep row IDs, owners and action states.
2. **Stop when there is nothing to lay out.** If no failure mode has been analysed, say so
   and suggest `clarity-failure-brainstorm` and `clarity-failure-analysis` first.
   Unattended, leave the template as it is and return that gap.
3. **Create the file if needed.** If `.clarity/failures/fmea.md` doesn't exist, copy
   `.compose/templates/clarity/failures/fmea.md` there. Keep `status: draft`.
4. **Fill the sections.**
   - **Scope**: the system or part covered, the functions analysed (one line each), and
     what is left out and why.
   - **Scales**: the severity scale from the failure documents. With scores on, also the
     1–10 scales for severity, occurrence and detection, each band in the project's own
     terms (what a 9 means here), and the note under **Scores** below.
   - **Worksheet**: one row per failure mode **and cause**. A failure mode with two
     independent causes gets two rows. Columns, in the template's order:
     - **ID**: `FM-001`, `FM-002`, … Keep the ID a row already has; never renumber. A row
       whose failure mode was dropped is removed, and its ID is not reused.
     - **Function**: what the system is meant to do at the point the failure occurs, in
       the user's terms ("Save an entry").
     - **Failure mode**: how that function fails, from the failure's title and summary.
     - **Effect**: the harm at the first harm boundary of the chain, and who bears it.
     - **Cause**: the trigger and mechanism from the chain's first steps.
     - **Current controls**: prevention and detection that exist **today**, from the
       intervention points and the code. Write "none" when there are none; a planned
       control is an action, never a current control.
     - **Severity**: exactly as the failure document rates it.
     - **Recommended action**: from the management plan. "Accepted: <reason>" for an
       accepted risk; "**no plan yet**" when failure management hasn't run for it.
     - **Owner**: a name or role the plan or the user gave. Otherwise leave "unassigned".
     - **Source**: a link to the failure document.
   - **Actions**: the recommended actions, each once, in the order the management plans
     sequence them, with the rows each covers, its owner and its state.
   Remove the template's row-format comment once the worksheet has rows.
5. **Check the worksheet against its sources.** Every analysed failure mode has at least
   one row; every row links a failure document that exists; severities match; no row
   states a control or an action the failure documents don't. Fix the worksheet, never the
   failure documents. If laying out the rows shows a real hole (a function with no failure
   considered, a failure with no detection at all), add a note in `.clarity/notes.md`
   tagged `[for: clarity-failure-analysis]` or `[for: clarity-failure-management]` and say so.
6. **Ask only about the gaps** that remain (see **Questions**).
7. **Finish** (see below).

## Scores

Off by default. The failure skills deliberately don't rank by severity times likelihood:
likelihood is hard to estimate for software, and the product can hide a rare, severe
failure behind a common, trivial one. Scores are for audits that expect them.

With scores on, the worksheet replaces Severity with **S**, **O**, **D** and **RPN**:

- **S** (severity, 1–10) follows the failure document: Critical 9–10, High 7–8, Medium
  4–6, Low 1–3.
- **O** (occurrence, 1–10) and **D** (detection, 1–10, where 10 means it would not be
  detected before it causes harm) need evidence: incident history, measured rates, or a
  person's judgement. Propose a value with its reasoning, mark it as proposed, and have a
  person confirm it. Never present a guessed O or D as fact.
- **RPN** is S × O × D. After Owner, add **S'**, **O'**, **D'** and **RPN'**: the scores
  expected once the action is done.
- Say in **Scales** that the RPN orders the work and decides nothing else: every row with
  S of 9 or 10 gets an action whatever its RPN, and no failure is dropped for a low one.

## Not applicable

Propose N/A only when the project has no failure modes to analyse, which also makes
`failures/failures.md` N/A. State the evidence. Only on the user's agreement set
`status: n/a` and a `reason:`. Never decide N/A alone. A project that simply doesn't need
the worksheet leaves it out of `mandatory.add`.

## Questions

Ask a person only what a person must answer: their intent and priorities, facts only they
hold (real users, numbers, deadlines, owners), a trade-off the material leaves open that is
theirs to own, a conflict the sources can't settle, and confirmations. Anything you can work
out from the sources, the code, the other `.clarity/` documents, earlier answers or
established practice, decide yourself: write it, mark it as inferred with where it came
from, and name it in your summary so the person can correct it. `/clarity` sets this out in
**Ask a person only what needs a person**.

For this document, what needs a person is: owners, the scope when it is narrower than the
whole system, and, with scores on, the occurrence and detection scores.

## Unattended

`/clarity` runs this skill unattended in its `auto`, `draft` and `apply` phases, and passes
`auto`. Work the same way whenever `COMPOSE_RUN_ID` is set or no person is present. Ask
nothing. Build the worksheet from the failure documents, drafts included. Fill what you
can work out yourself (see **Questions**), marked as inferred, and leave a
`[TBD — <what's missing or conflicting>]` note only for what a person must answer, in the
section it belongs to, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps: `/clarity`
turns them into questions for a person.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]` and the bracketed prompts) from
  the sections you filled.
- **When `/clarity` called you**: don't mark anything complete. Return the draft and the list
  of open gaps, including rows with no plan yet and any proposed scores.
- **When run directly**: show a short summary (rows, rows with no plan, the top actions) and
  the open gaps, and ask the user to confirm. On a clear yes, set `status: complete` and
  write `reviewed.hash` (this document's body hash) and `reviewed.deps` (the body hash of
  each `depends_on` document). A body hash is the output of the manifest's `hash_command`
  with `FILE` replaced by the quoted path; never compute it any other way. Then suggest
  `/clarity` to continue.

## Rules

- The worksheet never says more than the failure documents: no new failure modes, causes,
  controls or actions invented here. New thinking goes back to the failure skills.
- This skill writes only `.clarity/failures/fmea.md` and notes in `.clarity/notes.md`.
- Keep cells short: a phrase, not a paragraph. The detail is one link away.
- Talk about the project, not about files or front matter.
