---
name: compose
description: Operate compose for the user — start spec-driven workflows (pipeline — the default — full-cycle, quick, bugfix or custom), check run status, answer gates, resume or abort runs, and report traces, file changes and cost. Use when the user asks to run a compose workflow or asks about a compose run.
argument-hint: "[what to do, e.g. run full-cycle for <feature>]"
---

# Operate compose

The user's request:

```text
$ARGUMENTS
```

compose runs multi-step development workflows (specify → plan → tasks → implement → converge, …) on
Claude Code in a separate worktree per feature, and records every step's actions, cost and
file changes. You drive it through the `compose` CLI. Always pass `--json` when you need to
read results, and summarize them for the user in plain language instead of pasting JSON.

## Starting work

- See which workflows exist: `compose workflow list --json`; details and inputs:
  `compose workflow info <id>`.
- Start a run in the current repository:

  ```bash
  compose run <workflow> -i spec="<feature description>" --json
  ```

  Pass each input as `-i name=value` (`-i spec=@path/to/file.md` reads a file). Use
  `--feature NNN-name` to continue an existing feature, and `--detach` to run it in the
  background: it prints the run id at once and the run carries on after the command
  returns. Without `--detach` the command waits until the run completes, pauses or fails,
  which can take a long time — prefer `--detach` for anything beyond a quick test. Exit
  codes: 0 completed, 1 failed or aborted, 3 paused at a gate.
- Before the first run in a repository, `compose check` must pass; if it reports the repo
  is not initialized, run `compose init --engine claude`.

## Following a run

- `compose status --json` lists recent runs; `compose status <run_id> --json` shows every
  step with its status, cost and changes.
- A **paused** run is waiting at a gate (a human review). Tell the user what the gate asks
  and where the files to review are (in the feature's worktree, shown in the status). Only
  the user decides: never answer a gate yourself. When they decide, run
  `compose resume <run_id> --choice <option> --detach`.
- A **failed** run shows the failing step and its error. Explain it; after the cause is
  fixed (or with new inputs: `-i name=value`), `compose resume <run_id>` retries from the
  failed step. Completed steps are not repeated.
- `compose abort <run_id>` stops a run. Confirm with the user first.

## Reporting

- What the engine did: `compose trace <run_id> --json` (add `--step <id>` for one step).
- Files and lines changed: `compose changes <run_id> --json`.
- Cost: `compose cost --run <run_id> --json`, or `compose cost --by step|run|feature|day`
  for totals across runs.

Report cost as the engine reported it (on subscription plans it is a notional API-price
figure). Never invent numbers: if a command fails, show the error and what it suggests.
