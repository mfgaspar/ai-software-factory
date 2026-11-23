# compose clarity and compose build — design

Status: approved 2026-11-23. Builds on
[the clarity skills design](2026-11-22-clarity-skills-design.md), including its
2026-11-23 amendment (clarity is why, rules and how; compose is what).

## Intent

compose is an AI software factory with two steps:

1. **`compose clarity`, the foundation.** It settles the application's why, rules, standards,
   best practices, constraints and architecture once. It's like a constitution, but much more
   complete. This is where people are involved.
2. **`compose build`, delivery.** It specifies and builds features autonomously (specify
   through implement) inside that foundation.

Both must work the same from the CLI and the HTTP API. Workflows stay as the engine underneath
and are not part of how the product is described.

## Goals

- `compose clarity` runs in three modes. **mixed** is the default everywhere: on the CLI, in
  the API, and for `/clarity` in Claude Code.
  - **interactive**: today's `/clarity` conversation.
  - **auto**: reads the supplied documents and drafts everything with no questions.
  - **mixed**: drafts everything unattended like auto, then asks only what is still open, in
    batches, most important first.
- Only **mandatory** documents generate questions. Non-mandatory documents are drafted as well
  as the sources allow and are never asked about.
- Questions are **data, not conversation**. They live in a file, so any front end can answer
  them: a terminal, the API, a Claude Code conversation, or a future UI.
- A **person** still confirms the foundation and gives approvals. In mixed mode that's one
  review question and one approval question per approver, not a conversation per document.
- When a clarity run finishes, the **constitution is generated** from the clarity documents as
  a digest that cites its sources. It is never edited by hand.
- **`compose build "<feature>"`** runs the default workflow on a new feature, with a pre-run
  check:
  - **Clarity was started**: it refuses to start unless the foundation passes
    (`CLARITY: PASS`) and the constitution digest is current.
  - **Clarity was never started**: it starts. It warns that the foundation is a guessed
    constitution, and it creates that constitution unattended if there is none.
- Clarity runs are tracked like builds (history, events, cost) and are visible in
  `compose status`, the API and traces.

## Non-goals

- No new UI. The API is designed so a UI can be built on it later.
- No interactive mode through the API. It needs a person in a Claude Code session, so the API
  offers auto and mixed only.
- No push. compose merges the clarity branch locally; pushing the default branch stays with
  the user.
- No backlog automation. Turning `## Feature ideas` into build runs is a later step.
- No change to how `compose run <workflow>` works for custom workflows, apart from the shared
  pre-run check.

## Anti-goals

These would make it a failure even if it technically works:

- An autonomous build running on a foundation nobody confirmed, in a repo that started clarity.
- Questions about documents the project doesn't need, or a mixed run that turns back into a
  long interview.
- Clarity text or rules duplicated between the skills and the workflow YAML, so the two drift
  apart.
- A clarity run, or the API, marking documents complete or approved without a person's answer.

## Constraints (from the code today)

- Every run is a feature run. `Runner.create_run` always allocates an `NNN-name` feature
  (`runner/runner.py:697`). `Runner.execute` refuses a run without a feature
  (`runner.py:826`), locks on the feature, and works in the feature's worktree.
  `RunContext` requires a feature (`runner.py:135`). `recover_stale_runs` uses the feature lock
  key (`runner/recovery.py:29`).
- The database already allows runs without a feature: `runs.feature_id` can be NULL
  (`migrations/0001_initial.sql:27`). Views and cost aggregation already handle NULL.
- Gates accept only a choice from a list (`workflows/schema.py:242`). Free text can only reach
  a run through declared inputs on resume (`runner.py:639`).
- Runs never commit. Feature worktrees branch from the default branch
  (`repos/worktrees.py:31`), so a build only sees what is committed there.
- `docs/openapi.json` must equal the generated schema, and every CLI command must be in
  `docs/cli.md` (`tests/unit/test_release_docs.py`).
- The clarity skills stay the single place where clarity logic lives. compose orchestrates
  them; it does not reimplement them.

## Approaches

The user framed the product as "compose has two parts, clarity and build", so clarity runs
through compose's runner and is tracked like any run. Three ways were considered for the
mechanics:

