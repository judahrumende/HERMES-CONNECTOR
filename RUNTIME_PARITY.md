# OrbityLabs Native Runtime Parity Contract

OrbityLabs is moving from a dashboard that connects to an external Hermes gateway to a desktop application that owns and supervises its local agent runtime. Hermes Agent and OpenClaw are MIT-licensed reference implementations. Their names, marks, and upstream attribution remain separate from the OrbityLabs product.

This document is the product-truth boundary. A capability is not shown as available until the corresponding runtime path is implemented and verified.

## Profile isolation

Every profile is an independent operating environment:

- profile instructions and context;
- Obsidian vault or other knowledge sources;
- agents, roles, reporting lines, and permissions;
- conversations, memories, and session search;
- skills and profile-local skill improvements;
- tasks, scheduled jobs, approvals, and event history;
- model/provider selection and tool policy;
- workspace files and execution sandbox.

The global assistant is a federated view. It may retrieve from every profile, but every retrieved item retains its profile ID and source attribution. A global conversation cannot silently write into a profile; writes require an explicit target profile.

## Runtime architecture

1. **Desktop supervisor** starts and monitors the runtime, database, scheduler, channel gateway, and update service.
2. **Profile registry** owns isolated configuration and storage roots.
3. **Agent loop** handles model turns, tool calls, interruption, streaming, retries, and context compression.
4. **Tool policy** evaluates every tool call against profile permissions, command allowlists, risk level, and operator approvals.
5. **Memory service** stores attributed memories, full-text session search, user/profile models, and retention controls.
6. **Skill service** loads Agent Skills-compatible packages, records provenance, evaluates generated changes, and requires approval before installing or publishing self-authored skills.
7. **Scheduler** runs bounded jobs independently of an open UI and records delivery status.
8. **Channel gateway** connects approved messaging accounts and keeps conversation continuity across desktop and mobile.
9. **Execution backends** provide local and isolated execution first, followed by Docker, SSH, and optional cloud sandboxes.
10. **Event journal** provides observable lifecycle and tool summaries without exposing hidden chain-of-thought.

## Feature parity matrix

| Capability | Hermes Agent baseline | OpenClaw contribution | OrbityLabs status |
| --- | --- | --- | --- |
| Profile-isolated contexts | Context files, personalities, memory | Workspace/agent routing | Profiles, agents, tasks, knowledge sources, autonomy policy, and model routes are stored server-side in SQLite (`backend/hermes_jarvis/store.py`) with every query scoped by `profile_id`; conversations/messages remain browser-local pending a durable sessions store |
| Global cross-profile assistant | Session search and user model | Multi-agent/team routing | `GET /api/global/context` federates across profiles server-side with explicit per-item profile provenance; implemented |
| Streaming agent loop | Streaming TUI and run lifecycle | Gateway RPC and chat clients | Existing run/event bridge partial; native loop pending |
| Model/provider routing | Nous, OpenRouter, OpenAI-compatible and others | Model registry and provider auth | Per-agent, per-profile provider/model routes persist server-side and are sent with each verified Hermes `/v1/runs` request; the `orbitylabs` CLI, the desktop bridge, and the connect script now share one config path (previously three disconnected stores) and the bridge exposes it read-only via `GET /api/config`; native provider registry and credential lifecycle remain pending |
| Tool system | 40+ tools and toolsets | Tools, plugins, ClawHub | Pending |
| Automatic skill creation | Learning loop and Agent Skills standard | Skills/plugins ecosystem | Profile-scoped GitHub skill-source registry is implemented in SQLite. Steel Browser and AgenticMail are attached as required source references for every agent; the skill engineer returns a runtime-generated specification. Code download, credential setup, execution, scanning, evaluation, and installation remain pending and are never claimed as complete by the UI. |
| Skill self-improvement | Skill updates from experience | Plugin lifecycle | Pending versioned skill registry and regression checks |
| Persistent memory | Agent-curated memory, nudges, FTS5, Honcho | Workspace memory and sessions | Pending database-backed service |
| Subagents | Isolated delegates and parallel work | Agent routing and teams | Pending supervisor and budget controls |
| Scheduled automations | Cron with channel delivery | Gateway scheduling | Existing remote jobs bridge only; native scheduler pending |
| Messaging channels | Telegram, Discord, Slack, WhatsApp, Signal, email | Broad channel and companion-app ecosystem | Phone pairing UI partial; channel adapters pending |
| Voice/media | Voice transcription and TTS integrations | Device and channel media support | Pending |
| MCP | MCP client/server integration | Tools/plugins/nodes | Pending |
| Command approvals | Allowlist and interactive approval | Deterministic policy and sandboxing | Approval UI exists; enforcement engine pending |
| Execution isolation | Local, Docker, SSH, Singularity, Modal, Daytona, Vercel Sandbox | Device nodes and sandbox architecture | Local bridge exists; native sandbox manager pending |
| Browser/device control | Optional tool gateway/browser backend | Browser control and device nodes | Pending explicit provider connections |
| Conversation controls | New/reset, model, personality, retry, undo, compress, usage | Slash commands and clients | Pending |
| Research trajectories | Batch generation and compression | Extensible tools/plugins | Pending |
| Diagnostics and updates | Setup, doctor, update | Doctor, update channels, appcast | `orbitylabs doctor` reports verified config-file/Node/autonomy/model state, whether a gateway URL/key are present (never printing the key), and whether the local bridge is actually reachable; desktop release check exists; `setup`/`update`/`gateway`/`tools` CLI commands still pending |

## Security requirements

- Secrets stay in the desktop secret store or server environment, never localStorage or browser bundles.
- Profile boundaries are enforced in storage queries, tool execution, retrieval, scheduling, and channel delivery.
- Generated skills are untrusted code until scanned, tested, diffed, and approved.
- External communications, account creation, purchases, publishing, credential changes, and destructive actions require explicit operator approval.
- “Autopilot” means unattended execution inside pre-approved goals, budgets, tools, destinations, and time limits. It does not mean unlimited authority.
- Every completed action stores evidence: provider response, artifact, commit, message ID, or other verifiable result.

## Licensing and provenance

- Hermes Agent: MIT license, Nous Research. Reference: <https://github.com/NousResearch/hermes-agent>
- OpenClaw: MIT license, OpenClaw Foundation, with third-party notices. Reference: <https://github.com/openclaw/openclaw>

Before source is incorporated or adapted, preserve copyright notices, MIT license text, and applicable third-party notices in the repository and desktop distribution.
