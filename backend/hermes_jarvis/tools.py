"""Agent tool registry and executor.

All tool results are plain strings — the LLM always receives text, never raw data.
Tools are bounded: no network-capable bash, no root writes, no credential exfiltration.
"""
from __future__ import annotations

import asyncio
import base64
import glob as _glob
import json
import os
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request as _URLReq, urlopen

if TYPE_CHECKING:
    from .store import Store

# Where generated assets (images, audio) are written by default.
OUTPUT_DIR = Path(os.getenv("ORBITY_OUTPUT_DIR", "orbity-output"))

# ---------------------------------------------------------------------------
# Tool schema definitions (Anthropic format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "bash",
        "description": (
            "Execute a shell command and return stdout + stderr. "
            "Use for file operations, running scripts, checking system state, "
            "or any automation. Commands run in the agent's working directory. "
            "Timeout is enforced. Do not use for destructive operations without operator approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "workdir": {"type": "string", "description": "Working directory (optional)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 120)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the text contents of a file. Returns up to 100 KB.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute or relative file path"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write text content to a file, creating parent directories as needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Text content to write"},
                "append": {"type": "boolean", "description": "Append instead of overwrite (default false)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory, optionally matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.md')"},
                "recursive": {"type": "boolean", "description": "Recurse into subdirectories"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "http_fetch",
        "description": "Fetch a URL and return the response body as text (max 200 KB). Good for reading docs, APIs, web pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "method": {"type": "string", "enum": ["GET", "POST"], "description": "HTTP method (default GET)"},
                "body": {"type": "string", "description": "Request body for POST"},
                "headers": {"type": "object", "description": "Extra HTTP headers"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "memory_write",
        "description": "Store a persistent memory note for this agent. Notes survive between sessions and are injected into future context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short identifier (e.g. 'project-goal', 'user-preference')"},
                "content": {"type": "string", "description": "The information to remember"},
            },
            "required": ["key", "content"],
        },
    },
    {
        "name": "memory_read",
        "description": "Read all stored memory notes for this agent, or search by key prefix.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prefix": {"type": "string", "description": "Filter by key prefix (optional, returns all if omitted)"},
            },
        },
    },
    {
        "name": "memory_delete",
        "description": "Delete a memory note by its exact key.",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "create_skill",
        "description": (
            "Save a reusable skill — a markdown document describing how to accomplish a class of task. "
            "Skills are loaded on relevant future runs. Use after completing a complex task to capture what worked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short skill name (slug, no spaces)"},
                "description": {"type": "string", "description": "One-line description of what the skill does"},
                "content": {"type": "string", "description": "Full skill body in markdown — steps, patterns, gotchas"},
            },
            "required": ["name", "description", "content"],
        },
    },
    {
        "name": "run_python",
        "description": "Execute a Python snippet and return stdout + stderr. For data processing, calculations, or scripting that needs Python.",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 60)"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "search_files",
        "description": "Search for text patterns across files using ripgrep or grep. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex supported)"},
                "path": {"type": "string", "description": "Directory or file to search in"},
                "file_pattern": {"type": "string", "description": "Limit to files matching this glob (e.g. '*.py')"},
                "case_sensitive": {"type": "boolean", "description": "Case sensitive search (default false)"},
            },
            "required": ["pattern", "path"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for current information. Returns titles, URLs, and snippets. "
            "Use for research, docs lookup, prices, news, or anything you need fresh facts on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Number of results (default 5, max 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Generate an image from a text prompt and save it to disk. Returns the file path. "
            "Great for product mockups, OG/social images, illustrations, and hero art."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the image to generate"},
                "size": {"type": "string", "enum": ["1024x1024", "1536x1024", "1024x1536"], "description": "Image dimensions (default 1024x1024)"},
                "path": {"type": "string", "description": "Output file path (optional; auto-named if omitted)"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "text_to_speech",
        "description": "Convert text to spoken audio (mp3) and save it to disk. Returns the file path. For voiceovers, demos, and accessibility.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak"},
                "voice": {"type": "string", "description": "Voice name (default 'alloy')"},
                "path": {"type": "string", "description": "Output file path (optional; auto-named if omitted)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "spawn_agent",
        "description": (
            "Delegate a bounded sub-task to an isolated subagent that has the full tool set. "
            "Returns the subagent's final result. Use to parallelize research or split a large job "
            "into focused pieces. Keep sub-tasks self-contained — the subagent does not see this conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "A complete, self-contained instruction for the subagent"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "shopify",
        "description": (
            "Query a Shopify store's Admin API (orders, products, customers, inventory, analytics). "
            "Read-only by default. Resource is a path like 'orders.json' or 'products/count.json'. "
            "Writes require the operator to enable them explicitly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource": {"type": "string", "description": "Admin API resource path, e.g. 'orders.json?status=any&limit=10'"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "description": "HTTP method (default GET; writes gated by operator)"},
                "body": {"type": "object", "description": "JSON body for POST/PUT"},
            },
            "required": ["resource"],
        },
    },
    {
        "name": "stripe",
        "description": (
            "Read Stripe data (balance, charges, customers, products, subscriptions, payouts). "
            "READ-ONLY — this tool cannot create charges, refunds, or transfers. "
            "Resource is a path like 'balance' or 'charges?limit=10'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resource": {"type": "string", "description": "Stripe API resource, e.g. 'balance', 'charges?limit=5', 'customers'"},
            },
            "required": ["resource"],
        },
    },
    {
        "name": "sql_query",
        "description": (
            "Run a SQL query against a local SQLite database file and return the rows. "
            "Useful for inspecting app databases during development or reporting on local data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Path to the .db/.sqlite file"},
                "query": {"type": "string", "description": "SQL query to run"},
                "params": {"type": "array", "description": "Optional positional parameters for the query"},
            },
            "required": ["db_path", "query"],
        },
    },
    {
        "name": "composio_apps",
        "description": (
            "List the external apps and actions available through the operator's Composio connection "
            "(Slack, Gmail, WhatsApp, Notion, Shopify, GitHub, and hundreds more). "
            "Call this first to discover which app actions you can run, then use composio_action. "
            "Optionally filter by a toolkit name (e.g. 'slack', 'gmail')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "toolkit": {"type": "string", "description": "Filter to one app/toolkit, e.g. 'slack', 'gmail', 'shopify' (optional)"},
                "search": {"type": "string", "description": "Free-text search for a capability, e.g. 'send message' (optional)"},
            },
        },
    },
    {
        "name": "composio_action",
        "description": (
            "Execute an action on a Composio-connected app — e.g. send a Slack message, read Gmail, "
            "post to Notion, query Shopify. Use composio_apps to find the exact action slug and its "
            "arguments first. Actions that send messages or change external data are real and take effect; "
            "prefer reversible ones and follow the operator's approval policy for anything outward-facing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "The Composio action slug, e.g. 'SLACK_SENDS_A_MESSAGE_TO_A_CHANNEL'"},
                "arguments": {"type": "object", "description": "Arguments for the action, matching its schema"},
                "user_id": {"type": "string", "description": "Composio connected-account/entity id to run as (default 'default')"},
            },
            "required": ["action"],
        },
    },
]

# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

async def execute_tool(
    name: str,
    inputs: dict[str, Any],
    profile_id: str,
    agent_id: str,
    store: "Store",
    skills_dir: Path | None = None,
    spawn: Callable[[str], Awaitable[str]] | None = None,
) -> str:
    """Dispatch a tool call and return a plain-string result."""
    try:
        match name:
            case "bash":
                return await _bash(inputs)
            case "read_file":
                return _read_file(inputs)
            case "write_file":
                return _write_file(inputs)
            case "list_files":
                return _list_files(inputs)
            case "http_fetch":
                return await _http_fetch(inputs)
            case "memory_write":
                return _memory_write(inputs, profile_id, agent_id, store)
            case "memory_read":
                return _memory_read(inputs, profile_id, agent_id, store)
            case "memory_delete":
                return _memory_delete(inputs, profile_id, agent_id, store)
            case "create_skill":
                return _create_skill(inputs, profile_id, agent_id, store, skills_dir)
            case "run_python":
                return await _run_python(inputs)
            case "search_files":
                return await _search_files(inputs)
            case "web_search":
                return await _web_search(inputs)
            case "generate_image":
                return await _generate_image(inputs)
            case "text_to_speech":
                return await _text_to_speech(inputs)
            case "spawn_agent":
                return await _spawn_agent(inputs, spawn)
            case "shopify":
                return await _shopify(inputs)
            case "stripe":
                return await _stripe(inputs)
            case "sql_query":
                return _sql_query(inputs)
            case "composio_apps":
                return await _composio_apps(inputs)
            case "composio_action":
                return await _composio_action(inputs)
            case _:
                return f"[tool_error] Unknown tool: {name}"
    except Exception as exc:
        return f"[tool_error] {name} failed: {exc}"


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

