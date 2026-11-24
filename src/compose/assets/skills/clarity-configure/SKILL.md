---
name: clarity-configure
description: Agree with the user which clarity documents this project needs, which don't apply and why, any custom documents, and who approves what, then write .clarity/config.yml. The first step of /clarity; run alone to change the setup.
argument-hint: "[short-cuts like 'mandatory: PRD, API only'] [auto|draft|apply]"
---

# Configure the clarity documents for this project

What the user asked for (it may be empty, a short-cut, `auto`, `draft`, or `apply` with a setup
answer):

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

## Setup mode

`.clarity/config.yml` may carry `setup: dynamic` or `setup: static`. With no file, or no
`setup` key, the mode is **dynamic**.

- **dynamic**: a person decides which documents the project has. The sources (a brief, a
  PRD, the arguments' short-cuts) shape what you propose, and nothing more: a brief that
  says "only the problem and the requirements" gives you the proposal, never the agreement.
  The setup counts as agreed only when `notes.md` has a `Setup agreed` line that names the
  person or the question that confirmed it.
- **static**: the file is the decision. Ask nothing and propose nothing. Run the step 4
  checks on the file as it is; if one fails, say which and stop. Otherwise add
  `Setup agreed <date>: static, as written in config.yml` to `.clarity/notes.md` if it has
  no `Setup agreed` line, and return "setup follows config.yml (static)". This holds in
  every mode below, `auto`, `draft` and `apply` included.

When you propose a setup (step 3, and the summary in `draft`), show it as a **checklist of
every document** in the manifest and under `documents`, in `walk_order`, one line each:
`[x] <path>: <what it is>` for a document you propose to include, `[ ] <path>: <why you
would leave it out>` for one you don't, and `[n/a] <path>: <reason>` for an N/A candidate.
The person must be able to see every document they could still add.

## Steps

1. **Re-run check.** If `.clarity/config.yml` exists, show its effect in two or three lines
   (what is required, what is N/A, who approves). Also list any **new** document: one in the
   shipped manifest that has no file under `.clarity/` and that the config neither removes
   nor marks N/A (compose added it after the setup was agreed). Ask "keep this setup?". If
   the user keeps it and nothing is new, stop here.
2. **Apply short-cuts.** Apply short-cuts from the arguments directly.
   - `mandatory: PRD, API, setup guide only` means: remove every manifest document except
     those named and the `never_na` ones.
   - `no UI` means: propose ux-standards as N/A, with the reason.

   Map plain names to the manifest's paths (`PRD` is `product/prd.md`, `API` is
   `contracts/api.md`, `setup guide` is `ops/setup-guide.md`). When a name fits no document,
   or more than one, ask. Unattended, leave it out and say so in the summary.
3. **Propose.** Start from the manifest's mandatory set, with the short-cuts applied, and
   propose changes, each with its evidence:
   - N/A candidates, for example "No UI code or UI requirements found, so mark
     `product/ux-standards.md` N/A?", "No database or persistence, so `data/data-model.md` N/A?",
     or "No API, so `contracts/api.md` N/A?". Never propose N/A for a `never_na` document.
   - Optional shipped documents (`mandatory: false` in the manifest), added with
     `mandatory.add`. Propose `failures/fmea.md`, the FMEA worksheet built from the failure
     documents, when the material points to regulated or safety-related work, an audit, or
     a quality process that expects one; otherwise show it unticked. Set `fmea.scores: true`
     only when the user asks for scored rows.
   - Custom documents the material or the user implies, such as a runbook or a compliance
     checklist. Each needs a template, its required headings, what it depends on, which
     skill writes it (`produced_by: clarity` when none does) and where it comes in the order
     (`walk_after`), and a `memory` block for feature work: a one-sentence `summary` of
     what the document holds, `read_at` (the feature steps that always open it, from
     `specify`, `clarify`, `plan`, `tasks`, `implement`, `analyze`) and `read_when` (a
     condition in plain words for the other steps). compose puts these in the index of
     `.compose/memory/`. Put custom templates under `.clarity/templates/` and start them with the
     same front matter as the shipped templates (copy the shape from any shipped document
     template).
   - Approvers: ask who must sign off which documents. Approvals are optional. Names are
     recorded exactly as typed, and `decisions/*` covers every ADR.
   - `stale_fails`: leave it at the default `false` unless the user wants staleness to fail the
     check.

   Before you propose to drop a document, say where the rules it would have carried go.
   A project with no architecture document still needs its stack and structural rules,
   as constraints and standards in `goal/requirements.md`. Leaving a document out must not
   leave its subject undecided.

   Keep the proposal short: one line per change, then one question asking what's wrong or
   missing.
4. **Write.** Copy `.compose/templates/clarity/config.yml` (the commented starter) to
   `.clarity/config.yml` if it doesn't exist yet: copy the file itself, don't retype it.
   Then edit the copy: fill in only the keys that differ from the defaults, each under its
   own comment block, and leave every explanatory comment and example in place. Never
   replace the file with one that holds only your own keys. Keep a `setup:` key the file
   already has. Before saving, check the result:
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

## `draft`: proposal form

`/clarity` passes `draft` in its unattended phase. Ask nothing; a person confirms later,
through a `setup` question that `/clarity` raises.

1. **Re-run check.** If `.clarity/config.yml` exists, `notes.md` has a `Setup agreed` line,
   and the manifest has no new document (as step 1 above defines it), change nothing and
   return "setup already agreed". Never write a `Setup agreed` line yourself in this mode,
   and never treat what a source says as that agreement (see **Setup mode**).
2. **Propose and write** as in `auto` mode above: inferred N/A candidates **commented out**
   with their reasons, approvers only when the inputs or arguments name them, custom documents
   only when named. Apply short-cuts from the arguments. Run the step 4 checks before saving.
3. **Return the summary** that the setup question quotes, in plain words: the checklist of
   every document (see **Setup mode**), each N/A candidate with its evidence, the approvers
   (or "none named yet: who should sign off what?"), and any custom documents. Don't add the
   `Setup agreed` line.

## `apply`: a setup answer

`/clarity` passes `apply` with the answer to its setup question, and who gave it. Ask nothing.

- `confirm`: make the proposal real. Uncomment the N/A candidates the summary listed.
- Anything else: apply it as if the person had said it in step 3 (N/A choices, mandatory
  changes, custom documents, approvers, exactly as named), and keep the rest of the proposal.

Run the step 4 checks, then add `Setup agreed <date>: <summary> (<question id>, <name>)` to
`.clarity/notes.md`. A person's answer is the confirmation that N/A needs.

## Rules

- Never mark a document N/A without a reason the user gave or confirmed.
- Never add approvers the user didn't name.
- This skill changes only `.clarity/config.yml`, any custom templates under
  `.clarity/templates/`, and the one line in `.clarity/notes.md`. It never writes
  `.clarity/questions.yml`: `/clarity` raises the setup question.
- When `/clarity` called you, return to it. Otherwise suggest running `/clarity` to continue.
