---
name: clarity-decision
description: Help the user make an important choice well and record it as an ADR in .clarity/decisions/ with its index; accept, supersede or reconsider ADRs, and recheck accepted ones whose underlying documents changed. Use at any real fork, or when a past decision may need revisiting.
argument-hint: "[the decision to make, an ADR like 'ADR-003', or 'recheck']"
---

# Guide and record a decision

What the user asked for (a decision, an ADR to settle, or `recheck`):

```text
$ARGUMENTS
```

Decisions come up anywhere: in problem framing, solution, architecture, failure work, or just in
conversation. This isn't a phase; it's the tool for a fork that deserves careful thought. Each
decision is an ADR file `.clarity/decisions/ADR-NNN-<slug>.md`, listed in
`.clarity/decisions/index.md`. The index is the validated document; any ADR still `proposed` or
`reconsider` holds the project back until it is settled.

**ADR status:** `proposed` (analysis written, not yet chosen), `accepted` (the user chose),
`superseded` (replaced by a newer ADR, named in `superseded_by`), `reconsider` (its context
changed enough to revisit it).

## Before you start

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml`: the index's template,
   `helpers.adr` (the ADR template), and `hash_command`. Read `.clarity/notes.md` and act on
   items tagged `[for: clarity-decision]`, then remove them.
2. Read the index and the existing ADRs: earlier decisions may constrain this one, or be
   affected by it.
3. Read only the documents that bear on this decision (problem, stakeholders, requirements,
   solution, architecture, failures). A stakeholder-priority call doesn't need the
   architecture; a database choice doesn't need the whole problem statement.
4. If `.clarity/decisions/index.md` is missing, copy its template from
   `.compose/templates/clarity/decisions/index.md` and keep `status: draft`.

Ask only about gaps; don't re-ask what the documents already settle.

## Making a decision

Not every choice is a Decision. Routine or easily reversed calls are everyday judgment. Use this
when outcomes differ materially and the reasoning should survive.

1. **Clarify before choosing.** Lay out, sharply:
   - **the question**: "relational or document store for user profiles?", not "which
     database?";
   - **the criteria**: costs and benefits that matter (performance, complexity, familiarity,
     time, operating burden, flexibility, risk), most important first;
   - **the assumptions** taken for granted ("traffic stays under N for a year", "the team knows
     X"): the usual reason decisions need revisiting;
   - **the options**, each against the criteria, honestly: no buried downsides, no strawmen;
   - **a recommendation** if you have grounds for one, as input, not the decision.
2. **Write it down early.** Create the ADR (see **Files**) with `status: proposed` and the
   analysis so far, so an unfinished decision is still useful.
3. **The user decides.** They have context you lack: team, politics, risk appetite,
   experience. Make your case, then let them choose. Accept only on the user's explicit choice
   in this conversation; with no person present (an `auto` run), leave it `proposed`.
4. **Record the choice.** The Decision section gets what was chosen, by whom, and why it fits
   the criteria and assumptions. Consequences: what gets easier or harder. Reconsider when: the
   assumptions or criteria that would change it, plus any explicit review points ("after six
   months", "if the team passes five people"). Then **accept** it: set `status: accepted`,
   `date:` today (ISO), and `reviewed.hash` (the ADR's body hash) and `reviewed.deps` (the body
   hash of each `depends_on` document).
5. **Propagate.** Say which documents the decision changes (solution, architecture,
   requirements, other pending decisions) and update them or leave `[for: <skill>]` items in
   `.clarity/notes.md` for the skills that own them.
6. **Superseding.** When a new ADR replaces an accepted one, accept the new one, then set the
   old one's `status: superseded` and `superseded_by:` the new ADR's ID.

A decision the user wants to think about stays `proposed`, with the analysis and what is needed
to settle it. Push toward a choice; a well-documented set of options nobody picks only looks
like progress.

## Rechecking accepted decisions

Run this when asked (`recheck`), when `/clarity` sends an ADR in `reconsider`, or when you
notice a decision's basis has moved. For each accepted ADR:

1. Compute the current body hash of each `depends_on` document and compare it with
   `reviewed.deps`. Unchanged means nothing to do.
2. For a mismatch, read what changed in that document (with `git diff` when it is tracked) and
   judge whether it is **material**: does it change a criterion, break an assumption, add or
   remove an option, or hit a "reconsider when" condition? Most edits aren't.
3. **Not material:** re-record `reviewed.deps` with the current hashes (front matter only, so
   the ADR's body hash doesn't change) and tell the user in one line why it still holds.
4. **Material:** set `status: reconsider` and add a short dated note under "Reconsider when"
   saying what changed and why it matters. Then work it through with the user as a decision:
   reaffirm it (back to `accepted` with fresh `reviewed` hashes) or replace it with a new ADR
   and supersede the old one.

## Files

- **New ADR:** find the highest existing `ADR-NNN` number in `.clarity/decisions/`, take the
  next one, zero-padded to three digits (`ADR-001`, `ADR-002`…), and a short kebab-case slug
  from the title. Copy `.compose/templates/clarity/decisions/adr.md` to
  `.clarity/decisions/ADR-NNN-<slug>.md`, replace `NNN` and the title in its heading, set
  `date:`, and set `depends_on:` to the documents the decision rests on (paths relative to
  `.clarity/`). Fill every section and remove the placeholders.
- **Index:** keep one table row per ADR, linking the file, with its title, current status and
  date, in number order. Replace the index's "none recorded yet" sentence with one line on what
  the table holds. Update the row whenever an ADR's status changes.
- Body hash: run the manifest's `hash_command` with `FILE` replaced by the quoted path. Never
  compute a hash any other way.

**Not applicable.** If the project genuinely has no decision worth recording, propose N/A for
the index with the evidence; on the user's agreement set `status: n/a` and a `reason:`. Never
decide N/A alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft ADRs from the
sources and leave them `proposed`. Leave each gap as a `[TBD — …]` note. Never accept an ADR,
never set the index `complete`, and never write `reviewed` hashes.

## Finish

- **Called by `/clarity`:** don't mark the index complete. Return the ADRs written or changed,
  their statuses, and what's still open.
- **Run directly:** show the index and any ADR still `proposed` or `reconsider`, and ask the
  user to confirm the index. On a clear yes, set its `status: complete` and write
  `reviewed.hash` (its body hash) and `reviewed.deps` (`{}`, since it depends on nothing).
- If you edited a document that was already `complete`, leave its `status` and `reviewed` alone
  and tell the user which documents you touched.
- Return to the skill that raised the decision, or suggest `/clarity` to continue.

## Pitfalls

- **Treating every choice as a Decision.**
- **Analysis without resolution.**
- **Forgetting to propagate**: unreflected decisions create contradictions.
- **Treating decisions as permanent**: revisiting when the context changes is good stewardship,
  which is why "reconsider when" matters.

Adapted from microsoft/clarity-agent (decision-guidance.md), MIT License — see LICENSE.txt.