- **A. Modes only inside the `/clarity` skill**, with compose calling `claude -p` once. This is
  simple, but it gives no tracked pauses for questions, no API answers and no run history.
  It's rejected now that clarity is part of compose.
- **B. A full clarity workflow, one step per clarity skill**, with gates for questions. This
  duplicates the flow logic (stages, resume, recheck) in YAML and needs free-text gates.
  Rejected under the anti-goal on duplication.
- **C. Chosen: a thin built-in `clarity` workflow over phase-aware skills.** The `/clarity`
  skill gains two unattended phases, `draft` and `apply`, that read and write a questions
  file. The workflow is a few steps: draft, a new `questions` step that pauses for answers,
  apply (looping while new questions appear), constitution, validate. All clarity logic stays
  in the skills. The runner gains repo-scoped runs and the `questions` step.

## Decided

### Commands

**CLI**

| Command | What it does |
|---|---|
| `compose clarity [SOURCES…] [--mode mixed\|auto\|interactive] [-d] [--json]` | Starts a clarity run. Sources are paths or URLs, passed to `/clarity` as given. `--mode` defaults to `mixed`. |
| `compose clarity questions [--json]` | Lists the repo's pending questions, from the questions file in the clarity worktree. |
| `compose clarity answer ID ANSWER [--by NAME] [--no-resume]` | Records one answer in the questions file (repo-level, no run needed). `--by` defaults to the git user name. If a clarity run is paused on questions and nothing it waits for is pending any more, it resumes that run. |
| `compose clarity status [--json]` | Free, no model call. The declared status of each document, the recorded verdict and whether it is current, the open questions, and whether the constitution digest is current. |
| `compose clarity merge [--json]` | Retries merging a passing `clarity` branch into the default branch (see Where clarity works). |
| `compose clarity validate [--json]` | Runs `/clarity-validate` as a tracked run. It records the verdict and regenerates the constitution digest when the result is PASS and the digest is out of date. Exits 1 on FAIL. |
| `compose build DESCRIPTION [--workflow ID] [-i k=v…] [--feature NAME] [-d] [--json]` | Runs the configured default workflow (`automated`) with `spec=DESCRIPTION`, after the pre-run check. Other options are the same as `compose run`. |

**API.** Same auth and error mapping as today:

| Endpoint | Body | What it does |
|---|---|---|
| `POST /repos/{repo}/clarity` | `{sources?: [str], mode?: "mixed"\|"auto"}` | Starts a clarity run. 202, returns the run brief. `interactive` is rejected with 422. |
| `GET /repos/{repo}/clarity` | — | Same as `compose clarity status`. |
| `POST /repos/{repo}/clarity/validate` | — | Same as `compose clarity validate`. Starts a run, 202. |
| `POST /repos/{repo}/clarity/merge` | — | Same as `compose clarity merge`. 200 with the outcome, or 409 with the reason it can't merge. |
| `GET /repos/{repo}/clarity/questions` | — | The repo's pending questions. A paused run also shows what it waits for in `GET /runs/{run}` under `waiting.questions`. |
| `POST /repos/{repo}/clarity/answers` | `{answers: {ID: str}, by: str, resume?: bool = true}` | Records answers. Each must be for a pending question and pass the validation rules, or the whole request is rejected (422). Then it resumes a paused clarity run when nothing it waits for is pending. |
| `POST /repos/{repo}/builds` | `{spec: str, workflow?, feature?, inputs?}` | Same as `compose build`. A failed pre-run check gives 409 with the problems listed. Warnings go in the response under `warnings`. |

`POST /repos/{repo}/runs` and `compose run` apply the same pre-run check to feature runs
(see below).

### Repo-scoped runs

A workflow may declare `scope: repo` (the default is `feature`). For a repo-scoped run:

- **No feature.** `create_run` allocates no feature, and the run has `feature_id = NULL`.
- **Where it works:** the repo's clarity worktree (see Where clarity works).
- **Lock:** a repo-level key, `clarity:<repo_id>`, and stale-run recovery uses the same key.
  There is **one active clarity run per repo**, paused ones included: starting `clarity` or
  `clarity-validate` while another repo-scoped run is running or paused is refused (exit 1,
  409), with the fix: answer it, or `compose abort <run>`. *(builder-check call)*
