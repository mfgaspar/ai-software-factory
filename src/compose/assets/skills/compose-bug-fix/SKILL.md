---
name: compose-bug-fix
description: Apply the fix proposed in the current bug's assessment.md, add a test that pins it, run the relevant tests, and record what changed in fix.md. Use after /compose-bug-assess and a review of the assessment.
argument-hint: "[notes, e.g. the output of the last failing test run]"
---

# Fix the bug

Notes from the user or the workflow (for example, the last test run's output):

```text
$ARGUMENTS
```

## Steps

1. Run `compose feature paths --json` and read `<feature_dir>/assessment.md` in full. If
   there is none, tell the user to run `/compose-bug-assess` first and stop. Its proposed
   fix, files to change, tests and risks are what you work to. Read the constitution at
   `constitution_file` if it exists.
2. **Check before changing anything.** Restate in 3–6 bullets what you will change and
   where. If the verdict is `invalid`, stop: there is nothing to fix. If it is `likely
   valid, needs reproduction` with open questions, ask whether to go ahead; in a headless
   run (`COMPOSE_RUN_ID` is set), go ahead and say so in the report.
3. **Fix it.** Make the preferred change, staying within the files the assessment names
   unless new evidence says otherwise (record that under **Deviations**). Add or update
   the tests the assessment calls for, ideally seeing the new test fail first. Keep it
   minimal: no unrelated refactoring, no new dependencies the assessment didn't call for,
   no deleted files unless it required that. If the assessment turns out wrong (the root
   cause is elsewhere), stop changing code, write down what you found under
   **Deviations**, and recommend running `/compose-bug-assess` again.
4. **Run the tests** that cover the changed code, if the project has a test command and
   you are allowed to run it. Don't run destructive or network-dependent suites without
   asking.
5. **Record it** in `<feature_dir>/fix.md`. If the file exists (an earlier attempt), add a
   new `## Attempt N` section at the end instead of rewriting it:

   ```markdown
   # Bug fix: <short title>

   - Status: applied | partial | not applied

   ## Summary
   ## Changes
   | File | Change | Notes |
   ## Tests added or updated
   ## Local checks
   (commands run and their result)
   ## Deviations
   ## Follow-ups
   ```

Never edit `assessment.md`; disagreements go under **Deviations**. Do not commit, push or
open pull requests unless the user asks.

## Report

The status, the files changed, the tests and their result, and the next step:
`/compose-bug-test`.