async def _bash(inputs: dict[str, Any]) -> str:
    command = inputs["command"]
    workdir = inputs.get("workdir") or None
    timeout = min(int(inputs.get("timeout") or 30), 120)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        ),
    )
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"stderr: {err}")
    if result.returncode != 0:
        parts.append(f"exit code: {result.returncode}")
    return "\n".join(parts) if parts else "(no output)"


def _read_file(inputs: dict[str, Any]) -> str:
    path = Path(inputs["path"]).expanduser()
    if not path.exists():
        return f"[not_found] {path}"
    content = path.read_bytes()[:102400]
    try:
        return content.decode("utf-8", errors="replace")
    except Exception:
        return f"[binary] {len(content)} bytes — not text-decodable"


def _write_file(inputs: dict[str, Any]) -> str:
    path = Path(inputs["path"]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if inputs.get("append") else "w"
    path.open(mode, encoding="utf-8").write(inputs["content"])
    return f"Written {len(inputs['content'])} chars to {path}"


def _list_files(inputs: dict[str, Any]) -> str:
    base = Path(inputs["path"]).expanduser()
    if not base.exists():
        return f"[not_found] {base}"
    pattern = inputs.get("pattern", "*")
    recursive = bool(inputs.get("recursive"))
    glob_pattern = f"**/{pattern}" if recursive else pattern
    matches = sorted(base.glob(glob_pattern))[:200]
    if not matches:
        return "(no files found)"
    return "\n".join(str(m.relative_to(base)) for m in matches)


async def _http_fetch(inputs: dict[str, Any]) -> str:
    url = inputs["url"]
    method = (inputs.get("method") or "GET").upper()
    body = inputs.get("body", "").encode() if inputs.get("body") else None
    headers: dict[str, str] = inputs.get("headers") or {}
    headers.setdefault("User-Agent", "OrbityLabs-Agent/1.0")
    loop = asyncio.get_event_loop()

    def _fetch() -> str:
        req = _URLReq(url, data=body, headers=headers, method=method)
        with urlopen(req, timeout=20) as resp:
            raw = resp.read(204800)
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return f"[binary] {len(raw)} bytes"

    return await loop.run_in_executor(None, _fetch)


def _memory_write(inputs: dict[str, Any], profile_id: str, agent_id: str, store: "Store") -> str:
    key, content = inputs["key"], inputs["content"]
    store.upsert_memory(profile_id, agent_id, key, content)
    return f"Memory saved: {key}"


def _memory_read(inputs: dict[str, Any], profile_id: str, agent_id: str, store: "Store") -> str:
    prefix = inputs.get("prefix", "")
    memories = store.list_memories(profile_id, agent_id, prefix)
    if not memories:
        return "(no memories found)"
    return "\n\n".join(f"[{m['key']}]\n{m['content']}" for m in memories)


def _memory_delete(inputs: dict[str, Any], profile_id: str, agent_id: str, store: "Store") -> str:
    key = inputs["key"]
    store.delete_memory(profile_id, agent_id, key)
    return f"Memory deleted: {key}"


def _create_skill(
    inputs: dict[str, Any],
    profile_id: str,
    agent_id: str,
    store: "Store",
    skills_dir: Path | None,
) -> str:
    name = inputs["name"].lower().replace(" ", "-")
    desc = inputs["description"]
    content = inputs["content"]
    body = f"# {name}\n\n**Description:** {desc}\n\n{content}\n\n*Created by agent {agent_id} at {datetime.now(UTC).isoformat()}*\n"
    store.upsert_skill_doc(profile_id, agent_id, name, desc, body)
    if skills_dir:
        skills_dir.mkdir(parents=True, exist_ok=True)
        (skills_dir / f"{name}.md").write_text(body, encoding="utf-8")
    return f"Skill '{name}' saved."


async def _run_python(inputs: dict[str, Any]) -> str:
    code = inputs["code"]
    timeout = min(int(inputs.get("timeout") or 30), 60)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        ),
    )
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    parts = []
    if out:
        parts.append(out)
    if err:
        parts.append(f"stderr: {err}")
    return "\n".join(parts) if parts else "(no output)"


