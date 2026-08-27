from __future__ import annotations

import asyncio
import os
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub = Hub()
    service = HermesService(hub, STATE_DIR / "connection.json")
    service.load()
    app.state.hub, app.state.hermes = hub, service
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
