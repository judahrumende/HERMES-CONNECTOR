---
name: Hermes Jarvis
description: A dark-first operational interface for directing an autonomous AI organisation.
colors:
  void: "#08090a"
  carbon: "#0f1011"
  obsidian: "#161718"
  graphite: "#23252a"
  smoke: "#383b3f"
  ash: "#62666d"
  fog: "#8a8f98"
  mist: "#d0d6e0"
  bone: "#e5e5e6"
  paper: "#ffffff"
  acid-lime: "#e4f222"
  pulse-green: "#27a644"
  coral-red: "#eb5757"
  signal-teal: "#02b8cc"
  iris-violet: "#6366f1"
  lavender: "#8b5cf6"
  error-text: "#ffaaaa"
  modal-scrim: "rgba(0,0,0,.66)"
typography:
  hero:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "72px"
    fontWeight: 510
    lineHeight: 1.02
    letterSpacing: "-0.028em"
  display:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "64px"
    fontWeight: 510
    lineHeight: 1.04
    letterSpacing: "-0.022em"
  headline:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "48px"
    fontWeight: 510
    lineHeight: 1.08
    letterSpacing: "-0.022em"
  heading-small:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "32px"
    fontWeight: 510
    lineHeight: 1.13
    letterSpacing: "-0.012em"
  page-title:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "24px"
    fontWeight: 510
    lineHeight: 1.2
    letterSpacing: "-0.012em"
  title:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "20px"
    fontWeight: 510
    lineHeight: 1.33
    letterSpacing: "-0.012em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "-0.011em"
  caption:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "-0.011em"
  interface:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.011em"
  interface-small:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.011em"
  metadata:
    fontFamily: "Berkeley Mono, JetBrains Mono, ui-monospace, monospace"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  metadata-small:
    fontFamily: "Berkeley Mono, JetBrains Mono, ui-monospace, monospace"
    fontSize: "9px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  metadata-micro:
    fontFamily: "Berkeley Mono, JetBrains Mono, ui-monospace, monospace"
    fontSize: "8px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.01em"
  form-input-mobile:
    fontFamily: "Inter, system-ui, -apple-system, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "-0.011em"
rounded:
  micro: "2px"
  badge: "4px"
  control: "6px"
  card: "12px"
  pill: "9999px"
spacing:
  micro: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  section-sm: "48px"
  section: "96px"
components:
  button-primary:
    backgroundColor: "{colors.acid-lime}"
    textColor: "{colors.void}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "36px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.void}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "36px"
  card:
    backgroundColor: "{colors.carbon}"
    textColor: "{colors.mist}"
    rounded: "{rounded.card}"
    padding: "12px"
  input:
    backgroundColor: "{colors.obsidian}"
    textColor: "{colors.mist}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    height: "36px"
---

# Design System: Hermes Jarvis

## Overview

**Creative North Star: "The Quiet Command Centre"**

Hermes Jarvis uses a Linear-inspired operational world: dark, dense, precise, and calm. The interface should feel like a place where consequential work is observed and directed, with hierarchy created through tonal surfaces, hairline divisions, compact data rows, and disciplined typography rather than decorative effects.

The landing page and command centre share the same visual grammar. Product UI is the illustration language; capability is demonstrated through real interface components, layered inspectors, work queues, metadata rails, and explicit empty states—never stock imagery or invented operational metrics.

**Key Characteristics:**

- Near-black layered surfaces with one rare acid-lime action.
- Compact, information-rich controls and restrained 12px containers.
- Inter Variable for interface hierarchy; mono only for technical metadata.
- Explicit offline, unconfigured, empty, and local-only states.

## Colors

The palette is dark-first and almost achromatic; acid lime is deliberately rare, while semantic colors appear only in status-level details.

### Primary

- **Acid Lime:** Reserved for the single filled primary action on a screen and the active identity accent.

### Secondary

- **Pulse Green:** Live and successful status dots.
- **Coral Red:** Blocked and error status dots.
- **Iris Violet and Lavender:** Partial-progress and category indicators when those states exist.
- **Signal Teal:** Informational icon detail, never a competing primary action.

### Neutral

- **Void:** Page canvas.
- **Carbon:** Primary cards, sidebars, headers, and composer surfaces.
- **Obsidian:** Nested and interactive surfaces.
- **Graphite and Smoke:** Hairline borders and stronger separators.
- **Ash and Fog:** De-emphasized text, metadata, and placeholders.
- **Mist and Paper:** Body copy and highest-contrast headings.

### Named Rules

**The One Signal Rule.** Use only one acid-lime filled action per screen; all other actions remain neutral.

**The Truthful State Rule.** Operational status colors describe verified state only. Unconfigured systems remain neutral and explicitly labeled.

## Typography

**Display Font:** Inter Variable (with system UI fallback)  
**Body Font:** Inter Variable (with system UI fallback)  
**Label/Mono Font:** Berkeley Mono, falling back to JetBrains Mono and ui-monospace

