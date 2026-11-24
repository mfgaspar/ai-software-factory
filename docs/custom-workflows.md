# Writing workflows and hooks

A workflow is a YAML file that lists steps for compose to run against one feature. This
guide builds one up step by step; the [workflow reference](workflow-reference.md) lists
every field.

## 1. Start from the skills

Save this as `.compose/workflows/ship-it/workflow.yml` in your repo:

```yaml
schema_version: "1.0"
workflow:
  id: ship-it
  name: Ship it
  version: 1.0.0
  description: Spec, plan, tasks and implementation for a small change.
inputs:
  spec:
    type: string
    required: true
    prompt: Describe the change
steps:
  - id: specify
    command: compose-specify
    input:
      args: "{{ inputs.spec }}"
  - id: plan
    command: compose-plan
  - id: tasks
    command: compose-tasks
  - id: implement
    command: compose-implement
```

Check it and run it:

```bash
compose workflow validate .compose/workflows/ship-it
compose run ship-it -i spec="Show the build number in the footer"
```

A workflow in `.compose/workflows/` is found by id from anywhere in the repo, and a repo's
`quick`, `full-cycle` or `bugfix` replaces the built-in one. To use a workflow in every
repo, put it in `~/.compose/workflows/<id>/` (`$COMPOSE_HOME/workflows/`) or install it
with `compose workflow add --user <folder|file|url>`; a repo's copy still wins. You can also run a file
directly (`compose run ./ship-it.yml`) or install one from elsewhere
(`compose workflow add <folder|file|url>`).

`command` steps run a skill on the engine, exactly as typing `/compose-plan` in Claude
Code. `input.args` is what follows the slash command. On Copilot (`engine: copilot`) the
same skill runs with the same arguments.

## 2. Add a review gate and a model

```yaml
schema_version: "1.0"
workflow:
  id: ship-it
  name: Ship it
  version: 1.1.0
  model: claude-sonnet-5-5
  limits:
    max_cost_usd: 15
inputs:
  spec: {type: string, required: true}
  plan_verdict: {type: string, default: ""}
steps:
  - id: specify
    command: compose-specify
    input: {args: "{{ inputs.spec }}"}
  - id: plan
    command: compose-plan
  - id: review-plan
    type: gate
    message: "Read {{ context.feature.dir }}/plan.md: go ahead?"
    options: [approve, reject]
    on_reject: abort
    verdict_input: plan_verdict
  - id: tasks
    command: compose-tasks
  - id: implement
    command: compose-implement
    model: claude-opus-5-5
    limits: {max_cost_usd: 10}
```

- The run pauses at `review-plan` until someone answers:
  `compose resume <run> --choice approve`, the API's `POST /runs/{run}/gates/review-plan`,
  or the prompt on a terminal. `-i plan_verdict=approve` answers it in advance.
- `on_reject` is `abort`, `skip` (carry on) or `retry` (pause again for a new answer).
- `limits.max_cost_usd` on the workflow caps the whole run; on a step, just that step.
  The engine is stopped when a cap is reached and the step fails; resume after raising it.

## 3. Let implement run your tools

In a background run nobody can answer Claude Code's permission prompts. compose runs Claude
Code in auto mode (`permission_mode: auto`), where Claude Code approves or blocks each
action itself, so implement can run your tests and build without a list. To pin exactly
what runs, set another `permission_mode` (`acceptEdits` allows edits only) and list the
commands in `engine_options.allowed_tools`, fixed or from an input. Copilot has the same
three choices under other names (`assisted`, `allow-all`, `rules`) and takes the same
`allowed_tools` list:

```yaml
schema_version: "1.0"
workflow:
  id: ship-it
  name: Ship it
  version: 1.2.0
inputs:
  spec: {type: string, required: true}
  allowed_tools:
    type: string
    default: "Bash(npm test),Bash(npm run lint)"
steps:
  - id: specify
    command: compose-specify
    input: {args: "{{ inputs.spec }}"}
  - id: implement
    command: compose-implement
    engine_options:
      allowed_tools: ["{{ inputs.allowed_tools | split(',') }}"]
```

