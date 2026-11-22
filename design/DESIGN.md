---
version: alpha
name: OFE
description: Public skills catalog with provenance, submission review, and agent exports.
colors:
  primary: "#b938190f"
  color.accent: "#b938190f"
  color.canvas: "#06111f"
  color.critical-red: "#c63224"
  color.surface: "#f7e7e3"
  color.info-tint-blue: "#4b7bbf24"
  color.text.muted: "#0e0e149e"
  color.canvas-2: "#fff"
  color.positive-tint-green: "#2e8b5724"
typography:
  font.body.sm:
    fontFamily: monospace, JetBrains Mono, ui-monospace
    fontSize: 12px
    fontWeight: not_observed
  font.display.md:
    fontFamily: Archivo, system-ui, sans-serif
    fontSize: 36px
    fontWeight: not_observed
  font.heading.md:
    fontFamily: Archivo, system-ui, sans-serif
    fontSize: 24px
    fontWeight: not_observed
  font.ui:
    fontFamily: JetBrains Mono, ui-monospace, monospace
    fontSize: 12px
    fontWeight: 600 (inferred from .topbar-link; family not confirmed)
  font.caption:
    fontFamily: Archivo, system-ui, sans-serif
    fontSize: 10px
    fontWeight: not_observed
  font.body:
    fontFamily: Archivo, system-ui, sans-serif
    fontSize: 16px
    fontWeight: 700
rounded:
  radius.avatar-circle: 50%
  radius.markdown-code-radius: .45rem
  radius.none: 0
  radius.quarter-rem: .25rem
  radius.xl-theme: .75rem
  radius.rounded-20px: 20px
  radius.pill: 3.40282e+38px
components:
  primary-action:
    backgroundColor: rgb(14, 14, 20)
    textColor: rgb(255, 255, 255)
    rounded: 4px
  secondary-action:
    backgroundColor: rgb(247, 246, 241)
    textColor: rgb(14, 14, 20)
    rounded: 4px
  primary-button:
    backgroundColor: rgb(14, 14, 20)
    textColor: rgb(255, 255, 255)
    rounded: 4px
    padding: 12px 20px
    typography: JetBrains Mono
  secondary-button:
    backgroundColor: rgb(247, 246, 241)
    textColor: rgb(14, 14, 20)
    rounded: 4px
    padding: 12px 20px
    typography: JetBrains Mono
  tertiary-button:
    backgroundColor: rgb(255, 255, 255)
    textColor: rgb(14, 14, 20)
    rounded: 4px
    padding: 12px 16px
    typography: JetBrains Mono
  primary-sign-in-button:
    backgroundColor: "#0e0e14"
    textColor: "#ffffff"
    rounded: 4px
  secondary-create-account-button:
    backgroundColor: "#f7f6f1"
    textColor: "#0e0e14"
    rounded: 4px
  email-and-password-input:
    backgroundColor: "#ffffff"
    textColor: "#0e0e14"
    rounded: 4px
  ghost-action:
    backgroundColor: transparent
    textColor: ink (resolved value not captured)
    rounded: var(--r-sm), value not captured
sectionMap:
  header:
    background: rgb(247, 246, 241)
    text: rgb(14, 14, 20)
    border: none observed
    media: none
    layout: full-width 55px band, logo link left, sign-in link right
  main-form-column:
    background: transparent over page paper
    text: rgb(14, 14, 20)
    border: input borders at rgba(14,14,20,0.22)
    media: none
    layout: 640px wide column with stacked heading, inputs, buttons
  sign-in-form-panel:
    background: transparent (rgba(0,0,0,0)) over page background
    text: "#0e0e14"
    border: not captured
    media: none observed
    layout: single column panel, 640px wide, right half at desktop viewport (inferred from bounding box)
buildTokens:
  layout.header-height: 55px
---

# OFE — Style Reference
> restrained, media-aware, photography led, web experience

**Theme:** mixed

## Overview

