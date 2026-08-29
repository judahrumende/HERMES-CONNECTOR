from __future__ import annotations

import asyncio
import os
import re
import secrets
import socket
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .hermes import HermesError
from .service import HermesService, Hub
from .store import ProfileNotFound, Store

ROOT = Path(os.getenv("HERMES_JARVIS_ROOT", Path(__file__).resolve().parents[2]))
DIST = Path(os.getenv("HERMES_JARVIS_DIST_DIR", ROOT / "dist"))
STATE_DIR = Path(os.getenv("HERMES_JARVIS_STATE_DIR", ROOT / "state"))


def config_file() -> Path:
    """Return the shared local configuration file without exposing values to the browser."""
    override = os.getenv("HERMES_JARVIS_CONFIG_FILE")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home())) / "Hermes Jarvis" / ".env"
    if sys_platform := os.getenv("XDG_CONFIG_HOME"):
        return Path(sys_platform) / "Hermes Jarvis" / ".env"
    if Path("/Applications").exists():
        return Path.home() / "Library" / "Application Support" / "Hermes Jarvis" / ".env"
    return Path.home() / ".config" / "Hermes Jarvis" / ".env"


def load_environment(path: Path) -> None:
    """Load only simple KEY=VALUE entries and preserve explicitly supplied environment values."""
    try:
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and key not in os.environ:
                os.environ[key] = value.removeprefix('"').removesuffix('"').removeprefix("'").removesuffix("'")
    except OSError:
        return


load_environment(config_file())
load_environment(ROOT / ".env")


class ConnectionInput(BaseModel):
    base_url: str = Field(min_length=10, max_length=2048)


class PayloadInput(BaseModel):
    payload: dict[str, Any]


class PairingCompletion(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    device_name: str = Field(default="Phone", min_length=1, max_length=80)


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="", max_length=200)
    context: str = Field(default="", max_length=8000)
    vault_path: str = Field(default="", max_length=2048)


class AgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="", max_length=400)
    initials: str = Field(default="", max_length=8)


class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    area: str = Field(default="General", max_length=200)
    state: str = Field(default="draft", max_length=40)


class TaskUpdate(BaseModel):
    state: str = Field(min_length=1, max_length=40)


class SourceInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=2000)


class PolicyInput(BaseModel):
    autonomy: str = Field(pattern="^(manual|auto_safe)$")


class ModelRouteInput(BaseModel):
    agent_id: str = Field(default="", max_length=200)
    provider: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=200)


def local_address() -> str | None:
    """Best-effort LAN address for a QR opened by a phone on the same Wi-Fi."""
    override = os.getenv("HERMES_JARVIS_LAN_HOST")
    if override:
        return override.strip() or None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            address = sock.getsockname()[0]
            if not address.startswith("127."):
                return address
    except OSError:
        pass
    try:
        interfaces = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=2, check=False).stdout
        preferred = ("en0", "en1", "bridge100", "en2")
        blocks = re.split(r"\n(?=\S)", interfaces)
        for name in preferred:
            for block in blocks:
                if block.startswith(f"{name}:"):
                    match = re.search(r"\binet (10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[0-1])\.)[0-9.]+", block)
                    if match:
                        return match.group(0).split(" ")[-1]
        match = re.search(r"\binet (10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[0-1])\.)[0-9.]+", interfaces)
        return match.group(0).split(" ")[-1] if match else None
    except (OSError, subprocess.SubprocessError):
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub = Hub()
    service = HermesService(hub, STATE_DIR / "connection.json")
    service.load()
    app.state.hub, app.state.hermes = hub, service
    app.state.store = Store(STATE_DIR / "orbitylabs.db")
    app.state.pairings: dict[str, dict[str, Any]] = {}
    watcher = asyncio.create_task(service.watch())
    try:
        yield
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)


