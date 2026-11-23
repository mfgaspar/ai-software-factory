# compose clarity and compose build — Implementation Plan

Date: 2026-11-23
Design: [../specs/2026-11-23-clarity-and-build-design.md](../specs/2026-11-23-clarity-and-build-design.md)
(approved 2026-11-23)

## How to use this plan

Milestones are ordered by dependency. Each task lists the files it touches, what to build, the
tests that prove it, and when it's done. Every milestone ends green (`uv run pytest`,
`uv run ruff check`, `uv run ruff format --check`) and is committed on its own (`K<n>: …`).

Unit tests use the fake engine (`src/compose/engines/fake.py`, `tests/unit/runner_helpers.py`).
Fake scripts stand in for the clarity skills by writing `.clarity/` files, including
`questions.yml`, so the runner, CLI and API are tested without Claude. Skill behaviour is
covered by live tests in K10.

## Layout (target)

```text
src/compose/clarity/                 # new package: compose's deterministic side of clarity
  __init__.py
  summary.py        # moved from repos/clarity.py (front-matter status summary)
  questions.py      # questions.yml model: load, pending, validate and record answers
  fingerprint.py    # tree fingerprint of .clarity/ (branch or directory)
  verdict.py        # parse the validator's last line; read/write .clarity/verdict.yml
  constitution.py   # stamp/read the generated-from-clarity marker
  branch.py         # clarity worktree, update from default, commit, fast-forward merge
  preflight.py      # the pre-run check for feature runs
src/compose/runner/steps/questions.py    # `questions` step
src/compose/runner/steps/clarity.py      # internal `clarity` step (record/stamp/commit/merge)
src/compose/workflows/builtins/clarity/workflow.yml
src/compose/workflows/builtins/clarity-validate/workflow.yml
src/compose/cli/clarity.py               # `compose clarity …`
src/compose/cli/build.py                 # `compose build`
src/compose/assets/templates/clarity/questions.yml
tests/unit/test_repo_scoped_runs.py, test_clarity_branch.py, test_clarity_questions.py,
  test_clarity_verdict.py, test_questions_step.py, test_clarity_workflow.py,
  test_preflight.py, test_cli_clarity.py, test_cli_build.py, test_api_clarity.py
tests/live/test_clarity_build_live.py
```

---

## K0 — Repo-scoped runs

**T0.1 Schema.** `workflows/schema.py`: `WorkflowMeta.scope: Literal["feature", "repo"] =
"feature"`. Validation: a repo-scoped workflow may not use `context.feature.*` in expressions.
Do it with a load-time check over rendered fields if cheap; otherwise leave it as a runtime
error with a clear message.

**T0.2 Runner.** `runner/runner.py`:
- `create_run`: when `definition.workflow.scope == "repo"`, skip `_feature_for` and
  `feature=`, and create `Run(feature_id=None)`. Refuse with `RunError` when another
  repo-scoped run of this repo is `running` or `paused`. That's a DB query on
  `runs.feature_id IS NULL AND repo_id = ? AND status IN (…)`, plus a live lock check on
  `locks.repo_lock_key(repo.id)`. The `run_created` event gets `scope: "repo"`.
- `execute`: for repo scope, lock `repo_lock_key(repo.id)`, and the workdir comes from
  `clarity.branch.ensure_worktree(...)` (K1). Keep the feature path unchanged.
- `RunContext`: `feature: Feature | None`. `env()` leaves out `COMPOSE_FEATURE` and sets
  `COMPOSE_SCOPE=repo` (`COMPOSE_SCOPE=feature` for feature runs). `expression_context()`
  gives `context.feature = None` and adds `context.repo.dir` for both scopes.
- `create_child_run`: pass `parent.feature.id if parent.feature else None`.
- Persist the workdir in `RunState.workdir` (state.json; no migration). `views.run_detail`
  shows `worktree` from the feature when there is one, else from `state.workdir`.

