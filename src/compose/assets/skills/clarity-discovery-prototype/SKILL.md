---
name: clarity-discovery-prototype
description: Answer one open question by building the smallest disposable prototype that tests a specific hypothesis, inside .clarity/prototypes/, then record the findings and resolve or update the question. Use for open questions whose strategy is "prototyping".
argument-hint: "[open question, e.g. 'Q2', default the first prototyping question]"
---

# Test an open question with a prototype

The question to test (empty means the first unresolved question with strategy `prototyping`,
blocking ones first):

```text
$ARGUMENTS
```

This is not solution design. It tests one hypothesis ("does X actually work?") with something
built only to produce a finding. The prototype is disposable; the finding is what matters.

## Before you start

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml` (paths and
   `hash_command`) and `.clarity/notes.md`. Act on items tagged
   `[for: clarity-discovery-prototype]`, then remove them.
2. Read the question in `.clarity/goal/open-questions.md`, its Findings so far, and just enough
   of `goal/problem.md`, `goal/stakeholders.md` and `goal/requirements.md` to test it
   meaningfully. Absorbing the whole project is a sign you're drifting into solution work.
3. Check the strategy fits. If careful reasoning can answer it, it belongs with
   `clarity-problem`; if it needs information gathered from outside, with
   `clarity-discovery-research`. Say so and propose changing its Strategy.

## Steps

1. **State a hypothesis.** Restate the question so it can be tested: "approach A handles
   volume V within latency L on infrastructure I." If it's too vague to test, sharpen it first.
2. **Define the experiment** and show it to the user before building:
   - the hypothesis, in one sentence;
   - **success**: an observable result that confirms it;
   - **failure**: an observable result that rejects it (decide this up front, or everything
     "sort of works");
   - what you will build: the minimum that produces one of those results;
   - what you will not build: error handling, edge cases, polish, production concerns.

   This is the contract that says when you're done. Set the question's `Status: investigating`.
3. **Scope ruthlessly.** Build only what tests the hypothesis. Thinking about maintainability
   or extensibility means you've drifted. If it grows past the agreed scope, stop and either fix
   the scope with the user or cut back. A "no" in thirty minutes beats a "sort of" in three days.
4. **Build it** in `.clarity/prototypes/<question-slug>/` (for example
   `.clarity/prototypes/q2-peak-volume/`) and nowhere else:
   - never import it from product code, and don't add it to the product's build, dependencies
     or tests; keep any dependencies local to that folder;
   - it need not be code: a traced design scenario, a mockup to try with users, a spreadsheet
     model, or a worked thought experiment all count.

   As you go, note surprises, new questions, the assumptions you had to make (future failure
   points), and whether this is still the right question. If it isn't, stop: that is a finding.
5. **Evaluate** against the criteria you set. Clear success or clear failure: record the
   evidence. Ambiguous: record what you learned and what would settle it. Wrong question:
   record the right one. Don't move the goalposts; a result short of the bar is a failure, and
   useful. For each outcome, say what it means for the solution approach.
6. **Record.**
   - Write the evidence into the question's **Findings**, briefly. Longer results (numbers,
     traces, how to rerun it) go in `.clarity/prototypes/<question-slug>/findings.md`, linked
     from Findings.
   - **Answered:** move the question to `.clarity/goal/resolved-questions.md` (copy the
     template from `.compose/templates/clarity/goal/resolved-questions.md` if missing, and drop
     its "none yet" line), keeping its fields, with its status set to resolved and a
     **Resolution** line.
   - **Ambiguous:** keep it in `open-questions.md` as `investigating`, with what would resolve
     it. Re-check whether it still has to be `Blocking: yes`.
   - **New questions:** add them to `open-questions.md` with all their fields.
   - If the finding changes the problem or requirements, update those documents too.

## Questions

Ask a person only what a person must answer: their intent and priorities, facts only they
hold (real users, numbers, deadlines, owners), a trade-off the material leaves open that is
theirs to own, a conflict the sources can't settle, and confirmations. Anything you can work
out from the sources, the code, the other `.clarity/` documents, earlier answers or
established practice, decide yourself: write it, mark it as inferred with where it came
from, and name it in your summary so the person can correct it. `/clarity` sets this out in
**Ask a person only what needs a person**.

## Unattended

`/clarity` doesn't run this skill in its `auto`, `draft` and `apply` phases: it asks a person
about each blocking question instead. If you are run with `auto`, with `COMPOSE_RUN_ID` set
or with no person present, ask nothing and build nothing. Write the experiment (hypothesis,
success and failure results, what to build) into the question's Findings, leave the question
open, and return it as a gap. Never resolve a question, set `status: complete` or write
`reviewed` hashes.

## Finish

- If you edited a document that was already `complete` (usually `open-questions.md`), leave
  its `status` and `reviewed` alone: the change shows as edited and gets re-confirmed. Tell the
  user which documents you touched.
- **Called by `/clarity`:** return the outcome, the question's new state, and any new
  questions. Mark nothing complete yourself.
- **Run directly:** show the finding and the resulting question list. If the user confirms
  `open-questions.md`, set `status: complete` and write `reviewed.hash` (its body hash) and
  `reviewed.deps` (the body hash of each `depends_on` document), each from the manifest's
  `hash_command` with `FILE` replaced by the quoted path. Then suggest `/clarity` to continue.
- A finding that forks the approach ("it works, but only with trade-off X") is a decision for
  `clarity-decision`.

## Pitfalls

- **Building the solution.** If the finding is positive, the real solution starts fresh; the
  prototype was built for speed of learning.
- **Moving the goalposts** or **skipping the failure criteria**: decide what failure looks like
  before building.
- **Prototyping what you could think through.** Only prototype genuinely empirical questions.
