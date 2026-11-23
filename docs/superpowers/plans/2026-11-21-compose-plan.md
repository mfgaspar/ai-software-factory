# compose — Implementation Plan

Date: 2026-11-21
Design: [../specs/2026-11-21-compose-design.md](../specs/2026-11-21-compose-design.md)

## How to use this plan

Milestones are ordered by dependency. Each task lists the files it touches, what to build,
the tests that prove it, and when it's done. Every milestone ends green (`uv run pytest`,
`uv run ruff check`) and is committed on its own.

**Testing principle.** Almost everything is tested against a **fake engine** (M4) that replays
scripted events and file edits deterministically, so the runner, hooks and tracking are fully
tested without calling Claude. Tests that call real Claude Code are marked `@pytest.mark.live`
and skipped by default (`uv run pytest -m live` to run them; they cost money).

**Test isolation.** All tests set `COMPOSE_HOME` to a tmp dir and create throwaway git repos
via a `git_repo` fixture. Nothing touches `~/.compose`.

## Package layout (target)

```
pyproject.toml                  # uv project; console script `compose`
src/compose/
  cli/        app.py, repo.py, feature.py, workflow.py, run.py, report.py, serve.py, init.py
  core/       home.py, config.py, db.py, migrations/, models.py, ids.py, locks.py
  repos/      registry.py, git.py, features.py, worktrees.py
  workflows/  schema.py, loader.py, expressions.py, builtins/{full-cycle,quick,bugfix}/
  runner/     runner.py, state.py, context.py, steps/{command,prompt,shell,gate,control,
              fanout,subworkflow}.py, hooks.py, limits.py, recovery.py
  tracking/   snapshot.py, diff.py, events.py, records.py, aggregate.py
  engines/    base.py, registry.py, fake.py, claude/{adapter.py, install.py, mapping.py}
  assets/     skills/compose-*/SKILL.md, templates/*.md, memory/constitution.md
  api/        app.py, routes/{repos,features,workflows,runs,costs}.py, sse.py, auth.py
tests/        unit/, integration/, live/, fixtures/
docs/         workflow-reference.md, cli.md, api.md
```

Open naming risk: the distribution name `compose` is likely taken on PyPI. Keep the import
package `compose` and the command `compose`; pick a distribution name (e.g. `compose-sdd`)
before first publish. Not blocking.

---

## M0 — Project scaffold