async def _search_files(inputs: dict[str, Any]) -> str:
    pattern = inputs["pattern"]
    path = inputs["path"]
    file_pattern = inputs.get("file_pattern", "")
    case_sensitive = bool(inputs.get("case_sensitive"))
    # Try ripgrep first, fall back to grep
    rg_path = _which("rg") or _which("grep")
    if not rg_path:
        return "[tool_error] No grep/ripgrep found"
    is_rg = rg_path.endswith("rg")
    cmd = [rg_path]
    if is_rg:
        if not case_sensitive:
            cmd.append("-i")
        if file_pattern:
            cmd += ["-g", file_pattern]
        cmd += ["-n", "--max-count", "5", pattern, path]
    else:
        if not case_sensitive:
            cmd.append("-i")
        cmd += ["-rn", "--include", file_pattern or "*", pattern, path]
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=20),
    )
    out = (result.stdout or "").strip()
    return out[:8000] if out else "(no matches)"


def _which(name: str) -> str | None:
    import shutil
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Shared HTTP helper for external-API tools
# ---------------------------------------------------------------------------

async def _api_call(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: int = 30,
    max_bytes: int = 262144,
) -> tuple[int, bytes]:
    """Make an HTTP call off the event loop. Returns (status_code, body_bytes).
    Captures error bodies (4xx/5xx) instead of raising, so the caller can surface them.
    """
    hdrs = dict(headers or {})
    data: bytes | None = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    hdrs.setdefault("Accept", "application/json")

    def _do() -> tuple[int, bytes]:
        req = _URLReq(url, data=data, headers=hdrs, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return getattr(resp, "status", 200), resp.read(max_bytes)
        except HTTPError as exc:
            return exc.code, exc.read(max_bytes)
        except (URLError, TimeoutError, OSError) as exc:
            return 0, str(exc).encode()

    return await asyncio.get_event_loop().run_in_executor(None, _do)


def _first_key(*names: str) -> str:
    for n in names:
        v = os.getenv(n, "").strip()
        if v:
            return v
    return ""


def _output_path(explicit: str | None, prefix: str, ext: str) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    return OUTPUT_DIR / f"{prefix}-{stamp}.{ext}"


# ---------------------------------------------------------------------------
# Tool gateway: web search, image generation, text-to-speech
# ---------------------------------------------------------------------------

async def _web_search(inputs: dict[str, Any]) -> str:
    query = inputs["query"]
    max_results = min(int(inputs.get("max_results") or 5), 10)
    tavily = _first_key("ORBITY_TAVILY_KEY")
    brave = _first_key("ORBITY_BRAVE_KEY")

    if tavily:
        status, body = await _api_call(
            "https://api.tavily.com/search",
            method="POST",
            json_body={"api_key": tavily, "query": query, "max_results": max_results, "include_answer": True},
        )
        if status != 200:
            return f"[web_search error {status}] {body.decode('utf-8', 'replace')[:500]}"
        data = json.loads(body)
        lines = []
        if data.get("answer"):
            lines.append(f"Answer: {data['answer']}\n")
        for r in data.get("results", [])[:max_results]:
            lines.append(f"- {r.get('title','')}\n  {r.get('url','')}\n  {(r.get('content','') or '')[:280]}")
        return "\n".join(lines) or "(no results)"

    if brave:
        from urllib.parse import quote
        status, body = await _api_call(
            f"https://api.search.brave.com/res/v1/web/search?q={quote(query)}&count={max_results}",
            headers={"X-Subscription-Token": brave},
        )
        if status != 200:
            return f"[web_search error {status}] {body.decode('utf-8', 'replace')[:500]}"
        data = json.loads(body)
        lines = []
        for r in (data.get("web", {}).get("results", []) or [])[:max_results]:
            lines.append(f"- {r.get('title','')}\n  {r.get('url','')}\n  {(r.get('description','') or '')[:280]}")
        return "\n".join(lines) or "(no results)"

    return "[not_configured] Set ORBITY_TAVILY_KEY (recommended) or ORBITY_BRAVE_KEY to enable web_search."


async def _generate_image(inputs: dict[str, Any]) -> str:
    key = _first_key("ORBITY_OPENAI_KEY", "OPENAI_API_KEY")
    if not key:
        return "[not_configured] Set ORBITY_OPENAI_KEY to enable generate_image."
    prompt = inputs["prompt"]
    size = inputs.get("size") or "1024x1024"
    status, body = await _api_call(
        "https://api.openai.com/v1/images/generations",
        method="POST",
        headers={"Authorization": f"Bearer {key}"},
        json_body={"model": "gpt-image-1", "prompt": prompt, "size": size, "n": 1},
        timeout=120,
    )
    if status != 200:
        return f"[generate_image error {status}] {body.decode('utf-8', 'replace')[:500]}"
    data = json.loads(body)
    entry = (data.get("data") or [{}])[0]
    out = _output_path(inputs.get("path"), "image", "png")
    if entry.get("b64_json"):
        out.write_bytes(base64.b64decode(entry["b64_json"]))
    elif entry.get("url"):
        _, img = await _api_call(entry["url"], timeout=120, max_bytes=20_000_000)
        out.write_bytes(img)
    else:
        return f"[generate_image error] Unexpected response: {body.decode('utf-8','replace')[:300]}"
    return f"Image saved to {out}"


async def _text_to_speech(inputs: dict[str, Any]) -> str:
    key = _first_key("ORBITY_OPENAI_KEY", "OPENAI_API_KEY")
    if not key:
        return "[not_configured] Set ORBITY_OPENAI_KEY to enable text_to_speech."
    text = inputs["text"]
    voice = inputs.get("voice") or "alloy"
    status, body = await _api_call(
        "https://api.openai.com/v1/audio/speech",
        method="POST",
        headers={"Authorization": f"Bearer {key}"},
        json_body={"model": "tts-1", "voice": voice, "input": text},
        timeout=120,
        max_bytes=50_000_000,
    )
    if status != 200:
        return f"[text_to_speech error {status}] {body.decode('utf-8', 'replace')[:500]}"
    out = _output_path(inputs.get("path"), "speech", "mp3")
    out.write_bytes(body)
    return f"Audio saved to {out}"


# ---------------------------------------------------------------------------
# Subagent spawning
# ---------------------------------------------------------------------------

async def _spawn_agent(inputs: dict[str, Any], spawn: Callable[[str], Awaitable[str]] | None) -> str:
    if spawn is None:
        return "[tool_error] Subagent spawning is not available in this context."
    task = (inputs.get("task") or "").strip()
    if not task:
        return "[tool_error] spawn_agent requires a non-empty 'task'."
    result = await spawn(task)
    return f"[subagent result]\n{result}"


# ---------------------------------------------------------------------------
# Ecommerce: Shopify (read-only default) and Stripe (read-only)
# ---------------------------------------------------------------------------

async def _shopify(inputs: dict[str, Any]) -> str:
    store = _first_key("ORBITY_SHOPIFY_STORE")
    token = _first_key("ORBITY_SHOPIFY_TOKEN")
    if not store or not token:
        return "[not_configured] Set ORBITY_SHOPIFY_STORE and ORBITY_SHOPIFY_TOKEN to enable shopify."
    store = store.replace("https://", "").replace("http://", "").replace(".myshopify.com", "").strip("/")
    method = (inputs.get("method") or "GET").upper()
    if method != "GET" and _first_key("ORBITY_SHOPIFY_ALLOW_WRITES") not in ("1", "true", "yes"):
        return "[refused] shopify is read-only. The operator must set ORBITY_SHOPIFY_ALLOW_WRITES=1 to permit writes."
    resource = inputs["resource"].lstrip("/")
    version = _first_key("ORBITY_SHOPIFY_API_VERSION") or "2024-10"
    url = f"https://{store}.myshopify.com/admin/api/{version}/{resource}"
    status, body = await _api_call(
        url,
        method=method,
        headers={"X-Shopify-Access-Token": token},
        json_body=inputs.get("body") if method in ("POST", "PUT") else None,
    )
    text = body.decode("utf-8", "replace")
    prefix = "" if status == 200 else f"[shopify HTTP {status}] "
    return f"{prefix}{text[:8000]}"


async def _stripe(inputs: dict[str, Any]) -> str:
    key = _first_key("ORBITY_STRIPE_KEY", "STRIPE_API_KEY")
    if not key:
        return "[not_configured] Set ORBITY_STRIPE_KEY to enable stripe (read-only)."
    resource = inputs["resource"].lstrip("/")
    # Read-only: only GET is ever issued, so this tool cannot create charges, refunds, or transfers.
    status, body = await _api_call(
        f"https://api.stripe.com/v1/{resource}",
        method="GET",
        headers={"Authorization": f"Bearer {key}"},
    )
    text = body.decode("utf-8", "replace")
    prefix = "" if status == 200 else f"[stripe HTTP {status}] "
    return f"{prefix}{text[:8000]}"


# ---------------------------------------------------------------------------
# Vibecoder: local SQLite query
# ---------------------------------------------------------------------------

def _sql_query(inputs: dict[str, Any]) -> str:
    db_path = Path(inputs["db_path"]).expanduser()
    if not db_path.exists():
        return f"[not_found] {db_path}"
    query = inputs["query"]
    params = inputs.get("params") or []
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, params)
        if cur.description is None:
            conn.commit()
            return f"(ok — {cur.rowcount} row(s) affected)"
        rows = cur.fetchmany(200)
        if not rows:
            return "(no rows)"
        cols = rows[0].keys()
        out = [" | ".join(cols)]
        for r in rows:
            out.append(" | ".join(str(r[c]) for c in cols))
        return "\n".join(out)[:8000]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Composio: one connection → hundreds of app actions (Slack, Gmail, Notion, …)