app = FastAPI(title="Hermes Jarvis", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hermes/status")
async def status() -> dict[str, Any]:
    return app.state.hermes.snapshot


@app.put("/api/hermes/connection")
async def connect(value: ConnectionInput) -> dict[str, Any]:
    try:
        app.state.hermes.configure(value.base_url)
        return await app.state.hermes.refresh()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/hermes/refresh")
async def refresh() -> dict[str, Any]:
    return await app.state.hermes.refresh()


@app.post("/api/hermes/runs")
async def run(value: PayloadInput) -> dict[str, Any]:
    try:
        return await app.state.hermes.run(value.payload)
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/hermes/jobs")
async def job(value: PayloadInput) -> dict[str, Any]:
    try:
        return await app.state.hermes.create_job(value.payload)
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/profiles")
async def list_profiles() -> list[dict[str, Any]]:
    return app.state.store.list_profiles()


@app.post("/api/profiles")
async def create_profile(value: ProfileInput) -> dict[str, Any]:
    return app.state.store.create_profile(str(uuid.uuid4()), value.name, value.kind, value.context, value.vault_path)


@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: str) -> dict[str, str]:
    try:
        app.state.store.delete_profile(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    return {"status": "deleted"}


@app.get("/api/profiles/{profile_id}/agents")
async def list_agents(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_agents(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/agents")
async def create_agent(profile_id: str, value: AgentInput) -> dict[str, Any]:
    try:
        return app.state.store.create_agent(profile_id, str(uuid.uuid4()), value.name, value.role, value.initials)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/tasks")
async def list_tasks(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_tasks(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/tasks")
async def create_task(profile_id: str, value: TaskInput) -> dict[str, Any]:
    try:
        return app.state.store.create_task(profile_id, str(uuid.uuid4()), value.title, value.area, value.state)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.patch("/api/profiles/{profile_id}/tasks/{task_id}")
async def update_task(profile_id: str, task_id: str, value: TaskUpdate) -> dict[str, str]:
    try:
        app.state.store.update_task(profile_id, task_id, value.state)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    except LookupError as exc:
        raise HTTPException(404, "Task not found") from exc
    return {"status": "updated"}


@app.delete("/api/profiles/{profile_id}/tasks/{task_id}")
async def delete_task(profile_id: str, task_id: str) -> dict[str, str]:
    try:
        app.state.store.delete_task(profile_id, task_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    return {"status": "deleted"}


@app.get("/api/profiles/{profile_id}/sources")
async def list_sources(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_sources(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/sources")
async def create_source(profile_id: str, value: SourceInput) -> dict[str, Any]:
    try:
        return app.state.store.create_source(profile_id, str(uuid.uuid4()), value.title, value.detail)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/policy")
async def get_policy(profile_id: str) -> dict[str, Any]:
    try:
        return app.state.store.get_policy(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.put("/api/profiles/{profile_id}/policy")
async def set_policy(profile_id: str, value: PolicyInput) -> dict[str, Any]:
    try:
        return app.state.store.set_policy(profile_id, value.autonomy)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/profiles/{profile_id}/model-routes")
async def list_model_routes(profile_id: str) -> dict[str, Any]:
    try:
        return app.state.store.list_model_routes(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.put("/api/profiles/{profile_id}/model-routes")
async def set_model_route(profile_id: str, value: ModelRouteInput) -> dict[str, Any]:
    try:
        return app.state.store.set_model_route(profile_id, value.agent_id, value.provider, value.model)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/events")
async def list_events(profile_id: str, limit: int = 100) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_events(profile_id, min(max(limit, 1), 500))
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/global/context")
async def global_context() -> list[dict[str, Any]]:
    """Federated view across every profile. Each item carries its own profile_id and name for provenance."""
    return app.state.store.global_context()


@app.post("/api/pairing/start")
async def start_pairing() -> dict[str, Any]:
    """Create a short-lived, single-use pairing invitation; no Hermes credentials leave the laptop."""
    now = time.time()
    app.state.pairings = {key: value for key, value in app.state.pairings.items() if value["expires_at"] > now and not value.get("paired")}
    pairing_id, token = secrets.token_urlsafe(12), secrets.token_urlsafe(24)
    expires_at = now + 300
    app.state.pairings[pairing_id] = {"token": token, "expires_at": expires_at, "paired": False}
    return {"pairing_id": pairing_id, "token": token, "expires_at": expires_at, "lan_host": local_address()}


@app.get("/api/pairing/{pairing_id}")
async def pairing_status(pairing_id: str) -> dict[str, Any]:
    item = app.state.pairings.get(pairing_id)
    if not item or item["expires_at"] <= time.time():
        raise HTTPException(404, "Pairing invitation expired or does not exist")
    return {"status": "paired" if item.get("paired") else "waiting", "expires_at": item["expires_at"]}


@app.post("/api/pairing/{pairing_id}/complete")
async def complete_pairing(pairing_id: str, value: PairingCompletion) -> dict[str, Any]:
    item = app.state.pairings.get(pairing_id)
    if not item or item["expires_at"] <= time.time() or not secrets.compare_digest(item["token"], value.token):
        raise HTTPException(403, "Pairing invitation is invalid or expired")
    item.update({"paired": True, "device_name": value.device_name, "device_secret": secrets.token_urlsafe(32)})
    return {"pairing_id": pairing_id, "device_secret": item["device_secret"], "paired_with": "Laptop command centre"}


@app.websocket("/ws/live")
async def live(socket: WebSocket) -> None:
    await app.state.hub.add(socket)
    await socket.send_json({"type": "connection.snapshot", "data": app.state.hermes.snapshot})
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        app.state.hub.clients.discard(socket)


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = DIST / path
        return FileResponse(candidate if candidate.is_file() else DIST / "index.html")