- **Environment:** `COMPOSE_FEATURE` is unset and `COMPOSE_SCOPE=repo` is set.
  `context.feature` is null in expressions. `context.repo.dir` is the working directory.
- **Display:** the run's working directory is stored, so `status`, `run_detail` and the API
  show it. Text output says "clarity" where it would show a feature name.

`clarity` and `clarity-validate` are built-in repo-scoped workflows. They are listed by
`compose workflow list` like the others. `compose run clarity` works too, but `compose clarity`
is the documented way.

### Where clarity works

Clarity runs in a dedicated worktree, `$COMPOSE_HOME/worktrees/<repo>/clarity`, on a branch
named `clarity`. The branch name can be changed with config `clarity.branch`. The branch is
created from the default branch the first time.

Before a clarity run starts, compose brings the branch up to date: it merges the default
branch into `clarity`. A conflict refuses the run, naming the files, and leaves the branch
untouched. Whenever a clarity or clarity-validate run pauses, completes, fails or is aborted
after changing anything under `.clarity/` or the constitution, compose **commits those paths
only** on that branch *(builder-check call)*, with the message
`clarity: <mode> run <run id>`. This is the first place compose commits; it's limited to
documentation the run itself wrote.

**Auto-merge on PASS** (decided by the user). When a clarity or clarity-validate run records
a PASS, compose merges `clarity` into the local default branch. The PASS, with its human review
and approvals, is the only gate. Builds branch from the default branch, so they only ever see a
foundation that passed.

- **Fast-forward only.** `clarity` was brought up to date when the run started, so it's
  normally ahead of the default branch. If the default branch moved during the run, compose
  merges it into `clarity` first. If that conflicts, or the PASS no longer holds on the merged
  content, nothing is merged and the run reports why.
