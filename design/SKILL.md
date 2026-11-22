---
name: ofe
description: "Use when building, refactoring, or reviewing UI for hds-ofe.azurewebsites.net — OFE brand design system. OFE is a light-canvas web experience anchored on #2e8b570f as the primary accent using JetBrains . monospace, JetBrains Mono, ui-monospace typography, light theme. Actions: build, generate, refactor, restyle, theme, port, match-brand, design-review, audit-tokens, implement-from-DESIGN.md, write-Tailwind-theme, write-CSS-variables. Stacks: React, Next.js, Vue, Svelte, Astro, SwiftUI, React Nat"
allowed-tools: Bash Read Write Edit
---

# OFE — Design Skill

Standing instructions for any UI task that reads, applies, or audits the OFE `DESIGN.md`. Read this once; follow it for every surface touching this brand.

## Brand Identity

OFE is a light-canvas web experience anchored on #2e8b570f as the primary accent using JetBrains Mono typography and rounded interactive surfaces.

**Non-negotiables:**
- Preserve the light canvas with #2e8b570f accent relationship.
- Use JetBrains Mono as the primary typeface.

## When to Apply

### Must Use
- Implementing any page, screen, or component from this brand
- Setting up `:root` CSS custom properties or a Tailwind v4 `@theme` block
- Refactoring existing UI to match this brand
- Reviewing a diff for brand drift (off-token colors, fonts, radii, shadows)
- Writing component recipes (primary-action, secondary-action, primary_button, secondary_button)

### Recommended
- Resolving "doesn't look on-brand" feedback when the cause is unclear
- Bringing third-party components (shadcn/ui, headlessui) into this codebase
- Picking iconography style, motion timing, or photography crop

### Skip
- Pure backend, infra, or non-visual work
- One-off marketing copy with no UI surface

**Decision rule:** if the change affects how a surface *looks, spaces, types, colors, or moves*, DESIGN.md is the source of truth.

## Section Map

Jump directly to the right section instead of skimming the whole file.

| Task | Read this section of DESIGN.md |
| --- | --- |
| Pick a color for text / surface / accent / border | Colors → Token Roles |
| Set up `:root` CSS variables | Quick Start → CSS Custom Properties |
| Set up Tailwind v4 theme | Quick Start → Tailwind v4 (`@theme`) |
| Choose font / weight / size for a heading or body | Typography → Hierarchy table |
| Style a named section (header, main form column, sign-in form panel) | Layout → Section Treatment Map |
| Decide background / text / border for a page section | Layout → Section Treatment Map |
| Choose page rhythm, container width, gutters | Layout → Composition Principles |
| Apply shadows, elevation, or motion timing | Elevation & Depth |
| Pick a border radius for card / button / input | Shapes → Border Radius Scale |
| Build a component recipe | Components → Buildable Component Recipes |
| Determine hover / active / disabled / focus treatment | Components → State table |
| Avoid brand violations | Do's and Don'ts |
| Adapt across viewports | Responsive Behavior → Breakpoints table |
| Find aesthetic neighbors for visual mood | Similar Brands |
| Understand what NOT to invent | Known Gaps |

The YAML frontmatter is the canonical token store. If frontmatter and prose disagree, **frontmatter wins** for values; **prose wins** for intent.

## Standing Rules

### Token Discipline
- Every color, font, size, weight, radius, shadow, spacing, and component property in generated code **must trace to a key in the DESIGN.md frontmatter**.
- Write CSS as `var(--token-name)` from the Quick Start block — never raw hex.
- Write Tailwind using the `@theme` block from Quick Start — not arbitrary values.

### Never Invent
- Never introduce a color not present in `colors` in the frontmatter.
- Never add a font family, weight, or size not in `typography`.
- Never pick a radius, shadow, or spacing value outside the documented scales.
- Never invent a section background/text/border — use the Section Treatment Map.
- Never substitute a 'similar' color or font from training data — treat missing values as Known Gaps.
- Do not drop the system-ui and generic sans-serif fallbacks from the Archivo stack, or the ui-monospace and monospace fallbacks from the JetBrains Mono stack. No @font-face declaration was observed, so fallbacks are the only guaranteed rendering path.
- Do not introduce accent colors beyond the 12 observed in the palette.
- Do not place two primary-filled buttons in one row. Use the light secondary fill for the second action.
- Do not reduce input padding below 12px/16px or change the 14px mono text; the controls rely on that density for recognition.

