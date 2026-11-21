# compose — Design

Date: 2026-11-21
Status: Draft for review

## 1. Intent

compose is a spec-driven development tool modeled on GitHub's spec-kit, rebuilt as an
**orchestrator**: it runs multi-step development workflows (constitution → specify → plan →
tasks → implement, or any custom flow) on a coding engine, headlessly, and keeps a complete,
queryable record of what happened.

Why it exists: spec-kit gives you good prompts/skills and a basic workflow runner, but no API,
no hooks around workflow steps, and no record of what the agent did, what it cost, or what it
changed. compose adds exactly that:

- a **CLI** for people and an **HTTP API** for tools/CI to start, resume, inspect and abort runs;
- **hooks** around every workflow step, declared in the workflow;
- **traceability** — every engine action per step;
- **cost tracking** per step — tokens and USD;
- **change tracking** per step — files changed, lines added/removed.

It works with **Claude Code** first, behind an engine boundary so other coding engines
(Codex, Gemini, …) can be added later.

Naming: the product is **compose**. Nothing in code, files, commands, or docs references
"speckit"/"spec-kit"/"specify". spec-kit is prior art only.

## 2. Goals, non-goals, anti-goals

### Goals (v1)
- Install with one command; `compose init --engine claude` makes a repo ready for Claude Code.
- Ship the full skill set (constitution, specify, clarify, plan, tasks, analyze, checklist,
  implement) as Claude Code skills, usable **by hand** in Claude Code exactly like spec-kit's
  commands, and usable as workflow steps.
- Ship built-in workflows and let teams write their own.
- Run workflows from the CLI or the API; pause at gates; resume; abort.
- Report status of each run and each step, live.
- Per step: full action trace, cost, files changed, lines added/removed — hooks' work rolled
  into the step they run around.
- One server managing many repos, added from a local path or a git URL.
- Engine-agnostic core; Claude Code is the only adapter in v1.

### Non-goals (v1)
- Tracking or costing **manual** skill use in Claude Code. Only workflow runs are tracked.
- Hooks declared inside skills. Hooks live only in workflows.
- Separate "variables" — workflows use `inputs` only.
- Multi-user server with authentication, roles, or a web dashboard.
- Automatic push / PR creation at the end of a run (a workflow may add a step for that).
- spec-kit's extension catalog, presets, overlays, bundles, workflow-function packages, and
  custom step-type packages.
- Engines other than Claude Code (only the interface for them).

### Anti-goals (would make it a failure even if it "works")
- Tracking that is incomplete or wrong (costs or line counts that don't add up per step).
- Skills that behave differently when run by hand vs. in a workflow.
- Claude-specific assumptions leaking into the workflow format or core runner, so that a
  second engine needs a rewrite.
- Parallel runs corrupting each other's files or mixing each other's diffs.

## 3. Constraints

- Follow spec-kit's approach: Python, installed with `uv tool install`, Typer + Rich CLI;
  workflow format and run-state files are **loosely inspired** by spec-kit's workflow spec
  (see §6). spec-kit workflow files are **not** required to run unchanged; where details
  differ or are undocumented in spec-kit, compose defines its own behavior and documents it.
  The builder writes compose's own workflow reference (schema, expression semantics, step
  semantics incl. gate retry and fan-out) as part of the work.
- Claude Code is driven through the **Claude Agent SDK for Python**, which streams every
  message and tool call and returns usage, `total_cost_usd`, `session_id` and turn counts.
- Git is required; every repo compose manages is a git repo.
- Git credentials come from the machine (SSH keys, credential helper, `gh` auth). compose
  stores no secrets in v1.

## 4. Approaches considered

### 4.1 How tracking is captured (decided: C)
- **A. Built into the runner.** Runner snapshots git and reads the SDK stream around every
  step. Simplest and reliable, but tracking is fixed and invisible; nobody can extend it
  without changing compose.
