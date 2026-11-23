---
name: clarity-solution
description: Develop a solution approach grounded in the problem, stakeholders and requirements, one that can really be built, run and maintained, and write .clarity/solution/solution.md plus a first solution summary. Use once the problem is clear, or when the solution needs rethinking.
argument-hint: "[focus or constraint, e.g. 'rethink after Q2 finding']"
---

# Brainstorm the solution

What the user asked for (it may be empty):

```text
$ARGUMENTS
```

You already know how to brainstorm. This skill says what to ground the thinking in, what to
watch for, and when to bring the user in. The aim is an approach clear enough to drive the
architecture. It writes `.clarity/solution/solution.md` and a first version of
`.clarity/solution/solution-summary.md`.

## Before you start

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml` (templates,
   `required_sections`, `depends_on`, `hash_command`) and `.clarity/notes.md`. Act on items
   tagged `[for: clarity-solution]`, then remove them.
2. Read `goal/problem.md`, `goal/stakeholders.md`, `goal/requirements.md` and
   `goal/open-questions.md`, the existing solution documents and their `sources`, and any code
   or supplied material that already shows the approach.
3. If the goal documents are missing or still placeholders, go to `clarity-problem` first. If
   an unresolved open question is `Blocking: yes`, stop: name it and the skill its strategy
   routes to. Solution work waits for it.
4. Copy a missing document's template from `.compose/templates/clarity/` (the manifest's
   `template` field) and keep `status: draft`.

Ask only about gaps and conflicts; don't re-ask what the documents already settle.

## What to keep in mind

- **It has to become real.** Keep an eye on whether it can be built with reasonable effort by
  the actual team, understood and changed in six months, and deployed, monitored and operated.
  Architecture works out the details; notice early when something is fundamentally
  unbuildable.
- **Consider a genuinely different alternative** before committing, even briefly. You often
  find something simpler.
- **Bring the user in** when two approaches both satisfy the requirements but lead to
  materially different systems (their team, timeline and taste decide), when an edge case the
  requirements didn't foresee appears, or when an assumption is genuinely uncertain. Decide the
  rest yourself.
- **Take the user's instinct seriously.** Help them think it through rather than override it.
- **Exploratory projects.** If open questions say the project is exploratory (nobody yet knows
  what people need), frame the solution as infrastructure for cheap, fast experiments:
  flexibility, quick iteration and instrumentation over optimality.
- **Capture what you notice.** Failure concerns ("if X fails the consequences are severe"),
  hard constraints ("this needs Y always available"), misuse risks. Put them in the solution's
  risks, and leave `[for: clarity-failure-brainstorm]` or `[for: clarity-architecture]` items in
  `.clarity/notes.md` so they aren't lost.

## Writing

Fill the template sections and remove every placeholder (`[TBD…]`, `[To be determined…]`,
other bracketed prompts) from what you fill:

- `solution/solution.md`: the approach a stakeholder can follow and the key design choices in
  it; why it fits, citing the goals (`G-###` and the problem's success criteria) it serves and
  the rules (NFR-###, CON-###, STD-###) it meets, and saying how;
  the alternatives and why they lost; risks, assumptions and observations worth tracking.
- `solution/solution-summary.md` (first version, `status: draft`): at most two pages for
  someone who read the problem and asks "so what's the plan?". What we're building; what using
  it is like, concretely enough to picture; how it addresses the problem; the non-obvious
  choices that took real discussion. `clarity-architecture` extends it later.

A genuine fork you settle with the user deserves an ADR: use `clarity-decision`, or tell the
user one should be recorded. If the project summary in `.clarity/summary.md` now misses the
solution, add a `[for: clarity-message]` note.

Keep the language in the project's own domain; software framing only if the project is
software.

**Not applicable.** If a solution document clearly doesn't fit (for example the project only
needs its problem framed), propose N/A with the evidence; on the user's agreement set
`status: n/a` and a `reason:`. Never decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- **Called by `/clarity`:** don't mark anything complete. Return the drafts and the open gaps;
  `/clarity` confirms the stage.
- **Run directly:** show a short summary and ask for confirmation. On a clear yes, set
  `status: complete` on `solution.md` and write `reviewed.hash` (its body hash) and
  `reviewed.deps` (the body hash of each `depends_on` document). Body hash: run the manifest's
  `hash_command` with `FILE` replaced by the quoted path; never compute it any other way. The
  solution summary is confirmed after the architecture, since it depends on it.
- If you edited a document that was already `complete`, leave its `status` and `reviewed` alone
  and tell the user which documents you touched.
- Then suggest `/clarity` to continue (failure analysis and architecture come next).

## Pitfalls

- **Stopping at the first workable idea.**
- **Designing something nobody can build** with the real team and timeline.
- **Losing observations** because they "belong to another process".

Adapted from microsoft/clarity-agent (solution-brainstorming.md), MIT License — see LICENSE.txt.