OFE is a light-canvas web experience built on a warm off-white ground (`#f7f6f1`) with near-black ink (`#0e0e14`) doing the structural work. JetBrains Mono drives every interactive surface — button labels, nav links, form controls — while Archivo handles display headings and body prose. The palette is deliberately sparse: status signals (destructive red `#c63224`, info blue `#4b7bbf24`, positive green `#2e8b5724`) appear only as semantic indicators, never as decoration. Depth comes from 1px hairline borders and surface contrast, not shadows or gradients.

**Key Characteristics:**
- Core palette: near-black `#0e0e14`, warm white `#f7f6f1`, and translucent semantic tints for status states only
- Brand typeface pairing: Archivo for headings and prose; JetBrains Mono for all interactive labels and system-style captions
- Component patterns: flat-filled action buttons (primary dark, secondary warm-white, tertiary pure-white) at a consistent 4px radius and 12px/20px padding
- Shape language: 7 radius values observed, anchored at 0 for base controls and 4px for action buttons; 50% reserved exclusively for the avatar
- Start from the captured color palette, typography stack, and component measurements — do not introduce values not evidenced here
- Interactive elements carry a uniform 4px corner radius; structural containers step up to .25rem, .45rem, and .75rem as needed

**Non-negotiables:**
- The light `#f7f6f1` canvas is the default page surface. The dark navy `#06111f` is a full-bleed inverse treatment only.
- JetBrains Mono is the exclusive face for action labels, nav chrome, and short system captions. Archivo owns all headings and running text.

## Colors

### Color Philosophy
- Surface tokens set the page atmosphere before they serve as fills. `#f7f6f1` reads as warm paper; `#06111f` reads as deep night — use each only where that atmosphere is intentional.
- Foreground tokens are role-specific. Primary text (`#0e0e14`), muted/secondary text (`#0e0e149e`), and inverse text (`#ffffff`) must remain distinct; collapsing them into a single gray ramp breaks the legibility hierarchy.
- The three status tints — destructive red, info blue, positive green — are semantic signals, not palette accents. Applying them outside their defined roles (error callouts, status badges, destructive fills) dilutes the meaning they carry.
- Do not replace site-specific media with generic decorative imagery.

### Token Roles
#### Brand & Accent
- **{colors.color.accent}** (`#b938190f`): brand accent primary.
#### Surface
- **{colors.color.surface}** (`#f7e7e3`): critical_surface_tint. use for error callouts; validation message backgrounds; warning panels tied to critical state; avoid primary buttons; body text; navigation chrome.
- **{colors.color.canvas}** (`#06111f`): dark_canvas_background_inferred. use for dark full-bleed sections; inverse hero or footer backgrounds; avoid body text on light surfaces; default page background.
- **{colors.color.canvas-2}** (`#fff`): light_canvas_and_inverse_text. use for page background; card and panel surfaces; text on critical fills; avoid text on tinted or translucent surfaces where contrast drops; primary action fills outside critical actions.
#### Semantic
- **{colors.color.critical-red}** (`#c63224`): destructive_fill_and_error_signal. use for destructive action fill (action-danger); error indicators; validation signals; avoid large background fills; body text; decorative accents; non-destructive CTAs.
- **{colors.color.info-tint-blue}** (`#4b7bbf24`): informational_tint_inferred. use for informational callouts; neutral status highlights; avoid primary CTA fills; body text; critical or destructive states.
- **{colors.color.positive-tint-green}** (`#2e8b5724`): positive_status_tint_inferred. use for success badges; positive status backgrounds; avoid primary CTA fills; body text; large page sections.
#### Text
- **{colors.color.text.muted}** (`#0e0e149e`): muted_text_and_disabled_label. use for secondary text; captions; metadata; disabled action labels; avoid headings; primary body copy on dark surfaces; button fills.

## Typography

### Typography Principles

