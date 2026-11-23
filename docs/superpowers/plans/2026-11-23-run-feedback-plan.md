# Run feedback — Implementation Plan

Date: 2026-11-23
Design: [../specs/2026-11-23-run-feedback-design.md](../specs/2026-11-23-run-feedback-design.md)
(approved 2026-11-23)

## How to use this plan

Milestones are independent except R4, which documents them all. Each one ends green
(`uv run pytest`, `uv run ruff check`, `uv run ruff format --check`) and is committed on its
own (`R<n>: …`). Unit tests use the fake engine and recorded event dicts. Nothing here calls a
model.

## Layout (target)

```text
src/compose/notify.py                    # new: notify(title, message), OS command per platform
src/compose/core/config.py               # + NotificationsConfig
src/compose/runner/runner.py             # notify on paused / completed / failed
src/compose/cli/runs.py                  # Progress (files, commentary, live status), questions
src/compose/clarity/questions.py         # Question.details
src/compose/assets/skills/clarity/SKILL.md   # question rules: headline, details, real options
tests/unit/test_notify.py, test_progress.py (new); test_cli_runs.py, test_clarity_questions.py,
  test_home_config.py (extended)
tests/conftest.py                        # COMPOSE_NOTIFY=0 for every test
```

---

## R1 — Progress you can follow

**T1.1 File lines.** `Progress.__call__`, on `engine_event` with `kind == "tool_call"` and
`name in WRITE_TOOLS` (`Write`, `Edit`, `MultiEdit`, `NotebookEdit`), prints
`<pad>  ✎ <path>`, always (not only with `-v`). The path comes from the call's input
(`file_path`, or `notebook_path`). It's made relative to the run's workdir when it's under it.
The workdir is passed to `Progress` by its callers, or taken from the `run_started` event if
that event carries it (check `runner.py`; add it to the event if it doesn't). Repeated writes
to the same file in one step print once per write, so edits stay visible.

**T1.2 Commentary.** On `engine_event` with `kind == "message"`, print the first non-empty line
of the text, dimmed and prefixed `»`, clipped to the console width minus the padding. Skip
empty text.

**T1.3 Other tool calls.** With `-v`, every other tool call prints as today
(`· <name>`), plus a short argument hint: the path, pattern or command, clipped.

**T1.4 Live status.** When `console.is_terminal`, a model step shows a transient status line,
`<step> · 2m14s · $0.41`. The time comes from the step's start, and the cost is the latest
`usage_update` `cost_usd` (or the running sum, whichever the engine reports; check
`engines/claude/mapping.py`). Use `rich.status.Status` or `Live` with `transient=True`, started
on `step_started` for command and prompt steps and stopped on `step_finished`. It also stops
before any prompt (the `ask_*` functions), so the input isn't overwritten. When the output
isn't a terminal there's no status line, and lines print as plain text.

**T1.5 Callers.** `cli/clarity.py` and `cli/build.py` and `runs.run/resume/follow` already
build `Progress(verbose)`. Pass the workdir where they have it. `--json` and `-d` stay
silent.

Tests (`test_progress.py`), feeding recorded event dicts to a `Progress` with a recording
console (`Console(file=StringIO(), width=80)`):
- A Write tool call prints `✎ .clarity/goal/problem.md` (relative path), without `-v`.
- A Read tool call prints only with `-v`.
- A message event prints its first line, clipped to the width.
- No status line when the console isn't a terminal.
- Nested steps keep their indentation.

## R2 — Questions that invite an answer

**T2.1 Model.** `clarity/questions.py`: `Question.details: list[str] = Field(default_factory=list)`.
It's already allowed as an extra key, so files with it load either way. Recording answers keeps
it (the round-trip test covers it).

**T2.2 Terminal.**
- `ask_question` prints the headline, then each detail as `  • <text>`, then the options.
- Its hint reads `Answer: a number, your own words, or Enter for '<recommended>'` when
  `free_text`, and `Answer: a number (Enter for '<recommended>')` otherwise. Without a
  recommendation, Enter leaves the question pending, as today.
- `_print_questions` (the detached and paused listing) shows the details too, indented under
  each question.

**T2.3 API.** Check how `views` serializes questions for the clarity routes and the run
detail. If it lists fields by hand, add `details`. Regenerate `docs/openapi.json` if the schema
changes (`test_openapi_copy_is_current`).

**T2.4 Skill.** `assets/skills/clarity/SKILL.md`, the question-file rules:
- `question`: one or two sentences, what you need decided.
- `details`: the supporting points, one per item (what's known, from where, what the answer
  changes).
- `options`: offer concrete alternatives when they exist. For example, setup offers
  `confirm`, plus `also require <document>` for the likeliest additions. Review offers
  `confirm`, plus a named correction when the draft had a weak inference.
- Keep `confirm` as the recommendation where the text says so today.
- Update the `draft` section's setup and review steps, which hard-code `[confirm]` now.
- Mirror the change in the `mixed` section: show the details, and remind that the person can
  answer in their own words.

Tests:
- `test_clarity_questions.py`: details load, survive `record`, and default to `[]`.
- `test_cli_runs.py`, or a new test of `ask_question` with a patched prompt: details are
  printed, free text is accepted, the hint differs for `free_text: false`.
- `test_clarity_skills` (or whichever test checks skill text): the skill mentions `details`.

## R3 — Desktop notifications

**T3.1 Module.** `src/compose/notify.py`:
- `notify(title: str, message: str) -> None`. It returns at once if `COMPOSE_NOTIFY` is `0`,
  `false` or `no`, or when the config's notifications are disabled (the caller passes
  `enabled`).
