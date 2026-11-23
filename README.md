# compose

A spec-driven software factory for coding engines, starting with Claude Code. It works in two
steps:

1. **`compose clarity`: the foundation.** compose drafts the application's why, rules and how
   (problem, non-functional requirements and standards, architecture, ADRs, product brief,
   conventions, setup) from your documents and code, then asks people only what is still
   open, in batches. Once someone confirms it and the approvers sign off, it passes
   validation and is merged into your default branch, with a constitution generated from it.
2. **`compose build`: delivery.** You describe a feature in a sentence; compose has the
   engine specify, plan, break down and implement it on its own branch and worktree, inside
   that foundation. A repo that started clarity only builds on a foundation that passed.

```bash
compose clarity docs/                 # draft from docs/, then answer the open questions
compose build "Add a CSV export to the reports page"
```

Each step's actions, cost, tokens and changed files are recorded. You can drive it from the
command line, from an HTTP API, or by hand inside Claude Code with the same skills. See
[Clarity and build](docs/clarity.md).

- **Skills** for Claude Code: `/compose-specify`, `/compose-clarify`, `/compose-plan`,
  `/compose-tasks`, `/compose-analyze`, `/compose-checklist`, `/compose-implement`,
  `/compose-converge`, `/compose-bug-assess`, `/compose-bug-fix`, `/compose-bug-test`,
  `/compose-find-skills` (search and install other agent skills, with
  `npx skills`; adapted from vercel-labs/skills, MIT),
  `/compose-constitution`, and `/compose`, which operates compose itself.
- **Clarity skills**, a separate family for the application-level why, rules and how:
  `/clarity` writes and validates a project's problem, goals, non-functional requirements and
  standards, solution, failure analysis, architecture, ADRs, product brief, UX standards, API
  conventions, data rules and setup guide in `.clarity/` (adapted from microsoft/clarity-agent,
  MIT). The compose skills then specify and plan each feature within those rules. See
  [Clarity and build](docs/clarity.md).
- **Workflows**, the engine underneath, chain those skills with shell steps, review gates,
  question steps, loops, branches and hooks. `automated` (what `compose build` runs),
  `quick`, `full-cycle` and `bugfix` are built in, plus `clarity` and `clarity-validate`,
  and you can write your own.
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

From a checkout, the install scripts set everything up: they check git, install
[uv](https://docs.astral.sh/uv/) if it is missing (asking first; `--yes`/`-Yes` skips
the question), install compose with the Python it needs, and run `compose check`.

```bash
./install.sh                                  # Linux and macOS
./install.sh --source <path|git-url>          # install another checkout or a git URL
```

```powershell
.\install.ps1                                 # Windows (PowerShell)
.\install.ps1 -Source <path|git-url>
```

On Windows, install [Git for Windows](https://git-scm.com/download/win) first: workflow
shell steps run under its `sh`. Or install by hand with uv:

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

This installs the skills into `.claude/skills/`, the templates into
`.compose/templates/compose/` and `.compose/templates/clarity/`, a starter constitution into
`.compose/memory/constitution.md`, adds compose's local folders to `.gitignore` and registers
the repo. Commit those files so your team gets the skills.

### 1. The foundation: compose clarity

```bash
compose clarity docs/prd.md docs/notes.md   # mixed (the default): draft, then ask what's open
```

compose drafts every document unattended on a `clarity` branch, then asks the questions it
couldn't settle, most important first: the proposed setup, gaps in mandatory documents, one
review of the whole foundation and the approvals. On a terminal it asks them there; with
`--detach`, or through the API, the run pauses until they're answered:

```bash
compose clarity questions                   # what's pending, with recommendations
compose clarity answer Q-003 confirm        # records it; resumes the run when it can go on
compose clarity status                      # documents, verdict, whether a build can start
```

`--mode auto` only drafts and asks nothing (its questions wait for later). compose commits
the clarity documents and the generated constitution on the `clarity` branch as it goes, and
when validation passes (`CLARITY: PASS`) it fast-forwards your local default branch to it. It
never pushes.

### 2. Delivery: compose build

```bash
compose build "Add a CSV export to the reports page" -i allowed_tools="Bash(npm test)"
```

This runs the default `automated` workflow on a new feature, after a pre-run check: in a repo
that started clarity, it refuses until the foundation passes and the constitution is current,
saying how to fix it. Without clarity it builds anyway, with a warning that the foundation is a
guessed constitution. See [Clarity and build](docs/clarity.md).

### Workflows

Run any workflow directly, for example `quick` (specify → plan → tasks → implement →
converge):

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

The clarity skills work by hand too, in your own checkout (you commit yourself):

```text
/clarity docs/prd.md docs/notes.md      # mixed: draft, ask only about what's open, apply
/clarity docs/ interactive              # or the stage-by-stage conversation
/clarity-validate                       # ends with CLARITY: PASS or CLARITY: FAIL (n incomplete)
```

## HTTP API

```bash
compose serve                        # http://127.0.0.1:8765, docs at /docs
curl -X POST localhost:8765/repos/myrepo/clarity \
  -H 'content-type: application/json' -d '{"sources": ["docs/"]}'
curl localhost:8765/repos/myrepo/clarity/questions
curl -X POST localhost:8765/repos/myrepo/clarity/answers \
  -H 'content-type: application/json' -d '{"answers": {"Q-001": "confirm"}, "by": "Ana"}'
curl -X POST localhost:8765/repos/myrepo/builds \
  -H 'content-type: application/json' -d '{"spec": "Add a CSV export"}'
```

Runs started through the API and the CLI share one store: each can follow and resume the
other's. Live progress streams as Server-Sent Events from `/runs/{id}/events?stream=true`.

## Documentation

- [CLI reference](docs/cli.md)
- [HTTP API](docs/api.md)
- [Writing workflows and hooks](docs/custom-workflows.md)
- [Workflow reference](docs/workflow-reference.md): every field and behavior
- [Clarity and build](docs/clarity.md): modes, the questions file, the clarity branch, the
  pre-run check, and the clarity skills (documents, flow, config, approvals, validation)
- [Design](docs/superpowers/specs/2026-11-21-compose-design.md) and
  [implementation plan](docs/superpowers/plans/2026-11-21-compose-plan.md); clarity
  [design](docs/superpowers/specs/2026-11-22-clarity-skills-design.md) and
  [plan](docs/superpowers/plans/2026-11-22-clarity-skills-plan.md); clarity and build
  [design](docs/superpowers/specs/2026-11-23-clarity-and-build-design.md) and
  [plan](docs/superpowers/plans/2026-11-23-clarity-and-build-plan.md)

## Where things are kept

| what | where |
|---|---|
| database (runs, steps, hooks, actions, costs, file changes) | `~/.compose/compose.db` |
| per run: definition, inputs, state, event log, step records | `~/.compose/runs/<run>/` |
| feature worktrees | `~/.compose/worktrees/<repo>/<feature>/` |
| the clarity worktree (branch `clarity`) | `~/.compose/worktrees/<repo>/clarity/` |
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
