# Memory folder and constitution index — Implementation Plan

Date: 2026-11-24
Design: [../specs/2026-11-24-memory-index-design.md](../specs/2026-11-24-memory-index-design.md)
(approved 2026-11-24)

## How to use this plan

Milestones run in order: M2 needs M1, M3 needs M2's marker, M4 documents them all. Each one
ends green (`uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy
src`) and is committed on its own (`M<n>: …`). Nothing here calls a model: publishing is
plain Python, and the workflow tests use the fake engine.

## Layout (target)

```text
src/compose/clarity/memory.py                        # new: publish(workdir) -> PublishResult
src/compose/clarity/constitution.py                  # marker becomes memory-index; reads both
src/compose/clarity/branch.py                        # CLARITY_PATHS commits .compose/memory
src/compose/clarity/preflight.py                     # accepts only the memory-index marker
src/compose/clarity/service.py                       # status: constitution currency by new marker
src/compose/runner/steps/clarity.py                  # action publish-memory replaces stamp-constitution
src/compose/workflows/schema.py                      # CLARITY_ACTIONS, ClarityStep.action
src/compose/workflows/builtins/clarity/workflow.yml           # publish step
src/compose/workflows/builtins/clarity-validate/workflow.yml  # publish on PASS, always
src/compose/assets/templates/clarity/manifest.yml    # + memory: {summary, read_at, read_when} per document
src/compose/assets/templates/clarity/config.yml      # + memory block in the custom-document example
src/compose/assets/templates/compose/clarity.md      # rewritten as the memory guide
src/compose/assets/skills/compose-*/SKILL.md         # read the index; no .clarity/ paths
src/compose/assets/skills/compose-constitution/SKILL.md   # from-clarity mode removed
src/compose/assets/skills/clarity-configure/SKILL.md      # custom documents declare memory
tests/unit/test_clarity_memory.py (new); test_preflight.py, test_clarity_workflow.py,
  test_clarity_branch.py, test_clarity_assets.py, test_assets.py, test_cli_clarity.py,
  test_api_clarity.py (extended)
docs/clarity.md, docs/workflow-reference.md, docs/cli.md, README.md, docs/openapi.json
```

---

## M1 — The publisher

**T1.1 Manifest metadata.** In `templates/clarity/manifest.yml`, add a `memory` block to
every entry under `documents`:

```yaml
memory:
  summary: "<one sentence: what the file holds>"
  read_at: [<steps that always open it>]
  read_when: "<condition in plain words, or empty>"
```