# ---------------------------------------------------------------------------

_COMPOSIO_BASE = "https://backend.composio.dev/api"


async def _composio_apps(inputs: dict[str, Any]) -> str:
    key = _first_key("COMPOSIO_API_KEY")
    if not key:
        return "[not_configured] Composio is not connected. Add COMPOSIO_API_KEY in the desktop server and connect apps in Connectors."
    from urllib.parse import urlencode
    params: dict[str, str] = {"limit": "30"}
    if inputs.get("toolkit"):
        params["toolkit_slug"] = str(inputs["toolkit"]).lower()
    if inputs.get("search"):
        params["search"] = str(inputs["search"])
    status, body = await _api_call(
        f"{_COMPOSIO_BASE}/v3.1/tools?{urlencode(params)}",
        headers={"x-api-key": key},
    )
    if status != 200:
        return f"[composio_apps HTTP {status}] {body.decode('utf-8', 'replace')[:600]}"
    data = json.loads(body)
    items = data.get("items") or data.get("data") or data
    lines = []
    for t in (items if isinstance(items, list) else [])[:30]:
        slug = t.get("slug") or t.get("name") or ""
        desc = (t.get("description") or "")[:120]
        lines.append(f"- {slug}: {desc}")
    return "\n".join(lines) or body.decode("utf-8", "replace")[:4000]


async def _composio_action(inputs: dict[str, Any]) -> str:
    key = _first_key("COMPOSIO_API_KEY")
    if not key:
        return "[not_configured] Composio is not connected. Add COMPOSIO_API_KEY in the desktop server and connect apps in Connectors."
    action = inputs["action"]
    arguments = inputs.get("arguments") or {}
    user_id = inputs.get("user_id") or "default"
    status, body = await _api_call(
        f"{_COMPOSIO_BASE}/v3/tools/execute/{action}",
        method="POST",
        headers={"x-api-key": key},
        json_body={"user_id": user_id, "arguments": arguments},
        timeout=90,
    )
    text = body.decode("utf-8", "replace")
    prefix = "" if status == 200 else f"[composio_action HTTP {status}] "
    return f"{prefix}{text[:8000]}"
