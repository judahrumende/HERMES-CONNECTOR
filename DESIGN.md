---
name: OrbityLabs Orbital Archive
description: An editorial marketing world paired with a quiet professional operator workspace.
colors:
  paper: "#efe0bb"
  paper-light: "#f7ebcb"
  ink: "#17201d"
  orange: "#ce5526"
  ochre: "#d89735"
  brass: "#9b722e"
  muted: "#6f674f"
  verified: "#74b97a"
  blocked: "#dc6b50"
  operator-canvas: "#f6f7f9"
  operator-surface: "#ffffff"
  operator-ink: "#17191d"
  operator-accent: "#5653d8"
typography:
  display: "Bodoni Moda, Georgia, serif"
  interface: "DM Sans, system-ui, sans-serif"
  metadata: "JetBrains Mono, ui-monospace, monospace"
rounded:
  interface: "0-6px"
  status: "9999px"
---

# Design System: OrbityLabs Orbital Archive

## North star

**Orbital Archive** imagines the autonomous organisation as a hand-drawn future institution: part observatory, part archive, part transit system. Warm fibrous paper, carbon ink, oxidised orange, astronomical geometry, and architectural illustration give the product a tactile cultural home without making the operational interface harder to use.

The product deliberately has two visual registers. Marketing uses full illustration, editorial scale, and cinematic sequence. The command centre is a quiet professional workspace where product state, navigation, conversation, and operator actions remain immediately legible. The paired mobile companion remains a focused messaging and pairing surface.

## Image system

All flagship artwork is original GPT Images output saved under `public/assets/orbital-archive/`. It must not contain interface text, commercial claims, logos, or synthetic runtime data. Live HTML carries every product statement and interaction.

- `hero-metropolis.jpg`: the autonomous organisation as a connected future metropolis.
- `orchestration-tower.jpg`: the CEO and agent system as an architectural cross-section.
- `agent-triptych.jpg`: strategy, systems, and research as three editorial portraits.
- `profile-atlas.jpg`: isolated profile worlds connected through an overview observatory.
- `paper-texture.jpg`: the shared material substrate.

Images use fibrous paper, ink bleed, risograph grain, technical construction lines, solar discs, ivory, ochre, carbon, and vermilion. They avoid cyberpunk neon, generic neural-network graphics, photorealism, copied cities, and embedded text.

## Typography

Bodoni Moda is the editorial display voice and belongs to marketing. DM Sans or Inter carries the command centre, interface copy, controls, and page titles. JetBrains Mono remains limited to commands, identifiers, timestamps, and measured machine state.

- Hero display: 64–118px, regular, line-height .86–.94, tracking no tighter than -0.04em.
- Section display: 44–88px, regular, line-height .92–1.02.
- Body: 14–18px with 1.55–1.65 line-height and a 65–75 character measure.
- Interface: 10–13px, medium when an action needs emphasis.

## Layout and sequence

The landing page reads like a long-form exhibition publication:

1. An illustrated metropolis and live product thesis.
2. The real product interface framed as operational evidence.
3. CEO orchestration shown as architecture.
4. A three-part specialist portrait sequence.
5. A profile atlas demonstrating context isolation.
6. Human authority on a committed vermilion field.
7. A direct desktop call to action.

Sections meet at hard editorial seams. Panels use rules and material contrast rather than generic floating cards. Illustration crops remain art-directed at every breakpoint.

## Operational adaptation

The application is the **Operator Workspace**, not a reduced version of the landing page.

- Use a warm-neutral `#f6f7f9` canvas, white work surfaces, dark ink, and indigo `#5653d8` for primary actions and selected routes.
- Keep the sidebar compact. Eight frequent routes stay visible; secondary controls live behind a real More tools menu. The desktop rail collapses to icons and remains a drawer on small screens.
- Use 30px page titles, 12–13px body copy, and 9–11px metadata. Every operational heading uses the interface typeface.
- Working surfaces use 12–14px radii, quiet one-pixel rules, and low-elevation shadows. Avoid giant decorative empty states.
- Empty states explain what is missing and expose a real next action. Profile creation happens directly on the Profiles page.
- The global assistant is a contained conversation canvas with runtime state, scoped profile context, a centred first-use state, and a fixed composer.
- No generated artwork, archival texture, display serif, or marketing ornament appears inside the application.
- Green means observed or verified. Red means actually blocked. Unknown and unconfigured states remain neutral.

## Motion

The authored moment is the hero image revealing from the right as its city slowly breathes forward. Supporting illustrations gain a restrained scale response on hover. The archive seal rotates slowly. Every effect is removed for reduced-motion users.

## Rules

- Keep live text out of generated images.
- Do not fabricate agents, activity, metrics, integrations, or run success to fill the composition.
- Use illustration as product metaphor, never as evidence of a connected runtime.
- Preserve obvious keyboard focus, readable contrast, themed selection, scrollbars, disabled states, and truthful empty states.
- Do not introduce neon, glassmorphism, generic AI gradients, dashboard metric-card grids, or decorative terminal streams.
- Do not flatten the paired phone experience into a miniature desktop command centre.
