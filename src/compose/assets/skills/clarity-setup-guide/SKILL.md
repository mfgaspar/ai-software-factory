---
name: clarity-setup-guide
description: Write or revise the environment and setup guide (.clarity/ops/setup-guide.md) - prerequisites, environments, local setup from a fresh clone, configuration, secrets handling and troubleshooting - inferred from build files, Dockerfiles, CI and env examples. Never writes secret values. Use when /clarity reaches the technical stage.
argument-hint: "[focus, environments or extra sources]"
---

# Environment and setup guide

Focus, environments or extra sources from the user:

```text
$ARGUMENTS
```

A new developer should get from a fresh clone to a running system with this guide alone, and
an operator should know which environments exist and where every setting and secret comes
from. Every command in it should work as written.

## Steps

1. **Read before asking.**
   - The shipped manifest `.compose/templates/clarity/manifest.yml`, for the document's
     `template`, `required_sections` and `depends_on`.
   - `.clarity/notes.md`: act on items tagged `[for: clarity-setup-guide]`, then remove them.
   - The `depends_on` documents: `.clarity/solution/architecture.md` (deployment,
     components, external services), `.clarity/contracts/api.md` (base URLs, auth) and
     `.clarity/data/data-model.md` (stores, migrations). Also the operability NFRs in
     `.clarity/goal/requirements.md`.
   - The document's front matter `sources` and anything in the arguments.
   - **The repo.** README and contributing guides; build and package files (`package.json`,
     `pyproject.toml`, `go.mod`, `Makefile`, `justfile`, lock files, tool-version files);
     Dockerfiles and container orchestration files; CI workflows; infrastructure code; `.env.example` and
     config schemas or settings modules. CI is usually the most accurate record of how the
     project really builds and tests.
2. **Create the file if needed.** If `.clarity/ops/setup-guide.md` doesn't exist, copy
   `.compose/templates/clarity/ops/setup-guide.md` there, then fill its sections. Keep
   `status: draft` and save a rough draft early.
3. **Draft each section.**
   - **Prerequisites**: tools and versions (from version files and CI, not guesses),
     accounts and access a developer needs, and the supported operating systems.
   - **Environments**: each one (local, dev, staging, production, as they exist), its
     purpose, how it is deployed, and how to reach it.
   - **Local setup**: numbered commands from a fresh clone to a running system, then how to
     run the tests. Include starting local dependencies and running migrations or seeds.
   - **Configuration**: every setting, what it does, its default, and where it is set (env
     variable, file, flag). Group by component.
   - **Secrets handling**: each secret by **name only**, what it is for, where it comes from
     (a secrets manager path, a vault, a CI secret, a dashboard to generate a personal key),
     who can grant access, and how it is rotated. State that secrets never go in the repo.
   - **Troubleshooting**: the likely failures (wrong tool version, port in use, missing
     secret, migrations not run) with the symptom and the fix. Mine issues, the README and CI
     workarounds for real ones.
4. **Verify the local-setup commands** against the repo: the scripts and targets exist, the
   paths are right, the versions match the version files and CI. Read files to check; don't
   run anything that installs, deletes, resets, migrates or touches shared systems. A safe,
   read-only check (for example listing a script's targets) is fine. Mark any command you
   couldn't verify and ask about it.
5. **Ask only about the gaps** that remain (environments with no record, where a secret
   comes from, unclear defaults). Never re-ask what the documents, sources or repo already
   answer.
6. **Finish** (see below).

## Secrets

**Never write a secret value** into this guide or any other file: no passwords, tokens, API
keys, connection strings with credentials, private keys or certificates. Write only the name
and where it comes from. If a source (a `.env` file, a README, a pasted config, a sample)
contains what looks like a real secret, don't copy it, leave it out of `sources` quotes, and
warn the user plainly so they can rotate it and remove it from where it lives. Placeholders in
`.env.example` such as `changeme` are fine to mention as placeholders.

## Not applicable

Propose N/A only when there is nothing to set up: no code, no environments and nothing to run
(for example, a project whose output is a document or a process change). State the evidence.
Only on the user's agreement set `status: n/a` and a `reason:`. Never decide N/A alone.

## Questions

Ask a person only what a person must answer: their intent and priorities, facts only they
hold (real users, numbers, deadlines, owners), a trade-off the material leaves open that is
theirs to own, a conflict the sources can't settle, and confirmations. Anything you can work
out from the sources, the code, the other `.clarity/` documents, earlier answers or
established practice, decide yourself: write it, mark it as inferred with where it came
from, and name it in your summary so the person can correct it. `/clarity` sets this out in
**Ask a person only what needs a person**.

## Unattended

`/clarity` runs this skill unattended in its `auto`, `draft` and `apply` phases, and passes
`auto`. Work the same way whenever `COMPOSE_RUN_ID` is set or no person is present. Ask
nothing. Draft from the sources, the code and the other documents, drafts included. Fill
what you can work out yourself (see **Questions**), marked as inferred, and leave a
`[TBD — <what's missing or conflicting>]` note only for what a person must answer, in the
section it belongs to,
and propose any N/A only as a note. Never set `status: complete` or `n/a`, and never write
`reviewed` hashes. Return the draft and its list of gaps: `/clarity` turns them into
questions for a person.

## Finish

- Remove every placeholder (`[TBD…]`, `[To be determined…]` and the bracketed prompts) from
  the sections you filled.
- Notable choices (a secrets manager, dropping an environment) deserve an ADR: record one
  with the `clarity-decision` skill, or tell the user.
- If you changed another document that is already `complete`, leave its `status` and
  `reviewed` alone and tell the user which documents you touched.
- **When `/clarity` called you**: don't mark anything complete. Return the draft and the list
  of open gaps, including unverified commands and any secret you found and left out.
- **When run directly**: show a short summary and the open gaps, and ask the user to confirm.
  On a clear yes, set `status: complete` and write `reviewed.hash` (this document's body hash)
  and `reviewed.deps` (the body hash of each `depends_on` document). A body hash is the output
  of the manifest's `hash_command` with `FILE` replaced by the quoted path; never compute it
  any other way. Then suggest `/clarity` to continue.

## Rules

- The test of the guide: someone new follows it on a clean machine and never has to ask.
  Anything they would have to guess is a gap.
- Commands are copy-pasteable and in order; say which directory they run in.
- Prefer pointing at the project's own scripts over repeating long command lines.
- Talk about the project, not about files or front matter.