Steps are `specify`, `clarify`, `plan`, `tasks`, `implement`, `analyze`. Take `read_at` from
the per-step table in `templates/compose/clarity.md` as it is today, plus the design's
rules: `clarify` gets what `specify` gets; `implement` gets `goal/requirements.md` and
`solution/architecture.md`; every document has `analyze`. Documents that apply only to some
features (`product/ux-standards.md`, `contracts/api.md`, `data/data-model.md`) keep `plan`
out of `read_at` and say when in `read_when` ("the feature has a user interface", "the
feature adds or changes an API", "the feature stores or changes data"). Add a top-level
`memory` section for what isn't a document: the row text for accepted ADRs
(`read_when: "the feature touches this decision"`) and for `feature-ideas.md`
(`read_at: [specify]`).

**T1.2 `compose/clarity/memory.py`.**

- `MEMORY_DIR = ".compose/memory"`, `PUBLISHED_LIST = ".compose/memory/.published"`,
  `STEPS` (the six names).
- `publish(root: Path, fingerprint: str) -> PublishResult` (`written`, `removed`,
  `not_applicable`). Raises `PublishError` on a broken
  `.clarity/config.yml` (carry the YAML message).
- Sources: every `*.md` under `root/.clarity` with a `status` in its front matter, using
  `summary.front_matter` and the same skipped folders. `complete`/`draft` are copied;
  `n/a` goes to the not-applicable list with its `reason`. Add the config's
  `not_applicable` entries that have no file. For `decisions/ADR-*.md`, copy only
  `status: accepted`.
- A copy is `<!-- generated from .clarity/<path> (<status>) by compose; do not edit -->`,
  a newline, then the body: everything after the closing front-matter `---` line,
  unchanged. Write with `runner.state.atomic_write`.
- Metadata for a path: the shipped manifest's `documents[path].memory`, overridden by
  `.clarity/config.yml` `documents[path].memory`. Missing: summary is the document's first
  `# ` heading, `read_at: []`, `read_when: "relevant"`. Unknown step names in `read_at`
  raise `PublishError`.
- `contracts/api.md` `spec:`: when set, add it to that row. When it resolves to a file
  under `.clarity/`, copy that file to the same relative path under memory.
- `notes.md`: when it has a non-empty `## Feature ideas` section, write
  `feature-ideas.md` with the header comment and that section.
- Rule IDs for the Holds column: `re.findall(r"\b([A-Z]{1,5})-(\d{3})\b", body)`, grouped
  by prefix in first-seen order, shown as `NFR-001…NFR-014` (a single ID shows alone).
  Skip the `ADR` prefix outside ADR files, and `Q`.
- Index, written to `constitution.md`: the marker line, `# Project memory`, the how-to-use
  paragraph, the table (File as a relative Markdown link, Holds, Read, Standing), then
  `## Not applicable`. Rows follow the manifest's `walk_order`, then custom documents,
  ADRs by number, then `feature-ideas.md`. Read shows `always at: plan, tasks` and/or
  `when: …`. Escape `|` in cell text.
- `.published`: one relative path per line, sorted, including `constitution.md`. Before
  writing, read the old list and delete listed files that this run doesn't produce; remove
  directories left empty. Paths in the list that point outside `MEMORY_DIR` are ignored.

Tests (`test_clarity_memory.py`), on a temp git repo built with `clarity_helpers`:

- each copy's body hash equals its source's (`git hash-object` over the body);
- complete → `binding`, draft → `draft`, n/a → not copied and listed with its reason,
  config-only N/A listed;
- a `proposed` ADR is not copied, an `accepted` one has its own row;
- `read_at` and `read_when` reach the Read column; a custom document's config `memory`
  wins; a document with none gets its heading and "when: relevant";
- ID ranges in Holds;
- `spec:` outside `.clarity/` appears in the row; inside it, the file is copied;
- `feature-ideas.md` appears only with a non-empty section, standing `ideas`;
- a second publish after a document becomes n/a removes its copy and updates `.published`;
  a hand-added `memory/own.md` survives;
- publishing twice with no change writes byte-identical files;
- broken config YAML raises `PublishError`; an unknown step name raises it too.

## M2 — Wire it into clarity runs

**T2.1 Marker.** `constitution.py`: `marker()` and `stamp()` write
`<!-- memory-index: <fingerprint> -->`. `read_text`/`read_ref` return the fingerprint only
for the new marker. Add `is_legacy(text) -> bool` for the old `generated-from-clarity` line.
`memory.publish` writes the marker itself; keep `stamp` only if something else still needs
it, otherwise remove it.

**T2.2 Step action.** `workflows/schema.py`: replace `stamp-constitution` with
`publish-memory` in `CLARITY_ACTIONS` and `ClarityStep.action`. `runner/steps/clarity.py`:
`publish-memory` computes `fingerprint.of_dir(workdir)`, calls `memory.publish`, returns
`Outcome.ok(fingerprint=…, written=len(...), removed=len(...))`, and
`Outcome.failed(str(exc))` on `PublishError`. `record-verdict` keeps returning
`constitution_current` (now by the new marker).

**T2.3 Workflows.**

- `clarity/workflow.yml`: replace the `constitution` command step and the `stamp` step with
  one step, `id: memory`, `name: Publish the memory files`, `type: clarity`,
  `action: publish-memory`. Update the description. Bump the version to 1.1.0.
- `clarity-validate/workflow.yml`: replace `constitution-check` with an `if` on
  `steps.verdict.output.result == 'PASS'` holding the same single step. Bump the version.

**T2.4 Commit paths.** `branch.CLARITY_PATHS = (".clarity", ".compose/memory")`. Check
`commit_paths` stages deletions under both (a removed memory file must leave the tree) and
the dirty-tree message still reads right.

**T2.5 Preflight and status.** `preflight.check`: in a clarity repo, a constitution with no
`memory-index` marker, or one whose fingerprint differs, is the existing problem ("The
constitution is out of date with clarity.", `compose clarity validate`). `service.status`
keeps `constitution: {fingerprint, current}` by the new marker.

Tests:

- `test_clarity_workflow.py`: a mixed run and a validate run (fake engine) leave
  `.compose/memory/constitution.md` with the marker and the copies, committed on the
  clarity branch; no `compose-constitution` step runs; validate publishes on PASS even when
  the index was already current, and not on FAIL.
- `test_preflight.py`: new marker with the right fingerprint passes; a legacy marker with
  the right fingerprint is refused with the validate fix.
- `test_clarity_branch.py`: a memory file deleted by publish is deleted by the commit.
- `test_clarity_assets.py`: both workflows load; no built-in workflow mentions
  `stamp-constitution` or `from-clarity`.

## M3 — Skills and guide

**T3.1 The guide.** Rewrite `templates/compose/clarity.md` as the memory guide (keep the
file name: `features.py` and `summary.py` point at it). Keep: the why/rules/how split,
standing (`binding`, `draft`, `ideas`), Citing, Conflicts. Replace "Which documents count"
and "What each step reads" with: read `.compose/memory/constitution.md`; when its first
line is a `memory-index` marker, open the files whose Read column names your step and any
whose "when" fits the feature; follow `binding`, mark what you take from `draft` as an
assumption. State the step each skill reads as (`compose-converge` and `compose-bug-fix`
as `implement`, `compose-clarify` as `specify`). Replace "The constitution" with: the
folder is generated by compose from `.clarity/`; changes belong in the clarity documents,
through `/clarity`.

**T3.2 The compose skills.** In `compose-specify`, `compose-clarify`, `compose-plan`,
`compose-tasks`, `compose-implement`, `compose-analyze`, `compose-converge`,
`compose-bug-fix`: remove every `.clarity/` path and every "when the JSON's `clarity` is
not null"; say instead "read the constitution; when it is a memory index, follow
`.compose/templates/compose/clarity.md`". Per skill:

- `compose-specify`: feature ideas come from `feature-ideas.md` in memory.
- `compose-plan`: the Clarity check runs against the binding files the index names for
  `plan`; data, contracts and screens follow the memory copies; the published API spec is
  the one the index row names.
- `compose-tasks`: failures, standards and setup guide from memory.
- `compose-converge`: "the constitution's MUST and SHOULD principles" becomes, for an
  index, the binding NFR, CON, STD and accepted ADRs in the files `implement` reads.
- Conflict wording keeps suggesting `/clarity` and `/clarity-decision`.

**T3.3 `compose-constitution`.** Remove the `from-clarity` section and the step-3 clarity
branch that reads `.clarity/`. When the constitution's first line is either marker, stop
and say it is generated and that changes belong in the clarity documents.

**T3.4 `clarity-configure` and the config template.** Custom documents may declare
`memory: {summary, read_at, read_when}`; add it to the commented example in
`templates/clarity/config.yml` and to the skill's custom-document rule.

**T3.5 `clarity` skill.** Where it says the constitution is regenerated from clarity,
say compose publishes `.compose/memory/` after the run.

Tests (`test_clarity_assets.py`, `test_assets.py`): no `compose-*` skill body contains
`.clarity/` (allow the literal in `compose-constitution`'s "changes belong in" sentence
only if needed, by exact string); every manifest document has a `memory` block with a
non-empty summary and valid step names; the guide names `memory-index`.

## M4 — Docs

- `docs/clarity.md`: the run steps (publish replaces the constitution step), what
  `.compose/memory/` holds, the index, the legacy-constitution refusal and its one-command
  fix.
- `docs/workflow-reference.md`: the `clarity` step actions and the built-in workflow table.
- `docs/cli.md`, `README.md`: wherever the constitution step is described.
- `docs/openapi.json`: regenerate if the API schema changed (`test_release_docs.py`).

## Out of scope

The setup changes (asking which documents are mandatory, dynamic or static config, fuller
config comments) have their own design, to be written next.