- **A checked-out default branch.** When the default branch is checked out in some worktree
  (usually the user's own checkout), compose fast-forwards it there, and only if that worktree
  has no uncommitted changes under `.clarity/` or `.compose/memory/`. Otherwise it leaves the
  default branch alone and reports "PASS — merge pending", along with the fix.
- **`compose clarity merge`** (`POST /repos/{repo}/clarity/merge`) retries the merge, with the
  same rules. It's the fix for "merge pending".
- **No push.** The run's report says to push the default branch.

Running `/clarity` directly in your own checkout still works: you commit yourself.

### The questions file

`.clarity/questions.yml` is a companion: created from a template, never validated. A question
has these fields:

```yaml
- id: Q-007                      # stable, never reused
  round: 2                       # the draft/apply pass that raised it
  kind: setup | gap | conflict | review | approval
  document: product/prd.md       # null for setup questions
  question: "The PRD says 3 user roles; the code has 2. Which is right?"
  options: ["3 roles (PRD)", "2 roles (code)"]   # may be empty: free text
  recommended: "3 roles (PRD)"   # may be null
  free_text: true                # false: the answer must be one of the options
  approver: null                 # approval questions only: who must answer
  answer: null
  answered_by: null
  answered_at: null              # ISO date-time
```

A question is **pending** while `answer` is null. Skills write questions. compose writes only
`answer`, `answered_by` and `answered_at`. These rules apply *(builder-check calls)*:

- **Rounds carry over.** `round` keeps counting across runs: a new pass uses the highest
  round in the file plus one. `draft` keeps the older pending questions that still apply, and
  marks the rest `obsolete: true` (they are then no longer pending). So questions from an auto
  run are asked by the next mixed run.
- **All pending questions are asked**, ordered by kind (setup, gap and conflict, review,
  approval), then by impact.
- **Validation of answers.** With `free_text: false`, the answer must be one of `options`.
  Setup, gap, conflict and review questions have `free_text: true`. Approval questions have
  options `[approve, reject]`, `free_text: false`, and are accepted only when `by` equals
  their `approver`.
- **Answers are repo-level.** Recording an answer doesn't need a paused run: it writes to the
  file in the clarity worktree. If a clarity run is paused on questions, it is resumed once
  nothing in the round it asked is still pending (approvals excepted, see below). Otherwise the
  next `compose clarity` run applies the answers.
- **Approvals don't hold a run.** Approval questions are asked when the run reaches them, but a
  run doesn't pause waiting for an absent approver. If only approval questions are pending, the
  loop ends, and the run generates the constitution, validates (FAIL, unapproved) and commits.
  A later `compose clarity answer` from the approver, followed by `compose clarity`, applies
  the approval and validates again.

### Mixed and auto, as phases of `/clarity`

`/clarity` takes a mode or phase word: `interactive`, `auto`, `mixed`, or the unattended phases
`draft` and `apply` that compose uses. Without one, it runs **mixed**, the default
everywhere.

- **`draft`**: unattended. It runs steps 0–5 of today's flow in drafting-only form.
  - For setup, `clarity-configure` writes the proposed `config.yml` from the sources and raises
    one **setup** question: "Here's the proposed mandatory set, N/A list and approvers;
    confirm or correct."
  - Then it raises a **gap** or **conflict** question for each gap that stops a mandatory
    document (effective manifest) from being completed, and for each unresolved
    `Blocking: yes` open question.
  - Gaps in non-mandatory documents stay as placeholder notes and are not asked.
  - Questions are ordered by impact: setup first, then blocking questions, then conflicts, then
    other gaps.
- **`apply`**: unattended. It reads the answered questions from the newest round and applies
  them.
  - A setup answer rewrites `config.yml` and scaffolds or drafts any newly mandatory documents.
    That may raise new gap questions.
  - Gap and conflict answers are applied to their documents.
  - When no gap, conflict or setup question is pending, it raises one **review** question: a
    short summary of the foundation (what each mandatory document says, and what was inferred
    and from where), with options `confirm` and free-text corrections.
  - A `confirm` review answer marks every mandatory document complete (with `reviewed`
    hashes), or n/a with its reason. Corrections are applied, and a new review question is
    raised.
  - After a confirmed review, it raises one **approval** question per configured approver and
    document set. An approval answer `approve` from that approver records the approval, with
    the same rules as `clarity-approve`.
  - It runs today's step 6 (recheck) unattended, once. Documents that went stale become a new
    review question rather than being re-confirmed silently.
- **Loop guard**: at most 4 question rounds per run. Anything still pending after that stays in
  the file, and the run's report lists it.

`auto` mode runs `draft` only and never asks. Its questions stay in the file for a later
mixed run, or for `compose clarity answer`.

In Claude Code, `/clarity` (or `/clarity mixed`) does draft, asks the pending questions in the
conversation, records the answers in the file, and then applies them, until nothing is
pending. `/clarity interactive` is today's stage-by-stage conversation.

### The built-in `clarity` workflow

Inputs: `sources` (string, optional), `mode` (`mixed` | `auto`, default `mixed`). Steps:

1. `draft`: command `clarity`, args `{{ inputs.sources }} draft`.
2. If `mode == mixed`, a do-while loop of at most 4 rounds:
   1. `questions`: the new step type below.
   2. `apply`: command `clarity`, args `apply`.

   It repeats while the questions file has pending questions other than approvals (an
   approval is asked once per run and never holds it).
3. `constitution`: command `compose-constitution`, args `from-clarity`.
4. `validate`: command `clarity-validate`.
5. compose records the verdict, commits, and on PASS merges into the default branch (see
   Where clarity works).

`compose clarity --mode interactive` doesn't use this workflow. It starts `claude` in the
clarity worktree with `/clarity <sources> interactive`, attached to the terminal. When that session ends,
compose runs `clarity-validate` as a tracked run and commits.

### The `questions` step type

`type: questions`, with `file:` (a path relative to the run's working directory). It is generic
so other workflows can use it.

- **No pending questions:** it completes, with `output.answered = 0`.
- **On a terminal, in the foreground:** it asks each pending question in order. It shows the
  question, numbered options and the recommendation; Enter takes the recommendation. It records
  the answers with `answered_by` set to the git user name, then completes.
- **Otherwise:** it emits `questions_waiting` with the pending ids, and the run pauses (status
  paused, `paused_at` = this step). `compose clarity answer` and `POST /runs/{run}/answers`
  write the answers into the file in the run's working directory, then resume.
- **On resume:** if questions are still pending, it pauses again. Partial answers are kept.

`views.waiting_gate` gets a sibling, `waiting_questions`, so `GET /runs/{run}` and
`compose status` show what the run is waiting for, and `_print_outcome` suggests
`compose clarity answer`.

### The verdict and the fingerprint

- **Which default branch:** the local default branch, the same ref feature worktrees branch
  from. After merging the clarity PR on the remote, pull before building. The refusal message
  says so when the local branch is behind its upstream, as far as git already knows.
  *(builder-check call)*
- **The clarity fingerprint** is a git hash over `.clarity/**`, excluding `verdict.yml`,
  `questions.yml` and working files (`failures/brainstorm/`, `prototypes/`). It is computed
  from a tree: either the committed default branch, or the clarity worktree.
- **After `/clarity-validate`, compose records `.clarity/verdict.yml`:** `{result: PASS|FAIL,
  incomplete: n, fingerprint, run_id, at}`. The result comes from the validate step's last
  line. A missing or malformed line counts as FAIL.
- **The constitution digest** carries the fingerprint it was generated from, in its sync
  report comment: `<!-- generated-from-clarity: <fingerprint> -->`.

### The pre-run check (build and feature runs)

The check runs in `Runner.create_run` for feature-scoped runs, before anything is persisted, so
the CLI and the API share it. It reads the **default branch** (what the feature worktree will
get), not the user's checkout. The repo has **started clarity** when the default branch has a
`.clarity/` folder, or a `clarity` branch exists.

| Situation | Result |
|---|---|
| Not started | Starts. Warning: "No clarity foundation: building on a guessed constitution. Run `compose clarity` for a confirmed foundation." If the default branch has no constitution, the workflow's constitution step creates one, as today. |
| Started, but `.clarity/` not on the default branch | Refuses: "Clarity is in progress on branch `clarity` and hasn't passed yet. Run `compose clarity` to finish it." If the branch has a current PASS that wasn't merged, the fix is `compose clarity merge`. |
| `verdict.yml` missing, FAIL, or its fingerprint ≠ the default branch's fingerprint | Refuses: "The clarity foundation doesn't pass (or changed since it was validated). Run `compose clarity validate`." |
| Constitution digest fingerprint ≠ the default branch's fingerprint | Refuses: "The constitution is out of date with clarity. Run `compose clarity validate`." |
| All current and PASS | Starts. |

Refusing raises a user error before a run row exists, which gives exit code 1 on the CLI and
409 from the API, with the problem and its fix. Warnings go to stderr on the CLI and under
`warnings` in the API response, and are recorded as a `run_created` event field.

### The constitution in clarity repos

`compose-constitution from-clarity` regenerates `.compose/memory/constitution.md` from the
clarity documents, following the guide `.compose/templates/compose/clarity.md`. Every
principle cites its source, and the file records the fingerprint. In a clarity repo, a
hand-edited constitution is overwritten by the next clarity run; the file's header says so.
Repos without clarity keep today's behavior.

## Left to the builder

- Internal names, module layout, and how `scope: repo` threads through `RunContext`, child runs
  and hooks.
- Whether the working directory goes in a new runs column (with a `0002` migration) or in
  `state.json`.
- How the fingerprint is computed exactly (for example `git ls-tree` filtered and hashed), as
  long as it's deterministic, the same for a branch and a worktree with the same content, and
  excludes the listed files.
- Terminal formatting of questions, and the exact wording of messages.
- Cost caps for the draft and apply steps. Reuse the existing per-step cost options with
  sensible defaults.
- Tests: unit tests with the fake engine for repo-scoped runs, the questions step,
  pause/answer/resume over the CLI and the API, the verdict, the fingerprint and every row of
  the pre-run table. Plus one live test of `compose clarity --mode auto` and one of mixed with
  answers supplied through the API.
- Docs: `docs/cli.md`, `docs/api.md`, `docs/openapi.json`, `docs/clarity.md`, the README and
  the workflow reference (`scope`, `questions`).
