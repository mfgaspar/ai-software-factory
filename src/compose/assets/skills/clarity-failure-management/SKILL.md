---
name: clarity-failure-management
description: Decide with the user what to do about each analysed failure mode. Write its management plan (strategy, interventions, accepted risk, monitoring), summarise the plans in failures.md, capture induced failures, and revise the solution or architecture when a plan changes them. Use after failure analysis.
argument-hint: "[failure modes to plan, default every one without a plan]"
---

# Failure management

Failure modes to plan (empty means every mode without a management plan):

```text
$ARGUMENTS
```

Analysis says what could go wrong and where you could intervene. Management decides **what
to do about it**: which interventions to build, what residual risk to accept, how to watch for
trouble. It is a collaborative design exercise with real tradeoffs (cost against risk,
friction against safety, quick fixes against robust ones), and plans may change the solution
or architecture, slightly (a line of UX text) or deeply (rethinking the approach).
**Always propose a strategy and discuss it before writing a plan.** The user knows the
organization, the acceptable cost and the stakeholders' priorities.

Writes the Management plan section of each `.clarity/failures/failure-NN-*.md`, the
Management plans section and index entries of `.clarity/failures/failures.md`, induced
failures as new brainstorm files, and, when a plan requires it, edits to the solution,
architecture, stakeholders or requirements.

## Principles

1. **Tension with the problem means clarify the problem.** If managing a failure seems to
   contradict the problem statement, go back to basics with that failure in view: what does
   each stakeholder *really* need here? A restated requirement often dissolves the tension
   (run `clarity-problem` for it). If two stakeholders genuinely want opposite things, the
   user decides (compromise, or favour one); record it with `clarity-decision`. Rarely the
   whole approach proves impossible: write that up plainly; it saves everyone a dead end.
   The deeper the change, the more you re-check that the problem is still solved.
2. **Be flexible about what a plan is.** Change the system, prepare incident response, or
   change how you communicate (UX text, documentation, marketing). Fixes often land far from
   where the problem shows: most privacy problems are a mismatch between what users expect
   and what happens, fixed either way.
3. **The test is stakeholder sign-off on the total cost**: building and running the plan,
   plus the cost of the failures that still happen. Would every affected stakeholder accept
   it?
4. **Short-term and long-term can differ.** "Handle it manually if it happens" now and
   automation later is fine, if the short-term cost is acceptable. Say what would trigger the
   move.
5. **Plan for every failure; don't rank by severity times likelihood.** That product is
   noise, likelihood is hard to estimate, and at scale rare events are routine. Sequence
   work, if needed, by urgency and by the cost of the short-term mitigation.
6. **A new component gets a real design.** Incident response, monitoring, review queues
   and moderation tools are part of the solution. For incident response ask: who is called,
   how fast (a 5-minute SLA and a 1-business-day one are different jobs), do they have the
   information and the controls, can they reach others in time, can a tired person reach a
   "not bleeding" state at 3am, is there enough staff for the expected rate? Nearly every
   system needs some incident response for the unknown unknowns.

Apply the shared reasoning guidelines too: analyse the system as used, people included, and
care only about meaningful harm to non-adversarial stakeholders.

## Steps

1. **Read.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for `failures.md`'s
     `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-failure-management]`, then
     remove them.
   - `.clarity/failures/failures.md` and **every** failure document, planned or not:
     interactions matter.
   - `.clarity/goal/problem.md` (keep it in front of you), `.clarity/goal/stakeholders.md`,
     `.clarity/goal/requirements.md`, `.clarity/solution/solution.md`,
     `.clarity/solution/architecture.md` where they exist, and `.clarity/decisions/`.
2. **Survey.** List the modes needing plans: title, severity, one line each. Suggest where
   to start (severity, urgency, cheap short-term mitigations, interactions) and let the
   user choose. Don't spend longer choosing than starting would take.
3. **Look across all modes first**: shared intervention points and pinch points (one
   mechanism, several failures); conflicts (aggressive rate limiting against abuse locks out
   legitimate users); dependencies (managing A first, or managing A removes B). Note them;
   conflicts need an explicit tradeoff.
