from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .hermes import HermesClient, HermesError


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class Hub:
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


class HermesService:
    def __init__(self, hub: Hub, state_path: Path = Path("state/connection.json")) -> None:
        self.hub, self.state_path = hub, state_path
        self.base_url = os.getenv("HERMES_API_URL", "").rstrip("/")
        self.snapshot: dict[str, Any] = {"status": "not_configured" if not self.base_url else "unknown", "base_url": self.base_url or None, "checked_at": None, "health": None, "capabilities": None, "models": None, "jobs": None, "warnings": [], "error": None}
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def load(self) -> None:
        if self.base_url or not self.state_path.exists():
            return
        try:
            value = json.loads(self.state_path.read_text()).get("base_url")
            if isinstance(value, str):
                self.base_url = value.rstrip("/")
                self.snapshot.update({"base_url": self.base_url, "status": "unknown"})
        except (OSError, json.JSONDecodeError):
            self.snapshot["error"] = "Saved connection settings could not be read."

    def configure(self, base_url: str) -> None:
        client = HermesClient(base_url, os.getenv("HERMES_API_KEY"))
        self.base_url = client.base_url
        self.snapshot.update({"base_url": self.base_url, "status": "unknown", "error": None})
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"base_url": self.base_url}, indent=2) + "\n")

    def client(self) -> HermesClient:
        if not self.base_url:
            raise HermesError("Set a Hermes API URL before connecting.")
        return HermesClient(self.base_url, os.getenv("HERMES_API_KEY"))

    async def refresh(self) -> dict[str, Any]:
        if not self.base_url:
            self.snapshot.update({"status": "not_configured", "checked_at": None, "error": None})
            return self.snapshot
        client = self.client()
        try:
            observed = await client.probe()
            self.snapshot.update({"status": "online", "checked_at": now(), "error": None, **observed})
        except (HermesError, ValueError) as exc:
            self.snapshot.update({"status": "offline", "checked_at": now(), "error": str(exc), "health": None})
        finally:
            await client.close()
        await self.hub.publish("connection.changed", self.snapshot)
        return self.snapshot

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self.client()
        try:
            run = await client.create_run(payload)
        finally:
            await client.close()
        await self.hub.publish("run.created", {"run": run})
        run_id = run.get("run_id") or run.get("id")
        if isinstance(run_id, str):
            self.tasks[run_id] = asyncio.create_task(self.forward(run_id))
        return run

    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self.client()
        try:
            job = await client.create_job(payload)
        finally:
            await client.close()
        await self.hub.publish("job.created", {"job": job})
        await self.refresh()
        return job

    async def stop_run(self, run_id: str) -> dict[str, Any]:
        client = self.client()
        try:
            result = await client.stop_run(run_id)
        finally:
            await client.close()
        task = self.tasks.pop(run_id, None)
        if task:
            task.cancel()
        await self.hub.publish("run.stopped", {"run_id": run_id})
        return result

    async def forward(self, run_id: str) -> None:
        client = self.client()
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
            await asyncio.sleep(15)
