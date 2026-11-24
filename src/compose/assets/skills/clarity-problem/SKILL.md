---
name: clarity-problem
description: Turn a vague idea into a clear problem statement, stakeholder map, testable non-functional requirements, constraints and standards (NFR/CON/STD) and a list of open questions in .clarity/goal/. Use at the start of a project, when the team isn't aligned on the problem, or to think through a "thinking"-strategy open question.
argument-hint: "[what to clarify, or an open question like 'Q2' to think through]"
---

# Clarify the problem

What the user asked for (it may be empty, a topic, or an open question to think through):

```text
$ARGUMENTS
```

Knowing what to build and why is the hard part. This conversation sharpens the problem, finds
everyone who cares about it, and pins down the rules any solution must follow. It writes the goal
documents under `.clarity/goal/`: `problem.md`, `stakeholders.md`, `requirements.md` and
`open-questions.md` (resolved questions move to `resolved-questions.md`). Stay domain-neutral:
the project may not be software.

If the arguments name an open question (or `/clarity` sent you one with strategy `thinking`),
skip to **Thinking through an open question** below.

## Before you start

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml` for each document's
   `template`, `required_sections` and `depends_on`, and its `hash_command`.
2. Read `.clarity/notes.md`. Act on items tagged `[for: clarity-problem]` during the relevant
   step, then remove them. Untagged items are guiding principles.
3. Read the goal documents that exist, each one's front matter `sources`, and anything else in
   `.clarity/` or the repo that already speaks to the problem (README, supplied documents, code).
   If a document only holds template placeholders this is a first pass; otherwise you are
   refining: look for gaps, vagueness and staleness.
4. For each missing document, copy its template from `.compose/templates/clarity/` (the
   manifest's `template` field) and keep `status: draft`.

Ask **only** about gaps and conflicts. Never re-ask what the documents, sources or code already
answer; state what you inferred and move quickly through what's obvious. Save rough drafts as
you go.

## Steps

1. **The why.** What happens if this isn't solved? What's the current workaround and why isn't
   it good enough? Why now? Who feels the pain?
2. **Pressure-test the framing, once.** The stated goal is often a *means* to a goal one level
   up. Ask one of: "If this were already done, what could you do that you can't today?", "What's
   the worst version that would still count as success?", "Is this the goal or the route to it?"
   Probe harder when the goal names an artifact ("a dashboard", "a rewrite") while the why names
   an outcome. If a higher goal surfaces, say so and let the user choose; never swap silently. If
   they keep their framing, record both. Note in `problem.md` that the framing was examined. Say
   why you ask if they push back: you want to help with the right thing.
3. **Separate problems from solutions.** Detailed "requirements" are often someone's solution.
   Acknowledge it, ask what problem it solves, and record the need ("timely awareness of schedule
   slips"), not the mechanism ("hourly email"). Compatibility with an existing workflow can be a
   real requirement; record it as one. Functional behaviour ("users can export a report") is not
   a requirement here: each feature's specification defines it later (`compose-specify`). Note
   it in `.clarity/notes.md` under a `## Feature ideas` heading, one line each, and move on.
   With non-technical stakeholders:
   - ask for outcomes, not implementations, and have them decide concrete edge cases;
   - classify constraints: permanent or temporary, critical or nice-to-have, impossible,
     expensive or merely difficult;
   - translate loaded words: "must" (what if it fails 0.1% of the time?), "best practice"
     (what's the risk if we don't?), "secure" (against what, and what does a breach cost?).