OFE runs a two-family system with strict role separation. Archivo (`system-ui, sans-serif` fallback) owns every heading and body prose context — the 36px display label above the sign-in form, the 24px section heading, and any running paragraph text. JetBrains Mono (`ui-monospace, monospace` fallback) is reserved for interactive chrome: button labels at 14px/700, topbar nav links at 12px/600, and inline code chips inside rendered markdown. The two families never swap roles. Because no `@font-face` declaration was observed in the captured evidence, the full fallback stacks are non-negotiable rendering insurance — do not strip them.

### Font Family

- **monospace, JetBrains Mono, ui-monospace**; fallbacks: ui-monospace; monospace.

- **Archivo, system-ui, sans-serif**; fallbacks: system-ui; sans-serif.

- **Archivo, system-ui, sans-serif**; fallbacks: system-ui; sans-serif.

- **JetBrains Mono, ui-monospace, monospace**; fallbacks: ui-monospace; monospace.

- **JetBrains Mono, ui-monospace, monospace**; fallbacks: ui-monospace; monospace.

- **Archivo, system-ui, sans-serif**; fallbacks: system-ui; sans-serif.

- **Archivo, system-ui, sans-serif**; fallbacks: system-ui; sans-serif.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
| --- | --- | --- | --- | --- | --- |
| {typography.font.body.sm} | 12px | not_observed |  |  |  |
| {typography.font.display.md} | 36px | not_observed |  |  |  |
| {typography.font.heading.md} | 24px | not_observed |  |  |  |
| {typography.font.ui} | 14px | 700 (inferred from --font-weight-bold); 800 on ::before glyph |  |  |  |
| {typography.font.ui} | 12px | 600 (inferred from .topbar-link; family not confirmed) |  |  |  |
| {typography.font.caption} | 10px | not_observed |  |  |  |
| {typography.font.body} | 16px | 700 |  |  |  |

### Principles

- **display-md**: use `Archivo, system-ui, sans-serif`; size `36px`; weight `not_observed`.

- **heading-md**: use `Archivo, system-ui, sans-serif`; size `24px`; weight `not_observed`.

- **label-action**: use `JetBrains Mono, ui-monospace, monospace`; size `14px`; weight `700 (inferred); 800 on ::before`.

- **label-mono-sm**: use `JetBrains Mono, ui-monospace, monospace`; size `12px`; weight `600 (inferred)`.

## Layout

### Composition Principles
- The page frame is a narrow 55px header band followed by a single task-focused main region. There are no decorative section breaks, sidebars, or multi-column prose layouts — the chrome stays out of the way of the content.
- On desktop, the main content block sits inside a 1400px wide region centered within the 1920px viewport. The auth form column is 640px wide and occupies the right half of that region, keeping the heading, inputs, and button stack on a shared left edge at approximately x=665 within the main block.
- Vertical spacing between the heading, input group, and action row is generous; the form reads as a sequence of discrete tasks rather than a dense fieldset.
- Compose pages as named sections — each with explicit surface, text, media, and component treatment — rather than a single undifferentiated page container.

### Rhythm
- A single 55px header band anchors the top of every page; the main region below it carries all task content without competing chrome.
- Vertical rhythm inside the form column is sparse: the eyebrow label, 36px heading, stacked inputs, and action buttons each occupy their own breathing room, with inferred 1.5rem flow-stack gaps between groups (measured in docs CSS; not confirmed on the login page).
- The layout reads as form-first, with all visual weight concentrated in the interaction area rather than distributed across decorative sections.

### Implementation Notes
- Container widths: main content block measured at 1400px wide (desktop 1920px viewport); auth form column measured at 640px wide
- Estimated 2-column split, ~13% outer gutters, 2 interior columns (inferred from main 1400px region and 640px form column offset at x=640)
- Form content left-aligned to a 665px inset within the 1400px main block; heading and inputs share the same left edge

### Section Treatment Map

| Section | Background | Text | Border | Media | Layout | Treatment |
| --- | --- | --- | --- | --- | --- | --- |
| header | rgb(247, 246, 241) | rgb(14, 14, 20) | none observed | none | full-width 55px band, logo link left, sign-in link right |  |
| main form column | transparent over page paper | rgb(14, 14, 20) | input borders at rgba(14,14,20,0.22) | none | 640px wide column with stacked heading, inputs, buttons |  |
| sign-in form panel | transparent (rgba(0,0,0,0)) over page background | #0e0e14 | not captured | none observed | single column panel, 640px wide, right half at desktop viewport (inferred from bounding box) |  |