- **B. Claude Code hooks.** Install Claude Code `PostToolUse`/`Stop` hooks that post events to
  compose. Sees every action, but Claude Code hooks don't report cost (would be rebuilt from
  transcripts), they fire during manual use too, and each future engine needs its own
  equivalent.
- **C. Tracking as built-in workflow hooks (chosen).** compose ships default `before`/`after`
  step hooks every workflow inherits: `before` takes a git snapshot; `after` computes file/line
  changes and records the actions and cost the engine adapter collected from the SDK stream.
  Chosen because it matches the user's model ("traceability and costs managed by hooks in the
  workflow"), keeps skills plain (nothing extra installed into Claude Code), gets exact cost
  from the SDK, and works for any engine whose adapter reports actions and cost.

### 4.2 Server topology (decided: one server, many repos)
- **Server per repo:** simple process, but clients must track a port per repo and cross-repo
  questions ("what did everything cost this week?") need fan-out.
- **One server, many repos (chosen):** repos are registered; every call is repo-scoped; one
  index of runs/costs across repos. Small extra cost: a repo id on everything.

### 4.3 Isolation (decided: worktree per feature)
- **Work in the repo's checkout:** parallel runs overwrite each other; diffs mix.
- **Worktree per run:** isolated but scatters one feature's work across branches.
- **Worktree + branch per feature (chosen):** each feature (one specification) gets a branch
  `NNN-short-name` and a worktree; all runs for that feature use it; one active run per feature
  at a time; different features run in parallel.

## 5. Concepts

| Term | Meaning |
|---|---|
| **Repo** | A git repository registered with compose (local path, or cloned from URL). |
| **Feature** | One specification. Has a number + short name (`003-user-auth`), a branch of the same name, a worktree, and a folder `specs/003-user-auth/` holding spec.md, plan.md, tasks.md, etc. |
| **Skill** | A Claude Code skill (constitution, specify, plan, …). Same behavior by hand or in a workflow. |
| **Workflow** | A versioned definition of steps, inputs, hooks. Built-in or custom. |
| **Run** | One execution of a workflow against one feature in one repo. |
| **Step** | One unit in a workflow (engine command, prompt, shell, gate, control flow). Each *execution* of a step (including each loop iteration) gets its own record. |
| **Hook** | Something run before/after a step, declared in the workflow. Its trace and cost roll into the step. |
| **Engine** | The coding agent that executes command/prompt steps (Claude Code in v1), reached through an adapter. |

## 6. Workflow definition

Inspired by spec-kit's workflow spec (not compatible with it), with `integration` renamed to
`engine`, and hooks and tracking added. Semantics described here are compose's own.

### 6.1 Packaging and location
- A workflow is a directory with `workflow.yml` plus companion files (scripts, README); a bare
  YAML file also works.
- Built-in workflows ship inside compose. Repo-installed workflows live at
  `.compose/workflows/<id>/workflow.yml`. `compose workflow add <path|url>` installs one.
- A run records the exact definition it started with (`definition.yml` in the run folder), so
  editing a workflow never changes an in-flight run.

### 6.2 Top-level schema
```yaml
schema_version: "1.0"
workflow:
  id: full-cycle            # lowercase, digits, hyphens
  name: Full spec cycle
  version: 1.0.0
  description: ...
  engine: claude            # default engine for engine steps
  model: claude-sonnet-5-5  # default model (optional)
  reasoning_effort: medium  # optional
  limits:                   # optional run-wide caps
    max_cost_usd: 20
requires:
  compose_version: ">=0.1"
inputs:
  spec:        { type: string, required: true, prompt: "Describe the feature" }
  feature:     { type: string, required: false }   # existing feature id; omit to create one
  review_spec_verdict: { type: string, default: "" }
hooks:                       # see §7
  after_implement:
    - run: "npm test"
      description: Run tests after implementation
outputs:
  plan_path: { value: "{{ steps.plan.output.plan_path }}" }
steps:
  - id: specify
    command: compose-specify
    input: { args: "{{ inputs.spec }}" }
  - id: review-spec
    type: gate
    message: "Review spec.md before planning"
    verdict_input: review_spec_verdict
    options: [approve, reject]
    on_reject: abort
  - id: plan
    command: compose-plan
  - id: tasks
    command: compose-tasks
  - id: implement
    command: compose-implement
    limits: { max_cost_usd: 10, max_turns: 200 }
```

