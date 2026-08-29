#!/usr/bin/env python3
"""Configure Hermes Jarvis with one safe terminal command.

The API key is read from a hidden prompt or HERMES_API_KEY, verified against the
gateway, then stored only in the local app configuration file with owner-only
permissions when the platform supports them.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse


def default_config_file() -> Path:
    override = os.getenv("HERMES_JARVIS_CONFIG_FILE")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home())) / "OrbityLabs" / ".env"
    if os.getenv("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "OrbityLabs" / ".env"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OrbityLabs" / ".env"
    return Path.home() / ".config" / "OrbityLabs" / ".env"


def valid_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("Hermes URL must be an absolute http(s) URL")
    return value.rstrip("/")


def verify(url: str, api_key: str | None) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(f"{url}/health/detailed", headers=headers, method="GET")
    try:
        with urlopen(request, timeout=12) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else {}
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("Hermes rejected the API key. Nothing was saved.") from exc
        raise RuntimeError(f"Hermes returned HTTP {exc.code}. Nothing was saved.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Hermes could not be verified at that URL. Nothing was saved.") from exc


def write_config(path: Path, url: str, api_key: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        "# Managed by `npm run hermes:connect`. Keep this file private.",
        f"HERMES_API_URL={url}",
    ]
    if api_key:
        payload.append(f"HERMES_API_KEY={api_key}")
    temp = path.with_suffix(".tmp")
    temp.write_text("\n".join(payload) + "\n")
    try:
        temp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect Hermes Jarvis to a Hermes gateway")
    parser.add_argument("url", type=valid_url, help="Gateway base URL, e.g. http://127.0.0.1:8642")
    parser.add_argument("--no-key", action="store_true", help="Use only for a gateway that does not require bearer authentication")
    parser.add_argument("--config", type=Path, default=default_config_file(), help="Override the local private configuration file")
    args = parser.parse_args()
    key = None if args.no_key else os.getenv("HERMES_API_KEY") or getpass.getpass("Hermes API key (input hidden): ").strip()
    if not args.no_key and not key:
        parser.error("an API key is required unless --no-key is explicitly used")
    try:
        verify(args.url, key)
        write_config(args.config, args.url, key)
    except RuntimeError as exc:
        print(f"Connection not saved: {exc}", file=sys.stderr)
        return 1
    print(f"Hermes verified and saved to {args.config}")
    print("Restart Hermes Jarvis or open the desktop app to use the verified connection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
