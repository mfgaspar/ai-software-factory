---
name: clarity-failure-analysis
description: Turn the raw failures in .clarity/failures/brainstorm/ into a small set of failure modes, each with a failure chain, harm boundaries, intervention points and severity, and keep the failures.md index and cross-cutting patterns current. Use after brainstorming, or when new raw failures arrive.
argument-hint: "[brainstorm files or failure modes to focus on]"
---

# Failure analysis

Brainstorm files or failure modes to focus on (empty means every raw failure not yet
absorbed):

```text
$ARGUMENTS
```

Brainstorming gives a pile of things that could go wrong. Analysis turns it into an
understanding of **how** things go wrong: the sequence of events, the moment harm begins, and
where intervention is possible. Many raw failures share a mechanism ("SQL injection in login"
and "in search" are one failure: unvalidated input reaching an interpreter), so a tractable
set of failure modes results, usually ten or fewer. Look across them too: an intervention
point shared by several chains is a **pinch point**, where one mechanism addresses many
failures.

Writes:

- `.clarity/failures/failure-NN-<slug>.md`: one per failure mode, from the template
  `.compose/templates/clarity/failures/failure-mode.md` (the manifest's
  `helpers.failure_mode`). This skill fills everything above its Management plan section;
  failure management fills that section.
- `.clarity/failures/failures.md`: the validated index. If it doesn't exist, copy
  `.compose/templates/clarity/failures/failures.md` there, then fill its sections.
- `.clarity/observations.md`: an append-only log (from
  `.compose/templates/clarity/observations.md` if missing).

## Reasoning guidelines

These apply to brainstorming, analysis and management alike.

1. **Analyse the complete system, people included.** The object is the system *as used*.
   Operators make bad calls under pressure and fatigue; users have their own goals and mental
   models and route around what annoys them; organizations have communication gaps,
   misaligned incentives, thin staffing and knowledge that lives in one head; social harm
   (embarrassment, lost trust, exclusion) is harm. Don't stop at "the component fails": ask
   what the human does next, under what pressure, with what information. Keep in view the
   prior state (how the world works before this solution), adversarial and dual-nature
   stakeholders, and indirect stakeholders who may not know the system exists.
2. **Focus on meaningful harm.** A failure counts only if it causes meaningful harm to a
   non-adversarial stakeholder, in this system's actual context: a personal tool and a public
   service have very different failure landscapes. A violated principle that hurts nobody is
   not a failure mode; discard it at any stage. This is not a license to dismiss the
   unlikely: the question is "if this happens, does anyone get hurt?", not "how likely is
   it?". Someone harmed who isn't a listed stakeholder should be added.

## Steps

1. **Read.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the index's
     `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-failure-analysis]`, then remove
     them.
   - `.clarity/goal/problem.md`, `.clarity/goal/stakeholders.md`,
     `.clarity/solution/solution.md` and `.clarity/solution/architecture.md` where they
     exist.
   - The existing `failures.md` and every `failure-NN-*.md`.
   - `.clarity/observations.md`: every `Absorbed:` line lists brainstorm files a previous
     run already processed.
2. **Collect the new raw failures**: every `.clarity/failures/brainstorm/*.md` not listed on
   an `Absorbed:` line (or only those named in the arguments). If there are none and nothing
   is to be regrouped, say so and stop. Tell the user what you have: "N raw failures from these
   files, and M existing failure modes. I'll handle the obvious cases first, then we'll go
   through the rest together."
3. **Reduce automatically**, in this order, without asking:
   1. **Discard** raw failures with no meaningful harm in context (guideline 2), with a
      one-line reason each.
   2. **Prior-state triage.** Use the thinkers' pre-existing marks as a start, then judge.
      Pre-existing and not worsened: group into one **Existing issues** failure mode, whose
      plan is "keep handling as before"; it may span domains, since what unites it is the
      management, and needs no chain. Pre-existing but worsened, or new: keep, noting how the
      failure shows up today and what changes.
   3. **Deduplicate**: when two raw failures say the same thing, keep the more detailed one
      and note the other as its duplicate.
   4. **Merge into existing modes** when the mechanism is the same, the existing chain covers
      it with little change, and the group gets more complete, not less coherent. Add it to
      that document's Variants.
   5. **Cluster** the rest where a shared mechanism is clear: draft a name, summary, members
      and a first chain. Leave marginal cases separate.
4. **Show the reduction** transparently: what was discarded and why, what went to Existing
   issues, duplicates and what they duplicate, merges and into which mode, new clusters with
   their members, and how many remain for discussion. Ask whether anything should move or be
   undone, then write the Existing issues document and the drafted cluster documents.
5. **Work through the rest with the user.** Offer three activities, and offer them again
   after each:
   - **Discuss a raw failure.** Suggest a significant one (the user may pick another). Talk
     it through: is the description right, who is harmed and how, what is the sequence,
     where does harm begin and stop, where could the chain be broken? Draft the chain and let
     the user refine it. Then decide: a **new mode** (new document), a **variant** of an
     existing mode (add to Variants, extend the chain if it reveals steps), or **reject**
     (no real harm, or a duplicate; say why).
   - **Review a failure mode**: check the chain and grouping, split a group that holds
     genuinely different failures. If the user wants to decide what to do about a
     well-understood mode, run `clarity-failure-management` for it, then come back.
   - **Brainstorm more**: new ideas go to a new `.clarity/failures/brainstorm/human-<n>.md`
     (the next free number), in the format of
     `.compose/templates/clarity/failures/brainstorm/thinker.md`, and join the pool.

   Report progress after each ("N raw failures left, M modes so far"). The user may stop at
   any time: everything written so far stays, and a later run picks up the rest.