### 6.3 Inputs
Types `string`, `number`, `boolean`; fields `required`, `default`, `prompt`, `enum`. CLI values
are coerced (booleans accept true/1/yes, false/0/no). Inputs are the only variables in v1.

### 6.4 Step types (v1)
| Type | Purpose |
|---|---|
| `command` (default) | Run a skill on the engine (`command: compose-plan`, `input.args`). |
| `prompt` | Send an inline prompt to the engine. |
| `shell` | Run a shell command in the feature worktree. `strict: true` forbids `{{ }}` in `run`; pass values via `env`. `output_format: json` parses stdout into `output.data`. |
| `gate` | Human approval. `options`, `verdict_input`, `on_reject: abort \| skip \| retry`. If the verdict input is bound, the gate decides itself; otherwise it prompts on a TTY or pauses the run (`paused`). |
| `if` / `switch` | Branching on expressions. |
| `while` / `do-while` | Loops with mandatory `max_iterations` (e.g. implement → test → fix until green). |
| `fan-out` / `fan-in` | Run a step template over items with `max_concurrency`; collect results. |
| `workflow` | Call another workflow; child returns its declared `outputs`. Max depth 16; cycles rejected. |

Common step fields: `id` (required, no `:`), `type`, `engine`, `model`, `reasoning_effort`,
`timeout`, `continue_on_error`, `capture`, `limits` (`max_cost_usd`, `max_turns`) for engine
steps.

Error handling follows spec-kit: a failed step stops the run unless `continue_on_error: true`;
exit codes are kept in `steps.<id>.output.exit_code` for branching.

### 6.5 Expressions
`{{ expr }}`, spec-kit's expression language: namespaces `inputs.*`, `steps.<id>.output.*`,
`item` / `fan_in` (in fan-out), `context.run_id`, `context.workflow_dir`, plus compose
additions `context.feature.id`, `context.feature.dir`, `context.repo.id`, and per-step tracking
values `steps.<id>.cost_usd`, `steps.<id>.changes.files`, `steps.<id>.changes.added`,
`steps.<id>.changes.removed`. Operators `== != > < >= <= in not in and or not`; filters
`default join contains map from_json to_json upper lower split length`. No arithmetic. Shell
interpolation is plain substitution (use `strict` + `env` for safety).

## 7. Hooks

### 7.1 Where and how declared
Hooks are declared **only in the workflow**, under top-level `hooks:`. Skills have no hooks.
Event names:

- `before_<step-id>` / `after_<step-id>` — around a specific step.
- `before_step` / `after_step` — around every step (used by tracking).
- `before_run` / `after_run` — around the whole run.

Each event maps to one entry or a list. Entry fields (spec-kit's hook fields, executed by
compose instead of by the agent):

| Field | Meaning |
|---|---|
| one of `command` / `prompt` / `run` | A skill on the engine, an inline engine prompt, or a shell command. |
| `optional` | Default `false`. If `true`, the hook's failure is recorded but does not fail the step. |
| `prompt_text` | For optional hooks: question shown on a TTY before running ("Create Jira issues?"). Non-interactive runs execute the hook. |
| `description` | Human description. |
| `condition` | `{{ }}` expression; hook is skipped when false. |
| `priority` | Integer ≥ 1, default 10; lower runs first. |
| `engine`, `model`, `timeout`, `env` | As for steps. |

### 7.2 Execution semantics
- compose (not the engine) runs hooks, in priority order then declaration order.
- `before_*` hooks run before the step; a required one that fails fails the step without
  running it. `after_*` hooks run after the step succeeds; a required one that fails fails the
  step.