### Build Notes
- Measured desktop layout only; mobile breakpoints must be inferred from CSS media query list and verified before shipping
- Header height of 55px and main offset of 260px are measured; reuse them as anchors for the page frame
- Grid statement is inferred: 2-column split with ~13% outer gutters; confirm against additional viewports
- Use Archivo for headings and body text and JetBrains Mono for controls, per observed font families.
- Keep control padding at 12px/20px for buttons and 12px/16px for inputs.
- Form panel fills the right half of the desktop layout rather than the full width.

## Elevation & Depth

- box-shadow elevation scale: No brand shadow tokens or component shadows were observed in the captured evidence. Hierarchy between surfaces is established entirely through 1px hairline borders and foreground/background contrast — not drop shadows, blurs, or layered fills.

### Borders

- **{borders.border.blockquote-accent-rule}** (`4px solid var(--red)`): heavy red left rule marking blockquote callouts

- **{borders.border.focus-outline-red}** (`2px solid var(--red)`): keyboard focus indicator on docs-page interactive elements

- **{borders.border.hairline-line}** (`1px solid var(--line)`): primary hairline separator for panels, pills, segmented controls, and topbar bottom edge

- **{borders.border.markdown-hairline}** (`1px solid var(--color-line)`): hairline structure inside rendered markdown (code blocks, tables, rules)

- **{borders.border.secondary-action-edge}** (`1px solid var(--line-strong)`): stronger outline for secondary action buttons

- **{borders.border.transparent-action-edge}** (`1px solid #0000`): reserved transparent border so primary, ghost, and danger actions keep identical box geometry

No motion or transition system is evidenced.

## Shapes

### Border Radius Scale

| Token | Value | Use |
| --- | --- | --- |
| {rounded.radius.none} | 0 | square corners on base form controls and action elements |
| {rounded.radius.rounded-20px} | 20px | large soft rounding utility, arbitrary value |
| {rounded.radius.avatar-circle} | 50% | circular shape reserved for topbar avatar |
| {rounded.radius.markdown-code-radius} | .45rem | inline code chip rounding inside rendered markdown |
| {rounded.radius.quarter-rem} | .25rem | small rounding utility for generic rounded elements |
| {rounded.radius.xl-theme} | .75rem | theme-level large radius token |
| {rounded.radius.pill} | 3.40282e+38px | full-pill rounding utility as extracted; treat as a full-round sentinel, not a design value |

## Components

### Buildable Component Recipes
#### primary-action
- **Component:** button.action-primary
- **Background:** rgb(14, 14, 20)
- **Text:** rgb(255, 255, 255)
- **Border:** 1px solid transparent
- **Radius:** 4px

#### secondary-action
- **Component:** button.action-secondary
- **Background:** rgb(247, 246, 241)
- **Text:** rgb(14, 14, 20)
- **Border:** 1px solid rgba(14,14,20,0.22)
- **Radius:** 4px

#### primary_button
- **Component:** Primary Button
- **Background:** rgb(14, 14, 20)
- **Text:** rgb(255, 255, 255)
- **Border:** 1px
- **Radius:** 4px
- **Padding:** 12px 20px
- **Typography:** JetBrains Mono

#### secondary_button
- **Component:** Secondary Button
- **Background:** rgb(247, 246, 241)
- **Text:** rgb(14, 14, 20)
- **Border:** 1px
- **Radius:** 4px
- **Padding:** 12px 20px
- **Typography:** JetBrains Mono

#### tertiary_button
- **Component:** Tertiary Button
- **Background:** rgb(255, 255, 255)
- **Text:** rgb(14, 14, 20)
- **Border:** 1px
- **Radius:** 4px
- **Padding:** 12px 16px
- **Typography:** JetBrains Mono

