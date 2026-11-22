# compose

Spec-driven development workflows for coding engines, starting with Claude Code.

You describe a feature; compose has the engine write a specification, a plan and a task
list, then implement it, on its own branch and worktree. Each step's actions, cost, tokens
and changed files are recorded. You can drive it from the command line, from an HTTP API,
or by hand inside Claude Code with the same skills.

- **Skills** for Claude Code: `/compose-specify`, `/compose-clarify`, `/compose-plan`,
  `/compose-tasks`, `/compose-analyze`, `/compose-checklist`, `/compose-implement`,
  `/compose-converge`, `/compose-find-skills` (search and install other agent skills, with
  `npx skills`; adapted from vercel-labs/skills, MIT),
  `/compose-constitution`, and `/compose`, which operates compose itself.
- **Workflows** chain those skills with shell steps, review gates, loops, branches and
  hooks. Four are built in (`pipeline`, the default, plus `quick`, `full-cycle`, `bugfix`) and you can write your own.
- **Traceability:** every message, tool call and result per step, with hooks nested.
- **Cost and change tracking** per step, run, feature, repo or day, hooks included.
- **One worktree and branch per feature**; runs on different features run in parallel.
- **One store, many repos**: register local clones or clone from a git URL.

## Install

You need Python 3.11+, [uv](https://docs.astral.sh/uv/), git, and Claude Code signed in
(`claude auth login`) or `ANTHROPIC_API_KEY` set. compose runs the `claude` on your PATH
(`claude -p --output-format stream-json`), or the copy bundled with the Claude Agent SDK
when there is none. To drive Claude Code through the SDK instead, set
`engines.claude.transport: sdk` in `~/.compose/config.yml`.

```bash
uv tool install /path/to/compose        # a local checkout
uv tool install git+<repository-url>    # or straight from its git host
```

This puts `compose` on your PATH. Check the prerequisites:

```bash
compose check
```

## Quick start

In the repository you want to work on:

```bash
compose init --engine claude
```

This installs the skills into `.claude/skills/`, the templates into `.compose/templates/`,
a starter constitution into `.compose/memory/constitution.md`, adds compose's local folders
to `.gitignore` and registers the repo. Commit those files so your team gets the skills.

Run the `quick` workflow (specify → plan → tasks → implement → converge):

```bash
compose run quick -i spec="Add a CSV export to the reports page" \
  -i allowed_tools="Bash(npm test)"
```

compose creates feature `001-add-csv-export` with its own branch and worktree under
`~/.compose/worktrees/`, then runs each step there, printing a line per step. Nothing is
committed or pushed for you; review and merge the feature branch as usual.

`allowed_tools` names the commands implement may run without asking (here, the tests).
Without it, implement can edit files but not run your project's commands.

Follow and inspect runs:

```bash
compose status                       # recent runs
compose status <run>                 # each step: status, time, cost, tokens, files, lines
compose trace <run> --step implement # what the engine did
compose changes <run>                # files and lines per step
compose cost --by feature            # where the money went
```

`full-cycle` adds review gates. When a run reaches one, it pauses:

```bash
compose run full-cycle -i spec=@feature.md --detach   # background; prints the run id
compose status <run>                                  # "Waiting at gate review-spec ..."
compose resume <run> --choice approve --detach
```

On a terminal without `--detach`, compose asks at the gate instead.

## By hand

The skills work in Claude Code exactly as they do in a workflow, without tracking:

```text
/compose-specify Add a CSV export to the reports page
/compose-plan React frontend, existing Express API
/compose-tasks
/compose-implement
/compose-converge        # appends what is still missing to tasks.md; implement again
```

`/compose-specify` creates the numbered branch and `specs/NNN-name/` folder in your current
checkout. Or ask Claude Code to "run the quick compose workflow for …": the `compose`
skill starts and follows runs for you, and leaves gate decisions to you.

## HTTP API

```bash
compose serve                        # http://127.0.0.1:8765, docs at /docs
curl -X POST localhost:8765/repos/myrepo/runs \
  -H 'content-type: application/json' \
  -d '{"workflow": "quick", "inputs": {"spec": "Add a CSV export"}}'
```

Runs started through the API and the CLI share one store: each can follow and resume the
other's. Live progress streams as Server-Sent Events from `/runs/{id}/events?stream=true`.

## Documentation

- [CLI reference](docs/cli.md)
- [HTTP API](docs/api.md)
- [Writing workflows and hooks](docs/custom-workflows.md)
- [Workflow reference](docs/workflow-reference.md): every field and behavior
- [Design](docs/superpowers/specs/2026-11-21-compose-design.md) and
  [implementation plan](docs/superpowers/plans/2026-11-21-compose-plan.md)

## Where things are kept

| what | where |
|---|---|
| database (runs, steps, hooks, actions, costs, file changes) | `~/.compose/compose.db` |
| per run: definition, inputs, state, event log, step records | `~/.compose/runs/<run>/` |
| feature worktrees | `~/.compose/worktrees/<repo>/<feature>/` |
| repos cloned from URLs | `~/.compose/repos/` |
| settings | `~/.compose/config.yml` |

Set `COMPOSE_HOME` to use another folder. compose never deletes worktrees; run history
stays queryable after you remove one.

## Development

```bash
uv sync
uv run pytest                 # unit tests (fake engine; no network)
uv run pytest -m live         # live tests on Claude Code (spends a few cents)
uv run ruff check && uv run ruff format --check && uv run mypy
```
