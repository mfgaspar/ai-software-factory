# Memory folder and constitution index

Date: 2026-11-24. Status: approved.

## Intent

Today, in a repo with a clarity foundation, the feature skills (`compose-specify`,
`compose-plan`, `compose-tasks`, `compose-analyze` and the others) learn the application's
rules from two places: the constitution, which a model rewrites from the clarity documents
on every clarity run, and the `.clarity/` documents themselves, which the skills also open
directly. The same rules reach them twice, once paraphrased, and the constitution is only a
small part of what a feature needs.

The change: `.clarity/` becomes the workshop, where the foundation is drafted, questioned
and approved. `.compose/memory/` becomes the published result, and the only place the
`compose-*` skills read from. The constitution becomes an index: one entry per memory file,
saying what the file holds and when to read it. A coding agent always reads the index and
opens a memory file only when the step it is running needs it.

## Goals

- The `compose-*` skills never open `.clarity/`. Everything a feature step needs is in
  `.compose/memory/`.
- The constitution is a short index: for each memory file, what it holds, when to read it,
  and whether it is binding or a draft.
- Approved text reaches feature work unchanged: no paraphrase between what a person
  confirmed and what the agent follows.
- Agents load only what a step needs, so the foundation doesn't fill the context on every
  step.

## Non-goals

- No change to how clarity documents are drafted, questioned, validated or approved.
- No change for repos without clarity: the constitution stays the hand-written principles
  file `/compose-constitution` maintains, and the skills use it as today.
- No rules written out in the constitution itself. Decided in the conversation: the index
  entries, with a fixed "read at" step for the files that must never be missed, are enough.
- No distilled or rewritten topic files (see Approaches). If some memory files prove too
  long in practice, a distilled version of just those can be added later.
- The setup changes (asking which documents are mandatory, dynamic or static config, fuller
  config comments) are a separate design, to follow this one.

## Anti-goals

- A memory file that differs in wording from the approved clarity document.
- A rule a feature breaks because the agent decided not to open the file that holds it.
- Memory on the default branch that is out of step with the `.clarity/` it came from.

## Constraints

- compose never edits `.clarity/` outside the clarity skills; publishing only reads it.
- Memory reaches the default branch only as it does today: generated on the clarity branch,
  merged when validation passes.
- The feature-run preflight keeps working the way it does: it compares the fingerprint
  stamped on the constitution's first line with the default branch's `.clarity/`. It does
  not verify each memory file; hand edits to memory are not detected. (My call.)
- Publishing is deterministic and costs no model call.

## Approaches

1. **Mirror (chosen).** compose copies each clarity document into `.compose/memory/`,
   stripping only the clarity bookkeeping, and builds the index from metadata in the
   manifest. Nothing is paraphrased, it is free and instant, and it can be tested exactly.
   The cost: files keep clarity's shape, so some are longer than a feature step needs.
2. **Distil by topic.** A skill rewrites the documents into purpose-built files (`nfr.md`,
   `tech-stack.md`, `goals-and-users.md`) and writes the index. Compact, but every run costs
   model time and a rewrite can drift from what was approved, which is hard to check.
3. **Index into `.clarity/`.** The constitution points straight at the clarity documents.
   Dropped: the compose skills are to stop reading that folder.

Mirror was picked because approved text reaches the feature steps unchanged.

## Design

### What gets published

Publishing takes every Markdown file under `.clarity/` whose front matter declares a
`status` (what `compose/clarity/summary.py` already lists), and for each:

- `status: complete` or `draft`: copied to `.compose/memory/<same path as under .clarity/>`,
  for example `.compose/memory/goal/requirements.md`. Keeping the tree keeps relative links
  between documents working.
- `status: n/a`: not copied. The index lists it under "Not applicable" with its reason.
  A document `.clarity/config.yml` marks `not_applicable` that has no file is listed the
  same way.
- ADRs (`decisions/ADR-*.md`): only `accepted` ones are copied. `decisions/index.md` is
  copied as a document.

A copy is the document's body, byte for byte, with the front matter replaced by one comment
line: generated from `.clarity/<path>`, its status, do not edit. The body hash of a memory
file therefore equals the body hash of its source, which is how tests check it.

Publishing uses the **declared** status and does not repeat the validator's checks. (My
call.) That is safe because memory reaches the default branch only after validation passes,
and a document that declares `complete` but fails validation stops the merge. On the clarity
branch before a PASS, a standing may overstate; feature runs don't read that branch.

When `contracts/api.md` names a published API in its `spec:` front-matter field, the index
row for that file carries the spec's path. A spec file that lives under `.clarity/` is
copied to the same relative path in memory, so `compose-plan` can open it. (My call.)

A broken `.clarity/config.yml` fails the step with the YAML error. A document the manifest
lists that has no file is skipped.

Companion files are not published (`questions.yml`, `config.yml`, `observations.md`,
`goal/resolved-questions.md`, brainstorm and prototype folders), with one exception:
`compose-specify` uses the `## Feature ideas` section of `notes.md`, so that section alone
is published as `.compose/memory/feature-ideas.md` when it exists and isn't empty. (My call.)

Publishing keeps a list of the files it wrote (`.compose/memory/.published`). On the next
run it removes the listed files it no longer produces, and leaves alone anything else
someone put in the folder. (My call.)

### The index

`.compose/memory/constitution.md` is generated in full:

