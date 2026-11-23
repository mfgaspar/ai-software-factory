---
name: clarity-configure
description: Agree with the user which clarity documents this project needs, which don't apply and why, any custom documents, and who approves what, then write .clarity/config.yml. The first step of /clarity; run alone to change the setup.
argument-hint: "[short-cuts like 'mandatory: PRD, API only'] [auto]"
---

# Configure the clarity documents for this project

What the user asked for (it may be empty, a short-cut, or `auto`):

```text
$ARGUMENTS
```

This decides **which documents the project must have**. It doesn't write any of them. The
output is one file, `.clarity/config.yml`, which the project owns and commits. Installs never
touch it.

## Inputs

- The shipped manifest `.compose/templates/clarity/manifest.yml`. It lists every document,
  which ones are mandatory, and `never_na` (problem and requirements, which every project
  keeps).
- The existing `.clarity/config.yml`, if there is one.
- What is known about the project. When `/clarity` called you, it passed an **inputs summary**
  (the supplied documents and what each one informs). Use it and don't re-read the sources.
  When you're run on your own, take a quick look: the README, the top-level folders, and any
  documents the user names.

## Steps

1. **Re-run check.** If `.clarity/config.yml` exists, show its effect in two or three lines
   (what is required, what is N/A, who approves). Also list any manifest document that the
   config doesn't mention and that was added since it was written. Ask "keep this setup?". If
   the user keeps it and nothing is new, stop here.
2. **Propose.** Start from the manifest's mandatory set and propose changes, each with its
   evidence:
   - N/A candidates, for example "No UI code or UI requirements found, so mark
     `product/ux-flows.md` N/A?", "No database or persistence, so `data/data-model.md` N/A?",
     or "No API, so `contracts/api.md` N/A?". Never propose N/A for a `never_na` document.
   - Custom documents the material or the user implies, such as a runbook or a compliance
     checklist. Each needs a template, its required headings, and what it depends on. Put
     custom templates under `.clarity/templates/` and start them with the same front matter as
     the shipped templates (copy the shape from any shipped document template).
   - Approvers: ask who must sign off which documents. Approvals are optional. Names are
     recorded exactly as typed, and `decisions/*` covers every ADR.
   - `stale_fails`: leave it at the default `false` unless the user wants staleness to fail the
     check.

   Keep the proposal short: one line per change, then one question asking what's wrong or
   missing.
3. **Apply short-cuts.** Apply short-cuts from the arguments directly.
   - `mandatory: PRD, API, setup guide only` means: remove every manifest document except
     those named and the `never_na` ones.
   - `no UI` means: propose ux-flows as N/A, with the reason.

   Map plain names to paths using the manifest's document titles.
4. **Write.** Copy `.compose/templates/clarity/config.yml` (the commented starter) to
   `.clarity/config.yml` if it doesn't exist yet. Fill in only the keys that differ from the
   defaults, and leave the explanatory comments in place. Before saving, check the result:
   - it is valid YAML;
   - every path exists in the manifest or under `documents`;
   - every custom template exists;
   - no `never_na` document is removed or N/A;
   - every N/A has a non-empty reason.
5. **Confirm.** Show the final file, or its effect in plain words, and move on once the user
   confirms. Record the confirmation by adding a one-line entry in `.clarity/notes.md`:
   `Setup agreed <date>: <summary>`.

## `auto` mode

Don't ask anything. Write the proposal with every inferred N/A **commented out** together with
its reason (a person must decide N/A), with no approvers, and with custom documents only when
the user named them. Say in one line what you proposed and that it needs a person's
confirmation.

## Rules

- Never mark a document N/A without a reason the user gave or confirmed.
- Never add approvers the user didn't name.
- This skill changes only `.clarity/config.yml`, any custom templates under
  `.clarity/templates/`, and the one line in `.clarity/notes.md`.
- When `/clarity` called you, return to it. Otherwise suggest running `/clarity` to continue.
