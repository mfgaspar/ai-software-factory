---
name: clarity-architecture
description: Design how the chosen solution is built (its core nouns and verbs, components, data flows, deployment, cross-cutting concerns and a Mermaid threat model) as the System Architecture Document in .clarity/solution/architecture.md, and update the solution summary. Use once a solution approach exists.
argument-hint: "[focus, e.g. 'deployment' or 'revise after failure analysis']"
---

# Design the architecture

What the user asked for (it may be empty):

```text
$ARGUMENTS
```

Design a system someone has to build, understand, operate and change. The goal isn't an
impressive diagram; it's a design that is intuitive to reason about and practical to implement.
It writes the System Architecture Document `.clarity/solution/architecture.md` and updates
`.clarity/solution/solution-summary.md`.

## Before you start

1. Read the shipped manifest `.compose/templates/clarity/manifest.yml` (templates,
   `required_sections`, `depends_on`, `hash_command`) and `.clarity/notes.md`. Act on items
   tagged `[for: clarity-architecture]`, then remove them.
2. Read `goal/problem.md`, `goal/stakeholders.md`, `goal/requirements.md`,
   `solution/solution.md`, `failures/failures.md` (and the failure documents it links), the
   ADRs in `decisions/`, the existing architecture and its `sources`. Read the repo's code when
   there is some: describe what's already there before proposing changes.
3. If there's no solution approach yet, go to `clarity-solution` first. If failure analysis
   hasn't run, design anyway and note that the threat model and mitigations need revisiting.
4. Copy a missing document's template from `.compose/templates/clarity/` (the manifest's
   `template` field) and keep `status: draft`.

When in doubt about a trade-off, a level of complexity, or whether something must be
configurable, go back to the problem, requirements and stakeholders: they are the guide and the
limit. Ask only about gaps and conflicts.

## What to keep in mind

- **Nouns and verbs first.** Name the few fundamental objects the system manages and the
  actions they undergo. Good ones are intuitive (no manual needed), stable (they survive new
  features) and few. Borrow an analogy people already understand when it fits. Wrong nouns
  force a translation step into every interface and conversation.
- **The napkin test.** The boxes and arrows someone would draw to explain it are the natural
  components and relationships. The architecture should look like that drawing. Where people
  both view and control the same objects, prefer one way of interacting with them over separate
  read and write models, unless there's a strong reason to split.
- **Survive reality.** Can this team build it? Can someone deploy, monitor and debug it at
  3am? Can it absorb reasonable change without a rewrite? When parts fail, are failures visible
  and recoverable rather than silent and cascading?
- **Ask the user** about real choices between materially different systems, about constraints
  nobody captured, and before assuming anything about the team, infrastructure or operations.
  Technology choices especially: they know their stack and their people.
- **Don't over-specify or over-build.** Structure and key decisions, not implementation
  details. Design for current requirements and note where it could evolve.

## Writing

Fill every section of the template and remove every placeholder (`[TBD…]`,
`[To be determined…]`, other bracketed prompts) from what you fill:

- **Context**: the boundary, the people and external systems around it, the main interactions.
- **Components**: open with the core nouns and verbs. Then each component's responsibility and
  the technology chosen, linking the ADR for each notable choice. Cite the success criteria
  (and `G-###` goals, once the product brief defines them) and rules (NFR-###, CON-###, STD-###) a component exists to meet.
- **Data flows**: how data moves between components, its sensitivity, and where it crosses a
  trust boundary.
- **Deployment**: environments, hosting, topology, scaling, and how it is released and rolled
  back.
- **Cross-cutting concerns**: security, observability, error handling, performance,
  configuration, as relevant; tie each to the NFRs and to the failure modes it manages.
- **Threat model**: the main threats, each with its severity, affected components and a
  one-line mitigation (link the failure document when there is one), plus the single points of
  failure. End the section with a Mermaid diagram in a fenced `mermaid` block, written by hand:
  - the whole system, including people, external services and business processes, not just
    software;
  - one `subgraph` per trust boundary, with the data flows as labelled arrows;
  - threat-affected components highlighted (for example a `classDef` style) and named in the
    text;
  - readable at a glance by someone with no threat-modelling experience.

  Replace the template's sample diagram rather than appending to it.

Before you return, read it as the person who will plan a feature from it:

- every component has one responsibility and a named technology, or a question about it;
- the text and the diagram show the same components and flows;
- each NFR and constraint is tied to the component or concern that meets it, and each High
  or Critical failure mode to the element that manages it;
- what the code does today and what is planned are told apart;
- a new feature can be placed in a component without asking what was meant.

Also capture what surfaced while designing: new failure modes as
`[for: clarity-failure-brainstorm]` notes in `.clarity/notes.md`, requirement gaps as
`[for: clarity-problem]` notes, and open risks in the document.

Then update `solution/solution-summary.md` (still at most two pages): add the architecture in
brief, the non-obvious structural choices, and the design elements that manage the important
failure modes, especially cross-cutting ones. Keep it readable by stakeholders.

Each notable choice (a technology, a structural pattern, a trade-off the user settled) gets an
ADR through `clarity-decision`, or tell the user one should be recorded. If the design shows the
solution itself needs rethinking, say so and point to `clarity-solution`.

**Not applicable.** If the project has no system to architect (for example a purely
organizational change), propose N/A for the architecture with the evidence; on the user's
agreement set `status: n/a` and a `reason:`. Never decide N/A alone.

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

Describe what the code already does as fact. A technology or structural choice that isn't
made yet, and is the user's to make, becomes a `[TBD — …]` note naming the options, or a
`proposed` ADR through `clarity-decision`.

## Finish

- **Called by `/clarity`:** don't mark anything complete. Return the drafts, the ADRs you think
  are needed, and the open gaps; `/clarity` confirms the stage.
- **Run directly:** show a short summary of both documents and ask for confirmation. On a clear
  yes, set `status: complete` on each confirmed document and write `reviewed.hash` (its body
  hash) and `reviewed.deps` (the body hash of each `depends_on` document). Body hash: run the
  manifest's `hash_command` with `FILE` replaced by the quoted path; never compute it any other
  way.
- If you edited a document that was already `complete` (for example the solution), leave its
  `status` and `reviewed` alone and tell the user which documents you touched.
- Then suggest `/clarity` to continue.

## Pitfalls

- **Designing in a vacuum**: ask about team, infrastructure and operations.
- **Getting the nouns wrong**: spend time there; everything downstream inherits them.
- **Premature optimization** and **over-specifying**.
- **Forgetting operations**: a system that can't be deployed, monitored or debugged isn't done.