**T0.1 Project setup.** `pyproject.toml` (hatchling build, Python ≥ 3.11, deps: typer, rich,
pydantic v2, pyyaml, fastapi, uvicorn, httpx, claude-agent-sdk; dev: pytest, pytest-asyncio,
ruff, mypy), `src/compose/__init__.py` with `__version__`, console script
`compose = compose.cli.app:main`, `compose --version`.
Tests: CLI smoke (`compose --version` via Typer's `CliRunner`).
Done: `uv tool install .` gives a working `compose --version`.

**T0.2 Test fixtures.** `tests/conftest.py`: `compose_home` (tmp `COMPOSE_HOME`), `git_repo`
(init repo with one commit on `main`), `cli` runner helper.

---

## M1 — Home, config, database

**T1.1 Home and config.** `core/home.py` resolves `COMPOSE_HOME` (default `~/.compose`) and
creates `runs/ repos/ worktrees/`. `core/config.py` loads `config.yml` (server host/port,
optional API token, default engine/model) with pydantic defaults.
Tests: defaults, override via env, malformed config error message.

**T1.2 SQLite store.** `core/db.py` (sqlite3, WAL mode, `busy_timeout`, one connection per
thread) + ordered SQL migrations in `core/migrations/`. Tables: `repos`, `features`, `runs`,
`step_execs` (run_id, step_id, exec_id, parent_exec_id, iteration, status, timings, engine,
model, session_id, turns, tokens ×4, cost_usd, files_changed, lines_added, lines_removed,
error), `hook_execs` (same metrics + step_exec_id, event, hook index), `actions` (exec_id,
seq, kind, tool name, input summary, result summary, duration, ts), `file_changes`
(exec_id, hook_exec_id nullable, path, status, added, removed).
`core/models.py`: pydantic models mirroring rows. `core/ids.py`: ULID run/exec ids.
Tests: migrations apply idempotently; round-trip of each model; concurrent writers from two
processes don't error (WAL).

**T1.3 Locks.** `core/locks.py`: per-feature lock as a DB row with owner pid + heartbeat,
plus helper to detect stale owners (pid gone or heartbeat older than N s).
Tests: acquire/release; second acquire fails; stale lock is reclaimable.

---

## M2 — Repos, features, worktrees

**T2.1 Git helpers.** `repos/git.py`: thin subprocess wrapper (run, check, capture), default
branch detection, branch create, worktree add/list/remove, clone.
Tests against `git_repo`.

**T2.2 Repo registry.** `repos/registry.py`: add by path (must be a git repo) or URL (clone to
`$COMPOSE_HOME/repos/<name>`), unique short id/name, list, remove (unregister only; never
deletes clones' history in v1 unless `--delete-clone`). CLI `compose repo add|list|remove`.
`--repo` default: the registered repo containing cwd.
Tests: path add, URL add (clone from a local bare repo as "URL"), duplicates, remove.

**T2.3 Features.** `repos/features.py`: next number (max of `specs/NNN-*` dirs and `NNN-*`
branches + 1, zero-padded to 3), slug from text (lowercase, ascii, first ~4 meaningful words),
create branch + `specs/NNN-name/`.
- `compose feature new <name> [--json]`: if `COMPOSE_FEATURE` is set, print that feature and
  exit; otherwise create branch **in the current checkout** and switch to it (manual mode).
- `compose feature paths --json`: resolve feature from `COMPOSE_FEATURE` or current branch;
  return repo root, feature dir, spec/plan/tasks paths, constitution path, templates dir.
- `compose feature list|show`.
Tests: numbering with gaps, slug rules, env short-circuit, paths from branch vs env.

**T2.4 Worktrees for runs.** `repos/worktrees.py`: `ensure_feature_worktree(repo, feature)`
→ `$COMPOSE_HOME/worktrees/<repo>/<feature>/`, created from the feature branch (creating the
branch from default if new); recreated if missing; returns path.
Tests: create, reuse, recreate after manual deletion.

---

## M3 — Workflow definitions

**T3.1 Schema.** `workflows/schema.py`: pydantic models for the top level (§6.2), inputs
(§6.3), every step type (§6.4) as a discriminated union on `type` (default `command`), hooks
(§7.1), limits, outputs. Validation: unique step ids, no `:` in ids, `max_iterations`
required on loops, hook event names reference existing steps, one of `command|prompt|run`
per hook, workflow-call depth/cycle check (static where possible).
Tests: valid examples parse; each invalid case gives a precise error with path.

**T3.2 Expressions.** `workflows/expressions.py`: tokenizer + recursive-descent parser for
`{{ }}`: dotted/indexed lookups, literals, comparison, `in`/`not in`, `and/or/not`, filters
with args (`default join contains map from_json to_json upper lower split length`). Lone
expression → typed value; mixed → string. No arithmetic. Clear errors on unknown names.
Context object built by the runner (T4.2).
Tests: table-driven cases for each operator/filter, typing rules, error messages.

**T3.3 Loader and registry.** `workflows/loader.py`: load from dir or file; resolve id →
repo-installed (`.compose/workflows/<id>/`) then built-in; `compose workflow list|info|add|
remove|validate`. `info` shows the effective hooks including built-in tracking hooks.
Tests: precedence, add from path, validate output.

**T3.4 Workflow reference doc.** `docs/workflow-reference.md`: compose's own semantics for
every field and step type (incl. gate retry, fan-out, error handling, expressions). Kept in
sync with schema; examples in it are parsed by a test.

---

## M4 — Engine interface, fake engine, runner core

**T4.1 Engine interface.** `engines/base.py`: `EngineTask` (skill | prompt), `EngineOptions`,
`EngineEvent` (message | tool_call | tool_result | usage_update), `EngineResult`, and
`Engine` protocol (`run() -> AsyncIterator[EngineEvent]` ending with result, `install(path)`,
`check()`), plus `stop()` for limits/abort. `engines/registry.py`: name → adapter.
**`engines/fake.py`**: scripted engine — a script lists events, file writes/deletes to apply
in cwd, usage, and final status; used by most tests.
Tests: fake engine replays a script and edits files.

**T4.2 Run state and context.** `runner/state.py`: run folder `$COMPOSE_HOME/runs/<run_id>/`
(`definition.yml`, `inputs.json`, `state.json`, `log.jsonl`, `steps/`); atomic writes
(write tmp + rename); state transitions `created → running → completed|paused|failed|aborted`
enforced. `runner/context.py`: builds expression context (inputs, step outputs, `context.*`,
tracking values).
Tests: transition table; atomicity under simulated crash.

**T4.3 Runner loop.** `runner/runner.py`: input resolution/coercion; feature resolve/create +
worktree (T2.3/2.4) + lock; executes steps sequentially, recording each exec in DB + files;
`continue_on_error`; exports `COMPOSE_RUN_ID`, `COMPOSE_FEATURE`, `COMPOSE_WORKFLOW_DIR`.
Step executors:
- `steps/command.py`, `steps/prompt.py` → engine via registry;
- `steps/shell.py` (`run`, `env`, `strict`, `timeout`, `capture`, `output_format: json`,
  `exit_code` in output);
- `steps/gate.py` (verdict input bound → decide; TTY → prompt; else pause; `on_reject`
  abort/skip/retry);
- `steps/control.py` (`if`, `switch`, `while`, `do-while` with iteration exec records);
- `steps/fanout.py` (`fan-out` with asyncio semaphore `max_concurrency`, `fan-in`);
- `steps/subworkflow.py` (child run linked to parent, outputs, depth 16, cycle detection).
Tests (fake engine + shell): linear success; failure stops; continue_on_error; each control
type; gate pause → resume with verdict; reject modes; nested workflow outputs.

**T4.4 Resume, abort, recovery.** `resume(run_id, inputs)` for paused/failed only, replays
completed steps from state, re-runs the failed step fresh. `abort(run_id)` sets a flag in
DB the runner polls between events and calls `engine.stop()`. `runner/recovery.py`: on CLI
or server start, runs marked `running` whose lock owner is dead → `failed` ("process died").
Tests: resume after failure; resume after pause; abort mid-step (fake engine with a slow
script); recovery after killed subprocess.

**T4.5 Limits.** `runner/limits.py`: per-step and run-wide `max_cost_usd`/`max_turns`;
watches `usage_update` events, calls `engine.stop()`, fails with `limit_exceeded`.
Tests: fake engine exceeding cost; run-wide cap across steps.

---

## M5 — Hooks

**T5.1 Hook resolution.** `runner/hooks.py`: for a step exec, collect `before_run`,
`before_step`, `before_<id>` (and after equivalents), add built-in tracking hooks
(`compose.track.begin` first, `compose.track.end` last) unless `tracking: false`; sort by
priority then declaration order; evaluate `condition`.
Tests: ordering, conditions, tracking placement, `tracking: false`.

**T5.2 Hook execution.** Run `command`/`prompt` hooks through the engine and `run` hooks as
shell; required before-hook failure fails the step without running it; required after-hook
failure fails the step; optional failure is recorded only; `prompt_text` asks on TTY, runs
otherwise. Each hook exec gets a `hook_execs` row.
Tests: every failure/optional combination; TTY vs non-TTY.

---

## M6 — Tracking

**T6.1 Snapshot.** `tracking/snapshot.py`: snapshot of worktree as a tree object using a
temporary `GIT_INDEX_FILE` (`git read-tree HEAD`, `git add -A`, `git write-tree`), honoring
`.gitignore`, `.git/info/exclude`, and excluding `.compose/runs` and compose-installed files.
No commits, no change to the real index.
Tests: tracked edit, new untracked file, deletion, rename, ignored file excluded, real index
untouched.

**T6.2 Diff.** `tracking/diff.py`: `git diff --numstat -M` + `--name-status` between two
trees → per-file status/added/removed; binary files reported with `added/removed = null`.
Tests: each status; binary.

**T6.3 Events and records.** `tracking/events.py`: adapter events appended to `log.jsonl`
(with exec id) and `actions` rows in real time. `tracking/records.py`: `compose.track.begin`
/`end` implementations; the end hook writes step totals = step's own + every hook's metrics;
file changes for the whole window (step + hooks), with per-hook breakdown from snapshots
taken around each hook. Step records written to `steps/<exec_id>.json` and DB.
Tests: step + two hooks editing files → totals and per-hook breakdown add up exactly; cost
sums match; fan-out changes attributed to the fan-out exec, costs per item.

**T6.4 Aggregates.** `tracking/aggregate.py`: totals by step/run/feature/repo/day with time
filters; exposed to expressions as `steps.<id>.cost_usd`, `steps.<id>.changes.*`.
Tests: aggregation queries over seeded data.

---

## M7 — Claude Code adapter

**T7.1 Adapter.** `engines/claude/adapter.py` using `claude_agent_sdk`: options with
`cwd=worktree`, project setting sources (so skills load), model, max_turns, permission mode
(default accept-edits + allowed tools from workflow/step), env. Skill task → prompt
`/<skill> <args>`. `mapping.py`: SDK assistant/tool-use/tool-result/result messages →
`EngineEvent`s; result → `EngineResult` (session id, turns, usage incl. cache tokens,
`total_cost_usd`, duration). `stop()` interrupts the client.
Tests: mapping unit tests from recorded SDK message fixtures; live test: tiny prompt in a
tmp repo produces events, a file edit, and non-zero cost.

**T7.2 Install and check.** `engines/claude/install.py`: copy `assets/skills/compose-*` to
`<path>/.claude/skills/`, templates to `.compose/templates/`; in run worktrees, skip files the
repo already has committed and add compose-placed paths to the worktree's git exclude.
`check()`: `claude` CLI present + version, SDK importable, auth usable.
Tests: install into fresh repo; into worktree (excluded, not in snapshot diff); respects
committed versions.

---

## M8 — Skills, templates, init

**T8.1 Templates and constitution.** `assets/templates/{spec,plan,tasks,checklist}.md`,
`assets/memory/constitution.md` — adapted from the prior art's, renamed to compose, with no
references to the old project (a test greps assets for its name).

**T8.2 Skills.** `assets/skills/compose-{constitution,specify,clarify,plan,tasks,analyze,
checklist,implement}/SKILL.md`: adapted prompts; all filesystem/feature logic goes through
`compose feature new --json` / `compose feature paths --json` instead of scripts. Same text
for manual and workflow use.
Tests: frontmatter valid; each skill references only existing CLI commands; live smoke for
specify → plan on a toy repo.

**T8.3 Operator skill.** `assets/skills/compose/SKILL.md`: teaches Claude to use
`compose run/status/resume/trace/changes/cost --json` to operate compose for the user.

**T8.4 `compose init` and `compose check`.** `init --engine claude [--path]`: engine
`install()`, constitution if absent, `.gitignore` entries, register repo, print what to
commit. `check`: git, engine check, repo initialized.
Tests: init on fresh repo; idempotent re-init; check failures are actionable.

---

## M9 — CLI reporting surface

**T9.1** `compose run` (foreground with Rich live step table; `--detach` hands to server via
HTTP if running, else errors with a hint; `--json`), `status` (list or one run with per-step
table), `resume`, `abort`.
**T9.2** `compose trace` (actions per step, hooks nested), `compose changes` (files/lines per
step), `compose cost` (`--by step|run|feature|day`, filters). All with `--json`.
Tests: CliRunner snapshot tests over fake-engine runs; JSON shapes stable.

---

## M10 — API server

**T10.1 App and auth.** `api/app.py` FastAPI, `compose serve --host --port`; optional bearer
token from config; recovery (T4.4) on startup; `/health`, `/openapi.json`.

**T10.2 Routes.** Per design §14: repos, workflows, features, runs (create → background task
via the same runner; list/filter; detail; step exec detail; changes; resume; gate decision;
abort), costs. Response models reuse `core/models.py`.

**T10.3 Live events.** `api/sse.py`: `/runs/{id}/events?stream=true` tails `log.jsonl` (works
for runs started by the CLI too), paged mode otherwise.

**T10.4 Shared store.** Runs started by `compose run` are visible/resumable via API and vice
versa; feature lock prevents a second active run (409).
Tests: httpx `TestClient` for every route with fake engine; SSE receives step events; 409 on
busy feature; CLI-started run visible via API.

---

## M11 — Built-in workflows and end-to-end

**T11.1** `workflows/builtins/full-cycle`, `quick`, `bugfix` per design §16 (bugfix loop uses
`do-while` on test exit code, max 3).
Tests: each runs to completion on the fake engine with scripted skills; gates pause/resume.

**T11.2 Live E2E.** `tests/live/test_quick_e2e.py`: `compose init` a toy repo, run `quick`
with a tiny spec under a `max_cost_usd` cap; assert completed, per-step cost > 0, implement
step has file changes, totals add up. Same through the API.

---

## M12 — Docs and release

README (install with `uv tool install`, quick start, by-hand vs workflow use), `docs/cli.md`,
`docs/api.md` (linked to OpenAPI), `docs/workflow-reference.md` (T3.4), writing custom
workflows and hooks guide. Choose distribution name; tag v0.1.0.

---

## Suggested order and parallelism

M0 → M1 → M2 → M3 → M4 → (M5, M6 together; they meet in T6.3) → M7 → M8 → M9 → M10 → M11 →
M12. After M4, M3.4 docs, M7 (adapter) and M8.1/8.2 (assets) can proceed in parallel with M5/M6.

## Definition of done (v1)

- `uv tool install` + `compose init --engine claude` + `compose run quick -i spec=...` works
  on a real repo, and the same via `POST /repos/{repo}/runs`.
- For every step: status, actions, cost, files and lines changed, hooks included, visible via
  CLI and API, and totals add up across step → run → feature → repo.
- Skills work by hand in Claude Code with identical behavior and no tracking.
- No references to the old project's name anywhere in the shipped package (test enforced).
