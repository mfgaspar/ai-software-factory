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
| 409 | the feature already has an active run; the run is in the wrong state (e.g. resuming a completed run, answering a gate it is not waiting at) |
| 422 | missing or invalid inputs, an invalid workflow, an unknown engine, a bad query value |

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
| `POST /repos/{repo}/runs` | `{workflow, feature?, inputs}`: start a run (202) |
| `GET /runs?repo=&feature=&status=&since=&limit=` | root runs, newest first, with cost |
| `GET /runs/{run}` | status, current step, waiting gate, every step, totals |
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