4. **Stakeholders.** Probe primary (who uses it, pays for it, maintains it), secondary (who is
   affected, compliance, auditors) and hidden (who'd be upset if it went wrong, who approves,
   which experts matter). Classify each:
   - **aligned** (the builder wants them to succeed) or **adversarial** (the builder wants them
     to fail: attackers, spammers, scrapers). Actively ask who might misuse the system or gain
     from its failure. One person can be **dual**: record both personas;
   - **direct** (knowingly uses it) or **indirect** (affected without choosing to, like people
     who appear in someone else's photos). Ask whose data is in it without their knowledge and
     who gets hurt besides the users.

   For each: characteristics, goals (for adversaries, what they try to achieve against the
   system), concerns (for indirect stakeholders, the harms that could reach them).
5. **Scope.** What is explicitly out? Which related problems aren't being solved? Where does
   this end and other systems begin? What can be assumed to exist?
6. **Requirements.** The rules every feature must follow: which quality attributes matter
   (non-functional requirements), what limits the solution must live within (constraints), and
   which engineering standards apply (coding, testing, security, review). Each one is testable
   or checkable, necessary ("what happens without it?") and traceable to a stakeholder or
   problem aspect. Sweep every category, see **Covering the requirements**: these rules are
   what each feature is built and reviewed against, and a missing one gets decided again,
   differently, in every feature.
7. **Discovery check.** Are there fundamental unknowns that would change the solution approach?
   Signs: many solution paths hinging on unknown facts, "it depends on whether X" with nobody
   knowing X, stakeholders disagreeing about facts rather than priorities. Most projects pass
   quickly. See **Open questions** below. Unknowns don't stop the conversation; they make some
   success criteria conditional ("if X, success is A; otherwise B").
8. **Conflicts and trade-offs.** Opposing stakeholder needs, requirements that pull against each
   other (security vs. usability), and how to prioritize. A conflict that needs a real choice
   goes to `clarity-decision`.
9. **Success.** How will you know it works, for each stakeholder? What's good enough vs.
   perfect? Then sharpen fuzzy criteria (see below).
10. **Write the documents** (see **Writing**), then play back your understanding in a few
    lines: the problem in one sentence, the key stakeholders, the top must-haves. Ask what's
    wrong or missing, and iterate.
11. **First summary.** If `.clarity/summary.md` doesn't exist or still holds its template
    placeholders, offer a first version focused on the problem: a few conversational paragraphs
    that make a smart friend care (what's broken, a spark of the idea, why it matters). No
    bullet specs. Show it, adjust the tone, then write it with `status: draft`.
    `clarity-message` refines and confirms it later.

### Covering the requirements

Go through each category below. For each one, write the rule, or raise the gap, or leave it
out because it truly doesn't matter here. Don't skip a category because the sources are
silent: silence is where features later disagree.

- **Non-functional requirements**: performance and capacity, reliability and data loss,
  security (what input is untrusted, what must never leak or run), privacy, accessibility,
  compatibility (browsers, devices, versions), operability, maintainability.
- **Constraints**: the stack and what may or may not be added to it (languages, frameworks,
  dependencies, build steps), where it runs, what it may talk to, time, budget and team.
- **Standards**: how code is written and structured, what is tested, at which level and with
  which tool, how security is handled in code, what a review checks, what is documented.

A rule the sources imply but don't state still gets written, marked as inferred, so a person
can correct it: a page that shows text people typed needs a rule that the text is never run
as markup. A rule nobody has chosen ("no accessibility standard for now") is not a
requirement: leave it out and record the choice in `.clarity/notes.md`. When the project's
setup has no solution or architecture document, the constraints and standards here are all
a feature gets: put the stack and the structural rules here.

### Fuzzy criteria

Push hardest when the criteria decide whether the solution is acceptable, when others must apply
them, or when a step expects someone to "just know" what another intends.

- **Outrageous examples.** Propose cases that technically satisfy a vague criterion but clearly
  shouldn't ("30 seconds is fast?", "instant for one user, five minutes for ten?"). The answers
  reveal the real criterion.
- **Criteria for decisions at scale.** Agree on what the criteria are for; write them as the
  deciders will see them; generate clear, gray-area and edge-case examples and have the author
  decide each (help make examples, never steer the answers); have people like the real deciders
  judge them blind ("uncertain" is allowed); iterate until they agree with each other and the
  author. Expect at least three rounds. Keep the final criteria and the decided examples as
  their test cases.
- **Detecting magic.** If a step assumes someone will know something without being told, flag
  it and ask how they will actually know.

### Open questions

Write each fundamental unknown into `goal/open-questions.md` under `## Questions`, one
`### Q<n>: <sharp question>` subsection each, with the fields the template's comment lists:

- **Status**: `open` or `investigating`.
- **Strategy**: `prototyping` (try it to see if it works), `research` (gather information that
  doesn't exist yet) or `thinking` (reachable by discussing what is already known).
- **Blocking**: `yes` when solution work must wait for the answer, otherwise `no`. Be honest:
  a blocking question stops the project from passing until it is resolved.
- **Why it matters**: the decisions or solution paths it holds up.
- **Findings**: what has been learned so far.

Be specific: "Can we process our peak volume within a second?" is actionable; "Is this
feasible?" is not. If the uncertainty is pervasive (people want *something* but nobody knows
what), don't list questions: say the project is in an exploratory phase, so the solution should
be built for rapid experimentation. If no unknowns surfaced, the common case, replace the
placeholder with one sentence saying the problem is clear enough to proceed.

Never mark a question resolved in place. Move it to `goal/resolved-questions.md` (copy that
template from `.compose/templates/clarity/goal/resolved-questions.md` if missing, and drop its
"none yet" line), keep its fields, set its status to resolved and add a **Resolution** line. If
the answer changes the problem, update the goal documents too.

## Thinking through an open question

For a question with strategy `thinking`:

1. Read the question, its Findings so far, and the goal documents it touches.
2. Restate what exactly must be decided or known, and what is already known that bears on it.
   Work through it with the user: lay out the considerations, test candidate answers against
   the problem and requirements, and surface hidden assumptions. Ask only what you can't infer.
3. Record what you learn in its Findings as you go, and set `Status: investigating`.
4. If it is answered, move it to `resolved-questions.md` with its Resolution, and update the
   problem, requirements or success criteria it changes. If it turns out to need evidence,
   change its Strategy to `prototyping` or `research` and say so. If it stays open, say what
   would settle it, and whether it still has to block.
5. A choice between options with real trade-offs is a decision: hand it to `clarity-decision`.

## Writing

Fill each template's sections and remove every placeholder (`[TBD…]`, `[To be determined…]`
and the other bracketed prompts) from what you fill. Keep the HTML comments only where they
still help. Synthesize: ten minutes of talk is still two paragraphs. Don't transcribe a
source either: a brief repeated in other words adds nothing. Write what it implies and what
it leaves out, and keep remarks about the process ("not yet examined with the user") out of
the documents: they go in `.clarity/notes.md` or in a question.

- `goal/problem.md`: the problem and its context, why it matters (what the workaround costs
  and who pays), scope in and out, and the success criteria as a list, one per line, each
  saying how it is checked.
- `goal/stakeholders.md`: one subsection per stakeholder with type, engagement,
  characteristics, goals and concerns, in the template's shape. Dual stakeholders get one
  subsection per persona.
- `goal/requirements.md`: non-functional requirements as `NFR-001`, `NFR-002`… grouped by
  category, each with a measure and the stakeholder who needs it; constraints (technical,
  business, organizational) as `CON-001`…; engineering standards as `STD-001`…, each a MUST or
  SHOULD rule checkable in a review. No functional requirements: those go to `## Feature ideas`
  in `.clarity/notes.md`. IDs are stable: never renumber or reuse one; mark a dropped
  requirement as withdrawn instead.
- `goal/open-questions.md`: as above.

Add `sources:` entries for any supplied material you drew on. Record anything another stage will
need in `.clarity/notes.md` as a `[for: <skill>]` item.

**Not applicable.** Problem and requirements always apply. If stakeholders or open questions
clearly don't fit the project, propose N/A with the evidence; on the user's agreement set
`status: n/a` and a `reason:`. Never decide N/A alone. For open questions, "none found" is
usually better than N/A.

## Questions

Ask a person only what a person must answer: their intent and priorities, facts only they
hold (real users, numbers, deadlines, owners), a trade-off the material leaves open that is
theirs to own, a conflict the sources can't settle, and confirmations. Anything you can work
out from the sources, the code, the other `.clarity/` documents, earlier answers or
established practice, decide yourself: write it, mark it as inferred with where it came
from, and name it in your summary so the person can correct it. `/clarity` sets this out in
**Ask a person only what needs a person**.

## Unattended

`/clarity` runs this skill unattended in its `auto`, `draft` and `apply` phases, and passes
`auto`. Work the same way whenever `COMPOSE_RUN_ID` is set or no person is present. Ask
nothing. Draft from the sources, the code and the other documents, drafts included. Fill
what you can work out yourself (see **Questions**), marked as inferred, and leave a
`[TBD — <what's missing or conflicting>]` note only for what a person must answer, in the
section it belongs to,
and propose any N/A only as a note. Never set `status: complete` or `n/a`, and never write
`reviewed` hashes. Return the draft and its list of gaps: `/clarity` turns them into
questions for a person.

Do the thinking of steps 1–9 yourself, from the sources, instead of asking: what they imply,
what they leave out, who else is affected. Where they name an artifact as the goal while the
why names an outcome, keep their framing and note the higher goal as a `[TBD — …]` for a
person to choose; otherwise say nothing about the framing. Sweep every category of
**Covering the requirements**: write the rules the sources imply, marked as inferred, and
leave a `[TBD — …]` for each one that needs a person's choice. Skip step 11:
`clarity-message` drafts the summary.

## Finish

- **Called by `/clarity`:** don't mark anything complete. Return the drafts and the list of open
  gaps (including any blocking questions); `/clarity` confirms the goal stage.
- **Run directly:** show a short summary of each document and ask for confirmation. On a clear
  yes, for each confirmed document set `status: complete` and write `reviewed.hash` (its body
  hash) and `reviewed.deps` (the body hash of each `depends_on` document). Body hash: run the
  manifest's `hash_command` with `FILE` replaced by the quoted path. Never compute a hash any
  other way.
- If you edited a document that was already `complete`, leave its `status` and `reviewed` alone
  (it becomes edited and gets re-confirmed) and tell the user which documents you touched.
- Then suggest the next step: a blocking question goes to `clarity-discovery-prototype`,
  `clarity-discovery-research` or another pass here; otherwise `/clarity` to continue.

## Pitfalls

- **Accepting the framing.** Run the framing test even when the goal sounds concrete,
  especially then.
- **Jumping to solutions.** "That's one possible solution. What problem would it solve?"
- **Vague requirements.** "Fast" isn't a requirement; get a number ("NFR-003 — performance:
  search returns in under 1 s for 95% of queries").
- **Features as requirements.** "Users can share a list" is a feature idea, not a rule; note it
  for `compose-specify`.
- **Missing stakeholders.** Ask about every category, adversarial and indirect included.
- **Wants as needs.** Challenge each requirement: what happens without it?
- **Transcribing.** Capture the essence, not the conversation, and not the brief word for
  word.
- **Silent categories.** No security, stack or testing rule because nobody mentioned one.

You're done when the problem fits in one or two sentences people nod at, every stakeholder and
their needs are written down, the rules are sharp enough to judge solutions against, and
every "why?" has an answer.
