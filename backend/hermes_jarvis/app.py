from __future__ import annotations

import asyncio
import hashlib
import json
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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .connectors.discord import DiscordConnector
from .connectors.telegram import TelegramConnector
from .hermes import HermesError
from .loops import AgentLoopScheduler
from .service import Hub, RuntimeService
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
        return Path(os.getenv("APPDATA", Path.home())) / "OrbityLabs" / ".env"
    if sys_platform := os.getenv("XDG_CONFIG_HOME"):
        return Path(sys_platform) / "OrbityLabs" / ".env"
    if Path("/Applications").exists():
        return Path.home() / "Library" / "Application Support" / "OrbityLabs" / ".env"
    return Path.home() / ".config" / "OrbityLabs" / ".env"


def legacy_config_file() -> Path:
    """The pre-rebrand config path. Read-only fallback so installs from before the OrbityLabs rename keep working."""
    if os.getenv("HERMES_JARVIS_CONFIG_FILE"):
        return config_file()
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home())) / "Hermes Jarvis" / ".env"
    if sys_platform := os.getenv("XDG_CONFIG_HOME"):
        return Path(sys_platform) / "Hermes Jarvis" / ".env"
    if Path("/Applications").exists():
        return Path.home() / "Library" / "Application Support" / "Hermes Jarvis" / ".env"
    return Path.home() / ".config" / "Hermes Jarvis" / ".env"


def cli_config_file() -> Path:
    """The OrbityLabs CLI's autonomy/model-route config.json, shared read-only with the bridge."""
    override = os.getenv("ORBITYLABS_CONFIG_FILE")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home())) / "OrbityLabs" / "config.json"
    return Path.home() / "Library" / "Application Support" / "OrbityLabs" / "config.json"


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
load_environment(legacy_config_file())
load_environment(ROOT / ".env")


def read_cli_config() -> dict[str, Any]:
    """Read the OrbityLabs CLI's non-secret runtime config (autonomy, default model, per-agent routes)."""
    default: dict[str, Any] = {"autonomy": "manual", "models": [], "default_model": "", "agents": {}}
    try:
        raw = json.loads(cli_config_file().read_text())
    except (OSError, ValueError):
        return default
    if not isinstance(raw, dict):
        return default
    return {
        "autonomy": raw.get("autonomy") if raw.get("autonomy") in ("manual", "auto-safe") else "manual",
        "models": raw.get("models") if isinstance(raw.get("models"), list) else [],
        "default_model": raw.get("default_model") if isinstance(raw.get("default_model"), str) else "",
        "agents": raw.get("agents") if isinstance(raw.get("agents"), dict) else {},
    }


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
    output_path: str = Field(default="", max_length=2048)
    mirror_to_vault: bool = True
    loop_enabled: bool = True
    loop_interval_seconds: int = Field(default=300, ge=60, le=86400)


class ArtifactInput(BaseModel):
    relative_path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=2_000_000)

    @field_validator("relative_path")
    @classmethod
    def artifact_path_must_be_relative(cls, value: str) -> str:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("Artifact path must be a safe relative path")
        return value


class CEOMessage(BaseModel):
    message: str = Field(min_length=1, max_length=30_000)


class SkillDraftInput(BaseModel):
    agent_id: str = Field(min_length=1, max_length=200)
    request: str = Field(min_length=8, max_length=12_000)


class SkillSearchInput(BaseModel):
    query: str = Field(min_length=3, max_length=240)


class ManualPairingCompletion(BaseModel):
    code: str = Field(min_length=8, max_length=32)
    device_name: str = Field(default="Phone", min_length=1, max_length=80)


class SkillInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    repository: str = Field(min_length=15, max_length=2048)
    description: str = Field(default="", max_length=2000)

    @field_validator("repository")
    @classmethod
    def repository_must_be_a_github_url(cls, value: str) -> str:
        """Reject anything that is not a real https://github.com/<owner>/<repo> URL.

        This field is rendered as a raw <a href> in the browser, so a non-http(s)
        scheme (e.g. javascript:) would otherwise reach the DOM unvalidated.
        """
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Repository must be an https://github.com/<owner>/<repo> URL")
        if len([segment for segment in parsed.path.split("/") if segment]) < 2:
            raise ValueError("Repository must include an owner and a repository name")
        return value.strip()


class MessageInput(BaseModel):
    agent_id: str = Field(default="", max_length=200)
    direction: str = Field(pattern="^(outgoing|incoming)$")
    text: str = Field(min_length=1, max_length=30_000)
    run_id: str = Field(default="", max_length=200)


class ApprovalInput(BaseModel):
    agent_id: str = Field(default="", max_length=200)
    session_id: str = Field(default="", max_length=400)
    kind: str = Field(default="run", max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    state: str = Field(pattern="^(approved|denied)$")


class ToolEventInput(BaseModel):
    run_id: str = Field(default="", max_length=200)
    agent_id: str = Field(default="", max_length=200)
    tool_name: str = Field(min_length=1, max_length=200)
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="ok", max_length=40)
    duration_ms: int = Field(default=0, ge=0)