#### Primary sign-in button
- **Component:** button.action-primary
- **Background:** #0e0e14
- **Text:** #ffffff
- **Border:** 1px, color not captured (linked CSS border 1px solid transparent)
- **Radius:** 4px

#### Secondary create-account button
- **Component:** button.secondary
- **Background:** #f7f6f1
- **Text:** #0e0e14
- **Border:** 1px, color not captured
- **Radius:** 4px

#### Email and password input
- **Component:** input[type=text\\|password]
- **Background:** #ffffff
- **Text:** #0e0e14
- **Border:** 1px, color not captured
- **Radius:** 4px

#### Ghost action
- **Component:** button.action-ghost
- **Background:** transparent
- **Text:** ink (resolved value not captured)
- **Border:** 1px solid transparent
- **Radius:** var(--r-sm), value not captured

### Ghost action button
A transparent-background button that sits flush with its surroundings — no fill, no visible border — carrying a red `:before` marker glyph as its only visual anchor. On hover, the background lifts to the `paper-2` warm-white surface (`#f7f6f1`), making the affordance visible without demanding attention at rest. Reserved for low-emphasis actions where the primary and secondary fills would create too much visual weight. Present in the linked CSS but not rendered in the captured login view.

### Primary action button
Near-black fill (`#0e0e14`) with white text, 4px corner radius, 12px/20px padding, and 14px JetBrains Mono at 700 weight. The linked CSS adds a hover sheen through an `:after` pseudo-element and a red `:before` accent marker — the same red accent thread that runs through focus rings and blockquote rules. This button anchors the sign-in submit action and should appear only once per row.

### Secondary action button
Warm off-white fill (`#f7f6f1`) with near-black text (`#0e0e14`), identical 4px radius and 12px/20px padding, 14px JetBrains Mono. The lighter fill positions this button as the lower-emphasis alternative sitting beside the primary — the "Create account" action next to "Sign in," for example. The 1px border at `rgba(14,14,20,0.22)` gives it enough edge definition against the page's own `#f7f6f1` background.

### Sign-in form panel
A 640px wide column occupying the right half of the desktop main region. The panel opens with a monospaced eyebrow label (`/ SIGN IN`) at 12px JetBrains Mono, followed by a 36px Archivo heading ("Database-backed access to OFE."), two stacked text inputs (Email, Password) each with a trailing info affordance, and a full-width primary Sign In button. A helper line in muted text (`#0e0e149e`) sits below the button. The paired "Create account" section shares the same column structure immediately adjacent.

### Text input field
Pure white fill (`#ffffff`) with near-black text (`#0e0e14`), 4px radius, a 1px border at `rgba(14,14,20,0.22)`, and 12px/16px padding. Labels ("Email", "Password") sit above each field. Font is 14px JetBrains Mono — the same face as the button labels — keeping the entire interactive row typographically consistent. A trailing info icon on each field hints at contextual help. Focus and error states are unresolved CSS variables and must be confirmed before shipping.

## Do's and Don'ts

### Do
- Build depth and grouping with 1px hairline borders using the `--line` token (panels, pills, segmented controls, topbar bottom edge). Shadows and tinted fills are absent from the observed design; introducing them adds a visual layer the system was not built to support.
- Drop disabled actions to the muted ink token (`#0e0e149e`) on the disabled background surface. The destructive red fill must not appear on a disabled state — it signals active danger.
- Keep buttons, inputs, and selects at radius 0 or the observed 4px button radius. Apply larger rounding only through explicit container utilities; the 50% circle is reserved for the topbar avatar and nothing else.
- Keep the auth form in a 640px column within the 1400px main region, left-aligned so the eyebrow label, 36px heading, inputs, and button share one vertical axis.
- Treat the observed size scale (10px, 12px, 14px, 16px, 24px, 36px) as fixed stops. Each step corresponds to a named token and a specific role; inserting intermediate values without new evidence breaks the hierarchy.
- Limit interactive transitions to short color and background changes around 0.15s on actions and topbar links, using the standard ease curve `cubic-bezier(.4,0,.2,1)`.
- Maintain 44px tall action buttons and inputs on touch viewports; measured desktop actions already meet this height.
- Pair Archivo for headlines and wordmark text with JetBrains Mono for action labels and short system-style captions. Observed page text at 36px and 24px is Archivo; button and nav labels at 14px and 12px are JetBrains Mono.