### Preserve Brand Posture
- Re-read the Overview first; every decision must reinforce: “OFE is a light-canvas web experience anchored on #2e8b570f as the primary accent using JetBrains Mono typography and rou”
- Layout rhythm, typographic scale, and motion are part of the brand — do not flatten to generic defaults when the DESIGN.md says otherwise (restrained, media-aware).
- Honor `theme: light` in the frontmatter — do not silently invert.
- Create depth and grouping with 1px hairline borders in the line token (panels, pills, segmented controls, topbar bottom edge) rather than shadows or tinted fills.
- Disabled actions must drop to the muted ink token and the disabled background. Do not use the red fill for disabled destructive actions.
- Keep buttons, inputs, and selects square (radius 0). Apply rounding only through explicit utilities on containers; reserve the circular 50% shape for the topbar avatar.

### Known Gaps
- The Known Gaps section lists what extraction could not determine. Do not silently fill — omit, ask the user, or mark `/* TODO: not in DESIGN.md */`.

## Workflow

### 1. Orient (every task)
1. Read `## Overview` → state brand posture in one sentence.
2. Scan frontmatter keys → confirm which token groups exist.
3. Use the Section Map above → jump to the relevant section.

### 2. Build / Refactor
1. Paste **Quick Start → CSS Custom Properties** or **Tailwind v4 `@theme`** into the global stylesheet first.
2. For each section (header, main form column, sign-in form panel): consult the **Section Treatment Map** for background, text, border, media, and layout.
3. For each component: use the **Buildable Component Recipes** for anatomy, states, and motion.
4. Apply the **State table** to every interactive element.
5. Run the Pre-Delivery Checklist before returning code.

### 3. Review / Audit
For each visible value in the diff: *which DESIGN.md token does this trace to?* If none — it's a finding.
Group findings as: off-token value · section treatment violation · missing state · Do/Don't violation · Known Gap silently filled.

### 4. Restyle / Port
Replace frontmatter tokens and Quick Start blocks only; keep component anatomy unless the new DESIGN.md specifies different recipes.

## Pre-Delivery Checklist

- [ ] All colors trace to `colors` in the frontmatter (via CSS var or Tailwind class)
- [ ] All fonts / sizes / weights trace to `typography`
- [ ] All radii trace to `rounded`; all shadows to `shadows`; all spacing to `spacing` or `buildTokens`
- [ ] Each section uses the background / text / border from the Section Treatment Map
- [ ] Each interactive element has every state in the component's State table
- [ ] No item in Do's and Don'ts is violated
- [ ] Known Gaps are marked, not silently filled
- [ ] Brand posture from `## Overview` is still recognizable in the result

## Common Sticking Points

| Problem | Where to Look |
| --- | --- |
| Component feels 'off-brand' but I can't say why | `## Overview` posture + Similar Brands |
| Two valid colors for the same element | Colors → Token Roles (the role decides) |
| Don't know which radius to use | Shapes → Border Radius Scale → match component class |
| Hover / focus states unclear | Components → State table |
| Page rhythm feels cramped or sparse | Layout → Composition Principles + Spacing Tokens |
| Section background unclear | Layout → Section Treatment Map (by section role) |
| Token not in frontmatter | Known Gaps — ask user, don't invent |

## Example Prompts

1. Build a header section for OFE following the Section Treatment Map: use the documented background, text color, and border. Media: none. Layout: full-width 55px band, logo link left, sign-in link right. Keep copy hierarchy faithful to the Overview; avoid unsupported decorative styles.
2. Implement the `primary-action` component for OFE using its exact recipe — match background, text, border, radius, and padding from the Buildable Component Recipes. Implement all states (hover, active, focus, disabled) from the State table. Check the misuse warnings before shipping.
3. Audit this OFE implementation for brand drift: for each color, font, radius, and shadow in the code, verify it traces to a frontmatter token. Flag off-token values, section treatment violations, and any Do/Don't violations. Mark unresolved values as `/* TODO: not in DESIGN.md */` rather than inventing substitutes.
