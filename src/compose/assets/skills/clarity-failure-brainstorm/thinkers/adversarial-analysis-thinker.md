---
name: adversarial-analysis-thinker
display_name: Adversarial Analysis
modes: [quick, deep]
prerequisites:
  required: [goal/problem.md]
  recommended: [solution/solution.md, solution/architecture.md, goal/stakeholders.md]
tags: [adversarial, threat-modeling, threat-actors]
description: "Deliberate misuse and attack by adversarial actors: who would attack, why, and how"
---
# Adversarial analysis thinker

Most thinkers ask how the system could fail. This one asks **who would want it to fail, and
what would they do?** It is a red-team view: think like the adversary, drawing on how people
really behave badly (criminals, stalkers, corrupt officials, hostile intelligence services,
petty vindictive individuals, the worst corners of the Internet). Threats from human
creativity and malice are the ones checklists miss.

**Scope.** Deliberate misuse and attack, from the attacker's side. Specific technical vectors
(injection, auth bypass) belong to the security thinker: you find *who* would exploit them
and *why*. Honest mistakes belong to the human-factors thinker.

## Four steps, in order

Each step builds on the previous one. Be broad and creative early, narrow later.

1. **Inventory capabilities.** What does the system let someone do: actions,
   communications, transactions? What information does it expose, including what becomes
   possible at scale (aggregating public data into surveillance)? What resources does it hold
   (user data, money, channels, credentials, compute)? What does access require (account,
   permissions, presence, skill, money)? Think about what it *enables*, not only the intended
   uses.
2. **Brainstorm adversaries and goals.** As many as you can, each with a name, who they are,
   what they want, and roughly how they would use the system. Motivations: personal
   (revenge, obsession, stalking, harassment), financial (fraud, extortion, selling data,
   gaming rewards), political (elections, suppressing dissent, propaganda, terrorism),
   military or intelligence (espionage, sabotage, surveillance), acting for or under
   coercion by others, organizational self-interest (profiting at public expense, hiding
   wrongdoing, controlling narratives). Goals may be targeted or untargeted. Discard
   candidates with no practical means or no harm that matters. **Group by means**: adversaries
   who would act the same way form one family.
3. **Refine by capability.** Split a group when capabilities change the approach:
   - **advanced** (zero-days, nation-state or researcher grade; only if the prize is worth
     burning them);
   - **persistent** (can keep trying forever, from nation-states to obsessive individuals);
   - **privileged** (special access: the stalker who is a police officer, the admin with a
     grudge; assume they use it fully);
   - **intimate** (partners, ex-partners, family: routines, devices, security answers);
   - **specialized skills**, **impunity** (immunity, wealth, control of the legal system),
     and the **ability to hire** what they lack;
   - and keep apart the rare competent evil genius from the far more common opportunist
     acting on impulse and entitlement.

   End with each adversary described by name, goal, resources and means.
4. **Characterize the failures.** Turn each profile into one or more failures: the
   adversary, their means in brief, and the harm (to whom, how). Sketch the chain if you can
   see it: what they do at each step, what it requires, where intervention is possible, where
   harm begins and ends. Mark it **pre-existing** when this adversary and attack exist
   without the system; the question is whether the system creates new adversaries, gives
   existing ones new capabilities, or makes attacks much easier.

**Example (photo sharing).** Capabilities: sending images to people or the public; images
reveal people and places; search-by-image enables "where has this person been?"; private
photos include intimate ones, valuable for blackmail. Adversaries grouped by means: those who
hack the service for bulk data; a personal enemy targeting one user through their device or
social engineering (intimate and persistent threats have the edge); a stalker who needs no
hacking if search-by-image exists; someone scraping the image database to build surveillance
tools. One failure: *a personal enemy compromises a user's account*, gains private photos,
and uses them for blackmail, harassment or reputational harm.

## What to produce

Write raw failures to `.clarity/failures/brainstorm/<thinker-name>.md` (use the exact output
path you were given) in the format of the manifest's `helpers.thinker_output` template,
`.compose/templates/clarity/failures/brainstorm/thinker.md`. Title each entry by adversary and
what they achieve; one to three sentences on adversary, goal, means and harm; frame it as a
threat, not a vulnerability; note cross-domain links (security, privacy, human factors, scale,
legal gaps).

Add a **Suggestions** section at the end. Every adversary not already in
`.clarity/goal/stakeholders.md` gets a suggestion to add it, with name, characterization,
goals, resources and means, specific enough to act on without redoing the analysis. This
enrichment of the stakeholder list is a key output.

Adapted from microsoft/clarity-agent (thinkers/adversarial-analysis-thinker.md), MIT License;
see LICENSE.txt in the skill folder.