- Hooks run in the feature worktree with the same environment as steps.
- Every hook execution is traced; its actions, cost and file changes are **aggregated into the
  step it surrounds** (drill-down still shows each hook separately).

## 8. Tracking (built-in hooks)

Every workflow implicitly gets two built-in hooks; they are visible in `compose workflow info`
and in run definitions:

- `compose.track.begin` on `before_step`, runs **first**: takes a git snapshot of the worktree
  (tracked + untracked, excluding `.compose/` and ignored files) as a tree object without
  committing (e.g. temporary index + `git write-tree`); opens the step's trace.
- `compose.track.end` on `after_step`, runs **last** (so it includes other hooks' work):
  snapshots again; computes per-file `added` / `removed` / status via
  `git diff --numstat` between the two trees; sums the engine usage collected for the step and
  its hooks; writes the step record.

The engine adapter feeds a per-step event log in real time during the step: each assistant
message, tool call (name, input, result summary, duration), and final usage. The end hook
turns that into the step's summary.

Per step execution, the record holds:
- status, start/end time, duration, attempt/iteration number;
- engine, model, session id, turns;
- tokens (input, output, cache read, cache write) and `cost_usd` — as reported by the engine;
- the ordered action trace (and the raw event log);
- files changed with status (added/modified/deleted/renamed), lines added/removed per file,
  totals;
- per-hook breakdown of all of the above.

Aggregates: run totals, feature totals (across runs), repo totals, filterable by time.

Notes:
- `cost_usd` is the engine's reported cost (API-price equivalent for Claude Code; notional on
  subscription plans).
- Steps in a `fan-out` share one worktree concurrently, so file/line changes are attributed to
  the fan-out step as a whole; cost and actions are still per item.
- Workflows may set `tracking: false` to disable the built-in hooks (default on).

## 9. Runs

### 9.1 Lifecycle
States: `created → running → completed | paused | failed | aborted`. `paused` happens at a gate
without a verdict. `resume <run_id>` (with optional new inputs, e.g. a gate verdict) continues
`paused` or `failed` runs; completed steps are replayed from state, not re-executed. A failed
step re-runs from its start (a new engine session). A run that was `running` when its process
died is marked `failed` on next startup and is resumable.

A run ends at `completed`. compose performs no push, PR or merge; workflows add steps or hooks
for that if wanted. compose does not auto-commit between steps.

### 9.2 Limits
Engine steps and the run may set `max_cost_usd` and `max_turns`. The adapter watches running
usage and stops the engine when a limit is exceeded; the step fails with reason
`limit_exceeded`.

### 9.3 Features and concurrency
- Starting a run with no `feature` input creates a new feature **before the first step**: next
  number, short name from an optional `feature_name` input or else a slug of the first words of
  the spec input (no engine call), its branch from the repo's default branch, and its worktree.
  With `feature`, the run uses the existing one.
- The runner exports `COMPOSE_RUN_ID` and `COMPOSE_FEATURE` to the engine and hooks.
  `compose feature new` returns the current feature unchanged when `COMPOSE_FEATURE` is set, so
  the specify skill never creates a second feature inside a workflow.
- **By hand**, features work as in spec-kit: `compose feature new` creates the numbered branch
  and `specs/NNN-name/` **in the current checkout** — no worktree. Worktrees are only a
  workflow-run concern. `compose feature paths` resolves the feature from `COMPOSE_FEATURE` or
  the current branch, so the skills behave identically in both cases.
- One active run per feature (lock). A second run on a busy feature is rejected with a clear
  error. Runs on different features run in parallel.
- Worktrees live under the compose home: `~/.compose/worktrees/<repo>/<feature>/`.

## 10. Repos

- `compose repo add <path>` registers a local clone. `compose repo add <git-url>` clones into
  `~/.compose/repos/<name>/` and registers it.
- A repo must be initialized for an engine (`compose init`) before running workflows.
- Repos have a short unique id used in CLI flags and API paths.

## 11. Engines

The core talks to engines only through an adapter interface:

