# Run feedback: progress, questions and notifications — design

Status: approved 2026-11-23.

## Intent

The first real `compose clarity` run was a bad experience:

- The questions offered a single option (`1. confirm (recommended)`), so they looked like a
  forced choice. Typing your own answer already works, but nothing says so, and each question
  was one long paragraph.
- Long steps showed nothing. The draft ran for minutes with a start line and an end line only.
- Nothing told the person when the run needed them or had ended.

The fix is about what a person sees while a run goes, by default, without extra flags. The
workflows and the run engine don't change.

## Goals

1. **Progress you can follow.** While a model step runs, the terminal shows:
   - **which document** it's writing: a line for every file the model writes or edits, e.g.
     `✎ .clarity/goal/requirements.md`, relative to the worktree;
   - **the model's commentary**: its short remarks as it works, one dimmed line each, clipped
     to the terminal width;
   - **running time and cost** for the current step, updated in place.
   This is the default output. `-v` adds every other tool call (reads, searches, commands).
2. **Questions that invite an answer.**
   - The prompt says plainly that you can type your own answer whenever `free_text` is true:
     `Answer: a number, your own words, or Enter for 'confirm'`.
   - The clarity skills offer real alternatives where they exist, for example for setup:
     `confirm` and `also require <document>`, not only `confirm`.
   - A question has a short headline (`question`) and its supporting points in a new optional
     `details` list. The terminal prints the headline, then the details as bullets.
3. **Desktop notifications** when a run needs a person or ends:
   - waiting for answers (inline in the terminal, or paused for `compose clarity answer`);
   - waiting at a gate;
   - completed, or failed.
   Each says which run and what it waits for, e.g. *compose: clarity on wc-lite is waiting for
   your answers (Q-003, Q-004)*.

## Non-goals

- No change to workflows, step types, the questions file's existing keys or the API.
- No clickable notifications that focus the terminal (that needs a native helper).
- No custom notification command yet. It can be added later as an override in `config.yml`.

## Anti-goals

- A notification or display failure that fails or slows a run.
- Output so noisy that the step lines get lost: commentary and file lines stay one line each.
- Broken output when piped or in `--json` mode.

## Approaches (notifications)

1. **Built in, using each OS's own command** — chosen. macOS `osascript`, Linux
   `notify-send`, Windows a PowerShell toast. Sent by the process that runs the workflow, so it
   covers foreground, detached (`-d`) and API runs. No new dependency.
2. A user-defined notify command in `config.yml`. Flexible, but nobody gets notified until
   they write one. Can be added on top of 1 later.
3. A Python notification library (e.g. `desktop-notifier`). Clickable, but a native
   dependency for a small feature.

Progress and questions have one sensible approach each: the engine already emits message,
tool-call (with inputs) and usage events, and `questions.yml` already allows extra keys, so
both are display changes plus skill text.

## Decided

- **Progress** stays in `compose/cli/runs.py`'s `Progress`:
  - file lines from `tool_call` events of the write/edit tools, using their file path;
  - commentary from `message` events: the first line of the text, clipped;
  - the running time and cost as a live status line on a TTY (from `usage_update` events and a
    timer). It is left out when output isn't a TTY;
  - `--json` and `-d` print none of this, as today.
- **Questions:**
  - `Question` gains `details: list[str]` (optional, default empty);
  - `ask_question` and `_print_questions` show the details and the new hint;
  - the `clarity` skill's question rules ask for a short `question`, `details` for the
    supporting points, and real alternatives in `options` when they exist.
  - The API returns `details` with each question (an additive change).
- **Notifications:**
  - a new `compose/notify.py` with one `notify(title, message)` that picks the OS command,
    runs it with a short timeout and swallows every failure;
  - the runner calls it when a run pauses, completes or fails;
  - the CLI calls it when it starts asking questions inline;
  - on by default; off with `notifications: {enabled: false}` in `config.yml` or
    `COMPOSE_NOTIFY=0` (the test suite sets this).

## Left to the builder

- The exact wording and clipping width of the progress lines and notifications.
- Which tool names count as writes (at least `Write`, `Edit`, `MultiEdit`, `NotebookEdit`).
- How the live status line is drawn (rich's `Live` or `Status`), as long as plain output
  still works when piped.
- Tests:
  - `Progress` rendering, from recorded events;
  - `ask_question` with `details` and free text;
  - `notify` command selection and its failure handling, with the command stubbed;
  - the runner calling `notify` on pause, completion and failure.