**Character:** Inter creates a quiet, highly legible product voice with precise spacing. Monospace is a functional signal for issue IDs, model names, shortcuts, timestamps, and technical state—not a decorative technology motif.

### Hierarchy

- **Hero** (510, 72px, 1.02): Landing thesis only; reduces to 48px on compact screens.
- **Display** (510, 64px, 1.04): Large editorial statements.
- **Headline** (510, 48px, 1.08): Major marketing sections; reduces to 32px on mobile.
- **Page Title** (510, 24px, 1.2): Primary app-view titles.
- **Title** (510, 20px, 1.33): Screen and section titles.
- **Body** (400, 15px, 1.6): Explanatory copy with a restrained reading measure.
- **Interface** (400–510, 11–13px): Controls, navigation, and data rows.
- **Metadata** (400–500, 8–10px): Technical state and compact preview labels, with mono reserved for identifiers and machine state.

### Named Rules

**The No Bold Rule.** Inter uses only weights 300, 400, 510, and 590; never 700 or heavier.

## Layout

Marketing sections use wide editorial grids and a maximum working width of 1344–1480px. The landing proof is a near-full-width operating scene with navigation, status, work, activity, inspector, and agent layers. The command centre uses a persistent workspace sidebar with a flexible page canvas; messaging expands into conversation, thread, and metadata panes. At 900px navigation collapses to icons, and at 720px a fixed mobile command bar replaces the sidebar while messaging becomes a focused list-to-thread flow.

Spacing follows a 4px base ladder: 4, 8, 12, 16, 24, 32, 48, and 96px. Closely related controls use gaps rather than stacked margins. Product previews may crop nonessential detail responsively, but primary actions and status copy remain visible.

## Elevation & Depth

Depth is structural rather than shadow-driven. Carbon and obsidian surfaces are separated by graphite or smoke hairlines and occasional subtle inset highlights. No component uses a floating drop shadow; the acid-lime primary action alone receives an inset highlight stack. The hero may use one dark atmospheric floor gradient.

**The Tonal Depth Rule.** Establish hierarchy with neighboring surface tones and one-pixel borders before adding any shadow.

## Shapes

Cards, panels, and substantial overlays use gently curved 12px corners. Buttons, inputs, avatars, and icon controls use 6px corners. Small badges use 4px corners, micro indicators use 2px, and 9999px is reserved for true dots or pills. No ordinary component exceeds a 12px radius.

## Components

### Buttons

- **Shape:** Compact 6px corners with a 36px minimum height.
- **Primary:** Acid-lime fill, void text, and an inset highlight; one per screen.
- **Hover / Focus:** A restrained 180ms state transition and a two-pixel accent focus ring.
- **Secondary / Ghost:** High-contrast neutral fill or transparent surface with a graphite border.

### Chips

- **Style:** Translucent neutral fill, graphite border, fog text, and 4px corners.
- **State:** Color is confined to a dot or small indicator rather than a solid status background.

### Cards / Containers

- **Corner Style:** 12px.
- **Background:** Carbon for primary surfaces and obsidian for nested overlays.
- **Shadow Strategy:** Inset hairline highlight only.
- **Border:** One-pixel graphite, smoke when stronger separation is required.
- **Internal Padding:** 12–16px for compact UI and 24–32px for larger content regions.

### Inputs / Fields

- **Style:** Obsidian or carbon fill, graphite-to-smoke stroke, and 6px corners; composer fields may use 12px.
- **Focus:** Acid-lime focus outline with visible offset.
- **Disabled:** Lower-contrast tonal fill and ash text; never hidden.

### Navigation

Workspace navigation is compact and grouped. Default items use fog text, hover uses an obsidian surface, and the active item uses the same tonal fill with higher-contrast text. Icons use one consistent Lucide line-art family.

### Agent Activity Panel

Agent activity appears as a compact bottom-right panel with a neutral model badge, status dot, technical log lines in mono, and a collapsed work-duration footer. Offline state must be shown directly rather than simulated with fake streaming output.

### Operational Panels

Overview, work, agent, knowledge, approval, and settings surfaces share compact panel headers, hairline row divisions, truthful status dots, and progressive metadata. Density comes from useful simultaneous context—not decorative metrics or repeated feature cards.

## Do's and Don'ts

### Do:

- **Do** use the semantic color aliases so dark and light modes preserve the same hierarchy.
- **Do** render product UI as the landing page's proof of capability.
- **Do** keep disconnected systems visibly offline, unconfigured, or local-only.
- **Do** use Lucide line icons at a consistent 12–17px scale in dense controls.

### Don't:

- **Don't** add another chromatic filled call to action to a screen.
- **Don't** use gradients outside the single atmospheric hero floor.
- **Don't** use drop shadows, stock imagery, decorative mono, or radii above 12px.
- **Don't** turn status colors into large solid badges or fabricate live agent activity.