```
run(task, cwd, options) -> async stream of EngineEvent, ending in EngineResult
  task:    skill invocation (name + args) | inline prompt
  options: model, reasoning_effort, max_turns, max_cost_usd, timeout, permission settings
  EngineEvent:  message | tool_call | tool_result | usage_update
  EngineResult: status, session_id, turns, tokens{in,out,cache_read,cache_write},
                cost_usd, duration, final_text
install(repo) / check()   # put skills in place for this engine; verify prerequisites
```

Workflows refer to engines by name (`engine: claude`); nothing in the workflow format is
Claude-specific beyond the name and model strings.

**Claude adapter (v1):** uses the Claude Agent SDK for Python, running in the feature
worktree with project settings loaded (so the installed skills are available); invokes a
skill as `/<skill-name> <args>`; maps SDK messages to `EngineEvent`s and the SDK result to
`EngineResult`. Runs headless, so it sets a non-interactive permission mode (default: accept
edits plus an allowed-tools list configurable per workflow/step).

## 12. Skills and Claude Code install

`compose init --engine claude` in a repo:
- installs the skills into `.claude/skills/compose-<name>/SKILL.md`: `compose-constitution`,
  `compose-specify`, `compose-clarify`, `compose-plan`, `compose-tasks`, `compose-analyze`,
  `compose-checklist`, `compose-implement`;
- installs templates (`spec`, `plan`, `tasks`, `checklist`) under `.compose/templates/` and the
  constitution at `.compose/memory/constitution.md`;
- installs built-in workflows' references under `.compose/workflows/`;
- adds compose's local state to `.gitignore`;
- does **not** commit; it tells the user to commit the installed files (skills, templates,
  constitution) if they want them shared;
- installs a `compose` operator skill so a Claude Code user can ask Claude to run workflows,
  check status, and report cost via the CLI.

