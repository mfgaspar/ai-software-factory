# HTTP API

`compose serve` serves a JSON API on `http://127.0.0.1:8765` by default. The full OpenAPI
document is served at `/openapi.json` (a copy is in [openapi.json](openapi.json)), with
interactive docs at `/docs`.

Runs started through the API execute inside the server. The server and the CLI share one
store (`~/.compose`), so a run started by either can be followed, answered and resumed by
the other. Stopping the server marks the runs it was executing `failed`; resume them later.

## Authentication

With `server.token` set in `~/.compose/config.yml` (or `COMPOSE_API_TOKEN` in the
server's environment), every route except `/health` needs
`Authorization: Bearer <token>`. Without a token, anyone who can reach the port can start
runs, so keep the default localhost binding unless you set one.

## Errors

Errors are JSON `{"detail": "..."}`:

| status | when |
|---|---|
| 401 | missing or wrong token |
| 404 | unknown repo, workflow, feature, run or step |
| 409 | the feature already has an active run; the repo already has an active clarity run; the run is in the wrong state (e.g. resuming a completed run, answering a gate it is not waiting at); the pre-run check refused a feature run (see below); a clarity merge is still pending |
| 422 | missing or invalid inputs, an invalid workflow, an unknown engine, a bad query value, an invalid clarity answer, `mode: interactive` |

When the [pre-run check](clarity.md#compose-build) refuses a feature run (`POST
/repos/{repo}/runs` or `/builds`), the 409 body lists each problem with its fix:

```json
{
  "detail": "The clarity foundation doesn't pass (or changed since it was validated). Fix: compose clarity validate",
  "problems": [
    {"message": "The clarity foundation doesn't pass (or changed since it was validated).",
     "fix": "compose clarity validate"}
  ]
}
```

A run that starts returns 202 with the run brief plus `run_id` and `warnings`: the pre-run
check's warnings (for example "No clarity foundation: building on a guessed constitution…"),
empty when there are none and always empty for clarity runs.

## Routes

| method and path | what it does |
|---|---|
| `GET /health` | `{status, version, active_runs}` |
| `GET /repos` | registered repos |
| `POST /repos` | `{path}` or `{url}`, optional `name`: register or clone (201) |
| `GET /repos/{repo}` · `DELETE /repos/{repo}?force=&delete_clone=` | show · unregister |
| `GET /repos/{repo}/workflows` | built-in and installed workflows |
| `GET /repos/{repo}/workflows/{id}` | definition and effective hooks |
| `GET /repos/{repo}/features` | features with run counts |
| `GET /repos/{repo}/features/{feature}` | paths, which spec files exist, worktree, runs, totals |
| `POST /repos/{repo}/runs` | `{workflow, feature?, inputs}`: start a run (202, with the pre-run check's `warnings`) |
| `GET /runs?repo=&feature=&status=&since=&limit=` | root runs, newest first, with cost |
| `GET /runs/{run}` | status, current step, `waiting` (the gate or questions step it's paused at; at a questions step, `waiting.questions` lists the pending questions it waits for), every step, totals, `worktree` (the clarity worktree for repo-scoped runs) |
| `GET /runs/{run}/steps/{exec_id}` | one step execution: totals, hooks, files, actions |
| `GET /runs/{run}/trace?step=` | actions per step, hooks nested |
| `GET /runs/{run}/changes?step=` | files and lines per step |
| `GET /runs/{run}/events?after=&limit=` | the event log, paged |
| `GET /runs/{run}/events?stream=true` | the event log as Server-Sent Events |
| `POST /runs/{run}/resume` | `{inputs?, choice?}`: continue a paused or failed run (202) |
| `POST /runs/{run}/gates/{step}` | `{choice}`: answer the waiting gate and resume (202) |
| `POST /runs/{run}/abort` | abort |
| `GET /costs?repo=&feature=&run=&group_by=&from=&to=` | totals grouped by `step`, `run`, `feature`, `repo` or `day` |

Response bodies have the same shape as the matching CLI command's `--json` output.

## Clarity and build

The two steps of [Clarity and build](clarity.md), over HTTP. Interactive clarity needs a
person in a Claude Code session, so the API offers `mixed` and `auto` only.

| method and path | body | response |
|---|---|---|
| `POST /repos/{repo}/clarity` | `{sources?: [str], mode?: "mixed" \| "auto"}` (default `mixed`) | 202, the run brief with `run_id` and `warnings`. 409 while another clarity run is running or paused; 422 for `interactive` |
| `GET /repos/{repo}/clarity` | — | the clarity status, as `compose clarity status --json` (below). No model call |
| `GET /repos/{repo}/clarity/questions` | — | the pending questions, in the order they're asked: a list of question objects (the fields of [the questions file](clarity.md#the-questions-file)) |
| `POST /repos/{repo}/clarity/answers` | `{answers: {id: answer}, by: str, resume?: bool = true}` | `{recorded: [id], resumed_run: id \| null}`. All or nothing: any invalid answer (unknown or answered question, not one of the options, an approval from someone other than its approver) gives 422 and records nothing. With `resume`, the paused clarity run is resumed when nothing it asked is still pending (approvals aside) |
| `POST /repos/{repo}/clarity/validate` | — | 202, the brief of a `clarity-validate` run |
| `POST /repos/{repo}/clarity/merge` | — | `{merged: true}`, or 409 `{detail, merged: false, pending_reason}` |
| `POST /repos/{repo}/builds` | `{spec: str, workflow?, feature?, inputs?}` | 202, the run brief with `run_id` and `warnings`; 409 with `problems` when the pre-run check refuses. `spec` fills the workflow's first required string input (`spec` for the built-ins); don't also put it in `inputs` |

`GET /repos/{repo}/clarity`:

```json
{
  "repo": "shop",
  "started": true,
  "branch": "clarity",
  "worktree": "/home/me/.compose/worktrees/shop/clarity",
  "documents": {"goal/problem.md": "complete", "product/prd.md": "draft"},
  "fingerprint": "3f9c…",
  "verdict": {"result": "FAIL", "incomplete": 1, "fingerprint": "3f9c…",
              "run_id": "run_…", "at": "2026-11-23T10:00:00+00:00", "current": true},
  "questions": {"pending": 2, "holding": 1, "ids": ["Q-007", "Q-012"]},
  "constitution": {"fingerprint": "3f9c…", "current": true},
  "active_run": {"id": "run_…", "status": "paused", "...": "..."},
  "build": {"ok": false, "warnings": [],
            "problems": [{"message": "Clarity is in progress on branch `clarity` and hasn't passed yet.",
                          "fix": "compose clarity"}]}
}
```

`questions.holding` counts the pending questions that hold a run (all but approvals).
Before clarity starts, `started` is false, `documents` is empty and `verdict` null.

A paused clarity run shows what it waits for:

```json
{"status": "paused",
 "waiting": {"step_id": "questions", "questions": [
   {"id": "Q-007", "kind": "gap", "document": "product/prd.md",
    "question": "The PRD says 3 user roles; the code has 2. Which is right?",
    "options": ["3 roles (PRD)", "2 roles (code)"], "recommended": "3 roles (PRD)",
    "free_text": true, "approver": null, "answer": null, "...": "..."}]}}
```

### Example: clarity, then a build

```bash
API=http://127.0.0.1:8765
RUN=$(curl -s -X POST $API/repos/shop/clarity -H 'content-type: application/json' \
  -d '{"sources": ["docs/"]}' | jq -r .run_id)

curl -s $API/runs/$RUN | jq '.status, [.waiting.questions[]? | {id, question, recommended}]'

curl -s -X POST $API/repos/shop/clarity/answers -H 'content-type: application/json' \
  -d '{"answers": {"Q-001": "confirm", "Q-002": "3 roles (PRD)"}, "by": "Rui Costa"}'
# {"recorded": ["Q-001", "Q-002"], "resumed_run": "run_…"}

# … repeat until the run completes; then:
curl -s $API/repos/shop/clarity | jq '.verdict.result, .build'

curl -s -X POST $API/repos/shop/builds -H 'content-type: application/json' \
  -d '{"spec": "Wishlist for signed-in users"}' | jq '{run_id, warnings}'
```

## Example: a run with a review gate

```bash
API=http://127.0.0.1:8765

curl -s -X POST $API/repos -H 'content-type: application/json' \
  -d '{"path": "/work/shop"}'

RUN=$(curl -s -X POST $API/repos/shop/runs -H 'content-type: application/json' \
  -d '{"workflow": "full-cycle", "inputs": {"spec": "Wishlist for signed-in users"}}' \
  | jq -r .run_id)

curl -s $API/runs/$RUN | jq '{status, waiting}'
# {"status": "paused", "waiting": {"step_id": "review-spec", "message": "Review ...",
#  "options": ["approve", "reject"], ...}}

curl -s -X POST $API/runs/$RUN/gates/review-spec -H 'content-type: application/json' \
  -d '{"choice": "approve"}'

curl -s "$API/costs?run=$RUN&group_by=step" | jq '.groups[] | {key, cost_usd, changes}'
```

## Events

Each line of a run's event log is an event with a `type` (`run_started`, `step_started`,
`engine_event`, `hook_finished`, `gate_waiting`, `step_finished`, `run_paused`,
`run_finished`, …) and a `seq`, its position in the log.

- **Paged:** `GET /runs/{run}/events?after=<seq>&limit=500` returns
  `{run_id, events, next}`; pass `next` as `after` to continue.
- **Live:** `GET /runs/{run}/events?stream=true` is a Server-Sent Events stream. Each
  message has `id: <seq>`, `event: <type>` and the event as JSON in `data`. It ends with an
  `end` event once the run completes, pauses, fails or aborts; reconnect after a resume.
  Reconnecting with `Last-Event-ID` (or `after`) continues where you left off. A comment
  line is sent every 15 seconds when nothing happens.

```bash
curl -N "$API/runs/$RUN/events?stream=true"
```

Steps of a called workflow (`type: workflow`) are logged in that child run's own log; its
id is in `children` of `GET /runs/{run}`.