**T0.3 Locks and recovery.** `core/locks.py`: add `repo_lock_key(repo_id) -> "clarity:<id>"`.
`runner/recovery.py:29`: use `feature_lock_key` or `repo_lock_key`, depending on
`run.feature_id`.

**T0.4 CLI text.** `cli/runs.py`: `run` prints "on clarity" (not "on None") for repo runs, and
`_print_detail` omits the feature line, or prints `scope repo`.

Tests (`test_repo_scoped_runs.py`), using a minimal repo-scoped workflow with a fake shell or
command step:
- A repo-scoped run creates no feature or branch.
- It runs in the clarity worktree, with the env vars set as above.
- A second repo-scoped run while one is paused is refused.
- Stale recovery doesn't fail a live repo-scoped run.
- `run_detail` shows the workdir.
- Existing feature-run tests stay green.

Done: all of the above pass.

## K1 — The clarity branch

`clarity/branch.py`, all through `repos/git.py` helpers (add the missing ones):

- `ensure_worktree(db, home, repo) -> Path`: `$COMPOSE_HOME/worktrees/<repo>/clarity`, on
  branch `config.clarity.branch` (default `clarity`; add a `ClarityConfig` to `core/config.py`).
  The branch is created from the default branch when missing. Then merge the default branch
  into it (`git merge --no-edit <default>`). On conflict, run `git merge --abort` and raise
  `RunError` naming the conflicted files.
- `commit_paths(workdir, message) -> str | None`: stage only `.clarity/` and
  `.compose/memory/constitution.md`, commit if anything is staged, and return the sha.
- `merge_into_default(repo, workdir) -> MergeOutcome{merged, pending_reason}`:
  - Fast-forward only.
  - If the default branch is not an ancestor of `clarity`, merge the default branch into
    `clarity` first, then require the caller to re-check the verdict. Return
    `pending_reason="default branch moved; re-validate"`.
  - If the default branch is checked out in a worktree (`git worktree list --porcelain`), that
    worktree must have no changes under `.clarity/` or `.compose/memory/`. Then run
    `git merge --ff-only clarity` there.
  - Otherwise use `git update-ref` (or `git fetch . clarity:<default>`).
  - Never push.

Tests (`test_clarity_branch.py`) on `git_repo`:
- Create the branch.
- Update it from a default branch that moved.
- A conflict refuses and leaves both branches untouched.
- `commit_paths` ignores other files.
- Fast-forward with the default branch checked out and clean.
- Pending when that checkout has a dirty `.clarity/`.
- Pending when the default branch diverged.

## K2 — The questions file

- `assets/templates/clarity/questions.yml` (`questions: []`, with a header comment pointing to
  the docs).
- `manifest.yml`: add it under `companions`.
- `clarity/questions.py`:
  - A pydantic `Question` with every field from the design, plus `obsolete: bool = False`.
  - `load(path)`, `pending(questions, *, exclude_kinds=())` (ordered by kind, then file order).
  - `validate_answer(q, answer, by)`: options and free text; an approval needs `by ==
    q.approver` and an answer in `[approve, reject]`.
  - `record(path, answers: dict[id, str], by, at)`: all-or-nothing, raising `InputError` with
    every problem.
  - Writes are atomic and preserve unknown keys and comments as far as `yaml` allows. Write
    with `sort_keys=False`.

Tests (`test_clarity_questions.py`):
- Ordering.
- `obsolete` questions are not pending.
- Every validation rule.
- `record` is atomic when one answer is invalid.
- Round-trips keep the fields the skills write.

## K3 — Fingerprint, verdict, constitution marker

- `clarity/fingerprint.py`: `of_ref(root, ref)` and `of_dir(root)`. Both list the files under
  `.clarity/` (`git ls-tree -r <ref> -- .clarity`, or by walking the directory and hashing with
  `git hash-object`). They exclude `verdict.yml`, `questions.yml`, `failures/brainstorm/` and
  `prototypes/`, sort by path, and return the sha256 of the `path\0blobsha\n` lines. The same
  content gives the same value for a branch and for a directory.