**Worktree setup.** When compose creates (or reuses) a feature worktree for a run, the engine
adapter's `install()` makes sure the engine files exist there (for Claude: `.claude/skills/
compose-*`, `.compose/templates/`) — whether or not the repo committed them. Files compose put
there itself are listed in the worktree's git exclude file, so they never show up in diffs or
line counts. This is what makes cloned repos (where nobody commits init files) work. If the
repo has committed its own versions, those are used as-is.

**Constitution.** The constitution is project content at `.compose/memory/constitution.md`.
If `full-cycle` creates it inside a run, it lands on the feature branch and reaches the
default branch when the feature is merged; that change is tracked like any other.

Skills do the same thing by hand or in a workflow. Where spec-kit's commands call bash/
PowerShell helper scripts (create feature, locate feature paths, check prerequisites), compose
skills call the `compose` CLI instead (e.g. `compose feature new --json`,
`compose feature paths --json`) — one cross-platform implementation shared by manual use and
workflows.

## 13. CLI

```
compose init [--engine claude] [--path .]
compose check                                  # prerequisites (git, engine, versions)
compose repo add <path|url> [--name] | list | remove <repo>
compose feature list | new <short-name> | show <feature> | paths --json
compose workflow list | info <id> | add <path|url> | remove <id> | validate <file>
compose run <workflow-id|file> [--repo] [--feature] -i key=value ... [--detach] [--json]
compose status [<run_id>] [--json]             # run + per-step status
compose resume <run_id> [-i key=value ...]
compose abort <run_id>
compose trace <run_id> [--step <id>] [--json]  # actions per step
compose changes <run_id> [--step <id>]         # files and lines per step
compose cost [--repo] [--feature] [--run] [--by step|run|feature|day]
compose serve [--host 127.0.0.1] [--port 8765]
```

`--repo` defaults to the repo containing the current directory. `compose run` without
`--detach` runs in the foreground; with `--detach` (or when a server is running) the run is
handed to the server. CLI and server share the same store, so a run started in one is visible
and resumable from the other.

## 14. API

`compose serve` — FastAPI, JSON, binds to localhost by default; optional static bearer token
via config. Run ids are globally unique.

```
GET    /repos                         POST /repos {path | url, name?}     DELETE /repos/{repo}
GET    /repos/{repo}/workflows        GET  /repos/{repo}/workflows/{id}
GET    /repos/{repo}/features         GET  /repos/{repo}/features/{feature}
POST   /repos/{repo}/runs             {workflow, feature?, inputs}  -> {run_id, status}
GET    /runs?repo=&feature=&status=&since=
GET    /runs/{run_id}                 status, current step, per-step summary, totals
GET    /runs/{run_id}/steps/{exec_id} full step record incl. hooks breakdown
GET    /runs/{run_id}/events          paged; ?stream=true for Server-Sent Events (live)
GET    /runs/{run_id}/changes         files/lines per step
POST   /runs/{run_id}/resume          {inputs?}
POST   /runs/{run_id}/gates/{step_id} {choice}   # convenience: sets verdict and resumes
POST   /runs/{run_id}/abort
GET    /costs?repo=&feature=&run=&group_by=step|run|feature|day&from=&to=
GET    /health
```

An OpenAPI document is served at `/openapi.json`.

## 15. Storage

- **Per run (files):** `~/.compose/runs/<run_id>/` — `definition.yml`, `inputs.json`,
  `state.json` (status, step progress, outputs), `log.jsonl` (append-only event log incl.
  engine events), `steps/<exec_id>.json` (step records). Kept outside the worktree so run
  history survives when a feature's worktree is deleted after merge.
- **Database (SQLite):** `~/.compose/compose.db` — repos, features, runs, step executions,
  hook executions, action trace rows, cost/usage rows, file-change rows. The durable source
  for status, trace, change and cost queries; the run files are the raw log and resume state.
- **Compose home:** `~/.compose/` — `compose.db`, `config.yml`, `runs/`, `repos/`,
  `worktrees/`.
- compose never deletes worktrees in v1. If a worktree is removed, completed runs stay fully
  queryable; resuming a paused/failed run on that feature recreates the worktree from the
  feature branch.

## 16. Built-in workflows

- `full-cycle`: constitution (if missing) → specify → review-spec gate → clarify (optional) →
  plan → review-plan gate → tasks → analyze → implement.
- `quick`: specify → plan → tasks → implement, no gates.
- `bugfix`: assess → fix → test loop (`do-while` until tests pass, max 3) → summary.

## 17. Left to the builder

- Exact SQLite schema, file JSON shapes, and event schema (must cover §8 fields).
- Expression evaluator implementation (spec-kit-compatible semantics above).
- Skill prompt contents and templates (adapted from spec-kit's, renamed to compose).
- How the server executes runs internally (async tasks vs worker processes), as long as
  locks, crash recovery and the CLI/server shared store hold.
- Default allowed-tools list for headless Claude runs.
- Logging, config file format details, packaging metadata.

## 18. Calls made without explicit user confirmation (review these)

- Python + Typer/Rich + FastAPI + SQLite; Claude Agent SDK for Python.
- Run files under `~/.compose/runs/`, not in the repo (they were git-ignored anyway, so they
  wouldn't have travelled with the code); SQLite is the durable record. No auto-commits.
- New feature's short name: `feature_name` input or slug of the spec text, no engine call.
- Manual feature creation stays in the current checkout (branch only, like spec-kit);
  worktrees only for workflow runs.
- `compose init` doesn't commit; run worktrees get engine files installed and git-excluded.
- Fan-out: file/line changes attributed to the fan-out step, not per item.
- Optional hooks: failure doesn't fail the step; their TTY question is `prompt_text`;
  non-interactive runs execute them.
- Per-step and run-wide `max_cost_usd` / `max_turns` limits.
- Step types `github`, `init`, `slot` from spec-kit dropped.
- Skills call the `compose` CLI instead of bash/PowerShell scripts.
- A `compose` operator skill for driving compose from inside Claude Code.
- API on localhost, optional static token, no users.
- Second run on a busy feature is rejected (not queued).
