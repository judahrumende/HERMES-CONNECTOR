# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is the operator who sets organisational direction, supervises autonomous agents, reviews progress, and intervenes when work needs approval or judgment. A secondary reviewer needs to inspect decisions, outputs, status, and provenance without controlling daily execution.

## Product Purpose

OrbityLabs is a human-facing command centre for an autonomous AI organisation. It lets an operator communicate with a persistent AI CEO and specialised agents, understand current work, review decisions and blockers, and oversee execution that continues independently of a browser session.

OrbityLabs supports multiple isolated profiles. A profile may represent a business, software project, or another operating context, with its own instructions, Obsidian vault, agents, work, knowledge, memories, skills, and runtime policy. A global assistant can answer across profiles while preserving profile and source attribution.

## Positioning

OrbityLabs organises durable Hermes profiles as an operating company rather than presenting one chatbot with temporary subagents. The organisation, agents, work, knowledge, and decisions are intended to persist across sessions and remain observable to the operator.

## Operating Context

The product is used from a web interface alongside Hermes Agent and Hermes Gateway. Planned operating context includes profile synchronisation, direct and group messaging, shared organisational knowledge, task graphs, model routing, approvals, and unattended background work.

## Capabilities and Constraints

- The repository contains a responsive landing page, functional command centre, browser-local work/role/source/message persistence, and a server-side Hermes bridge.
- The bridge verifies Hermes health, discovers models/profiles, submits runs, relays structured events, and exposes Hermes scheduled jobs when the connected gateway supports them.
- Browser-local planning state is not a substitute for a production database or multi-user synchronisation.
- Live Hermes operation, Obsidian, Graphify, and other providers remain unconfigured until real endpoints and credentials are supplied.
- Unavailable integrations and telemetry must be shown as unavailable or unconfigured, never simulated as live.
- Existing navigation, landing-to-command-centre transition, conversation selection, and local message composition must remain functional during visual redesigns.
- Profile boundaries must prevent agents, messages, work, knowledge, vaults, memories, skills, and credentials from leaking between profiles.
- OrbityLabs is transitioning toward a bundled native runtime informed by the MIT-licensed Hermes Agent and OpenClaw projects. Runtime parity must be tracked as implemented, partial, or unavailable; upstream capability lists are not evidence that OrbityLabs already supports them.

## Brand Commitments

The product name is OrbityLabs. Hermes remains the connected runtime and gateway name. The interface should feel precise, operational, calm, and executive rather than playful or chatbot-like. The user supplied a Linear-inspired dark-first design system as the binding visual direction for the current redesign.

## Evidence on Hand

- Product requirements reference: `/Users/judahrumende/Downloads/hermes-jarvis-prd.html`
- Current implementation under `src/`
- No verified customers, usage figures, costs, performance metrics, or live integration status are available and none should be fabricated.

## Product Principles

- Make autonomous work legible without implying that unconnected systems are live.
- Keep human judgment focused on decisions, approvals, risk, and exceptions.
- Preserve history and context across the organisation once persistence is implemented.
- Prefer clear operational state over decorative dashboards.
- Keep dangerous actions behind explicit approval boundaries.

## Accessibility & Inclusion

The web interface must remain keyboard-accessible, responsive across desktop and mobile, and readable in both dark and light color schemes.
