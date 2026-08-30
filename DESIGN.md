---
name: OrbityLabs Ground Track
description: A route-based command surface for evidence-led AI operations.
colors:
  void: "#090a0c"
  plane: "#0e1013"
  raised-plane: "#13161a"
  rule: "#252930"
  text: "#f3f5f6"
  body: "#b2b7be"
  muted: "#747b85"
  verified: "#68d391"
  attention: "#e5b96b"
  blocked: "#f07b74"
typography:
  display: "DM Sans, system-ui, sans-serif; 68px/0.99; -0.067em"
  page: "DM Sans, system-ui, sans-serif; 32px/1.08; -0.055em"
  section: "DM Sans, system-ui, sans-serif; 19px/1.2; -0.04em"
  interface: "DM Sans, system-ui, sans-serif; 12px/1.4"
  metadata: "JetBrains Mono, ui-monospace, monospace; 10px/1.4"
---

# Design System: OrbityLabs Ground Track

## North star

**Ground Track** makes OrbityLabs feel like a precise laptop control room rather than a collection of dashboard cards. An operator sets intent; a route reveals what is configured, observed, and still unavailable. The system is dark, sparse, and dense where it needs to be. It treats evidence as the visual centre of gravity.

The product UI and landing page share this language. A paired phone is deliberately different: it is a simple, light remote conversation surface, never a compressed desktop dashboard.

## Visual rules

- Use near-black graphite planes, single-pixel rules, and low-radius rectangles for hierarchy.
- Put the primary route near the top of an operational screen. It connects real stages such as runtime, leadership, and observed activity.
- Use orbital geometry only as a meaningful ground-track motif around profile or run relationships. Never add a decorative grid, glowing widget, or fake terminal stream.
- The light primary action is reserved for an operator action such as setting a directive. All other controls are dark and outlined.
- Green means verified or observed. Amber and red are only for real attention or blocked states. Unconfigured and unknown state remains neutral and explicit.
- Mobile paired mode switches to a quiet white chat experience. It omits the sidebar, profile administration, surveillance, and desktop controls.

## Typography

DM Sans is used for all readable UI, with large negative-tracked display type for the operating thesis and compact, clear data rows below it. JetBrains Mono is only for identifiers, timestamps, commands, and runtime metadata.

- Display: 48–68px, 600 weight, tight tracking.
- Page title: 32px, 600 weight.
- Section title: 19–21px, 600 weight.
- UI body: 12–15px, 400–650 weight.
- Metadata: 9–10px mono, uppercase only for labels where it clarifies hierarchy.

## Layout

Desktop has a persistent 258px route rail, a 66px app top bar, and a fluid working canvas. The Ground Track overview uses a single mission route above a two-column evidence layout, then a profile-scoped roster. It should not use a repeated metric-card grid.

Operational panels use 6px radius at most. Adjacent dark planes and hairline rules provide depth before any shadow. Rows are interactive where they open a real location in the product.

## Component behaviour

- **Route point:** is a button that opens the real related surface. It states one actual detail and a verified/neutral visual state.
- **Evidence rail:** lists only recorded runtime events. When none exist, it tells the user why and provides the appropriate route to setup or monitoring.
- **Command agent:** opens the selected CEO conversation or routes to agent creation. It never claims the agent is working unless runtime evidence exists.
- **Roster:** is profile-scoped and opens each agent’s real conversation.
- **Status:** is expressed with a small dot plus readable text, never colour alone.
- **Buttons/inputs:** meet visible-focus requirements and preserve the normal interaction state; animations are limited to control transitions and a subtle ground-track drift, and are disabled for reduced-motion users.

## Do and do not

Do show the user what has been configured, saved, discovered, or observed. Do make unavailable integrations visible. Do preserve profile isolation in every label, list, and action.

Do not manufacture timelines, agent screens, run completions, live activity, or numeric performance. Do not use gradient-heavy AI aesthetics, excessive rounded cards, or decoration that obscures work. Do not turn the mobile remote into a tiny command centre.
