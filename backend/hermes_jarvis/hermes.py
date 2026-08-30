from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

import httpx


class HermesError(RuntimeError):
    """An operator-safe Hermes integration error."""


class HermesClient:
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Hermes URL must be an absolute HTTP(S) URL")
        self.base_url = base_url.rstrip("/")
        headers = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=httpx.Timeout(20, connect=5))

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self.client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None
        except httpx.HTTPStatusError as exc:
            raise HermesError(f"Hermes returned HTTP {exc.response.status_code} for {path}.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise HermesError(f"Unable to read Hermes {path} response.") from exc

    async def probe(self) -> dict[str, Any]:
        health = await self.request("GET", "/health/detailed")
        warnings: list[str] = []
        observed: dict[str, Any] = {"health": health, "capabilities": None, "models": None, "jobs": None}
        for name, path in (("capabilities", "/v1/capabilities"), ("models", "/v1/models"), ("jobs", "/api/jobs")):
            try:
                observed[name] = await self.request("GET", path)
            except HermesError:
                warnings.append(f"{name} unavailable")
        observed["warnings"] = warnings
        return observed

    async def create_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        value = await self.request("POST", "/v1/runs", json=payload)
        if not isinstance(value, dict):
            raise HermesError("Hermes returned an invalid run response.")
        return value

    async def create_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        value = await self.request("POST", "/api/jobs", json=payload)
        if not isinstance(value, dict):
            raise HermesError("Hermes returned an invalid job response.")
        return value

    async def stop_run(self, run_id: str) -> dict[str, Any]:
        value = await self.request("DELETE", f"/v1/runs/{run_id}")
        return value if isinstance(value, dict) else {"run_id": run_id, "status": "stop_requested"}

    async def stream_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        path = f"/v1/runs/{run_id}/events"
        try:
            async with self.client.stream("GET", path, headers={"Accept": "text/event-stream"}) as response:
                response.raise_for_status()
                event, lines = "message", []
                async for line in response.aiter_lines():
                    if not line:
                        if lines:
                            raw = "\n".join(lines)
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                data = {"raw": raw}
                            yield {"event": event, "data": data}
                        event, lines = "message", []
                    elif line.startswith("event:"):
                        event = line[6:].strip() or "message"
                    elif line.startswith("data:"):
                        lines.append(line[5:].lstrip())
        except (httpx.HTTPError, httpx.HTTPStatusError) as exc:
            raise HermesError("Hermes event stream ended unexpectedly.") from exc
