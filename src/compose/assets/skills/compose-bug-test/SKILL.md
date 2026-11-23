---
name: compose-bug-test
description: Check that the current bug is really fixed - rerun its reproduction, the tests the fix added and the regression suite - and record the result (verified, partial or failed) in test.md. Changes no code.
argument-hint: "[extra checks to run]"
---

# Verify the bug fix

Extra checks from the user, if any:

```text
$ARGUMENTS
```

**Do not change any code.** This skill only runs checks and writes `test.md` in the bug's
folder.

## Steps

1. Run `compose feature paths --json`. Read `<feature_dir>/assessment.md` (the symptom and
   how to reproduce it) and `<feature_dir>/fix.md` (what changed and which tests were
   added). If either is missing, name the skill that writes it (`/compose-bug-assess`,
   `/compose-bug-fix`) and stop.
2. **Plan the checks.** To show the bug is gone: the reproduction from the assessment (or
   an automated equivalent) and the tests the fix added. To show nothing else broke: the
   existing tests of the changed modules, and lint and type checks if the project uses
   them.
3. **Run them.** For each, keep the command, its exit status and a short excerpt of the
   output. Skip destructive, network-dependent or very slow checks unless the user
   agreed, and record them as `skipped` with the reason. A check you can't run at all
   (missing tools) is `not run`, with the reason; never make a result up.
4. **Decide:**
   - `verified`: the critical checks pass and the original symptom no longer appears;
   - `partial`: the symptom is gone but something else regressed or some checks are
     inconclusive, or the reproduction couldn't actually be exercised (tests alone don't
     make it verified);
   - `failed`: the symptom still appears, or the fix broke the suite.
5. Write `<feature_dir>/test.md`. If it exists (an earlier check), add a new
   `## Check N` section at the end instead of rewriting it:

   ```markdown
   # Bug verification: <short title>

   - Result: verified | partial | failed

   ## Summary
   ## Checks
   | Check | Command or action | Result | Notes |
   ## Output excerpts
   ## Remaining risks
   ## Recommendation
   ```

## Report

End with exactly one line, on its own, so a workflow can tell the outcome:
`RESULT: verified`, `RESULT: partial` or `RESULT: failed`. Before it, the checks and what
to do next: close the bug, verify somewhere else (say where), or run `/compose-bug-assess`
again with the new evidence from `test.md`.
