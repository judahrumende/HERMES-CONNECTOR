"""Service layer: Hub (WebSocket broadcast) + RuntimeService (local agent or external bridge).

RuntimeService replaces the old HermesService. It prefers the local AgentRuntime when an
API key is configured, and falls back to the external Hermes bridge URL for operators who
still have a separate Hermes Agent installation.

All callers (app.py, loops.py) use the same .run() / .refresh() / .snapshot interface.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .hermes import HermesClient, HermesError
from .runtime import AgentRuntime, RuntimeConfig

if TYPE_CHECKING:
    from .store import Store


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Hub:
    """Broadcast JSON events to all connected WebSocket clients."""

    def __init__(self) -> None:
        self.clients: set[Any] = set()

    async def add(self, socket: Any) -> None:
        await socket.accept()
        self.clients.add(socket)

    async def publish(self, kind: str, data: dict[str, Any]) -> None:
        payload = json.dumps({"type": kind, "at": now(), "data": data})
        dead = []
        for socket in self.clients:
            try:
                await socket.send_text(payload)
            except Exception:
                dead.append(socket)
        for socket in dead:
            self.clients.discard(socket)


class RuntimeService:
    """Unified runtime service — local AgentRuntime preferred, external bridge as fallback."""

    def __init__(self, hub: Hub, store: "Store", state_path: Path = Path("state/connection.json")) -> None:
        self.hub = hub
        self.store = store
        self.state_path = state_path
        self.config = RuntimeConfig()
        self._runtime: AgentRuntime | None = None
        self._bridge_url = os.getenv("HERMES_API_URL", "").rstrip("/")
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.snapshot: dict[str, Any] = {
            "status": "loading",
            "mode": None,
            "provider": None,
            "model": None,
            "base_url": None,
            "checked_at": None,
            "error": None,
            "models": None,
            "jobs": None,
        }

    def load(self) -> None:
        """Load persisted config from state file (bridge URL or provider settings)."""
        if not self.state_path.exists():
            self._update_initial_status()
            return
        try:
            saved = json.loads(self.state_path.read_text())
            if saved.get("provider") and saved.get("api_key"):
                self.config.update(
                    provider=saved["provider"],
                    model=saved.get("model", self.config.model),
                    api_key=saved["api_key"],
                    base_url=saved.get("base_url", ""),
                )
            elif saved.get("base_url"):
                self._bridge_url = saved["base_url"].rstrip("/")
        except (OSError, json.JSONDecodeError):
            pass
        self._update_initial_status()

    def _update_initial_status(self) -> None:
        if self.config.ready:
            self.snapshot.update({"status": "unknown", "mode": "local", "provider": self.config.provider, "model": self.config.model})
        elif self._bridge_url:
            self.snapshot.update({"status": "unknown", "mode": "bridge", "base_url": self._bridge_url})
        else:
            self.snapshot.update({"status": "not_configured", "mode": None, "error": "Configure an API key in Settings → Runtime, or connect a Hermes bridge."})

    def configure_local(self, provider: str, model: str, api_key: str, base_url: str = "") -> None:
        """Switch to the local runtime with the given provider."""
        self.config.update(provider, model, api_key, base_url)
        self._runtime = None
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "provider": provider, "model": model, "api_key": api_key, "base_url": base_url,
        }, indent=2) + "\n")
        self.snapshot.update({"mode": "local", "provider": provider, "model": model, "status": "unknown", "error": None})

    def configure_bridge(self, base_url: str) -> None:
        """Switch to the legacy external Hermes bridge."""
        from .hermes import HermesClient
        client = HermesClient(base_url, os.getenv("HERMES_API_KEY"))
        self._bridge_url = client.base_url
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"base_url": self._bridge_url}, indent=2) + "\n")
        self.snapshot.update({"mode": "bridge", "base_url": self._bridge_url, "status": "unknown", "error": None})

    @property
    def mode(self) -> str:
        return "local" if self.config.ready else ("bridge" if self._bridge_url else "none")

    def _get_runtime(self) -> AgentRuntime:
        if self._runtime is None:
            self._runtime = AgentRuntime(self.store, self.hub, self.config)
        return self._runtime

    async def refresh(self) -> dict[str, Any]:
        if self.config.ready:
            runtime = self._get_runtime()
            result = await runtime.probe()
            self.snapshot.update({
                "checked_at": now(),
                "mode": "local",
                "provider": self.config.provider,
                "model": self.config.model,
                **result,
            })
        elif self._bridge_url:
            client = HermesClient(self._bridge_url, os.getenv("HERMES_API_KEY"))
            try:
                observed = await client.probe()
                self.snapshot.update({"status": "online", "mode": "bridge", "checked_at": now(), "error": None, **observed})
            except (HermesError, ValueError) as exc:
                self.snapshot.update({"status": "offline", "checked_at": now(), "error": str(exc)})
            finally:
                await client.close()
        else:
            self.snapshot.update({"status": "not_configured", "checked_at": now()})
        await self.hub.publish("connection.changed", self.snapshot)
        return self.snapshot

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.config.ready:
            return await self._get_runtime().run(payload)
        elif self._bridge_url:
            return await self._run_bridge(payload)
        else:
            raise HermesError("No runtime configured. Add an API key in Settings → Runtime.")

    async def _run_bridge(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = HermesClient(self._bridge_url, os.getenv("HERMES_API_KEY"))
        try:
            run = await client.create_run(payload)
        finally:
            await client.close()
        await self.hub.publish("run.created", {"run": run})
        run_id = run.get("run_id") or run.get("id")
        if isinstance(run_id, str):
            self._tasks[run_id] = asyncio.create_task(self._forward_bridge(run_id))
        return run

    async def execute_approved_tool(
        self, profile_id: str, agent_id: str, tool: str, inputs: dict[str, Any], run_id: str = "",
    ) -> str:
        """Execute a tool call that the operator approved. Only the local runtime can run tools."""
        if self.config.ready:
            return await self._get_runtime().execute_approved(profile_id, agent_id, tool, inputs, run_id)
        raise HermesError("No local runtime is configured to execute the approved action.")

    async def stop_run(self, run_id: str) -> dict[str, Any]:
        if self.config.ready:
            await self._get_runtime().stop(run_id)
            await self.hub.publish("run.stopped", {"run_id": run_id})
            return {"run_id": run_id, "status": "stop_requested"}
        elif self._bridge_url:
            client = HermesClient(self._bridge_url, os.getenv("HERMES_API_KEY"))
            try:
                result = await client.stop_run(run_id)
            finally:
                await client.close()
            task = self._tasks.pop(run_id, None)
            if task:
                task.cancel()
            await self.hub.publish("run.stopped", {"run_id": run_id})
            return result
        return {"run_id": run_id, "status": "no_runtime"}

    async def _forward_bridge(self, run_id: str) -> None:
        client = HermesClient(self._bridge_url, os.getenv("HERMES_API_KEY"))
        try:
            async for event in client.stream_events(run_id):
                await self.hub.publish("run.event", {"run_id": run_id, **event})
        except HermesError as exc:
            await self.hub.publish("run.stream_ended", {"run_id": run_id, "error": str(exc)})
        finally:
            await client.close()

    async def watch(self) -> None:
        while True:
            await self.refresh()
            await asyncio.sleep(30)


# Backward-compat alias used in a few places that still import HermesService
HermesService = RuntimeService