### Don't
- Do not drop the `system-ui` and generic `sans-serif` fallbacks from the Archivo stack, or the `ui-monospace` and `monospace` fallbacks from the JetBrains Mono stack. No `@font-face` declaration was observed, so the fallback stacks are the only guaranteed rendering path in environments where the custom fonts fail to load.
- Do not introduce accent colors beyond the 12 observed in the palette. Every additional color competes with the semantic tints that carry functional meaning.
- Do not place two primary-filled (`#0e0e14`) buttons in the same row. The light secondary fill (`#f7f6f1`) exists precisely to rank the second action below the first.
- Do not reduce input padding below 12px/16px or reduce the 14px mono label size. The controls are measured at this density; shrinking either dimension degrades the interaction target and breaks visual alignment with the button row.
- Do not set running body paragraphs or headings in JetBrains Mono. The monospace face is observed exclusively on action labels, nav links, eyebrow tags, and inline code — placing it in prose inverts the Archivo/Mono hierarchy the system is built on.
- Do not use the dark navy canvas (`#06111f`) as the default page background. It inverts the light base the site is built on and reduces contrast for the muted secondary text that depends on a warm-white ground.
- Do not use critical red (`#c63224`) for ordinary primary CTAs, navigation links, or decorative accents. Its meaning is confined to destructive actions and error signals; diluting it outside those contexts breaks the signal.
- Do not apply sharp 0-radius corners to interactive elements where the 4px button radius is specified — the observed radius scale starts at 4px for action buttons and 20px for larger container utilities.
- Do not use the `action-danger` (critical-fill) variant for any non-destructive action, regardless of visual preference.
- Do not flood large page areas with the translucent status tints (green `#2e8b5724`, blue `#4b7bbf24`). At large scale these low-opacity fills lose their signal value and muddy the neutral warm-white palette.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
| --- | --- | --- |
| desktop | min-width 64rem (1024px) and above, observed at 1920px | Header spans full 1920px width at 55px height; Main content region is 1400px wide, offset 260px from left |
| mobile | not measured; CSS breakpoints present at 40rem, 48rem, 64rem, 80rem, 96rem | Mobile layout not captured; behavior inferred only |

## Iteration Guide

1. Start from the evidenced tokens and component patterns before inventing new variants.

## Known Gaps

