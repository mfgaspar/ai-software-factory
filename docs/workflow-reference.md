# Workflow reference

A **workflow** is a versioned list of steps that compose runs against one feature of one
repo. This page is the authoritative description of the format and its behavior.
(compose's format is inspired by spec-kit's workflows but is not compatible with them.)

- [Where workflows live](#where-workflows-live)
- [File layout](#file-layout)
- [Inputs](#inputs)
- [Steps](#steps) and [step types](#step-types)
- [Outputs of steps](#step-outputs)
- [Hooks](#hooks)
- [Tracking](#tracking)
- [Limits](#limits)
- [Engines and models](#engines-and-models)
- [Expressions](#expressions)
- [Errors, pausing and resuming](#errors-pausing-and-resuming)

## Where workflows live

| Source | Location | Notes |
|---|---|---|
| built-in | shipped with compose | `full-cycle`, `quick`, `bugfix` |
| repo | `.compose/workflows/<id>/workflow.yml` | installed with `compose workflow add`; shadows a built-in with the same id |
| file | any path passed to `compose run` | e.g. `compose run ./my-flow.yml` |

A workflow folder can contain companion files (scripts, prompts, README). Its path is
available to steps as `context.workflow_dir`. A run keeps a copy of the definition it
started with, so editing a workflow never changes a run in progress.

```bash
compose workflow list
compose workflow info full-cycle
compose workflow validate ./my-flow.yml
compose workflow add ./my-flow/          # or a file, or an https:// URL of a YAML file
compose workflow remove my-flow
```

## File layout

```yaml
schema_version: "1.0"          # optional, must be "1.0"
workflow:
  id: review-and-ship          # lowercase letters, digits, hyphens
  name: Review and ship
  version: 1.2.0               # X.Y.Z, default 0.0.0
  author: platform-team
  description: Specify, plan, implement and run the tests.
  engine: claude               # default engine for engine steps and hooks
  model: claude-sonnet-5-5     # default model
  reasoning_effort: medium
  limits:
    max_cost_usd: 25           # cap for the whole run
  tracking: true               # built-in tracking hooks (default true)
requires:
  compose_version: ">=0.1"     # informational
  engines: [claude]
inputs:
  spec:
    type: string
    required: true
    prompt: Describe the feature
  run_tests:
    type: boolean
    default: true
hooks:
  after_implement:
    - run: npm test
      description: Tests must pass after implementation
outputs:
  plan_file:
    value: "{{ context.feature.dir }}/plan.md"
steps:
  - id: specify
    command: compose-specify
    input:
      args: "{{ inputs.spec }}"
  - id: plan
    command: compose-plan
  - id: implement
    command: compose-implement
    limits:
      max_cost_usd: 10
      max_turns: 200
```

Unknown keys anywhere are errors, so typos are caught by `compose workflow validate`.

## Inputs

Inputs are the only variables in a workflow. Each has:

| Field | Default | Meaning |
|---|---|---|
| `type` | `string` | `string`, `number` or `boolean` |
| `required` | `false` | the run cannot start without it |
| `default` | none | used when not supplied |
| `prompt` | none | question shown when asking for a missing required input on a terminal |
| `description` | none | documentation |
| `enum` | none | allowed values |

Values given on the command line (`-i name=value`) or through the API are coerced to the
input's type. Booleans accept `true/1/yes/y/on` and `false/0/no/n/off`. Numbers accept
integers and decimals. An input that isn't supplied and has no default is *undefined* in
expressions (use `| default(...)`).

When a run starts without an existing feature, compose creates one and names it from the
`feature_name` input if the workflow declares it and it has a value, otherwise from the
first *required* string input (e.g. `spec`). A run on an existing feature passes the
`feature` option (`compose run --feature 003-user-auth`), not an input.

## Steps

Every step has:

| Field | Default | Meaning |
|---|---|---|
| `id` | required | unique within the workflow (nested steps included); letters, digits, `_`, `-`; `run` and `step` are reserved |
| `type` | inferred | see below |
| `name`, `description` | none | documentation |
| `continue_on_error` | `false` | if the step fails, record it and carry on |
| `timeout` | none | seconds; exceeding it fails the step |

`type` may be omitted: a step with `command:` is a `command` step, with `prompt:` a `prompt`
step, with `run:` a `shell` step.

### Step types

#### `command` — run a skill on the engine

```yaml
- id: plan
  command: compose-plan          # skill name
  input:
    args: "focus on the API first"
  engine: claude                 # optional overrides, see Engines and models
  model: claude-opus-5-5
  limits: { max_cost_usd: 5 }
```

#### `prompt` — send an inline prompt to the engine

```yaml
- id: review
  prompt: |
    Review {{ context.feature.dir }}/plan.md for missing error handling.
```

#### `shell` — run a command in the feature worktree

```yaml
- id: test
  run: npm test
  env: { CI: "1" }
  timeout: 600
  output_format: text            # or json: stdout is parsed into output.data
  capture: true                  # keep stdout/stderr in the output (default true)
  capture_max_bytes: 1000000
```

Values from `{{ }}` are substituted into `run` **as plain text, without shell escaping**.
To pass untrusted values safely, set `strict: true` (which forbids `{{ }}` in `run`) and pass
them through `env`:

```yaml
- id: notify
  type: shell
  strict: true
  env:
    TITLE: "{{ inputs.spec }}"
  run: ./scripts/notify.sh "$TITLE"
```

A non-zero exit code fails the step (use `continue_on_error: true` to branch on it).

#### `gate` — ask a human

```yaml
- id: review-spec
  type: gate
  message: "Review {{ context.feature.dir }}/spec.md"
  options: [approve, reject]     # default; at least two, unique
  verdict_input: spec_verdict    # optional: an input that answers the gate in advance
  on_reject: abort               # abort | skip | retry
```

How the gate decides:

1. If `verdict_input` names an input with a non-empty value, that value is the choice.
2. Otherwise, a run in the foreground on a terminal asks the user.
3. Otherwise the run **pauses**. Resume it with the choice:
   `compose resume <run> -i spec_verdict=approve`, or
   `POST /runs/{run}/gates/review-spec {"choice": "approve"}`.

A choice that isn't one of `options` is rejected and the gate stays paused. Choosing
`reject` applies `on_reject`:

- `abort` — the run ends with status `aborted`.
- `skip` — the gate completes with `output.choice == "reject"` and the run continues; use
  an `if` step to branch on it.
- `retry` — the run pauses at the same gate again (e.g. after someone edits the spec by
  hand); the next resume decides it anew. A pre-set verdict input is cleared on a retry,
  so the next resume must give a new answer.

Any other choice completes the gate with `output.choice` set and the run continues.

#### `if` — branch

```yaml
- id: maybe-clarify
  type: if
  condition: "{{ inputs.clarify }}"
  then:
    - id: clarify
      command: compose-clarify
  else:
    - id: note
      run: echo "skipping clarify"
```

#### `switch` — choose among cases

```yaml
- id: by-size
  type: switch
  expression: "{{ inputs.size }}"
  cases:
    small:
      - id: quick-plan
        command: compose-plan
    large:
      - id: deep-plan
        command: compose-plan
        model: claude-opus-5-5
  default:
    - id: default-plan
      command: compose-plan
```

The expression's value is converted to text and compared with the case keys.

#### `while` and `do-while` — loop

```yaml
- id: fix-until-green
  type: do-while               # body runs at least once
  max_iterations: 3            # required
  condition: "{{ steps.test.output.exit_code != 0 }}"
  steps:
    - id: fix
      prompt: Make the failing tests pass.
    - id: test
      run: npm test
      continue_on_error: true
```

`while` checks the condition before each iteration, `do-while` after. Reaching
`max_iterations` while the condition still holds is not a failure: the loop ends and
`output.exhausted` is `true`. Each iteration of each inner step is recorded separately;
`steps.<id>` refers to the most recent one.

#### `fan-out` and `fan-in` — parallel items

```yaml
- id: per-service
  type: fan-out
  items: "{{ inputs.services | split(',') }}"
  max_concurrency: 2
  step:
    id: review-service
    prompt: "Review the {{ item }} service against the plan."
- id: collect
  type: fan-in
  wait_for: [per-service]
  output:
    count: "{{ fan_in.results | length }}"
```

`item` is the current item inside the fan-out's template step. All items share the
feature worktree, so file changes are recorded against the fan-out step as a whole;
actions and cost are still recorded per item. In a fan-in step, `fan_in.<step-id>` is the
list of item outputs of that fan-out and `fan_in.results` is all of them concatenated.

#### `workflow` — call another workflow

```yaml
- id: run-bugfix
  type: workflow
  workflow: bugfix
  input:
    report: "{{ inputs.report }}"
    test_command: npm test
```

The child runs in the same feature and worktree as a linked child run. Its declared
`outputs` become this step's output. Calls nest up to 16 deep; a workflow cannot call
itself directly or through others.

### Step outputs

| Step type | `steps.<id>.output` |
|---|---|
| `command`, `prompt` | `text` (the engine's final response), `session_id` |
| `shell` | `exit_code`, `stdout`, `stderr` (when captured), `data` (with `output_format: json`) |
| `gate` | `choice` |
| `if` | `branch`: `"then"`, `"else"` or `null` |
| `switch` | `case`: the matched key, `"default"` or `null` |
| `while`, `do-while` | `iterations`, `exhausted` |
| `fan-out` | `results` (one output per item, in item order), `count` |
| `fan-in` | the evaluated `output` mapping |
| `workflow` | the child's declared outputs, plus `run_id` |

Every step also exposes its tracking values (see [Tracking](#tracking)):

| Expression | Meaning |
|---|---|
| `steps.<id>.status` | `completed`, `failed`, `skipped`, … |
| `steps.<id>.cost_usd` | cost of the step including its hooks |
| `steps.<id>.tokens.input` / `.output` / `.cache_read` / `.cache_write` | token counts |
| `steps.<id>.changes.files` / `.added` / `.removed` | files changed and lines added/removed |

### Context

| Expression | Meaning |
|---|---|
| `context.run_id` | this run's id |
| `context.workflow_dir` | folder of the workflow definition |
| `context.worktree` | the feature worktree the run works in |
| `context.repo.id`, `context.repo.name` | the repo |
| `context.feature.id`, `.name`, `.branch`, `.dir` | the feature; `dir` is `specs/<name>` relative to the worktree root |
| `context.constitution_exists` | whether `.compose/memory/constitution.md` exists |

## Hooks

Hooks run before or after steps, or around the whole run. They are declared only in the
workflow, under `hooks:`, keyed by event:

| Event | When |
|---|---|
| `before_run`, `after_run` | once, around the whole run (`after_run` only when it completes) |
| `before_step`, `after_step` | around every step |
| `before_<step-id>`, `after_<step-id>` | around one step |

```yaml
hooks:
  before_implement:
    - run: npm ci
      description: Install dependencies
  after_implement:
    - run: npm test
    - command: compose-checklist
      optional: true
      prompt_text: Generate a release checklist?
      condition: "{{ inputs.release }}"
      priority: 20
  after_step:
    run: ./scripts/post-progress.sh
    optional: true
```

Each event takes one hook or a list. Hook fields:

| Field | Default | Meaning |
|---|---|---|
| `command` / `prompt` / `run` | — | exactly one: a skill (with optional `args`), an inline engine prompt, or a shell command |
| `optional` | `false` | a failure is recorded but doesn't fail the step |
| `prompt_text` | none | for optional hooks: question asked on a terminal before running; non-interactive runs just run the hook |
| `description` | none | label shown in traces |
| `condition` | none | expression; the hook is skipped when false |
| `priority` | `10` | lower runs first; ties keep declaration order |
| `env`, `timeout` | none | as for shell steps |
| `engine`, `model`, `reasoning_effort`, `engine_options` | inherited | for `command`/`prompt` hooks |

Semantics:

- compose runs hooks itself (not the engine), in the feature worktree, with the same
  environment as steps.
- For a step, the order is: `before_step` hooks, then `before_<id>` hooks, the step, then
  `after_<id>`, then `after_step` (each group sorted by priority).
- A required `before` hook that fails fails the step without running it. A required
  `after` hook that fails fails the step. `after` hooks run only if the step succeeded.
- Tracking's end hook runs even when the step or one of its hooks failed, so every step
  execution gets a record.
- `after` hooks can read the step they follow as `steps.<id>` (its status and output).
- A hook whose `condition` is false, or whose `prompt_text` question is answered no, is
  recorded as `skipped`.
- Hooks' actions, tokens, cost and file changes are added to the step they surround (so
  `steps.<id>.cost_usd` includes them); traces still show each hook separately. Hook cost
  counts toward the run's `max_cost_usd`; step `limits` apply to the step only.
- Hooks don't run around control-flow steps themselves (`if`, `switch`, loops, `fan-out`,
  `fan-in`, `workflow`), only around the steps inside them; `before_<id>` / `after_<id>`
  naming a control-flow step is a validation error. The exception is the fan-out
  template step: its hooks run once per item and can use `item`.
- A required `before_run` hook that fails fails the run before any step runs; a required
  `after_run` hook that fails fails the run.
- On resume, hooks that already finished for the same step execution (a gate that paused)
  or for the run (`before_run`, earlier `after_run` hooks) are not run again.

## Tracking

Every workflow implicitly includes two built-in hooks (shown by `compose workflow info`):

- `compose.track.begin` on `before_step`, always first: snapshots the worktree.
- `compose.track.end` on `after_step`, always last: records the files changed, lines
  added and removed, engine actions, tokens and cost of the step and its hooks.

Tracking wraps every step that does work (`command`, `prompt`, `shell`, `gate`) and, as
a whole, every `fan-out` (its items share the worktree, so their file changes can't be
told apart). Snapshots never commit or touch your index. Files ignored by git and
compose's own files are excluded. Set `workflow.tracking: false` to turn tracking off.

A step's changes cover everything from just before its first hook to just after its
last: the step itself, its hooks, and any edits made by hand while a gate was waiting.
Each hook is also measured on its own, so a step record shows which hook changed what.
Fan-out items keep their own cost and actions, but their file changes are recorded on
the fan-out. A loop or `if` shows the sum of the steps inside it. Run and feature totals
count a file once even when several steps changed it.

## Limits

```yaml
workflow:
  limits: { max_cost_usd: 30 }         # whole run
steps:
  - id: implement
    command: compose-implement
    limits: { max_cost_usd: 10, max_turns: 150 }
```

When a limit is reached compose stops the engine and the step fails with reason
`limit_exceeded`.

## Engines and models

`engine`, `model`, `reasoning_effort` and `engine_options` can be set on the workflow, on
an engine step, or on a hook. The most specific setting wins; unset values come from the
workflow, then from `defaults` in `~/.compose/config.yml`. `engine_options` are passed to
the engine adapter.

For Claude Code (`engine: claude`):

| `engine_options` key | Default | Meaning |
|---|---|---|
| `permission_mode` | `acceptEdits` | `default`, `acceptEdits`, `plan`, `bypassPermissions`, `dontAsk` or `auto` |
| `allowed_tools` | `compose` CLI only | tools allowed without asking, e.g. `["Bash(npm test)"]`; added to `Bash(compose:*)`, which compose's skills need |
| `disallowed_tools` | none | tools never allowed |
| `setting_sources` | `[project]` | which Claude Code settings to load: `user`, `project`, `local` |
| `add_dirs` | none | extra directories Claude Code may access |
| `cli_path` | bundled CLI | a specific `claude` executable |

`reasoning_effort` is one of `low`, `medium`, `high`, `xhigh`, `max`. A step's
`max_cost_usd`, or what is left of the run's, is passed to Claude Code as its budget, so
it stops itself when the budget runs out. A `command` step runs as the slash command
`/<skill> <args>`, the same as typing it. compose installs its skills into each feature
worktree and hides them from git, unless the repo commits its own copies.

## Expressions

Text fields can contain `{{ expression }}`. A field that is exactly one expression gets the
expression's typed value (a number, list, boolean…); otherwise the result is text.
Conditions (`if`, `while`, hook `condition`) may be written with or without braces.

- **Names:** `inputs`, `steps`, `context`, and inside fan-out/fan-in `item` and `fan_in`.
  Keys are letters, digits, `_` and `-`: `steps.review-spec.output.choice`.
- **Lookups:** `a.b`, `a[0]`, `a.0`, `a[inputs.key]`.
- **Literals:** `'text'`, `"text"`, `42`, `-1.5`, `true`, `false`, `null`, `[1, 2]`.
- **Comparisons:** `== != > < >= <=`, `in`, `not in` (substring for text).
- **Logic:** `and`, `or`, `not`.
- **Filters:** `value | filter` or `value | filter(arg)`, binding tighter than comparisons:

| Filter | Result |
|---|---|
| `default(x)` | `x` when the value is undefined or null |
| `join(sep)` | list joined into text (default `,`) |
| `contains(x)` | whether a list/text contains `x` |
| `map(key)` | list of `item[key]` |
| `from_json`, `to_json` | parse / serialize JSON |
| `upper`, `lower` | case |
| `split(sep)` | text split into a list (default: whitespace) |
| `length` | length of a list, mapping or text |

- **Undefined:** looking up something missing gives *undefined*. It is falsy and equals
  `null` in comparisons; `default` replaces it; rendering it into text is an error. An
  unknown top-level name (e.g. `input.spec`) is always an error.
- **Text conversion:** `true`/`false`, `null` → empty, lists and mappings → JSON.
- **Not supported:** arithmetic, function calls, string concatenation operators.

`compose workflow validate` checks every expression's syntax and that it only names
declared inputs and existing steps.

## Errors, pausing and resuming

Run states: `created → running → completed | paused | failed | aborted`.

- A step fails when its engine reports an error, a shell command exits non-zero, a limit
  or timeout is reached, or a required hook fails. The run then fails, unless the step has
  `continue_on_error: true`.
- A run pauses at a gate with no answer. `compose resume <run>` (optionally with
  `-i name=value`) continues a `paused` or `failed` run: steps that completed are not run
  again; the failed or paused step starts over. `--choice <option>` answers the gate
  that is waiting, even one inside a called workflow.
- `compose abort <run>` stops a running run between engine events and marks it `aborted`.
  A paused or failed run is aborted at once; an aborted run cannot be resumed.
- A run whose process died is marked `failed` the next time compose starts, and can be
  resumed.

## Running and reporting

```bash
compose run <workflow|file> [-i name=value ...] [--feature NNN-name] [--repo r] [--detach]
compose status [<run>] [--status paused] [--feature f]
compose resume <run> [--choice option] [-i name=value ...] [--detach]
compose abort <run>
compose trace <run> [--step id] [--full]
compose changes <run> [--step id]
compose cost [--run r | --feature f | --repo r | --all] [--by step|run|feature|repo|day]
             [--since 2026-11-01] [--until 2026-12-01]
```

- Every command takes `--json`. `-i name=@file` reads an input from a file.
- In the foreground, compose prints a line per step and, on a terminal, asks for missing
  inputs and gate decisions (`--no-interactive` pauses at gates instead).
- `--detach` starts the run in a background process and returns at once; its output goes
  to `process.log` in the run folder.
- `run` and `resume` exit with 0 when the run completes, 1 when it fails or is aborted, and
  3 when it pauses at a gate.
- `trace` lists each step's messages, tool calls and results, with each hook's own actions
  under it. The built-in tracking hooks appear only in `--json`.
- `cost` defaults to the repository you are in (all repositories elsewhere, or with
  `--all`) and groups by run, or by step with `--run`.

## HTTP API

`compose serve [--host 127.0.0.1] [--port 8765]` serves the same operations over HTTP;
the OpenAPI document is at `/openapi.json` and interactive docs at `/docs`. Runs started
through the API execute inside the server; runs started by the CLI are visible and
resumable through it, and the other way round.

| method and path | what it does |
| --- | --- |
| `GET /health` | liveness, version, runs executing in this server |
| `GET/POST /repos`, `GET/DELETE /repos/{repo}` | list, add (`path` or `url`), show, remove |
| `GET /repos/{repo}/workflows[/{id}]` | workflows, or one with its effective hooks |
| `GET /repos/{repo}/features[/{feature}]` | features, or one with its files, runs and totals |
| `POST /repos/{repo}/runs` | `{workflow, feature?, inputs}`: start a run (202; 409 if the feature is busy) |
| `GET /runs?repo=&feature=&status=&since=&limit=` | root runs, newest first |
| `GET /runs/{run}` | status, waiting gate, every step, totals |
| `GET /runs/{run}/steps/{exec_id}` | one step execution with hooks, files and actions |
| `GET /runs/{run}/trace?step=`, `GET /runs/{run}/changes?step=` | as `compose trace` / `changes` |
| `GET /runs/{run}/events?after=&limit=` | the event log, paged by `seq` |
| `GET /runs/{run}/events?stream=true` | Server-Sent Events until the run stops (honours `Last-Event-ID`) |
| `POST /runs/{run}/resume` | `{inputs?, choice?}` |
| `POST /runs/{run}/gates/{step}` | `{choice}`: answer the waiting gate and resume |
| `POST /runs/{run}/abort` | abort |
| `GET /costs?repo=&feature=&run=&group_by=&from=&to=` | as `compose cost` |

Set `server.token` in `config.yml` (or `COMPOSE_API_TOKEN`) to require
`Authorization: Bearer <token>` on every route except `/health`. Errors are JSON
`{"detail": ...}`: 404 for an unknown repo, run or feature, 409 for a busy feature or a run
in the wrong state, 422 for bad inputs or workflows. Stopping the server marks the runs it
was executing `failed`, so they can be resumed.