`compose` itself is always allowed, because the skills call it.

## 4. Add hooks

Hooks run before or after steps, or around the whole run, and are declared once at the top
of the workflow. compose runs them itself, in the feature worktree. Their cost, tokens and
file changes are added to the step they surround, and traces show each one separately.

```yaml
schema_version: "1.0"
workflow:
  id: ship-it
  name: Ship it
  version: 1.3.0
inputs:
  spec: {type: string, required: true}
  release: {type: boolean, default: false}
hooks:
  before_run:
    run: git diff --quiet HEAD
    description: Refuse to start on uncommitted changes
  before_implement:
    run: npm ci
    description: Install dependencies
  after_implement:
    - run: npm test
      description: Tests must pass
    - command: compose-checklist
      args: release readiness
      optional: true
      condition: "{{ inputs.release }}"
      prompt_text: Write a release checklist?
  after_step:
    run: ./scripts/notify.sh "$COMPOSE_RUN_ID" done
    optional: true
    priority: 50
steps:
  - id: specify
    command: compose-specify
    input: {args: "{{ inputs.spec }}"}
  - id: plan
    command: compose-plan
  - id: tasks
    command: compose-tasks
  - id: implement
    command: compose-implement
```

- A hook that fails fails its step, unless it is `optional`. A failing `before_` hook stops
  the step from running; `after_` hooks run only when the step succeeded.
- `condition` skips a hook when false; `prompt_text` asks first on a terminal (a
  background run just runs it).
- Lower `priority` runs first (default 10).
- `npm test` above counts toward `implement`: if the tests fail, implement fails and
  `compose resume` runs implement (and its hooks) again.

## 5. Loop until the tests pass

```yaml
schema_version: "1.0"
workflow:
  id: make-it-green
  name: Make it green
  version: 1.0.0
inputs:
  goal: {type: string, required: true}
  test_command: {type: string, default: "npm test"}
steps:
  - id: attempt
    type: do-while
    max_iterations: 4
    condition: "{{ steps.test.output.exit_code != 0 }}"
    steps:
      - id: change
        prompt: |
          {{ inputs.goal }}
          Last test output:
          {{ steps.test.output.stdout | default("(none yet)") }}
      - id: test
        type: shell
        strict: true
        env: {TEST_COMMAND: "{{ inputs.test_command }}"}
        run: sh -c "$TEST_COMMAND"
        capture: true
        continue_on_error: true
  - id: report
    type: if
    condition: "{{ steps.test.output.exit_code == 0 }}"
    then:
      - id: done
        type: shell
        run: echo "green after {{ steps.attempt.output.iterations }} attempt(s)"
    else:
      - id: give-up
        type: shell
        run: echo "still failing" && exit 1
```

- `prompt` steps send inline text instead of a skill.
- `capture: true` keeps a shell step's stdout and stderr in `steps.<id>.output`;
  `continue_on_error` lets the loop look at a failure instead of stopping on it.
- `strict: true` with `env` passes input values to the shell without pasting them into
  the command line, which is safer for text people type.

## 6. See what happened

```bash
compose status <run>                  # per step: status, time, cost, tokens, files, lines
compose trace <run> --step implement  # messages and tool calls, hooks nested
compose changes <run>                 # what each step (and each hook) changed
compose cost --run <run>              # per step, hooks included
```

## Tips

- `compose workflow info <id>` shows the hooks that will run, the built-in tracking hooks
  included.
- A run keeps the exact definition it started with, so editing a workflow never changes a
  run that is under way or paused.
- Steps share one worktree, and nothing is committed between them; compose commits the
  worktree on the feature branch once, when the run stops. Add a `shell` step or hook
  (`git add -A && git commit -m ...`) if you want a commit per step.
- Use `{{ context.feature.dir }}` for the feature's specs folder, and `steps.<id>.cost_usd`
  or `steps.<id>.changes.files` to branch on what a step did.
