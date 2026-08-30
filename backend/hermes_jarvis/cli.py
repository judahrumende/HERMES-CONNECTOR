"""hermes — OrbityLabs terminal command.

Usage:
  hermes run "do this task"          Run a task through the local agent runtime
  hermes chat                        Start an interactive chat session
  hermes configure                   Set API key, model, and provider
  hermes doctor                      Check backend status
  hermes memory list                 List agent memories
  hermes memory set <key> <value>    Write a memory entry
  hermes memory delete <key>         Delete a memory entry
  hermes skills                      List agent-created skills

Environment respected:
  ORBITY_RUNTIME_URL  (default: http://127.0.0.1:8787)
  ORBITY_PROFILE_ID   (default: first profile found)
  ORBITY_AGENT_ID     (default: empty — profile-level)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


RUNTIME_URL = os.getenv("ORBITY_RUNTIME_URL", "http://127.0.0.1:8787").rstrip("/")
DEFAULT_PROFILE = os.getenv("ORBITY_PROFILE_ID", "")
DEFAULT_AGENT = os.getenv("ORBITY_AGENT_ID", "")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict[str, str] | None = None) -> Any:
    url = f"{RUNTIME_URL}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _post(path: str, body: dict[str, Any]) -> Any:
    data = json.dumps(body).encode()
    req = Request(
        f"{RUNTIME_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def _delete(path: str) -> Any:
    req = Request(f"{RUNTIME_URL}{path}", headers={"Accept": "application/json"}, method="DELETE")
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _put(path: str, body: dict[str, Any]) -> Any:
    data = json.dumps(body).encode()
    req = Request(
        f"{RUNTIME_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="PUT",
    )
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------

def _resolve_profile(profile_id: str) -> str:
    if profile_id:
        return profile_id
    try:
        profiles = _get("/api/profiles")
        if profiles:
            return profiles[0]["id"]
    except Exception:
        pass
    print("No profile found. Create one in the OrbityLabs app first.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> None:
    profile_id = _resolve_profile(args.profile or DEFAULT_PROFILE)
    task = " ".join(args.task)
    if not task:
        print("Provide a task string after 'run'.", file=sys.stderr)
        sys.exit(1)
    print(f"Running: {task!r}")
    try:
        result = _post("/api/runs", {
            "payload": {
                "input": task,
                "session_id": f"cli:{profile_id}:{args.session or 'default'}",
                "metadata": {
                    "profile_id": profile_id,
                    "agent_id": args.agent or DEFAULT_AGENT,
                    "mode": "chat",
                    "source": "cli",
                },
            }
        })
        output = result.get("output") or result.get("error") or json.dumps(result)
        print(output)
    except (HTTPError, URLError, OSError) as exc:
        print(f"Runtime error: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_chat(args: argparse.Namespace) -> None:
    profile_id = _resolve_profile(args.profile or DEFAULT_PROFILE)
    agent_id = args.agent or DEFAULT_AGENT
    session_id = f"cli:{profile_id}:{agent_id or 'chat'}"
    print(f"OrbityLabs chat (profile={profile_id}). Type 'exit' to quit.\n")
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit", "q"}:
            break
        try:
            result = _post("/api/runs", {
                "payload": {
                    "input": text,
                    "session_id": session_id,
                    "metadata": {
                        "profile_id": profile_id,
                        "agent_id": agent_id,
                        "mode": "chat",
                        "source": "cli",
                    },
                }
            })
            output = result.get("output") or result.get("error") or "(no response)"
            print(f"\nAgent> {output}\n")
        except (HTTPError, URLError, OSError) as exc:
            print(f"[error] {exc}")


def cmd_doctor(_args: argparse.Namespace) -> None:
    try:
        health = _get("/api/health")
        snap = _get("/api/hermes/connection")
        print(f"Backend  : ok ({RUNTIME_URL})")
        print(f"Mode     : {snap.get('mode', 'unknown')}")
        print(f"Status   : {snap.get('status', 'unknown')}")
        provider = snap.get("provider") or snap.get("model")
        if provider:
            print(f"Provider : {snap.get('provider')} / {snap.get('model')}")
        err = snap.get("error")
        if err:
            print(f"Error    : {err}")
    except (HTTPError, URLError, OSError) as exc:
        print(f"Backend unreachable: {exc}", file=sys.stderr)
        print(f"Start the OrbityLabs backend: npm run server", file=sys.stderr)
        sys.exit(1)


def cmd_configure(_args: argparse.Namespace) -> None:
    import getpass
    import stat

    print("OrbityLabs runtime configuration")
    provider = input("Provider [anthropic]: ").strip() or "anthropic"
    model = input("Model [claude-opus-4-5]: ").strip() or "claude-opus-4-5"
    api_key = getpass.getpass("API key (hidden): ").strip()
    if not api_key:
        print("API key cannot be empty.", file=sys.stderr)
        sys.exit(1)

    # Write to local config file
    if sys.platform == "darwin":
        cfg = Path.home() / "Library" / "Application Support" / "OrbityLabs" / ".env"
    elif os.name == "nt":
        cfg = Path(os.getenv("APPDATA", Path.home())) / "OrbityLabs" / ".env"
    else:
        cfg = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "OrbityLabs" / ".env"

    cfg.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# OrbityLabs runtime configuration — keep this file private",
        f"ORBITY_PROVIDER={provider}",
        f"ORBITY_MODEL={model}",
        f"ORBITY_API_KEY={api_key}",
    ]
    tmp = cfg.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    try:
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    tmp.replace(cfg)
    print(f"Saved to {cfg}")

    # Also push to running backend if available
    try:
        _put("/api/runtime/config", {"provider": provider, "model": model, "api_key": api_key, "base_url": ""})
        print("Runtime updated.")
    except Exception:
        print("(Backend not running — restart it to pick up the new key.)")


def cmd_memory(args: argparse.Namespace) -> None:
    profile_id = _resolve_profile(args.profile or DEFAULT_PROFILE)
    agent_id = args.agent or DEFAULT_AGENT
    base = f"/api/profiles/{profile_id}/agents/{agent_id}/memories"

    if args.memory_cmd == "list":
        try:
            items = _get(base)
            if not items:
                print("(no memories)")
                return
            for m in items:
                print(f"[{m['key']}] {m['content']}")
        except (HTTPError, URLError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.memory_cmd == "set":
        if not args.key or not args.value:
            print("Usage: hermes memory set <key> <value>", file=sys.stderr)
            sys.exit(1)
        try:
            _put(base, {"key": args.key, "content": " ".join(args.value)})
            print(f"Memory set: {args.key!r}")
        except (HTTPError, URLError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.memory_cmd == "delete":
        if not args.key:
            print("Usage: hermes memory delete <key>", file=sys.stderr)
            sys.exit(1)
        try:
            _delete(f"{base}/{args.key}")
            print(f"Memory deleted: {args.key!r}")
        except (HTTPError, URLError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)


def cmd_skills(args: argparse.Namespace) -> None:
    profile_id = _resolve_profile(args.profile or DEFAULT_PROFILE)
    try:
        items = _get(f"/api/profiles/{profile_id}/skill-docs")
        if not items:
            print("(no agent-created skills)")
            return
        for s in items:
            print(f"  {s['name']}  —  {s.get('description', '')}")
            print(f"    agent: {s.get('agent_id', 'unknown')}  updated: {s.get('updated_at', '')}")
    except (HTTPError, URLError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="hermes",
        description="OrbityLabs agent OS — terminal interface",
    )
    parser.add_argument("--profile", default="", help="Profile ID (or set ORBITY_PROFILE_ID)")
    parser.add_argument("--agent", default="", help="Agent ID (or set ORBITY_AGENT_ID)")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run a task through the agent runtime")
    p_run.add_argument("task", nargs="+", help="Task description")
    p_run.add_argument("--session", default="", help="Session ID for conversation continuity")

    sub.add_parser("chat", help="Interactive chat session")

    sub.add_parser("doctor", help="Check backend status")

    sub.add_parser("configure", help="Set API key, model, and provider")

    p_mem = sub.add_parser("memory", help="Manage agent memories")
    mem_sub = p_mem.add_subparsers(dest="memory_cmd")
    mem_sub.add_parser("list", help="List all memories")
    p_set = mem_sub.add_parser("set", help="Write a memory entry")
    p_set.add_argument("key", help="Memory key")
    p_set.add_argument("value", nargs="+", help="Memory content")
    p_del = mem_sub.add_parser("delete", help="Delete a memory entry")
    p_del.add_argument("key", help="Memory key to delete")

    sub.add_parser("skills", help="List agent-created skills")

    args = parser.parse_args()

    match args.command:
        case "run":
            cmd_run(args)
        case "chat":
            cmd_chat(args)
        case "doctor":
            cmd_doctor(args)
        case "configure":
            cmd_configure(args)
        case "memory":
            cmd_memory(args)
        case "skills":
            cmd_skills(args)
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
