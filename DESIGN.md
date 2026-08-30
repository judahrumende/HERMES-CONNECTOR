---
name: OrbityLabs Midnight Operations
description: A dark editorial command system with copper punctuation and emerald verified automation.
colors:
  void: "#08080a"
  onyx: "#040406"
  carbon: "#111216"
  raised: "#17181d"
  line: "#27282e"
  text: "#e2e3e9"
  muted: "#9194a1"
  copper: "#cc9166"
  verified: "#54f078"
typography:
  display: "Playfair Display, Georgia, serif"
  interface: "-apple-system, BlinkMacSystemFont, SF Pro Text, sans-serif"
rounded:
  compact: "10px"
  controls-small: "12px"
  panels: "14px"
  canvas: "16px"
  controls: "9999px"
---

# Design System: OrbityLabs Midnight Operations

## North star

OrbityLabs should feel like a calm operations room on a MacBook at night: deep black surfaces, exact hairline structure, editorial type for consequential ideas, and compact interface text for work. The system is quiet until automation becomes active. Then restrained emerald connections make the work visible without turning the product into a generic cyberpunk dashboard.

The landing page and command centre share one visual world. Marketing uses the same dark surfaces at a cinematic scale, with the existing generated Orbital Archive artwork darkened and desaturated so product copy and controls remain primary. The application uses that world at operational density.

## Color roles

- `#08080a` is the page canvas.
- `#040406` is the deepest card and contained-work surface.
- `#111216` and `#17181d` create neighboring panel levels.
- `#27282e` and `#383a43` are the structural borders.
- `#e2e3e9` is normal readable copy; white is reserved for headings and critical emphasis.
- Copper `#cc9166` is the editorial accent: brand mark, selected icon, links, and category punctuation.
- Emerald `#54f078` is not a general brand color. It means active, verified automation and appears in status dots, workflow connectors, and active schedule nodes.

## Typography

Playfair Display is reserved for headings at 28px and above, important directives, and major schedule times. The Mac system face handles navigation, controls, form fields, body copy, status, and metadata. Monospace remains limited to actual identifiers, commands, model names, and timestamps.

- Display: 44–94px, regular, .9–1.08 line-height.
- Page title: 34–56px, regular serif.
- Interface title: 15–22px, 500–600 sans.
- Body: 12–16px, 1.5–1.65 line-height.
- Metadata: 9–11px, compact and explicit.

## Scheduled work

The Schedule page is profile-scoped and uses the real laptop scheduler. Each list item exposes its directive, owning agent, repeat interval, enabled state, and computed next run. Clicking a schedule opens a dotted workflow canvas whose nodes show agent ownership, the recurring directive, next run, and latest recorded evidence.

The bottom schedule chat is a real mutation surface, not a simulated assistant. It can change the repeat interval, assigned agent, directive text, or enabled state and only confirms a change after the profile API saves it. If the laptop runtime is unavailable, schedules remain visible and editable but explicitly state that execution is waiting.

## Surface rules

- Use one-pixel borders and neighboring dark tones before shadows.
- Cards use 14px radii; buttons, small status controls, and inputs may use full pills.
- The dotted background is reserved for the schedule workflow canvas because it is an actual node surface.
- The workflow canvas may use restrained glow to describe an active connection. Do not apply glow globally.
- Use only one white filled primary action per working region.
- Keep empty, loading, paused, offline, error, and verified states visibly distinct and truthful.
- Existing generated artwork remains metaphor, never proof of runtime state.
- Mobile remains a focused laptop-pairing and CEO messaging surface, not a miniature desktop dashboard.

## Motion

Cards lift by a few pixels with an exponential ease-out. Workflow nodes keep their authored angle and rise on hover. The active connection may glow softly. All motion is removed under `prefers-reduced-motion`; no interaction depends on animation.

## Product truth

- Never claim a schedule ran without a stored run or error record.
- Never claim an agent owns a schedule unless its stored `agent_id` matches a real profile agent.
- Never show external integrations, models, or credentials as configured without verified backend state.
- Never use generated activity, fake metrics, placeholder accounts, or pretend chat replies to fill the interface.