6. **Look for cross-cutting patterns** as modes accumulate: shared intervention points
   (pinch points), shared mechanisms (validation, rate limiting, audit logging) and cascades
   where one failure enables another. Mention each to the user when you notice it, with the
   architectural insight it suggests.
7. **Write the index** (see below) and **log** (see Observations). Then summarise: modes
   identified from how many raw failures, any left ungrouped, the main patterns.

## Failure chains

The core of the work; take time with it.

- Keep steps **as generic as possible**, keeping only the details that matter, so the chain
  covers every variant in the group.
- Mark the step where **harm begins**. A violated principle is not harm until someone is
  actually hurt.
- Continue past harm through recovery: mark where **harm ends** (no more damage is being
  done), and go on until the system settles.
- Show **branch points** (the post owner can delete a comment; another viewer can only hide
  it) and loops (harm recurring each time until something works).
- Note **when each actor becomes aware**. An operator who learns from the press learned late.
- Annotate steps inline with **intervention points** (prevention, detection, mitigation or
  recovery, with a first idea of how) and **observations** (why a step matters or is tricky).

Chains follow no rigid template: linear, branching, looping or short, whatever fits.

## Failure mode documents

For each mode, copy the failure-mode template to
`.clarity/failures/failure-NN-<slug>.md` (next free two-digit number, short kebab-case slug)
and fill it: the summary naming the stakeholders harmed and any variants; the chain; the
observations (severity, related failures, and variants citing their brainstorm file and
`RF-` number); and the intervention points collected by type. Leave the Management plan
section for failure management.

**Severity** is how bad things get when the failure occurs: Critical, High, Medium or Low,
with a line of reasoning. Never estimate likelihood or multiply severity by it: the product is
noise, likelihood is hard to estimate, and at software scale rare events happen constantly.
Plans will be made for every mode.

## The index: `failures/failures.md`

- **Failure modes**: one numbered entry per mode, in the format shown in the template's
  comment: linked title, severity in parentheses, what goes wrong (mechanism and trigger) and
  what it means for the stakeholders, then the management summary, or
  "**no mitigation plan**" until failure management has run. A reader should understand the
  mode without opening the document. Replace the template's "No failure modes have been
  analyzed yet" text.
- **Cross-cutting patterns**: pinch points, shared mechanisms and cascades, each naming the
  modes involved.
- **Management plans**: leave for failure management. Don't fill it here.

Update the index whenever a mode is created, changed or merged.

## Observations

Append to `.clarity/observations.md` (replace its "No observations have been recorded yet"
line the first time; afterwards never rewrite, only append). Add a dated section with:

- **Coverage**: the perspectives examined so far (thinkers and dates) and those still
  missing.
- **Provenance**: where modes came from and how raw failures were grouped, discarded or
  merged.
- **Pattern notes** that fit no single document.
- One line `Absorbed:` followed by every brainstorm file this run processed, as paths
  relative to `.clarity/` (for example `failures/brainstorm/security.md`). That line is how
  the next run knows what is new. List a file only when every raw failure in it is
  accounted for (grouped, merged or rejected with a reason).

## Not applicable

Rarely, failure analysis has nothing to work on: a throwaway experiment where nobody can be
harmed. Propose N/A with that evidence; only on the user's agreement set `status: n/a` and a
`reason:` in `failures.md`. Never decide N/A alone.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]`, bracketed prompts) from the
  sections you filled. Keep HTML comments only where they help.
- A grouping or severity call with real tradeoffs deserves an ADR: record one with the
  `clarity-decision` skill, or tell the user one should be recorded.
- If you edited a `complete` document (for example adding a harmed stakeholder to
  `goal/stakeholders.md`), leave its `status` and `reviewed` alone and tell the user which
  documents you touched.
- With no one to ask (`auto` mode), skip the interactive loop: make your best grouping and
  list the uncertain calls as open gaps.
- **When `/clarity` called you**: don't mark anything complete. Return the draft, the modes
  with no plan, and the open gaps; `clarity-failure-management` runs next.
- **When run directly**: show a short summary and the gaps. If every mode already has a
  management plan, ask the user to confirm; on a clear yes set `status: complete` and write
  `reviewed.hash` (this document's body hash) and `reviewed.deps` (the body hash of each
  `depends_on` document that exists; one that doesn't exist yet is left out, and `/clarity`
  re-confirms later). A body hash is the output of the manifest's `hash_command` with `FILE`
  replaced by the quoted path; never compute it any other way. Otherwise keep
  `status: draft` and suggest `/clarity-failure-management` next.

Adapted from microsoft/clarity-agent (processes/failure-analysis.md and
processes/failure-reasoning-guidelines.md), MIT License. See LICENSE.txt.