1. First line: `<!-- memory-index: <fingerprint> -->`. This is a **new** marker, so an
   index can be told from an old, model-written constitution, which carries
   `generated-from-clarity`.
2. A title and a short "how to use this" paragraph: read this file at every step; open the
   files whose "Read" column names your step; open the others when their "when" fits the
   feature; `binding` files are rules, `draft` files are assumptions to mark as such.
3. One table row per published file: **File** (a relative link), **Holds**, **Read**,
   **Standing**.
4. A "Not applicable" list: document and reason.

**Holds** and **Read** come from the manifest. Each document entry gains a `memory` block:

```yaml
goal/requirements.md:
  memory:
    summary: "Non-functional requirements, constraints and standards every feature must meet."
    read_at: [plan, tasks, analyze]      # steps that always open it
    read_when: ""                        # otherwise: a condition in plain words
product/ux-standards.md:
  memory:
    summary: "UI conventions: layout, states, accessibility, wording."
    read_at: [analyze]
    read_when: "the feature has a user interface"
```

Step names are the feature steps: `specify`, `clarify`, `plan`, `tasks`, `implement`,
`analyze`. Each skill that reads the constitution today uses one of them: `compose-converge`
and `compose-bug-fix` read as `implement`, and `compose-clarify` reads what `specify` reads.
`implement` always opens `goal/requirements.md`, and the architecture when it exists.
`compose-converge`'s check of "the constitution's MUST and SHOULD principles" becomes a
check against the binding rules in the files `implement` reads (NFR, CON, STD, accepted
ADRs). `compose-checklist` and `compose-bug-assess` don't read the constitution today and
don't change. (My call.) Custom documents declare the same block under `documents:` in
`.clarity/config.yml`; without one, the summary is the document's first heading and the row
reads "when relevant". `analyze` is in every shipped document's `read_at`, as the backstop.

The shipped `read_at` values follow what each step reads today (the table in
`templates/compose/clarity.md`): specify reads problem, stakeholders, PRD and requirements;
plan reads architecture, decisions, requirements, failures, and API, data, UX and setup
conventions when they apply; tasks reads failures, requirements and the setup guide.

**Holds** also lists the rule IDs found in the file (for example `NFR-001…NFR-014,
CON-001…CON-006`), found by pattern, so an agent chasing a cited ID knows which file to
open. (My call.) Accepted ADRs get one row each, with the ADR's title as the summary and
`read_when` "the feature touches this decision".

**Standing** is `binding` for a `complete` document or an `accepted` ADR, `draft` for a
draft document, and `ideas` for `feature-ideas.md` (read at `specify`; suggestions, not
rules).

### When it runs

A new built-in clarity step action, `publish-memory`, replaces both the
`compose-constitution from-clarity` command step and the `stamp-constitution` action, in the
`clarity` and `clarity-validate` workflows. It writes the folder and stamps the index in one
go. The clarity branch commits `.compose/memory/` as a whole (today it commits only the
constitution file).

- `clarity` workflow: order unchanged: publish, validate, record the verdict, commit, merge
  on PASS.
- `clarity-validate` workflow: validate, record the verdict, then publish whenever the
  result is PASS. Today's "only when the constitution isn't current" condition goes:
  publishing is free and writes nothing when nothing changed, and running it always picks
  up a compose upgrade that changes the shipped index metadata. (My call.)

The code lives in a new module beside `compose/clarity/constitution.py` (which keeps the
marker reading the preflight uses). `compose clarity status` keeps reporting whether the
constitution is current.

### The skills

Every `compose-*` skill that reads the constitution today keeps doing so, and gains one
rule: when the constitution is an index (it starts with the `memory-index` marker),
open the files whose **Read** column names this step, and any other whose "when" fits the
feature; follow `binding` files, and mark anything taken from a `draft` file as an
assumption. When it isn't an index, behave as today.

All references to `.clarity/` paths, and to the `clarity.guide`, come out of the
`compose-*` skills. `templates/compose/clarity.md` is rewritten as the memory guide: it
keeps the standing rules, how to cite clarity IDs in specs and plans, and what to do on a
conflict, and it names memory files instead of clarity documents. The plan's "Clarity
check" stays, run against the binding files the index tells plan to read.

`/compose-constitution` loses its `from-clarity` mode. In a repo whose constitution carries
either marker, it explains that the file is generated and that changes belong in the clarity
documents. Elsewhere it works as today.

### Existing repos

A repo whose constitution carries the old `generated-from-clarity` marker has no memory
files, and the skills no longer read `.clarity/`, so a feature run there would work with
less than it has today. The preflight therefore accepts only the `memory-index` marker in a
clarity repo, and refuses a feature run with the fix it already gives ("The constitution is
out of date with clarity", `compose clarity validate`). One `compose clarity validate` run
publishes memory and clears it. (My call; no separate migration command.)

## Left to the builder

- The exact wording of the index header and the generated-file comment.
- The exact `summary`, `read_at` and `read_when` for each shipped document, following the
  current per-step table.
- The ID patterns used for the "Holds" column.
- Whether `compose feature paths --json` keeps its `clarity` entry for API compatibility;
  the skills no longer use it. A `memory` entry (folder and index path) may be added.
- Tests: body-hash equality of each copy, the index rows for each status, removal of stale
  files, the marker, and that no `compose-*` skill mentions `.clarity/`.
- Docs: `docs/clarity.md`, `docs/workflow-reference.md` and the README where they describe
  the constitution step.