- @font-face declarations: Font files and providers cannot be confirmed from runtime evidence. Preserve the family stack and fallbacks, not a hosted-file claim.
- Body paragraph size and weight: No body paragraph sample was captured, so no body token is emitted. Do not infer a body size from the 16px wordmark sample.
- box-shadow elevation scale: No brand shadow tokens or component shadows were observed; depth is carried by borders.
- decorative gradient or atmospheric orb elements: No absolutely or fixed positioned gradient decoration was captured, so the site's visual signature cannot rely on decorative gradient tokens.
- mobile viewport capture: Responsive behavior cannot be claimed beyond desktop
- generic_language: The quality bar names #b938190f as the primary brand accent, but this hex is absent from the color tokens and all evidence refs. No accent token was emitted.
- extraction_artifact: Transparent placeholder values (#0000) from Tailwind gradient and shadow variables were excluded. The computed rgb(247, 246, 241) value for buttons has no source reference and was excluded.
- generic_language: Focus, hover, and error states for live inputs were not captured. Radius, border color, and focus ring values are unresolved CSS variables.
- extraction_artifact: Browser size samples are sparse (7 entries) and omit weight and line-height. Type styles rely on CSS selectors that may not be the rendered login elements.
- extraction_artifact: Duplicate desktop screenshot and duplicate structured section entries indicate repeated capture; treat counts as single observation.
- extraction_artifact: The full-round radius value 3.40282e+38px is a float-max sentinel rather than a true design value; treat as 'fully rounded' only.
- extraction_artifact: The same sign-in form section appears twice with identical bounding boxes, so it was treated as one component.

## Agent Prompt Guide

Quick Color Reference:
- primary action: `#b938190f`
- background: `#06111f`
- muted text: `#0e0e149e`

Quick Typography Reference:
- body: monospace, JetBrains Mono, ui-monospace, 12px, not_observed
- headings: Archivo, system-ui, sans-serif, 36px, not_observed
- ui: JetBrains Mono, ui-monospace, monospace, 14px, 700 (inferred from --font-weight-bold); 800 on ::before glyph

Implementation Rules:
- Preserve the light canvas with #2e8b570f accent relationship.
- Use JetBrains Mono as the primary typeface.
- Create depth and grouping with 1px hairline borders in the line token (panels, pills, segmented controls, topbar bottom edge) rather than shadows or tinted fills.
- Disabled actions must drop to the muted ink token and the disabled background. Do not use the red fill for disabled destructive actions.
- Keep buttons, inputs, and selects square (radius 0). Apply rounding only through explicit utilities on containers; reserve the circular 50% shape for the topbar avatar.
- Keep the auth form in a narrow column (~640px) centered within the 1400px main region so the heading, inputs, and buttons share one left edge.

Example Component Prompts:
1. Create a header section for OFE using the documented background, text color, layout, and media treatment. Keep copy hierarchy faithful to the Overview and avoid unsupported decorative styles.
2. Create a primary-action component using its exact background, text, radius, padding, typography, state, and motion guidance. Include focus-visible behavior.

## Similar Brands

No taste references were established from the available evidence.

## Quick Start

### CSS Custom Properties

```css
:root {
  --color-accent: #b938190f;
  --color-canvas: #06111f;
  --color-critical-red: #c63224;
  --color-surface: #f7e7e3;
  --color-info-tint-blue: #4b7bbf24;
  --color-text-muted: #0e0e149e;
  --color-canvas-2: #fff;
  --color-positive-tint-green: #2e8b5724;
  --radius-avatar-circle: 50%;
  --radius-markdown-code-radius: .45rem;
  --radius-none: 0;
  --radius-quarter-rem: .25rem;
  --radius-xl-theme: .75rem;
  --radius-rounded-20px: 20px;
  --radius-pill: 3.40282e+38px;
  --layout-header-height: 55px;
  --font-body-sm: monospace, "JetBrains Mono", ui-monospace;
  --font-display-md: Archivo, system-ui, sans-serif;
  --font-heading-md: Archivo, system-ui, sans-serif;
  --font-ui: "JetBrains Mono", ui-monospace, monospace;
  --font-caption: Archivo, system-ui, sans-serif;
  --font-body: Archivo, system-ui, sans-serif;
}
```

### Tailwind v4

```css
@theme {
  --color-accent: #b938190f;
  --color-canvas: #06111f;
  --color-critical-red: #c63224;
  --color-surface: #f7e7e3;
  --color-info-tint-blue: #4b7bbf24;
  --color-text-muted: #0e0e149e;
  --color-canvas-2: #fff;
  --color-positive-tint-green: #2e8b5724;
  --radius-avatar-circle: 50%;
  --radius-markdown-code-radius: .45rem;
  --radius-none: 0;
  --radius-quarter-rem: .25rem;
  --radius-xl-theme: .75rem;
  --radius-rounded-20px: 20px;
  --radius-pill: 3.40282e+38px;
  --layout-header-height: 55px;
  --font-body-sm: monospace, "JetBrains Mono", ui-monospace;
  --font-display-md: Archivo, system-ui, sans-serif;
  --font-heading-md: Archivo, system-ui, sans-serif;
  --font-ui: "JetBrains Mono", ui-monospace, monospace;
  --font-caption: Archivo, system-ui, sans-serif;
  --font-body: Archivo, system-ui, sans-serif;
}
```