class SkillInstallInput(BaseModel):
    version: str = Field(default="", max_length=200)
    sha: str = Field(default="", max_length=200)


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


class ScheduledDirectiveInput(BaseModel):
    agent_id: str = Field(default="", max_length=200)
    directive: str = Field(..., min_length=1, max_length=8000)
    interval_seconds: int = Field(default=3600, ge=60, le=604800)


class ScheduledDirectiveUpdate(BaseModel):
    agent_id: str | None = None
    directive: str | None = Field(default=None, min_length=1, max_length=8000)
    interval_seconds: int | None = Field(default=None, ge=60, le=604800)
    enabled: bool | None = None


class GroupRunInput(BaseModel):
    agent_ids: list[str] = Field(..., min_length=1, max_length=20)
    directive: str = Field(..., min_length=1, max_length=8000)


class WebhookPayload(BaseModel):
    summary: str = Field(default="Incoming webhook", max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


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


def profile_vault(profile_id: str) -> tuple[dict[str, Any], Path | None, str | None]:
    """Resolve only a vault explicitly assigned to this profile.

    The bridge never falls back to the user's home directory or scans a disk for
    vaults. This keeps profile context and desktop file access intentionally
    scoped to an operator-chosen folder.
    """
    try:
        profile = app.state.store.get_profile(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    configured = str(profile.get("vault_path") or "").strip()
    if not configured:
        return profile, None, "No Obsidian vault path is configured for this profile."
    try:
        vault = Path(configured).expanduser().resolve(strict=True)
    except OSError:
        return profile, None, "The configured Obsidian vault folder cannot be found."
    if not vault.is_dir():
        return profile, None, "The configured Obsidian vault path is not a folder."
    return profile, vault, None


def graphify_state(profile_id: str) -> tuple[dict[str, Any], Path | None, Path | None]:
    profile, vault, issue = profile_vault(profile_id)
    if vault is None:
        return {
            "profile_id": profile_id,
            "profile_name": profile["name"],
            "vault_configured": bool(str(profile.get("vault_path") or "").strip()),
            "vault_available": False,
            "vault_path": str(profile.get("vault_path") or ""),
            "graph_available": False,
            "graph_html_available": False,
            "report_available": False,
            "issue": issue,
        }, None, None
    output = (vault / "graphify-out").resolve()
    if output != vault and vault not in output.parents:
        raise HTTPException(400, "Invalid Graphify output location")
    graph_html = output / "graph.html"
    report = output / "GRAPH_REPORT.md"
    graph_json = output / "graph.json"
    graph_available = graph_html.is_file() or graph_json.is_file() or report.is_file()
    return {
        "profile_id": profile_id,
        "profile_name": profile["name"],
        "vault_configured": True,
        "vault_available": True,
        "vault_path": str(vault),
        "graph_available": graph_available,
        "graph_html_available": graph_html.is_file(),
        "report_available": report.is_file(),
        "issue": None if graph_available else "No Graphify output exists in this vault yet.",
    }, graph_html if graph_html.is_file() else None, report if report.is_file() else None


def composio_snapshot() -> dict[str, Any]:
    return {
        "configured": bool(os.getenv("COMPOSIO_API_KEY", "").strip()),
        "verified": False,
        "provider": "Composio",
        "scope": "server-side only",
        "detail": "Add COMPOSIO_API_KEY to the OrbityLabs desktop configuration, then verify it here.",
    }


def verify_composio_key() -> dict[str, Any]:
    key = os.getenv("COMPOSIO_API_KEY", "").strip()
    if not key:
        return {**composio_snapshot(), "detail": "COMPOSIO_API_KEY is not configured in the desktop server environment."}
    request = UrlRequest(
        "https://backend.composio.dev/api/v3.1/tools?limit=1",
        headers={"x-api-key": key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            response.read(1)
        return {**composio_snapshot(), "verified": True, "detail": "Composio API key verified. Account connections still require an explicit Connect Link flow per profile."}
    except HTTPError as exc:
        return {**composio_snapshot(), "detail": f"Composio rejected the configured API key (HTTP {exc.code})."}
    except (URLError, OSError, TimeoutError):
        return {**composio_snapshot(), "detail": "Could not reach Composio to verify this key. Check your internet connection and try again."}


def configured_agent_folder(profile_id: str, agent_id: str) -> tuple[dict[str, Any], Path]:
    """Resolve an existing operator-configured output directory for one agent."""
    try:
        agent = next(item for item in app.state.store.list_agents(profile_id) if item["id"] == agent_id)
    except StopIteration as exc:
        raise HTTPException(404, "Agent not found") from exc
    configured = str(agent.get("output_path") or "").strip()
    if not configured:
        raise HTTPException(422, "Choose an existing output folder for this agent before it can write files")
    try:
        output = Path(configured).expanduser().resolve(strict=True)
    except OSError as exc:
        raise HTTPException(422, "The configured agent output folder cannot be found") from exc
    if not output.is_dir():
        raise HTTPException(422, "The configured agent output path is not a folder")
    return agent, output


def find_ceo(profile_id: str) -> dict[str, Any]:
    agents = app.state.store.list_agents(profile_id)
    ceos = [agent for agent in agents if "ceo" in f"{agent['name']} {agent['role']}".lower()]
    if not ceos:
        raise HTTPException(422, "Create a CEO agent for this profile before sending it a message")
    return ceos[0]


def paired_device_or_403(secret: str | None) -> None:
    if not secret:
        raise HTTPException(401, "This request must come from a paired mobile device")
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    if not app.state.store.verify_paired_device(digest):
        raise HTTPException(401, "Mobile device is not paired or its access key has been revoked")


def skill_summary(profile_id: str, request: str) -> str:
    matches = app.state.store.match_skills(profile_id, request)
    if not matches:
        return "No registered profile skill source matched this request. Do not assume an unregistered capability exists."
    lines = [f"- {skill['name']}: {skill['repository']} — {skill['description']}" for skill in matches]
    return "Relevant registered skill sources (source-only; do not execute unreviewed code):\n" + "\n".join(lines)


def github_skill_search(query: str) -> list[dict[str, str]]:
    """Search public GitHub repositories as reviewable skill sources, without cloning or executing them."""
    encoded = urlencode({"q": f"{query} skill", "sort": "stars", "order": "desc", "per_page": "8"})
    request = UrlRequest(
        f"https://api.github.com/search/repositories?{encoded}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "OrbityLabs"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 403:
            raise HTTPException(429, "GitHub search is temporarily rate-limited. Try again later.") from exc
        raise HTTPException(502, f"GitHub search failed (HTTP {exc.code}).") from exc
    except (URLError, OSError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, "Could not reach GitHub to search skill sources.") from exc
    results: list[dict[str, str]] = []
    for item in body.get("items", []) if isinstance(body, dict) else []:
        if not isinstance(item, dict) or not isinstance(item.get("html_url"), str):
            continue
        results.append({"name": str(item.get("full_name") or item["html_url"]), "repository": item["html_url"], "description": str(item.get("description") or "No repository description provided."), "state": "source_only"})
    return results


def _build_connectors() -> list[TelegramConnector | DiscordConnector]:
    connectors: list[TelegramConnector | DiscordConnector] = []
    runtime_url = os.getenv("ORBITY_RUNTIME_URL", "http://127.0.0.1:8787")
    def _id_set(name: str) -> set[str]:
        return {p.strip() for p in os.getenv(name, "").split(",") if p.strip()}

    tg_token = os.getenv("ORBITY_TELEGRAM_TOKEN", "")
    tg_profile = os.getenv("ORBITY_TELEGRAM_PROFILE_ID", "")
    if tg_token and tg_profile:
        connectors.append(TelegramConnector(
            token=tg_token,
            profile_id=tg_profile,
            agent_id=os.getenv("ORBITY_TELEGRAM_AGENT_ID", ""),
            runtime_url=runtime_url,
            allowed_user_ids=_id_set("ORBITY_TELEGRAM_ALLOWED_IDS"),
        ))
    dc_token = os.getenv("ORBITY_DISCORD_TOKEN", "")
    dc_profile = os.getenv("ORBITY_DISCORD_PROFILE_ID", "")
    if dc_token and dc_profile:
        raw_channels = os.getenv("ORBITY_DISCORD_CHANNEL_IDS", "")
        channel_ids = [int(c.strip()) for c in raw_channels.split(",") if c.strip().isdigit()]
        connectors.append(DiscordConnector(
            token=dc_token,
            profile_id=dc_profile,
            agent_id=os.getenv("ORBITY_DISCORD_AGENT_ID", ""),
            runtime_url=runtime_url,
            allowed_channel_ids=channel_ids or None,
            allowed_user_ids=_id_set("ORBITY_DISCORD_ALLOWED_IDS"),
        ))
    return connectors


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub = Hub()
    app.state.store = Store(STATE_DIR / "orbitylabs.db")
    service = RuntimeService(hub, app.state.store, STATE_DIR / "connection.json")
    service.load()
    app.state.hub, app.state.hermes = hub, service
    app.state.pairings: dict[str, dict[str, Any]] = {}
    watcher = asyncio.create_task(service.watch())
    scheduler = AgentLoopScheduler(app.state.store, service, hub)
    loop_watcher = asyncio.create_task(scheduler.watch())
    connector_tasks = [asyncio.create_task(c.run()) for c in _build_connectors()]
    try:
        yield
    finally:
        watcher.cancel()
        loop_watcher.cancel()
        for t in connector_tasks:
            t.cancel()
        await asyncio.gather(watcher, loop_watcher, *connector_tasks, return_exceptions=True)


app = FastAPI(title="Hermes Jarvis", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def cli_config() -> dict[str, Any]:
    """Non-secret runtime config set through the `orbitylabs` CLI (never includes HERMES_API_KEY)."""
    return read_cli_config()


@app.get("/api/hermes/status")
async def status() -> dict[str, Any]:
    return app.state.hermes.snapshot


@app.put("/api/hermes/connection")
async def connect(value: ConnectionInput) -> dict[str, Any]:
    try:
        app.state.hermes.configure_bridge(value.base_url)
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


@app.delete("/api/hermes/runs/{run_id}")
async def stop_run(run_id: str) -> dict[str, Any]:
    try:
        return await app.state.hermes.stop_run(run_id)
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/runs")
async def run_direct(value: PayloadInput) -> dict[str, Any]:
    """Convenience alias for /api/hermes/runs — used by the hermes CLI and connectors."""
    try:
        return await app.state.hermes.run(value.payload)
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/hermes/jobs")
async def job(value: PayloadInput) -> dict[str, Any]:
    try:
        if hasattr(app.state.hermes, "create_job"):
            return await app.state.hermes.create_job(value.payload)
        return await app.state.hermes.run(value.payload)
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc


# -- Runtime configuration (replaces external Hermes URL requirement) ----------

class RuntimeConfigInput(BaseModel):
    provider: str = Field(default="anthropic", max_length=50)
    model: str = Field(default="claude-opus-4-5", max_length=200)
    api_key: str = Field(default="", max_length=500)
    base_url: str = Field(default="", max_length=500)


@app.get("/api/runtime/config")
async def get_runtime_config() -> dict[str, Any]:
    cfg = app.state.hermes.config
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "api_key_set": bool(cfg.api_key),
        "base_url": cfg.base_url,
        "mode": app.state.hermes.mode,
        "ready": cfg.ready,
    }


@app.put("/api/runtime/config")
async def set_runtime_config(value: RuntimeConfigInput) -> dict[str, Any]:
    if not value.api_key.strip():
        raise HTTPException(422, "API key is required")
    app.state.hermes.configure_local(value.provider, value.model, value.api_key.strip(), value.base_url.strip())
    return await app.state.hermes.refresh()


# -- Memory endpoints (Hermes Agent-style persistent notes) --------------------

class MemoryInput(BaseModel):
    key: str = Field(..., max_length=200)
    content: str = Field(..., max_length=10000)


@app.get("/api/profiles/{profile_id}/agents/{agent_id}/memories")
async def list_agent_memories(profile_id: str, agent_id: str, prefix: str = "") -> list[dict[str, Any]]:
    try:
        return app.state.store.list_memories(profile_id, agent_id, prefix)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


@app.put("/api/profiles/{profile_id}/agents/{agent_id}/memories")
async def upsert_agent_memory(profile_id: str, agent_id: str, value: MemoryInput) -> dict[str, Any]:
    try:
        app.state.store.upsert_memory(profile_id, agent_id, value.key, value.content)
        return {"key": value.key, "content": value.content}
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


@app.delete("/api/profiles/{profile_id}/agents/{agent_id}/memories/{key}")
async def delete_agent_memory(profile_id: str, agent_id: str, key: str) -> dict[str, Any]:
    try:
        app.state.store.delete_memory(profile_id, agent_id, key)
        return {"deleted": key}
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


# -- Skill docs (agent-created learning loop skills) ----------------------------

@app.get("/api/profiles/{profile_id}/skill-docs")
async def list_skill_docs(profile_id: str, agent_id: str = "") -> list[dict[str, Any]]:
    try:
        return app.state.store.list_skill_docs(profile_id, agent_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/profiles/{profile_id}/skill-docs/{name}")
async def get_skill_doc(profile_id: str, name: str) -> dict[str, Any]:
    doc = app.state.store.get_skill_doc(profile_id, name)
    if not doc:
        raise HTTPException(404, "Skill doc not found")
    return doc


@app.delete("/api/profiles/{profile_id}/skill-docs/{name}")
async def delete_skill_doc(profile_id: str, name: str) -> dict[str, Any]:
    app.state.store.delete_skill_doc(profile_id, name)
    return {"deleted": name}


# -- Session history ------------------------------------------------------------

@app.get("/api/profiles/{profile_id}/sessions")
async def list_sessions(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_sessions(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/profiles")
async def list_profiles() -> list[dict[str, Any]]:
    return app.state.store.list_profiles()


@app.get("/api/connectors/composio")
async def composio_status() -> dict[str, Any]:
    """Report Composio configuration without sending its secret to the client."""
    return composio_snapshot()


@app.post("/api/connectors/composio/verify")
async def composio_verify() -> dict[str, Any]:
    """Validate the configured key with Composio's server API; key remains server-side."""
    return await asyncio.to_thread(verify_composio_key)


@app.get("/api/profiles/{profile_id}/graphify")
async def profile_graphify(profile_id: str) -> dict[str, Any]:
    state, _, _ = graphify_state(profile_id)
    return state


@app.get("/api/profiles/{profile_id}/graphify/view")
async def profile_graphify_view(profile_id: str) -> FileResponse:
    _, graph_html, _ = graphify_state(profile_id)
    if graph_html is None:
        raise HTTPException(404, "Graphify graph.html is not available for this profile")
    return FileResponse(graph_html, media_type="text/html", headers={"Content-Security-Policy": "default-src 'self' data: blob: 'unsafe-inline'"})


@app.get("/api/profiles/{profile_id}/graphify/report")
async def profile_graphify_report(profile_id: str) -> FileResponse:
    _, _, report = graphify_state(profile_id)
    if report is None:
        raise HTTPException(404, "Graphify GRAPH_REPORT.md is not available for this profile")
    return FileResponse(report, media_type="text/markdown; charset=utf-8")


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
        return app.state.store.create_agent(profile_id, str(uuid.uuid4()), value.name, value.role, value.initials, value.output_path, value.mirror_to_vault, value.loop_enabled, value.loop_interval_seconds)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/agents/{agent_id}/notes")
async def get_agent_notes(profile_id: str, agent_id: str) -> dict[str, Any]:
    try:
        notes = app.state.store.get_agent_notes(profile_id, agent_id)
        return {"notes": notes}
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


class AgentNotesInput(BaseModel):
    notes: str = Field(default="", max_length=10000)


@app.put("/api/profiles/{profile_id}/agents/{agent_id}/notes")
async def set_agent_notes(profile_id: str, agent_id: str, value: AgentNotesInput) -> dict[str, Any]:
    try:
        app.state.store.set_agent_notes(profile_id, agent_id, value.notes)
        return {"notes": value.notes}
    except ProfileNotFound as exc:
        raise HTTPException(404, str(exc))


@app.post("/api/profiles/{profile_id}/agents/{agent_id}/artifacts")
async def write_agent_artifact(profile_id: str, agent_id: str, value: ArtifactInput) -> dict[str, Any]:
    """Write a real artifact to the selected agent folder and optional profile vault mirror."""
    agent, output = configured_agent_folder(profile_id, agent_id)
    target = (output / value.relative_path).resolve()
    if output != target and output not in target.parents:
        raise HTTPException(422, "Artifact path escapes the configured agent output folder")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(value.content, encoding="utf-8")
    mirrored_to = ""
    if agent.get("mirror_to_vault"):
        _, vault, _ = profile_vault(profile_id)
        if vault:
            mirror_root = (vault / "OrbityLabs" / "agents" / agent_id).resolve()
            if vault != mirror_root and vault not in mirror_root.parents:
                raise HTTPException(422, "Invalid vault mirror location")
            mirror_target = (mirror_root / value.relative_path).resolve()
            if mirror_root != mirror_target and mirror_root not in mirror_target.parents:
                raise HTTPException(422, "Artifact path escapes the vault mirror")
            mirror_target.parent.mkdir(parents=True, exist_ok=True)
            mirror_target.write_text(value.content, encoding="utf-8")
            mirrored_to = str(mirror_target)
    app.state.store.record_event(profile_id, "agent.artifact_written", {"agent_id": agent_id, "path": str(target), "mirrored_to": mirrored_to or None})
    return {"path": str(target), "mirrored_to": mirrored_to or None}


@app.post("/api/profiles/{profile_id}/ceo/messages")
async def message_ceo(profile_id: str, value: CEOMessage) -> dict[str, Any]:
    """The single laptop-side conversational entry point for a profile's CEO."""
    ceo = find_ceo(profile_id)
    try:
        result = await app.state.hermes.run({
            "input": f"Operator message: {value.message}\n\n{skill_summary(profile_id, value.message)}\n\nSelect only relevant registered skills before acting. A source is not permission to execute code or claim a capability.",
            "session_id": f"orbitylabs:{profile_id}:{ceo['id']}:ceo",
            "metadata": {"profile_id": profile_id, "agent_id": ceo["id"], "role": "ceo", "entrypoint": "operator_chat"},
        })
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc
    app.state.store.record_event(profile_id, "ceo.message_sent", {"agent_id": ceo["id"], "run_id": result.get("run_id") or result.get("id")})
    return result


@app.get("/api/profiles/{profile_id}/skills")
async def list_skills(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_skills(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/skills/search")
async def search_skills(profile_id: str, value: SkillSearchInput) -> dict[str, Any]:
    try:
        local = app.state.store.match_skills(profile_id, value.query)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    external = await asyncio.to_thread(github_skill_search, value.query)
    return {"query": value.query, "registered_matches": local, "github_candidates": external, "notice": "GitHub candidates are source-only. Review code, permissions, and credentials before registering or using any source."}


@app.post("/api/profiles/{profile_id}/skill-drafts")
async def request_skill_draft(profile_id: str, value: SkillDraftInput) -> dict[str, Any]:
    try:
        agent = next(item for item in app.state.store.list_agents(profile_id) if item["id"] == value.agent_id)
    except StopIteration as exc:
        raise HTTPException(404, "Agent not found") from exc
    try:
        result = await app.state.hermes.run({
            "input": f"Design a reviewable OrbityLabs skill specification for this agent request: {value.request}\n\n{skill_summary(profile_id, value.request)}\n\nReturn the skill name, purpose, inputs, outputs, required tools/configuration, security boundary, and verification plan. Do not claim it is installed, executable, or permitted.",
            "session_id": f"orbitylabs:{profile_id}:{agent['id']}:skill-draft",
            "metadata": {"profile_id": profile_id, "agent_id": agent["id"], "mode": "skill_draft"},
        })
    except HermesError as exc:
        raise HTTPException(502, str(exc)) from exc
    draft = app.state.store.create_skill_draft(profile_id, agent["id"], value.request, str(result.get("run_id") or result.get("id") or ""))
    return {"draft": draft, "run": result}


@app.get("/api/profiles/{profile_id}/operations")
async def profile_operations(profile_id: str) -> dict[str, Any]:
    try:
        return {"loops": app.state.store.list_agent_loops(profile_id), "events": app.state.store.list_events(profile_id, 40)}
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/skills")
async def create_skill(profile_id: str, value: SkillInput) -> dict[str, Any]:
    try:
        return app.state.store.create_skill(profile_id, str(uuid.uuid4()), value.name, value.repository, value.description)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/skills/{skill_id}/install")
async def install_skill(profile_id: str, skill_id: str, value: SkillInstallInput) -> dict[str, Any]:
    try:
        return app.state.store.install_skill(profile_id, skill_id, value.version, value.sha)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    except LookupError as exc:
        raise HTTPException(404, "Skill not found") from exc


@app.post("/api/profiles/{profile_id}/skills/{skill_id}/uninstall")
async def uninstall_skill(profile_id: str, skill_id: str) -> dict[str, str]:
    try:
        app.state.store.uninstall_skill(profile_id, skill_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    return {"status": "uninstalled"}


@app.get("/api/profiles/{profile_id}/agent-skills")
async def list_agent_skills(profile_id: str) -> dict[str, list[str]]:
    try:
        return app.state.store.list_agent_skills(profile_id)
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


@app.get("/api/profiles/{profile_id}/messages")
async def list_messages(profile_id: str, agent_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_messages(profile_id, agent_id, min(max(limit, 1), 500))
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/messages")
async def save_message(profile_id: str, value: MessageInput) -> dict[str, Any]:
    try:
        return app.state.store.save_message(profile_id, str(uuid.uuid4()), value.agent_id, value.direction, value.text, value.run_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/messages/search")
async def search_messages(profile_id: str, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    if not q.strip():
        return []
    try:
        return app.state.store.search_messages(profile_id, q.strip(), min(max(limit, 1), 200))
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/message-previews")
async def message_previews(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.message_previews(profile_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.get("/api/profiles/{profile_id}/approvals")
async def list_approvals(profile_id: str, state: str = "") -> list[dict[str, Any]]:
    try:
        return app.state.store.list_approvals(profile_id, state or None)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/approvals")
async def create_approval(profile_id: str, value: ApprovalInput) -> dict[str, Any]:
    try:
        return app.state.store.create_approval(profile_id, str(uuid.uuid4()), value.agent_id, value.session_id, value.kind, value.summary, value.payload)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.patch("/api/profiles/{profile_id}/approvals/{approval_id}")
async def decide_approval(profile_id: str, approval_id: str, value: ApprovalDecision) -> dict[str, Any]:
    """Approve or deny. Approving 'run' kind approvals immediately fires the Hermes run."""
    try:
        approval = app.state.store.get_approval(profile_id, approval_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    except LookupError as exc:
        raise HTTPException(404, "Approval not found") from exc
    if approval["state"] != "pending":
        raise HTTPException(409, f"Approval is already {approval['state']}")

    run_id = ""
    if value.state == "approved" and approval.get("kind") == "run":
        payload = approval.get("payload") or {}
        if isinstance(payload, dict) and payload.get("input"):
            try:
                result = await app.state.hermes.run(payload)
                run_id = str(result.get("run_id") or result.get("id") or "")
                app.state.store.record_event(profile_id, "approval.run_started", {"approval_id": approval_id, "run_id": run_id})
            except HermesError as exc:
                raise HTTPException(502, f"Approval granted but Hermes run failed: {exc}") from exc
    elif value.state == "approved" and approval.get("kind") == "tool_action":
        payload = approval.get("payload") or {}
        tool, inputs = payload.get("tool"), (payload.get("inputs") or {})
        run_id = str(payload.get("run_id") or "")
        if tool:
            try:
                await app.state.hermes.execute_approved_tool(profile_id, approval.get("agent_id", ""), tool, inputs, run_id)
                app.state.store.record_event(profile_id, "approval.tool_executed", {"approval_id": approval_id, "tool": tool})
            except HermesError as exc:
                raise HTTPException(502, f"Approval granted but the action failed: {exc}") from exc

    try:
        return app.state.store.decide_approval(profile_id, approval_id, value.state, run_id)
    except LookupError as exc:
        raise HTTPException(404, "Approval not found") from exc


@app.get("/api/profiles/{profile_id}/tool-events")
async def list_tool_events(profile_id: str, limit: int = 50, run_id: str = "") -> list[dict[str, Any]]:
    try:
        return app.state.store.list_tool_events(profile_id, min(max(limit, 1), 200), run_id)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc


@app.post("/api/profiles/{profile_id}/tool-events")
async def record_tool_event(profile_id: str, value: ToolEventInput) -> dict[str, str]:
    try:
        app.state.store.record_tool_event(profile_id, value.run_id, value.agent_id, value.tool_name, value.input, value.output, value.status, value.duration_ms)
    except ProfileNotFound as exc:
        raise HTTPException(404, "Profile not found") from exc
    return {"status": "recorded"}


@app.get("/api/doctor")
async def doctor() -> dict[str, Any]:
    """Comprehensive health check for the OrbityLabs doctor view."""
    checks: list[dict[str, Any]] = []

    checks.append({
        "name": "Bridge process",
        "status": "ok",
        "detail": "This bridge server is responding.",
    })

    gateway = app.state.hermes.snapshot
    checks.append({
        "name": "Hermes gateway",
        "status": "ok" if gateway.get("status") == "online" else "error" if gateway.get("status") == "offline" else "warning",
        "detail": gateway.get("error") or (gateway.get("base_url") or "Not configured") + (" — verified online" if gateway.get("status") == "online" else ""),
    })

    cfg = config_file()
    checks.append({
        "name": "Config file",
        "status": "ok" if cfg.exists() else "warning",
        "detail": str(cfg) + (" (found)" if cfg.exists() else " (not found — create it to persist credentials)"),
    })

    try:
        stats = app.state.store.db_stats()
        checks.append({
            "name": "Local database",
            "status": "ok",
            "detail": f"{stats.get('profiles', 0)} profiles · {stats.get('agents', 0)} agents · {stats.get('messages', 0)} messages · {stats.get('approvals', 0)} approvals",
        })
    except Exception as exc:
        checks.append({"name": "Local database", "status": "error", "detail": str(exc)})

    loop_candidates = app.state.store.agent_loop_candidates()
    errored = [l for l in loop_candidates if l.get("last_error")]
    checks.append({
        "name": "Agent loops",
        "status": "error" if errored else "ok",
        "detail": f"{len(loop_candidates)} loop(s) configured" + (f" · {len(errored)} with errors: " + "; ".join(l['agent_id'] for l in errored) if errored else ""),
    })

    api_key_set = bool(os.getenv("HERMES_API_KEY", "").strip())
    checks.append({
        "name": "HERMES_API_KEY",
        "status": "ok" if api_key_set else "warning",
        "detail": "Set in server environment" if api_key_set else "Not set — add it to the OrbityLabs .env file",
    })

    return {
        "checks": checks,
        "gateway": gateway,
        "config_file": str(cfg),
        "db_stats": app.state.store.db_stats(),
    }


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
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    manual_code = "".join(secrets.choice(alphabet) for _ in range(8))
    expires_at = now + 300
    app.state.pairings[pairing_id] = {"token": token, "manual_code": manual_code, "expires_at": expires_at, "paired": False}
    return {"pairing_id": pairing_id, "token": token, "manual_code": manual_code, "expires_at": expires_at, "lan_host": local_address()}


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
    return finish_pairing(pairing_id, item, value.device_name)


def finish_pairing(pairing_id: str, item: dict[str, Any], device_name: str) -> dict[str, Any]:
    device_secret = secrets.token_urlsafe(32)
    device_id = str(uuid.uuid4())
    app.state.store.register_paired_device(device_id, hashlib.sha256(device_secret.encode("utf-8")).hexdigest(), device_name)
    item.update({"paired": True, "device_name": device_name, "device_secret": device_secret, "device_id": device_id})
    return {"pairing_id": pairing_id, "device_id": device_id, "device_secret": device_secret, "paired_with": "Laptop command centre"}


@app.post("/api/pairing/manual/complete")
async def complete_manual_pairing(value: ManualPairingCompletion) -> dict[str, Any]:
    candidate = value.code.strip().upper()
    for pairing_id, item in app.state.pairings.items():
        if item["expires_at"] > time.time() and not item.get("paired") and secrets.compare_digest(item.get("manual_code", ""), candidate):
            return finish_pairing(pairing_id, item, value.device_name)
    raise HTTPException(403, "Pairing code is invalid or expired")


@app.get("/api/mobile/manifest")
async def mobile_manifest(x_orbity_device_secret: str | None = Header(default=None)) -> dict[str, Any]:
    paired_device_or_403(x_orbity_device_secret)
    return {"profiles": app.state.store.mobile_manifest(), "host": "Laptop command centre"}


@app.post("/api/mobile/ceo/messages")
async def mobile_message_ceo(value: CEOMessage, profile_id: str, x_orbity_device_secret: str | None = Header(default=None)) -> dict[str, Any]:
    paired_device_or_403(x_orbity_device_secret)
    return await message_ceo(profile_id, value)


# -- run timeline -----------------------------------------------------------------

@app.get("/api/profiles/{profile_id}/runs")
async def list_runs(profile_id: str, limit: int = 50) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_runs(profile_id, min(200, limit))
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")


# -- scheduled directives ---------------------------------------------------------

@app.get("/api/profiles/{profile_id}/scheduled-directives")
async def list_scheduled_directives(profile_id: str) -> list[dict[str, Any]]:
    try:
        return app.state.store.list_scheduled_directives(profile_id)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")


@app.post("/api/profiles/{profile_id}/scheduled-directives")
async def create_scheduled_directive(profile_id: str, value: ScheduledDirectiveInput) -> dict[str, Any]:
    try:
        return app.state.store.create_scheduled_directive(profile_id, value.agent_id, value.directive, value.interval_seconds)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")


@app.patch("/api/profiles/{profile_id}/scheduled-directives/{directive_id}")
async def update_scheduled_directive(profile_id: str, directive_id: str, value: ScheduledDirectiveUpdate) -> dict[str, Any]:
    updates = {k: v for k, v in value.model_dump(exclude_none=True).items()}
    result = app.state.store.update_scheduled_directive(profile_id, directive_id, **updates)
    if result is None:
        raise HTTPException(404, "Directive not found")
    return result


@app.delete("/api/profiles/{profile_id}/scheduled-directives/{directive_id}", status_code=204)
async def delete_scheduled_directive(profile_id: str, directive_id: str) -> None:
    app.state.store.delete_scheduled_directive(profile_id, directive_id)


# -- group run (fan-out to multiple agents) ----------------------------------------

@app.post("/api/profiles/{profile_id}/group-run")
async def group_run(profile_id: str, value: GroupRunInput) -> dict[str, Any]:
    try:
        app.state.store.get_profile(profile_id)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")
    if app.state.hermes.snapshot.get("status") != "online":
        raise HTTPException(503, "Hermes runtime is not online")
    results: list[dict[str, Any]] = []
    for agent_id in value.agent_ids[:20]:
        try:
            result = await app.state.hermes.run({
                "input": value.directive,
                "session_id": f"orbitylabs:{profile_id}:{agent_id}:group",
                "metadata": {"profile_id": profile_id, "agent_id": agent_id, "mode": "group_run"},
            })
            run_id = str(result.get("run_id") or result.get("id") or "")
            if run_id:
                app.state.store.save_run(run_id, profile_id, agent_id, f"orbitylabs:{profile_id}:{agent_id}:group", value.directive[:200])
            results.append({"agent_id": agent_id, "run_id": run_id, "status": "started"})
        except HermesError as exc:
            results.append({"agent_id": agent_id, "error": str(exc), "status": "failed"})
    return {"runs": results}


# -- profile export / import -------------------------------------------------------

@app.get("/api/profiles/{profile_id}/export")
async def export_profile(profile_id: str) -> StreamingResponse:
    try:
        data = app.state.store.export_profile(profile_id)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")
    filename = f"profile-{profile_id[:8]}.json"
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/profiles/import")
async def import_profile_endpoint(request: Request) -> dict[str, Any]:
    from fastapi import Request as Req
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Request body must be valid JSON")
    try:
        return app.state.store.import_profile(body)
    except Exception as exc:
        raise HTTPException(400, f"Import failed: {exc}")


# -- vault diff --------------------------------------------------------------------

@app.get("/api/profiles/{profile_id}/vault-diff")
async def vault_diff(profile_id: str, since: str | None = None) -> list[dict[str, Any]]:
    try:
        profile = app.state.store.get_profile(profile_id)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")
    vault_path = profile.get("vault_path", "")
    if not vault_path:
        raise HTTPException(422, "This profile has no vault path configured")
    return app.state.store.vault_diff(vault_path, since)


# -- approval audit export ---------------------------------------------------------

@app.get("/api/profiles/{profile_id}/approvals/export")
async def export_approvals(profile_id: str, fmt: str = "json") -> StreamingResponse:
    try:
        approvals = app.state.store.list_approvals(profile_id)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")
    if fmt == "csv":
        import csv, io
        output = io.StringIO()
        fields = ["id", "agent_id", "kind", "summary", "state", "decided_at", "run_id", "created_at"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(approvals)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=approvals.csv"})
    return StreamingResponse(iter([json.dumps(approvals, indent=2)]), media_type="application/json", headers={"Content-Disposition": "attachment; filename=approvals.json"})


# -- webhook receiver --------------------------------------------------------------

@app.post("/api/webhooks/{profile_id}")
async def receive_webhook(profile_id: str, value: WebhookPayload) -> dict[str, Any]:
    try:
        approval = app.state.store.create_approval(
            profile_id,
            agent_id="",
            session_id="",
            kind="webhook",
            summary=value.summary[:500],
            payload=value.payload,
        )
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found")
    await app.state.hub.publish("approval.created", {"profile_id": profile_id, "approval_id": approval["id"], "kind": "webhook"})
    return {"received": True, "approval_id": approval["id"]}


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