- `clarity/verdict.py`:
  - `parse(text) -> Verdict` from the last non-empty line (`CLARITY: PASS`, or
    `CLARITY: FAIL (<n> incomplete)`). Anything else is FAIL with `incomplete=None`.
  - `write(workdir, verdict, fingerprint, run_id)` and `read_ref(root, ref)`, using
    `git show <ref>:.clarity/verdict.yml`.
- `clarity/constitution.py`: `stamp(path, fingerprint)` adds or replaces
  `<!-- generated-from-clarity: <fp> -->` as the first line. `read_ref(root, ref)` returns the
  stamped fingerprint, or None.
- Move `repos/clarity.py` to `clarity/summary.py`, and update the import in
  `repos/features.py` and the test.

Tests (`test_clarity_verdict.py`):
- The fingerprint ignores excluded files.
- A branch and its checked-out directory give the same value.
- The fingerprint changes on any document edit.
- Parsing covers PASS, FAIL, garbage and a trailing blank line.
- The stamp is idempotent.

## K4 — The `questions` step and the internal `clarity` step

**T4.1 `questions` step.** `schema.py`: `QuestionsStep(type="questions", file: str, ask: bool
= True, holding_kinds: list[str] | None = None)`. `None` means all kinds except `approval`.
Register it in the `Step` union and in the step dispatcher. `runner/steps/questions.py`:
- **`ask: false`:** count only. Output `{pending, holding}` and complete.
- **Otherwise, on an interactive terminal:** for each pending question, call
  `interaction.ask_question(q)`. Add `ask_question` to `Interaction` in `cli/runs.py`: show the
  question, numbered options and the recommendation; Enter takes the recommendation; with
  `free_text` any text is accepted. Record the answer with `by` = the git user name, then
  complete.
- **Otherwise,** if any pending question has a holding kind: emit
  `questions_waiting{exec_id, step_id, ids}` and raise `RunPaused`. If none does, complete.
- The output is `{answered, pending, holding}`.

`tracking/views.py`: `waiting_questions(run)`, the sibling of `waiting_gate`, embedded in
`run_detail` as `waiting.questions` (the pending question objects). `cli/runs.py`
`_print_outcome`: for a questions pause, print the pending questions and
`compose clarity answer <ID> "<answer>"`.

**T4.2 Internal `clarity` step.** `ClarityStep(type="clarity", action: Literal["record-verdict",
"stamp-constitution", "commit", "merge"], from_step: str | None)`. It's allowed only in
built-in workflows: the loader rejects it from repo or user workflows.
`runner/steps/clarity.py`:
- **`record-verdict`:** parse `steps.<from_step>.output.text`, write `verdict.yml` with
  `fingerprint.of_dir(workdir)`, and output `{result, incomplete, fingerprint}`.
- **`stamp-constitution`:** stamp the workdir's constitution with `of_dir`.
- **`commit`:** `commit_paths(...)`, output `{sha}`.
- **`merge`:** only when the recorded verdict is PASS and its fingerprint still equals
  `of_dir`. Calls `merge_into_default` and outputs `{merged, pending_reason}`. It emits
  `clarity_merge_pending` when not merged, and never fails the run.

**T4.3 Commit on pause, fail and abort.** For repo-scoped runs whose workflow is `clarity` or
`clarity-validate`, `_drive`'s pause, fail and abort paths call `branch.commit_paths` with
`clarity: <mode> run <id> (<status>)`. Errors are logged as events and never mask the original
outcome.

Tests (`test_questions_step.py`), with a workflow of a fake command that writes
`questions.yml`, then a `questions` step:
- It pauses with `waiting.questions`.
- `record` + resume completes it.
- A partial answer pauses again.
- Approvals alone don't pause.
- An interactive answer through `env.interaction` works.
- `ask: false` counts.
- A user workflow with `type: clarity` is rejected by the loader.