- The command per platform:
  - macOS: `osascript -e 'display notification <msg> with title <title>'`, with both
    strings escaped as AppleScript literals (backslash and double quote);
  - Linux: `notify-send <title> <message>` when it's on PATH;
  - Windows: `powershell -NoProfile -Command` with a `New-BurntToastNotification`-free toast:
    `[Windows.UI.Notifications.ToastNotificationManager]` and a toast XML template, with the
    strings XML-escaped.
- `subprocess.run(..., timeout=5, capture_output=True)`, with every exception swallowed and
  logged at debug level. It never raises.

**T3.2 Config.** `core/config.py`: `NotificationsConfig(_Section)` with `enabled: bool = True`,
and `Config.notifications`. Document it in `docs/cli.md`'s config block.

**T3.3 Runner.** In `Runner._set_status`, after the store update, call a
`_notify(run, status)` for `PAUSED`, `COMPLETED` and `FAILED`, never `ABORTED`:
- The message names the workflow and the repo: `clarity on wc-lite`, `automated on wc-lite
  (001-word-count)`.
- For `PAUSED` it says what it waits for:
  - the question ids, from the waiting questions step;
  - or the gate's message, from the paused gate step.
  Use what `views.waiting_questions` and the gate row already give.
- `FAILED` includes the failing step id.
- Only root runs notify (`parent_run_id is None`), so a called workflow doesn't double up.

**T3.4 Inline questions.** In the CLI's `_interaction`, the first `ask_question` of a batch
notifies "waiting for your answers (Q-001)". The CLI is in the foreground, but the person may
be elsewhere. Notify once per questions step, not once per question.

**T3.5 Tests stay quiet.** `tests/conftest.py`'s autouse fixture sets `COMPOSE_NOTIFY=0`.
The notify tests unset it locally.

Tests (`test_notify.py`, `test_home_config.py`):
- With `subprocess.run` and `sys.platform` patched:
  - macOS builds an osascript call with escaped quotes;
  - Linux uses notify-send, or does nothing when it's missing;
  - Windows builds a powershell call.
- `COMPOSE_NOTIFY=0` and `enabled: false` send nothing.
- A `TimeoutExpired`, `OSError` or non-zero exit doesn't raise.
- A fake-engine run that pauses on a questions step, and one that completes, each call
  `notify` once, with the expected message. A child run doesn't notify.
- The config accepts `notifications: {enabled: false}` and rejects unknown keys.

## R4 — Docs

- `docs/cli.md`:
  - what a running step shows (✎ lines, » commentary, the status line) and what `-v` adds;
  - the answer hint;
  - notifications and how to turn them off.
- `docs/clarity.md`: the `details` key in `questions.yml`.
- `README.md`: one line on notifications under configuration, if the config block lives
  there.
- The demo kit (`../compose.build.automate.demo/DEMO.md`): in Act 2 and Act 3, mention the
  file lines, and that you can type your own answer. It isn't in this repo, so no commit.
