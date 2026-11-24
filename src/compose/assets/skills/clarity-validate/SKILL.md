---
name: clarity-validate
description: Check that every mandatory clarity document in .clarity/ is complete, validly not applicable, unblocked and approved, and report PASS or FAIL with what is left and who must act. Reads only; changes nothing.
argument-hint: "[document paths to report on, default all]"
---

# Validate the clarity documents

Documents to report on (empty means all of them):

```text
$ARGUMENTS
```

This skill **reads only**. It never writes, fixes, or marks anything; it reports. Run it the
same way every time: the point is that two runs on the same files give the same answer.

## 1. Build the effective manifest

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml`. If it is missing, stop
   and report `CLARITY: FAIL (clarity is not installed)`.
2. Read the project config `.clarity/config.yml` if it exists (a missing or empty file means
   the shipped defaults). Apply it on top, in this order:
   - `documents`: add each custom document. It needs a `template` that exists, `depends_on`
     paths that exist in the manifest or in `documents`, and `required_sections`. Custom
     documents are mandatory unless `mandatory: false`, and allow N/A.
   - A shipped document with `mandatory: false` (such as `failures/fmea.md`) is optional:
     leave it out of the check unless `mandatory.add` names it.
   - `mandatory.add`: make those documents mandatory. `mandatory.remove`: drop them from the
     check. Removing a path listed in the manifest's `never_na` is a **config error**.
   - `not_applicable`: a map of path → reason, treated as if that document said `status: n/a`
     with that reason (see the conflict rule below).
   - `approvals`: a map of path or glob → list of approver names. `decisions/*` matches every
     ADR file.
   - `stale_fails`: `true` makes stale a failure; default `false`.
3. A config that isn't valid YAML, names an unknown document, or points at a missing template
   is a **config error**. Report every config error and fail; never ignore the config.
4. Order: the manifest's `walk_order`, with each custom document placed after its
   `walk_after` path (or at the end).

## 2. How to compute a body hash

Every hash in this skill is a **body hash**: run the manifest's `hash_command` with `FILE`
replaced by the document's path in single quotes, from the project root. It fingerprints the
text after the front matter, so editing front matter never changes it. Never compute or guess a
hash any other way.

## 3. Check each document

For each mandatory document in order, assign the
**first** state that applies, reading the document's front matter (the YAML between the first
two `---` lines):

1. **missing**: the file doesn't exist under `.clarity/`.
2. **n/a**: `status: n/a`, or listed in config `not_applicable`. It's valid only if the reason
   is non-empty and the document allows N/A (`allow_na`, and not in `never_na`). Otherwise
   report **invalid-n/a**, which fails. When the config lists a document and its front
   matter has another status, the front matter wins: go on down this list with that status,
   and note the mismatch under **Config**.
3. **draft**: any of the following.
   - `status` is `draft`, missing, or unknown.
   - Any of the manifest's `placeholder_markers` appears anywhere in the body.
   - A `required_sections` heading (`## <name>`) is missing.
   - A required heading has no text before the next heading.

   This applies even when the front matter says `complete`. List each gap.
4. **edited**: `status: complete`, but the body hash differs from `reviewed.hash`, or
   `reviewed.hash` is empty. Confirmed content changed and was not re-confirmed.
5. **blocked**: one of the following.
   - Questions (`kind: questions`): any question in the file that is not resolved and has
     `**Blocking:** yes`. Name each one.
   - Decisions (`kind: decisions`): any `ADR-*.md` file whose front matter `status` is
     `proposed` or `reconsider`. Name each ADR.
6. **unapproved**: approvers are configured for this path, or for a glob matching it or (for
   decisions) its ADRs. For each listed name, look for an entry in the document's `approvals`
   with that `by` and a `hash` equal to the document's current body hash. Name every approver
   without a valid approval. An approval with an old hash is **outdated**, not missing.
   An ADR's approvals are in its own front matter, against its own body hash; a
   `superseded` ADR needs none.
   An answered approval question in `.clarity/questions.yml` is also a valid approval, with
   the same hash rule: `kind: approval`, not `obsolete`, `answer: approve`, `answered_by`
   equal to its `approver` and to the listed name (`answered_at` is its date), and the hash
   recorded for this document under its `hashes` equal to the current body hash. Otherwise it
   doesn't count. Never read the file's other questions as approvals.
7. **complete**: none of the above.

Kind-specific completeness, checked as part of step 3 (draft):

- `kind: decisions`: complete also needs at least one `ADR-*.md` file listed in the index
  table.
- `kind: contract`: `spec` is optional; an empty or missing `spec` is fine. When the front
  matter `spec` is non-empty, it must name a file that exists (relative to `.clarity/` or the
  repo root) and is well-formed. For OpenAPI that means valid YAML or JSON with an `openapi`
  key; for GraphQL, a schema with at least one type. A named spec that is missing or bad
  counts as draft, with that reason.

Then, as a **separate** check for complete and edited documents, find the **stale** ones. A
document is stale when a document in `depends_on` has a current body hash that differs from the
one recorded in `reviewed.deps`, or that has no recorded hash. Name the changed dependencies.
Stale is a warning, unless `stale_fails: true`, in which case it fails. Do the same for each
accepted ADR's `depends_on` and list those ADRs under **Decisions to recheck** (a warning).

## 4. Report

Print one table, in check order:

| Document | State | Detail | Next |
|---|---|---|---|

- **State**: missing, n/a, invalid-n/a, draft, edited, blocked, unapproved, or complete. Add
  ", stale" when it applies.
- **Detail**: the specific gaps, the N/A reason, the blocking questions or ADRs, or the
  missing approvers.
- **Next**: the skill that fixes it (the document's `produced_by`, the strategy skill for a
  blocking question, `clarity-decision` for an ADR) or `clarity-approve` plus the approver's
  name.

Below the table:

- **Config**: whether `.clarity/config.yml` was applied, plus any mismatches or errors.
- **Decisions to recheck**, if any.
- One plain sentence on the most important next step.

The **last line** of the output is exactly one of:

```text
CLARITY: PASS
CLARITY: FAIL (<n> incomplete)
```

PASS means no config error, and every mandatory document is either complete or validly n/a,
with nothing missing, draft, edited, blocked, unapproved, or invalid-n/a, and nothing stale
when `stale_fails` is true. `<n>` counts the documents that fail, with each config error
counted as one. Print nothing after that line.

When the arguments name documents, print only their rows, but check every document and
count them all: the last line is always the verdict on the whole foundation.
