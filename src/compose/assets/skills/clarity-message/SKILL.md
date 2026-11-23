---
name: clarity-message
description: Find the honest, human story of what the project is and why anyone should care, and write it to .clarity/summary.md, with optional audience-specific narratives in .clarity/messaging.md. Use once a problem and at least a rough solution exist, or when the summary reads like a spec.
argument-hint: "[audience or angle, e.g. 'for the finance team']"
---

# Clarify the message

What the user asked for (it may be empty, or name an audience):

```text
$ARGUMENTS
```

Messaging here is a thinking tool, not marketing. If you can't tell a good story about the
system, the system probably isn't good yet. This writes `.clarity/summary.md`, the project's
introduction and always the first thing people read, and optionally `.clarity/messaging.md`
(versions of the story for specific audiences; not a validated document).

## Before you start

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml` (the summary's template,
   `depends_on` and `hash_command`) and `.clarity/notes.md`. Act on items tagged
   `[for: clarity-message]`, then remove them.
2. Read `goal/problem.md`, `goal/stakeholders.md`, `solution/solution.md`,
   `solution/solution-summary.md`, the existing `summary.md` and its `sources`, and
   `messaging.md` if it exists.
3. If the problem or solution is still vague, say so and work on those first
   (`clarity-problem`, `clarity-solution`): you can't tell a story about something not yet
   figured out.
4. If `summary.md` is missing, copy its template from `.compose/templates/clarity/summary.md`
   and keep `status: draft`.

## Steps

1. **Start from what changed.** On a revisit, ask what they've learned since: conversations
   that shifted their thinking, reactions they didn't expect. Messaging improves through
   contact with the world. On a first pass, read the documents and tell the story back in two
   or three sentences, then ask "does that land? what's wrong with it?"
2. **Find the general narrative**: what problem exists in the world (the human one, not the
   technical one), what this project does about it, and why that matters. Techniques:
   - **the friend test**: how would you explain it to a smart friend over coffee?
   - **the "so what?" chain**: keep asking until you reach something a real person cares about
     ("novel caching" → "pages load in a second" → "people don't abandon the task midway");
   - **before and after**: life without the project and with it; the contrast is the story.

   When it reads aloud as honest and resonant (true, not perfect), write it.
3. **Ask about audiences.** Is there anyone who'll see it differently or care about different
   things? If not, you're done. If so, for each audience in `.clarity/messaging.md`, one section
   per audience: who they are (by perspective, not job title), what's already on their mind,
   and the story told from their starting point. Address resistance head on; talking around a
   concern reads as shallow or deceptive.
4. **Notice what the story exposes.** "This audience will hate that we do X" is a failure mode:
   add a `[for: clarity-failure-brainstorm]` item to `.clarity/notes.md`. "We can't say why it's
   safe" is a solution gap: note it for `clarity-solution`. "The story doesn't work because the
   problem is wrong" sends you back to `clarity-problem`. Tell the user.
5. **Check consistency.** Every version is profoundly honest about what the project can and
   can't do, consistent with the others (different framings of one truth), and direct about
   concerns. A contradiction means the thinking isn't settled yet; raise it.

## Writing

`summary.md`: replace the title placeholder with the project's name and the prompt with a few
short conversational paragraphs. Enough to make someone care, not enough to bore them. No
bullet-point specs, no jargon; if it reads like a spec, rewrite it until it sounds like a person.
Remove every placeholder. Add `sources:` for any supplied material you drew on.

**Not applicable.** A project summary almost always applies. If it clearly doesn't, propose N/A
with the evidence; on the user's agreement set `status: n/a` and a `reason:`. Never decide N/A
alone.

## Unattended (`auto`)

When `/clarity` passes `auto`, or no person is present, ask nothing. Draft from the sources,
the code and the other documents. Leave each gap as a `[TBD — <what's missing or
conflicting>]` note, and propose any N/A only as a note. Never set `status: complete` or
`n/a`, and never write `reviewed` hashes. Return the draft and its list of gaps.

## Finish

- **Called by `/clarity`:** don't mark anything complete. Return the draft and any open gaps;
  `/clarity` confirms it with the summaries stage.
- **Run directly:** show the summary and ask for confirmation. On a clear yes, set
  `status: complete` and write `reviewed.hash` (its body hash) and `reviewed.deps` (the body
  hash of each `depends_on` document). Body hash: run the manifest's `hash_command` with `FILE`
  replaced by the quoted path; never compute it any other way.
- If you edited a document that was already `complete`, leave its `status` and `reviewed` alone
  and tell the user which documents you touched.
- Then suggest `/clarity` to continue.

## Pitfalls

- **Starting too early**, before the problem and solution are solid.
- **Features instead of a story**: the narrative is what changes for people.
- **Writing for approval instead of truth**: if the honest version doesn't sound good, that's
  information about the project.
- **Pleasing every audience at once**: that's what audience versions are for.

Adapted from microsoft/clarity-agent (message-clarification.md), MIT License — see LICENSE.txt.