## K5 — Skills

**T5.1 `/clarity` modes and phases.** In `assets/skills/clarity/SKILL.md`:
- Parse the mode word: `interactive`, `auto`, `mixed` (the default), `draft`, `apply`.
- **`draft`:** steps 0–5, drafting only.
  - Configure in proposal form, writing `config.yml` and one `setup` question.
  - Raise `gap` and `conflict` questions only for mandatory documents in the effective
    manifest, plus each unresolved `Blocking: yes` open question.
  - Carry over older pending questions that still apply, and mark the rest `obsolete`.
  - Start rounds at the highest round in the file plus one, with stable ids `Q-###`.
- **`apply`:** apply answered questions as the design says.
  - Setup answers reshape the config and drafts.
  - When no setup, gap or conflict question is pending, raise one `review` question.
  - A `confirm` marks mandatory documents complete or n/a, with their hashes.
  - Then raise `approval` questions per approver.
  - Approval answers go through clarity-approve's rules.
  - Run one unattended recheck.
- **`mixed` in Claude Code:** draft → ask the pending questions in the conversation → record
  them in the file → apply, until nothing holding is pending.
- **`interactive`:** today's flow.
- **`auto`:** draft only.
- Rules: in `draft` and `apply`, never ask anything and never mark anything complete except
  from a recorded `confirm` answer. Question text is plain language. The file format is
  `questions.yml`.

**T5.2 `clarity-configure`:** a proposal form for `draft`. It writes the config and returns
the summary that the setup question quotes, and asks nothing.

**T5.3 `compose-constitution from-clarity`:**
- Regenerate the whole file from clarity, following the guide, with every principle citing its
  source.
- Its header says it's generated and that hand edits are overwritten.
- Never ask questions.
- compose stamps the fingerprint afterwards (T4.2).

**T5.4 `clarity-approve` and `clarity-validate`:** mention that answers in `questions.yml` are
a valid source of approvals (`answered_by`, `answered_at`), with the same hash rule.

Tests (`test_clarity_assets.py`):
- The orchestrator names every mode word, and says mixed is the default.
- It references `questions.yml`, `obsolete` and `round`.
- `questions.yml` is a companion.
- compose-constitution mentions `from-clarity`.
- The existing structure tests pass.

## K6 — Built-in workflows

