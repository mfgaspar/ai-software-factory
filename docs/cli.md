# CLI reference

Every command that reports something takes `--json` and prints a stable JSON shape (the
same as the [HTTP API](api.md)). `--repo` defaults to the registered repo containing the
current directory. `compose <command> --help` shows the same options.

## Setup

| command | what it does |
|---|---|
| `compose init [--engine claude] [--path .]` | install skills and templates, add a starter constitution and `.gitignore` entries, register the repo. Safe to run again; commits nothing |
| `compose check [--engine claude]` | check git, the engine (installed, signed in) and the current repo; exits 1 if something required is missing, with how to fix it |

## Repos

| command | what it does |
|---|---|
| `compose repo add <path\|url> [--name n]` | register a local clone, or clone a git URL into `~/.compose/repos/` |
| `compose repo list` | registered repos |
| `compose repo remove <repo> [--force] [--delete-clone]` | unregister (`--force` if it has runs; `--delete-clone` only for repos compose cloned) |

## Features

Used by the skills; also handy by hand. Outside a workflow run, a feature is a numbered
branch plus `specs/NNN-name/` in your current checkout.

| command | what it does |
|---|---|
| `compose feature new <description> [--name short] [--no-switch]` | create the next numbered branch and specs folder (inside a run: returns the run's feature) |
| `compose feature paths` | paths of the current feature (from `COMPOSE_FEATURE` or the branch) |
| `compose feature list` | features found in branches and specs folders |
| `compose feature show <feature>` | a feature's paths and which spec files exist |

## Workflows

| command | what it does |
|---|---|
| `compose workflow list` | built-in workflows and those in `.compose/workflows/` (a repo's copy shadows a built-in) |
| `compose workflow info <id\|path>` | inputs, steps and the hooks that will run, tracking included |
| `compose workflow validate <path>` | check a workflow without running it |
| `compose workflow add <folder\|file\|url> [--force]` | install into `.compose/workflows/<id>/` |
| `compose workflow remove <id>` | remove an installed workflow |

## Runs

```bash
compose run <workflow|path> [-i name=value ...] [--feature NNN-name] [--repo r]
            [--detach] [--interactive/--no-interactive] [-v]
compose status [<run>] [--status s] [--feature f] [--repo r] [-n 20]
compose resume <run> [--choice option] [-i name=value ...] [--detach] [-v]
compose abort <run>
```

- `-i name=value` sets an input; repeat it. `-i name=@file` reads the value from a file.
- Without `--feature`, a run creates a new feature (named from `feature_name` or the first
  required text input) with its own branch and worktree.
- In the foreground a run prints a line per step (`-v` adds each tool call). On a terminal
  it asks for missing inputs and gate decisions; `--no-interactive` pauses at gates.
- `--detach` runs in a background process and returns the run id at once. Its output goes
  to `~/.compose/runs/<run>/process.log`.
- `resume` continues a paused or failed run. Completed steps are not run again; the failed
  or paused step starts over. `--choice` answers the gate it waits at.
- `abort` stops a running run at its next engine event, or ends a paused or failed one.
  An aborted run cannot be resumed.
- Exit codes of `run` and `resume`: 0 completed (or detached), 1 failed or aborted,
  3 paused at a gate.
- A run whose process died is marked failed the next time compose looks, and can be
  resumed. Only one run at a time per feature.

## Reports

```bash
compose trace <run> [--step id] [--full]
compose changes <run> [--step id]
compose cost [--run r | --feature f | --repo r | --all] [--by step|run|feature|repo|day]
             [--since 2026-11-01] [--until 2026-12-01]
```

- `trace`: each step's messages, tool calls and results, with each hook's own actions under
  it. Long values are cut to one line unless `--full`. The built-in tracking hooks show only
  in `--json`.
- `changes`: files and lines per step, counting everything in the step's window (its hooks
  too); `--json` also breaks out what each hook changed.
- `cost`: cost, tokens (input, output, cache read, cache write), files and lines, grouped.
  Defaults to the current repo and `--by run` (or `--by step` with `--run`). A file changed
  by two steps counts once in a total. Called workflows count toward the run that called
  them.

## Server

```bash
compose serve [--host 127.0.0.1] [--port 8765] [--log-level info]
```

See [api.md](api.md). Set `server.token` in `~/.compose/config.yml` (or
`COMPOSE_API_TOKEN`) before binding to anything but localhost.

## Configuration

`~/.compose/config.yml` (or `$COMPOSE_HOME/config.yml`), all optional:

```yaml
defaults:
  engine: claude
  model: claude-sonnet-5-5   # used when a workflow or step names none
server:
  host: 127.0.0.1
  port: 8765
  token: null
engines:                     # default engine_options per engine
  claude:
    transport: cli           # cli (claude -p, stream-json) or sdk (Claude Agent SDK)
```

Inside a run, steps and hooks see `COMPOSE_RUN_ID`, `COMPOSE_FEATURE`, `COMPOSE_REPO` and
`COMPOSE_WORKFLOW_DIR`.
