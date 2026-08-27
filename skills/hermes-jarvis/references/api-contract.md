# Hermes integration contract

## Upstream Hermes Agent

- `GET /health/detailed`: authenticated readiness and bounded runtime state.
- `GET /v1/models`: available model routes and multiplexed profile discovery.
- `GET /v1/capabilities`: machine-readable feature discovery.
- `POST /v1/runs`: create a long-running agent run.
- `GET /v1/runs/{run_id}/events`: structured SSE lifecycle and tool events.
- `GET /api/jobs`: list scheduled/background jobs when supported.
- `POST /api/jobs`: create a scheduled/background job when supported.

Optional endpoint failures remain warnings. Do not replace missing values with zero unless Hermes explicitly returned zero.

## Browser-facing bridge

- `GET /api/health`: bridge liveness.
- `GET /api/hermes/status`: latest observed snapshot.
- `PUT /api/hermes/connection`: save a non-secret base URL and verify it.
- `POST /api/hermes/refresh`: force a new probe.
- `POST /api/hermes/runs`: server-side run submission.
- `POST /api/hermes/jobs`: server-side job creation.
- `WS /ws/live`: `connection.snapshot`, `connection.changed`, `run.created`, `run.event`, `run.stream_ended`, and `job.created` events.

## Security and resilience

Validate absolute HTTP(S) URLs, bound request timeouts, cap browser event history, preserve safe upstream errors, and never send credentials through WebSocket payloads. Production deployments should restrict CORS to their real origin, terminate TLS, authenticate the command centre, rate-limit mutation routes, and use a managed secret store.
