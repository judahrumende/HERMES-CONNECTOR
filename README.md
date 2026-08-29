# Hermes Jarvis

Hermes Jarvis is a command centre for directing and observing a Hermes Agent runtime. The browser works in an honest local mode without Hermes; live runs, profile discovery, events, and scheduled jobs activate only after the server verifies a real gateway.

## Run locally

```bash
npm install
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

Put the Hermes API key in `.env` as `HERMES_API_KEY`. Never use a `VITE_` prefix for it.

## Connect Hermes in one command

Once the local setup is complete, connect and verify a gateway with one command:

```bash
npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs-connect http://127.0.0.1:8642
```

The command asks for the API key in a hidden terminal prompt, verifies `/health/detailed` before saving anything, and stores the connection in your private local Hermes Jarvis configuration. The web server and desktop app both read that same configuration. For gateways without bearer authentication, add `--no-key`.

Development uses two terminals:

```bash
npm run server
npm run dev
```

For a single production-style process:

```bash
npm run build
set -a; source .env; set +a
npm start
```

Open `http://127.0.0.1:8787`. The FastAPI process serves the built frontend and same-origin API.

## Desktop app

The desktop app is a native macOS window around the exact same production frontend and local Hermes Jarvis server. It does not send your Hermes API key to the renderer.

## Profile integrations

Each profile can hold the path to one Obsidian vault. The **Graphify** tab reads only that configured folder and displays Graphify's real `graphify-out/graph.html` when it exists. OrbityLabs does not scan the computer for vaults or invent a graph when one has not been generated. Install Graphify and generate output inside the profile vault using its official instructions: [Graphify](https://github.com/Graphify-Labs/graphify).

The **Connectors** tab verifies an optional server-only `COMPOSIO_API_KEY` against Composio. Add it to the OrbityLabs desktop configuration file or `.env`, restart OrbityLabs, then choose **Verify Composio key**. Account connections remain explicit per profile through Composio Connect Link; the API key is never returned to the browser or included in agent prompts.

Desktop capabilities are intentionally limited to an operator-configured profile vault. Agents do not receive unrestricted access to every local file, application, or macOS permission by default.

## Autonomy and model configuration

OrbityLabs supports a profile-scoped `auto-safe` policy for routine, reversible work. It does not bypass confirmation for external messages, account or credential creation, payments, deletion, publishing, or security changes. The configuration CLI writes to the private OrbityLabs application-support directory:

```bash
npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs config set autonomy auto-safe
npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs models add ollama:llama3.2
npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs model ollama:llama3.2
npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs agent model ceo openrouter:openai/gpt-4.1
npx --yes --package=github:judahrumende/HERMES-CONNECTOR orbitylabs config list
```

`orbitylabs model` sets a default route, while `orbitylabs agent model` stores a route for one named agent only. In the command centre, per-agent routes are sent to Hermes on each `/v1/runs` request as the `provider` and `model` fields, so one agent's route does not alter the other agents or the gateway default. A route does not download a model or claim that a provider is available; the provider must be installed and configured separately.

Build a downloadable `.dmg` installer with one command:

```bash
npm run desktop:package
```

The installer is written to `release/`. This first packaging run downloads the normal Electron build tooling and, if needed, PyInstaller for the local Python environment. Launch the development desktop app with `npm run desktop:dev`.

## Verification

```bash
npm run build
npx tsc --noEmit
.venv/bin/pytest -q
```

The reusable Codex skill is in `skills/hermes-jarvis/`.

## Deployment boundary

Before an internet-facing deployment, add command-centre authentication, a managed secret store, TLS/reverse-proxy configuration, mutation-route rate limits, a production database for shared planning state, backups, and monitoring. Hermes scheduled jobs—not browser timers—provide unattended execution. A live Hermes connection cannot be verified without a real URL and API key.
