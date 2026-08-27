---
name: hermes-jarvis
description: Build, operate, or troubleshoot the Hermes Jarvis command centre and its server-side Hermes Agent bridge. Use for Hermes connection health, profile discovery, runs, live events, scheduled jobs, or truthful command-centre state; do not use for unrelated dashboards.
---

# Hermes Jarvis

Keep Hermes Agent as the runtime authority and Hermes Jarvis as its human-facing control plane.

## Start with product truth

Read `PRODUCT.md`, `DESIGN.md`, `.env.example`, and the relevant implementation before changing the app. Preserve these invariants:

- Never show unobserved agents, activity, costs, usage, profiles, jobs, or connection health as live.
- Keep `HERMES_API_KEY` server-side. Never add it to a `VITE_` variable, browser storage, frontend bundle, screenshot, or report.
- Represent missing infrastructure as `Not configured`, `Not observed`, `Bridge unavailable`, or `Hermes unreachable` according to the actual failure.
- Surface lifecycle events, tool summaries, and state changes; do not expose or imply hidden chain-of-thought.
- Creating a run or scheduled job is an external action. Require a direct user action in the interface and preserve Hermes errors.

## Integration boundary

Use `backend/hermes_jarvis/hermes.py` for upstream HTTP/SSE behavior, `backend/hermes_jarvis/service.py` for connection state and WebSocket fan-out, and `backend/hermes_jarvis/app.py` for browser-facing routes. Keep the browser on the local `/api/hermes/*` and `/ws/live` contract.

Profile synchronisation is discovery from Hermes `/v1/models`; do not invent a separate profile database or assume a model is assigned to a planned organisation role. Background operation uses Hermes `/api/jobs`; a browser tab or timer is not a 24/7 worker.

Read [references/api-contract.md](references/api-contract.md) before adding or changing an integration route.

## Completion gate

For implementation work:

1. Run `npm run build`.
2. Run the Python bridge tests when present.
3. Verify the landing-to-command-centre flow, every changed control, a mobile viewport, and the unavailable-server state.
4. If credentials are not supplied, report the bridge as locally verified and the live Hermes connection as unverified.

Do not call the app production-ready when required secrets, a persistent production data store, deployment, TLS, monitoring, or a live Hermes gateway remain absent. Name each remaining deployment requirement precisely.
