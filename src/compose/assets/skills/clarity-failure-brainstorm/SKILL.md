---
name: clarity-failure-brainstorm
description: Brainstorm what could go wrong with the project by running the clarity failure thinkers (general, security, catalog, human factors, adversarial, codebase scan) in parallel where possible, plus the user's own ideas, into raw-failure files under .clarity/failures/brainstorm/. Use before failure analysis or when the solution changes.
argument-hint: "[thinkers to run, focus area, or the user's own failure ideas]"
---

# Failure brainstorming

Thinkers to run, focus area, or failure ideas from the user:

```text
$ARGUMENTS
```

The aim is **breadth**: as many things that could go wrong as possible. This is the divergent
phase. Don't filter, group or rank; failure analysis does that. Brainstorming can happen many
times: each run adds to the same pool of raw failures in `.clarity/failures/brainstorm/`, one
file per thinker or contributor. This skill writes no validated document.

## Thinkers

Six reference guides live next to this skill, in `thinkers/`:

| File | Perspective |
|---|---|
| `thinkers/general-thinker.md` | broad first pass: technical, human, social, misuse, cascades |
| `thinkers/security-thinker.md` | vulnerabilities: auth, data protection, injection, crypto, supply chain, operations |
| `thinkers/security-catalog-thinker.md` | OWASP LLM and agentic top tens and STRIDE, mapped to components |
| `thinkers/human-factors-thinker.md` | good-faith error by users, operators, deciders and AI |
| `thinkers/adversarial-analysis-thinker.md` | who would attack or misuse it, why, and how |
| `thinkers/codebase-scanner-thinker.md` | what the code actually is: routes, config, auth, secrets, AI, infra |

Each has front matter with `prerequisites.required` and `prerequisites.recommended`: paths
of `.clarity/` documents, as named in the shipped manifest
`.compose/templates/clarity/manifest.yml`.

## Steps

1. **Read the context.**
   - `.clarity/notes.md`: act on items tagged `[for: clarity-failure-brainstorm]`, then
     remove them. Untagged notes are guiding principles; respect them.
   - `.clarity/goal/problem.md`, `.clarity/goal/stakeholders.md`,
     `.clarity/goal/requirements.md`, `.clarity/solution/solution.md` and
     `.clarity/solution/architecture.md` where they exist, and the `sources` in their front
     matter when they add detail.
   - What is already in `.clarity/failures/`: the existing brainstorm files, `failures.md`
     and the `failure-NN-*.md` documents, so this run adds rather than repeats.
   - Whether the repo has code (source files beyond docs and config).

   Brainstorming on the problem alone is fine if the solution isn't fleshed out yet: it
   surfaces important failures early. More context makes the failures more specific.
2. **Pick the thinkers.** A thinker is eligible when every document in its
   `prerequisites.required` exists and has been drafted: it holds real content, not only
   its template's placeholders. It doesn't have to be confirmed. Brainstorming on a draft
   is fine and often the point; the output file's header then says which inputs were still
   drafts. Run `codebase-scanner-thinker` only when the repo has code. If the arguments
   name thinkers, run those (still checking prerequisites). Tell the user in one line which
   thinkers will run and which are skipped and why.
3. **Choose each output file.** Each thinker writes
   `.clarity/failures/brainstorm/<name>.md`, where `<name>` is its `name` without the
   `-thinker` suffix (`general.md`, `security.md`, `security-catalog.md`,
   `human-factors.md`, `adversarial-analysis.md`, `codebase-scanner.md`). **Never overwrite
   an existing file**: if the name is taken, append the next free number (`security-2.md`,
   then `security-3.md`). Brainstorm files are write-once; new ideas always go in a new
   file.
4. **Run the thinkers.**
   - **If you can start subagents**, dispatch one per selected thinker **in parallel**.
     Give each: the path of its thinker file, the project context paths from step 1, its
     output path, and the format template
     `.compose/templates/clarity/failures/brainstorm/thinker.md`. Tell it to write only
     its own output file and change nothing else.
   - **Otherwise**, run them one after another yourself: read the thinker file, apply it,
     write its output file, then move to the next.

   Each output file follows the template: a header with the perspective and inputs read,
   then one entry per raw failure, numbered `RF-1`, `RF-2`… Every entry ends in actual harm to
   someone; pre-existing failures are marked as such. Thinkers may add **Suggestions** (gaps
   in project documents) and, for the general thinker, **Recommended specialists**.
5. **Follow up.** When all thinkers are done:
   - If the general thinker recommends a specialist that didn't run, offer to run it (or run
     it when `/clarity` called you and its prerequisites are met).
   - Move each suggestion into `.clarity/notes.md` as an item tagged for the skill that owns
     the target document (`[for: clarity-problem]` for stakeholders or requirements,
     `[for: clarity-architecture]` for architecture), so the right skill picks it up. Don't
     edit those documents here.
   - If the user wants a specific area explored with no thinker for it ("what about data
     privacy?"), do it yourself and write the results to a new file named after the area.
6. **Invite the user's own failures.** Say how many raw failures the thinkers found, then
   ask: from your experience or domain knowledge, what else could go wrong that automated
   analysis would miss? People know the organizational dynamics, past incidents, regulatory
   subtleties and cultural factors. Help phrase each idea as a raw failure that ends in harm,
   and write them to `.clarity/failures/brainstorm/human-<n>.md` (the next free number),
   naming the contributor or role if given. Ideas in the arguments go there too. Ask again
   until the user has nothing more.
7. **Summarise.** A count per file, one or two highlights each, which perspectives ran and
   which were skipped. Then offer: add more ideas, explore an area, or move on to failure
   analysis.

## Rules

- Breadth over polish. Don't dismiss a failure as unlikely: unlikely and severe still
  matters. If one entry takes more than a minute, you are analysing, not brainstorming.
- Think beyond the technical: human factors, social dynamics, misuse, organizations,
  cascades. Harm has to land on someone; a violated principle alone is not a failure.
- Write as you go, so nothing is lost if the run stops.
- Never touch another thinker's file or an earlier run's file. Never edit
  `failures/failures.md` or the failure documents; that is failure analysis.
- Unattended (`/clarity` passed `auto`, `COMPOSE_RUN_ID` is set, or nobody is present): ask nothing, run every eligible thinker, skip
  step 6 and the offers in steps 5 and 7, and say that human contributions are still open.
- **When `/clarity` called you**, return to it with the list of new brainstorm files.
  **When run directly**, suggest `/clarity-failure-analysis` next (or `/clarity` to
  continue).