- **`builtins/clarity/workflow.yml`** (`scope: repo`). Inputs: `sources` (string, default
  `""`) and `mode` (string, default `mixed`, must be `mixed` or `auto`; add an `enum` to
  `InputSpec` if it's missing, otherwise validate in a first step). Steps:
  1. draft
  2. `if mode == mixed`: a do-while of at most 4 rounds over
     `questions`, `apply` (command `clarity` with args `apply`) and `count`
     (`questions`, `ask: false`). It repeats while `steps.count.output.holding > 0`.
  3. constitution (`compose-constitution`, args `from-clarity`)
  4. `stamp-constitution`
  5. validate (`clarity-validate`)
  6. `record-verdict` (`from_step: validate`)
  7. `commit`
  8. `merge`
- **`builtins/clarity-validate/workflow.yml`** (`scope: repo`):
  1. validate
  2. `record-verdict`
  3. an `if` on PASS with a stale constitution: constitution, then `stamp-constitution`
  4. `commit`
  5. `merge`
- Update the builtin id sets in `tests/unit/test_loader.py:29` and
  `tests/unit/test_cli_workflow.py:16`.

Tests (`test_clarity_workflow.py`), driving the whole workflow with the fake engine. The
scripts for `clarity` (draft and apply), `compose-constitution` and `clarity-validate` write
plausible files and a `CLARITY: PASS` or `FAIL` line.
- **mixed:** pauses on questions, completes after answers, the verdict is PASS, a commit lands
  on `clarity`, and the default branch is fast-forwarded.
- **auto:** never pauses, FAIL, nothing merged.
- **Approvals only pending:** completes with FAIL.
- **Loop guard:** stops after 4 rounds.
- **clarity-validate:** regenerates a stale constitution only on PASS.

## K7 — The pre-run check

`clarity/preflight.py`: `check(repo) -> Preflight{problems: list[Problem{message, fix}],
warnings: list[str]}`, reading the **local default branch** through git (no checkout). It
implements every row of the design's table:
- **Not started:** a warning.
- **Started but `.clarity/` not on the default branch:** a problem. The fix is
  `compose clarity merge` when the `clarity` branch has a current PASS, else `compose clarity`.
- **Verdict missing, FAIL or stale against `fingerprint.of_ref(default)`:** a problem.
- **Constitution marker stale:** a problem.
- **Local default branch behind its upstream** (per `git rev-list --count
  <default>..<default>@{u}`, no fetch): add a "pull first" hint to the problem.

Wire it into `Runner.create_run` for feature-scoped runs, before anything is written: problems
raise `PreflightError(RunError)` carrying the list. `create_run` returns the run and records
warnings on the `run_created` event. Add `Runner.last_warnings`, or return a small
`CreatedRun` (builder's choice), so the CLI and the API can show them.

Tests (`test_preflight.py`): one per table row. Build the git states with `git_repo`, writing
and committing `.clarity/`, `verdict.yml` and the constitution with real fingerprints. Also
check that `compose run` refuses with exit 1 and the fix text, and that no run row is created.

## K8 — CLI

`cli/clarity.py`, registered as `app.add_typer(clarity.app, name="clarity")`:
- **The sources argument.** A group whose bare form takes sources (`compose clarity docs/ …`)
  can't also have subcommands with positional parsing. Implement a click `Group` subclass that
  resolves an unknown first token to a hidden `start` command (`resolve_command` fallback), so
  `compose clarity docs/prd.md` → `start docs/prd.md`, while `status`, `questions`, `answer`,
  `validate` and `merge` stay subcommands. Document that a source named like a subcommand
  needs `./`.
- **`start [SOURCES…] --mode --detach --interactive/--no-interactive --json`:**
  - **mixed and auto:** create a run of `clarity` with inputs and run it like `compose run`
    (foreground or detach, the same `_finish` exit codes).
  - **interactive:** requires a TTY. It ensures the clarity worktree, then
    `subprocess.run([claude, "/clarity <sources> interactive"], cwd=worktree)` attached to the
    terminal (installing skills first, as `_install_engines` does). Afterwards it starts and
    runs `clarity-validate`.
- **`status`:** `summary.summary(worktree)`, plus the verdict (current or stale against
  `of_dir`), the pending question count and constitution currency. With `--json`, the same
  shape as the API.
- **`questions`:** the pending questions as a table or JSON.
- **`answer ID ANSWER --by --no-resume`:** `questions.record`. If the repo's repo-scoped run is
  paused on questions and nothing holding is pending, `prepare_resume` then `execute` (or
  `spawn` when `--detach`).
- **`validate`:** run `clarity-validate`, exit 1 on FAIL.
- **`merge`:** `merge_into_default` after re-checking the verdict, exit 1 when it's pending.

`cli/build.py`: `compose build DESCRIPTION [--workflow] [-i…] [--feature] [-d]
[--interactive/--no-interactive] [-v] [--json]`. It resolves the default workflow and the
input name: the workflow's first required string input (`spec` for the built-ins), and errors
if there is none. It then calls the same code path as `compose run`. Warnings print to stderr
as `warning: …` and go in the JSON under `warnings`.

Tests (`test_cli_clarity.py`, `test_cli_build.py`) with the `cli` fixture and fake engine:
- Bare sources route to `start`.
- `--mode interactive` without a TTY errors.
- Pause → `questions` → `answer` resumes and completes.
- An invalid answer exits 1 with the reasons.
- `status` JSON.
- `build` without clarity warns and runs.
- `build` with clarity not passing exits 1 and creates no run.
- `build` with a current PASS runs.

## K9 — API

In `api/app.py`, with the same auth and errors. Add `PreflightError` to `EXPECTED`, mapped to
409 with `{"detail", "problems"}`.

| Route | Notes |
|---|---|
| `POST /repos/{repo}/clarity` | `StartClarity{sources: list[str] = [], mode: Literal["mixed","auto"] = "mixed"}`. Mode `interactive` gives 422 with a clear message. 202 + brief. |
| `GET /repos/{repo}/clarity` | Status, the same shape as the CLI `--json`. |
| `GET /repos/{repo}/clarity/questions` | The pending questions. |
| `POST /repos/{repo}/clarity/answers` | `Answers{answers: dict[str,str], by: str, resume: bool = True}`. 422 on any invalid answer. When it resumes, `server.launch`. Returns `{recorded, resumed_run}`. |
| `POST /repos/{repo}/clarity/validate` | 202 + brief. |
| `POST /repos/{repo}/clarity/merge` | 200 `{merged: true}`, or 409 with `pending_reason`. |
| `POST /repos/{repo}/builds` | `StartBuild{spec, workflow?, feature?, inputs?}`. 202 + brief + `warnings`. A preflight failure gives 409. |

`POST /repos/{repo}/runs` also returns `warnings`. `GET /runs/{run}` includes
`waiting.questions`.

Regenerate `docs/openapi.json` with the command in `tests/unit/test_release_docs.py`.

Tests (`test_api_clarity.py`):
- A full mixed run: start → wait for paused → GET questions → POST answers → wait for
  completed → verdict PASS → the default branch moved.
- The answers endpoint validates.
- Interactive gives 422.
- Builds: 409 with problems, and 202 with warnings.

## K10 — Docs, live tests, release

- **Docs:**
  - `docs/cli.md`: the `compose clarity …` subcommands and `compose build`. The release-docs
    test checks every command.
  - `docs/api.md`: the new routes.
  - `docs/workflow-reference.md`: `scope`, the `questions` step, and a note that the `clarity`
    step is internal.
  - `docs/clarity.md`: the three modes, the questions file, the branch and auto-merge, and the
    pre-run check.
  - The README: the two-step story, with `compose clarity` then `compose build`.
- **Live tests** (`tests/live/test_clarity_build_live.py`, real Claude, sonnet, budget
  capped):
  1. `compose clarity docs/ --mode auto` on a small fixture repo → the run completes, FAIL,
     `questions.yml` has setup and gap questions, every document is draft, nothing is merged.
  2. A mixed run through the API → paused with questions. Answer each with its recommendation
     (or `confirm` / `approve`, giving `by` from the approver list), resume, and repeat until
     completed. The verdict is PASS, the default branch has `.clarity/` and the stamped
     constitution, and `POST /repos/{repo}/builds` is accepted by the pre-run check. Stop the
     build right after it's created; there's no need to build.
- **Release:**
  - Bump the version (`src/compose/__init__.py`), the changelog section if present, and
    `docs/openapi.json`.
  - Run the full unit suite and the two live tests.

## Risks to watch

- **Skill compliance with the questions file.** A model may write a malformed
  `questions.yml`. `questions.load` must fail with a clear run error (the step fails, and the
  run can be resumed after a fix) rather than silently dropping questions. Consider a
  validation retry: the step reports the parse error, and `apply` runs again with it as input.
- **The draft step's cost.** Drafting the whole foundation in one `claude -p` call is the
  largest single step compose runs. Set a generous per-step `max_budget_usd` default in the
  workflow, and expose `inputs.max_budget_usd`.
- **The merge touching the user's checkout.** Keep the dirty-path rule strict, and cover it
  with tests before wiring `merge` into the workflow.