4. **For each mode** (or group planned together):
   1. Re-read the chain, its intervention points and the problem. Weigh each intervention
      for feasibility, effectiveness, cost (build, run, friction) and side effects.
   2. **Start from the prior state.** Pre-existing and not worsened: "keep handling as
      before" (should already be in Existing issues). Pre-existing but worsened: how is it
      handled today, and does that still hold? New: look for analogous failures today and how
      they are handled.
   3. **Propose a strategy** before writing: the overall approach, the key interventions and
      why, the main tradeoff, an alternative considered and why not. Layer prevention,
      detection, mitigation and recovery (prevention alone is brittle); acceptance is valid
      when intervention costs more than the failure. Wait for the user's view.
   4. **Assess residual risk**: what can still happen, how bad, and is it acceptable to
      each stakeholder? If not, strengthen the plan, record the tradeoff with
      `clarity-decision`, or, if it clashes with the problem, return to the problem
      (principle 1).
   5. **Write the plan** in the document's Management plan section, following the
      template's prompt there: strategy; planned interventions, each with its type and the
      chain steps it covers, split into short-term and long-term (with the trigger to move)
      when they differ; accepted risks, stated specifically ("an attacker with valid
      credentials can still…"); monitoring (signals, thresholds, who is alerted). Replace
      that section's placeholder.
5. **Update `failures.md`.**
   - In each managed index entry, replace "**no mitigation plan**" with a short strategy
     summary (for example "layered: validate inputs + anomaly alerts + automated
     rollback"). Change nothing else in the entry.
   - In **Management plans**, one line per mode: its strategy and residual risk, linked to
     its document. Note shared mechanisms that cover several modes. Replace the section's
     placeholder.
6. **Check for induced failures.** Does any intervention create a new way to fail? Rate
   limits lock out real users; heavy authentication drives people away; automated rollback
   oscillates; monitoring causes alert fatigue. Write each as a raw failure, in the format of
   `.compose/templates/clarity/failures/brainstorm/thinker.md`, to a new
   `.clarity/failures/brainstorm/induced-<n>.md` (the next free number; never overwrite),
   naming the failure mode whose plan induced it, and note the link in that mode's document.
   An intervention that adds a component needs at least the principle 6 questions answered
   in its plan.
7. **Carry changes upstream.** When a plan changes the solution or architecture (a new
   component, a changed flow, a new control), edit `.clarity/solution/solution.md` or
   `.clarity/solution/architecture.md` to match. New stakeholders, goals or requirements
   found along the way go straight into `.clarity/goal/stakeholders.md` or
   `.clarity/goal/requirements.md` (as new NFR-### or STD-### IDs, never functional
   requirements). Cite the failure
   document in what you add. If an edited document is already `complete`, leave its
   `status` and `reviewed` alone so `/clarity` re-confirms it, and tell the user which
   documents you touched and why.
8. **Record notable choices** (accepting a significant risk, favouring one stakeholder,
   choosing one intervention over another with real tradeoffs) as ADRs with the
   `clarity-decision` skill, or tell the user one should be recorded.
9. **Summarise**: per mode, severity, strategy in a sentence and residual risk; shared
   mechanisms; conflicts that need a decision; induced failures written; documents edited.

## Questions

Ask a person only what a person must answer: their intent and priorities, facts only they
hold (real users, numbers, deadlines, owners), a trade-off the material leaves open that is
theirs to own, a conflict the sources can't settle, and confirmations. Anything you can work
out from the sources, the code, the other `.clarity/` documents, earlier answers or
established practice, decide yourself: write it, mark it as inferred with where it came
from, and name it in your summary so the person can correct it. `/clarity` sets this out in
**Ask a person only what needs a person**.

## Rules

- No plan aims for zero residual risk; that breeds over-engineering and new failures. Name
  what remains.
- Check acceptability from every stakeholder's view, not only the builders'.
- "We'll page someone" is not an incident response plan.
- Plans evolve: re-run this skill when the system, threats or experience change.
- Remove every placeholder (`[TBD…]`, `[To be determined…]`, bracketed prompts) from the
  sections you fill. Keep HTML comments only where they help.
- Unattended (`/clarity` passed `auto`, `COMPOSE_RUN_ID` is set, or nobody is present): ask nothing. Draft each plan from the most
  defensible strategy, without waiting for the user's view, and list every unconfirmed
  strategy and accepted risk as an open gap.

## Finish

- **When `/clarity` called you**: don't mark anything complete. Return the draft, the open
  gaps, the induced-failure files (unabsorbed, so analysis and management may need another
  pass), and the documents you edited.
- **When run directly**: show the summary and gaps and ask the user to confirm
  `failures/failures.md`. On a clear yes, set `status: complete` and write `reviewed.hash`
  (this document's body hash) and `reviewed.deps` (the body hash of each `depends_on`
  document that exists; one that doesn't exist yet is left out, and `/clarity` re-confirms
  later). A body hash is the output of the manifest's `hash_command` with `FILE` replaced by
  the quoted path; never compute it any other way. Then suggest the next step: analysis
  again if induced failures were written, otherwise `/clarity` to continue (architecture
  comes next).
