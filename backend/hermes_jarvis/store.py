"""Durable, profile-isolated local storage for OrbityLabs.

Every read/write is scoped by profile_id at the query level so that no code
path can silently return or mutate another profile's data. This is the
server-enforced boundary described in RUNTIME_PARITY.md.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '',
    vault_path TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    initials TEXT NOT NULL DEFAULT '',
    output_path TEXT NOT NULL DEFAULT '',
    mirror_to_vault INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, id)
);

CREATE TABLE IF NOT EXISTS agent_loops (
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    interval_seconds INTEGER NOT NULL DEFAULT 300,
    last_started_at TEXT,
    last_run_id TEXT,
    last_error TEXT,
    PRIMARY KEY (profile_id, agent_id),
    FOREIGN KEY (profile_id, agent_id) REFERENCES agents(profile_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paired_devices (
    id TEXT PRIMARY KEY,
    secret_hash TEXT NOT NULL UNIQUE,
    device_name TEXT NOT NULL,
    paired_at TEXT NOT NULL,
    last_seen_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, id)
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, id)
);

CREATE TABLE IF NOT EXISTS policy (
    profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    autonomy TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS model_routes (
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (profile_id, agent_id)
);

CREATE TABLE IF NOT EXISTS skill_sources (
    id TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    repository TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, id),
    UNIQUE (profile_id, repository)
);

CREATE TABLE IF NOT EXISTS agent_skill_sources (
    profile_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    PRIMARY KEY (profile_id, agent_id, skill_id),
    FOREIGN KEY (profile_id, agent_id) REFERENCES agents(profile_id, id) ON DELETE CASCADE,
    FOREIGN KEY (profile_id, skill_id) REFERENCES skill_sources(profile_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_profile ON events(profile_id, id);
"""


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class ProfileNotFound(LookupError):
    """Raised when a request targets a profile_id that does not exist."""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Apply additive migrations for existing local installations."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
        if "output_path" not in columns:
            conn.execute("ALTER TABLE agents ADD COLUMN output_path TEXT NOT NULL DEFAULT ''")
        if "mirror_to_vault" not in columns:
            conn.execute("ALTER TABLE agents ADD COLUMN mirror_to_vault INTEGER NOT NULL DEFAULT 1")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _require_profile(self, conn: sqlite3.Connection, profile_id: str) -> None:
        row = conn.execute("SELECT 1 FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise ProfileNotFound(profile_id)

    def _ensure_default_skills(self, conn: sqlite3.Connection, profile_id: str) -> None:
        defaults = (
            ("steel-browser", "Steel Browser", "https://github.com/steel-dev/steel-browser", "Browser automation infrastructure for agent-run web work."),
            ("agenticmail", "AgenticMail", "https://github.com/agenticmail/agenticmail", "Email, SMS, and phone-call infrastructure for agents."),
        )
        for skill_id, name, repository, description in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO skill_sources (id, profile_id, name, repository, description, is_default, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (skill_id, profile_id, name, repository, description, now()),
            )

    # -- profiles ---------------------------------------------------------
    def list_profiles(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY created_at").fetchall()
            return [dict(row) for row in rows]

    def get_profile(self, profile_id: str) -> dict[str, Any]:
        """Return exactly one profile for profile-scoped local integrations."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            if row is None:
                raise ProfileNotFound(profile_id)
            return dict(row)

    def create_profile(self, id: str, name: str, kind: str, context: str, vault_path: str) -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO profiles (id, name, kind, context, vault_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (id, name, kind, context, vault_path, created_at),
            )
            conn.execute("INSERT OR IGNORE INTO policy (profile_id, autonomy) VALUES (?, 'manual')", (id,))
            self._ensure_default_skills(conn, id)
        return {"id": id, "name": name, "kind": kind, "context": context, "vault_path": vault_path, "created_at": created_at}

    def delete_profile(self, profile_id: str) -> None:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

    # -- agents -------------------------------------------------------------
    def list_agents(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT * FROM agents WHERE profile_id = ? ORDER BY created_at", (profile_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def create_agent(self, profile_id: str, id: str, name: str, role: str, initials: str, output_path: str = "", mirror_to_vault: bool = True, loop_enabled: bool = True, loop_interval_seconds: int = 300) -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO agents (id, profile_id, name, role, initials, output_path, mirror_to_vault, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (id, profile_id, name, role, initials, output_path, int(mirror_to_vault), created_at),
            )
            self._ensure_default_skills(conn, profile_id)
            conn.execute(
                "INSERT OR IGNORE INTO agent_skill_sources (profile_id, agent_id, skill_id) SELECT ?, ?, id FROM skill_sources WHERE profile_id = ? AND is_default = 1",
                (profile_id, id, profile_id),
            )
            conn.execute(
                "INSERT INTO agent_loops (profile_id, agent_id, enabled, interval_seconds) VALUES (?, ?, ?, ?)",
                (profile_id, id, int(loop_enabled), loop_interval_seconds),
            )
        return {"id": id, "profile_id": profile_id, "name": name, "role": role, "initials": initials, "output_path": output_path, "mirror_to_vault": mirror_to_vault, "created_at": created_at}

    def agent_loop_candidates(self) -> list[dict[str, Any]]:
        """Return enabled loops. The scheduler, not this storage method, owns timing."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT l.*, a.name, a.role, a.output_path, a.mirror_to_vault, p.name AS profile_name, p.context, p.vault_path "
                "FROM agent_loops l JOIN agents a ON a.profile_id = l.profile_id AND a.id = l.agent_id "
                "JOIN profiles p ON p.id = l.profile_id WHERE l.enabled = 1"
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_agent_loop(self, profile_id: str, agent_id: str, *, run_id: str = "", error: str = "") -> None:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "UPDATE agent_loops SET last_started_at = ?, last_run_id = ?, last_error = ? WHERE profile_id = ? AND agent_id = ?",
                (now(), run_id or None, error or None, profile_id, agent_id),
            )

    def mobile_manifest(self) -> list[dict[str, Any]]:
        """Return the non-secret host state sent to a paired mobile remote."""
        with self._connect() as conn:
            profiles = [dict(row) for row in conn.execute("SELECT id, name, kind, context FROM profiles ORDER BY created_at").fetchall()]
            for profile in profiles:
                agents = conn.execute("SELECT id, name, role, initials FROM agents WHERE profile_id = ? ORDER BY created_at", (profile["id"],)).fetchall()
                profile["agents"] = [dict(agent) for agent in agents]
            return profiles

    def register_paired_device(self, device_id: str, secret_hash: str, device_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO paired_devices (id, secret_hash, device_name, paired_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
                (device_id, secret_hash, device_name, now(), now()),
            )

    def verify_paired_device(self, secret_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM paired_devices WHERE secret_hash = ?", (secret_hash,)).fetchone()
            if row is None:
                return False
            conn.execute("UPDATE paired_devices SET last_seen_at = ? WHERE id = ?", (now(), row["id"]))
            return True

    # -- profile skills ------------------------------------------------------
    def list_skills(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            self._ensure_default_skills(conn, profile_id)
            rows = conn.execute(
                "SELECT id, name, repository, description, is_default, created_at FROM skill_sources WHERE profile_id = ? ORDER BY is_default DESC, created_at",
                (profile_id,),
            ).fetchall()
            return [{**dict(row), "default": bool(row["is_default"]), "status": "source"} for row in rows]

    def create_skill(self, profile_id: str, id: str, name: str, repository: str, description: str) -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO skill_sources (id, profile_id, name, repository, description, is_default, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (id, profile_id, name, repository, description, created_at),
            )
        return {"id": id, "name": name, "repository": repository, "description": description, "default": False, "status": "source", "created_at": created_at}

    def list_agent_skills(self, profile_id: str) -> dict[str, list[str]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            self._ensure_default_skills(conn, profile_id)
            conn.execute(
                "INSERT OR IGNORE INTO agent_skill_sources (profile_id, agent_id, skill_id) SELECT a.profile_id, a.id, s.id FROM agents a JOIN skill_sources s ON s.profile_id = a.profile_id AND s.is_default = 1 WHERE a.profile_id = ?",
                (profile_id,),
            )
            rows = conn.execute(
                "SELECT agent_id, skill_id FROM agent_skill_sources WHERE profile_id = ?", (profile_id,)
            ).fetchall()
            result: dict[str, list[str]] = {}
            for row in rows:
                result.setdefault(row["agent_id"], []).append(row["skill_id"])
            return result

    # -- tasks ----------------------------------------------------------------
    def list_tasks(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT * FROM tasks WHERE profile_id = ? ORDER BY created_at", (profile_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def create_task(self, profile_id: str, id: str, title: str, area: str, state: str) -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO tasks (id, profile_id, title, area, state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (id, profile_id, title, area, state, created_at),
            )
        return {"id": id, "profile_id": profile_id, "title": title, "area": area, "state": state, "created_at": created_at}

    def update_task(self, profile_id: str, task_id: str, state: str) -> None:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            cursor = conn.execute(
                "UPDATE tasks SET state = ? WHERE profile_id = ? AND id = ?", (state, profile_id, task_id)
            )
            if cursor.rowcount == 0:
                raise LookupError(task_id)

    def delete_task(self, profile_id: str, task_id: str) -> None:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute("DELETE FROM tasks WHERE profile_id = ? AND id = ?", (profile_id, task_id))

    # -- sources --------------------------------------------------------------
    def list_sources(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT * FROM sources WHERE profile_id = ? ORDER BY created_at", (profile_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def create_source(self, profile_id: str, id: str, title: str, detail: str) -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO sources (id, profile_id, title, detail, created_at) VALUES (?, ?, ?, ?, ?)",
                (id, profile_id, title, detail, created_at),
            )
        return {"id": id, "profile_id": profile_id, "title": title, "detail": detail, "created_at": created_at}

    # -- policy -----------------------------------------------------------------
    def get_policy(self, profile_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            row = conn.execute("SELECT autonomy FROM policy WHERE profile_id = ?", (profile_id,)).fetchone()
            return {"profile_id": profile_id, "autonomy": row["autonomy"] if row else "manual"}

    def set_policy(self, profile_id: str, autonomy: str) -> dict[str, Any]:
        if autonomy not in ("manual", "auto_safe"):
            raise ValueError("autonomy must be 'manual' or 'auto_safe'")
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO policy (profile_id, autonomy) VALUES (?, ?) "
                "ON CONFLICT(profile_id) DO UPDATE SET autonomy = excluded.autonomy",
                (profile_id, autonomy),
            )
        return {"profile_id": profile_id, "autonomy": autonomy}

    # -- model routes -------------------------------------------------------------
    def list_model_routes(self, profile_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT agent_id, provider, model FROM model_routes WHERE profile_id = ?", (profile_id,)
            ).fetchall()
            return {row["agent_id"] or "default": {"provider": row["provider"], "model": row["model"]} for row in rows}

    def set_model_route(self, profile_id: str, agent_id: str, provider: str, model: str) -> dict[str, Any]:
        key = agent_id or ""
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO model_routes (profile_id, agent_id, provider, model) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(profile_id, agent_id) DO UPDATE SET provider = excluded.provider, model = excluded.model",
                (profile_id, key, provider, model),
            )
        return {"agent_id": agent_id, "provider": provider, "model": model}

    # -- events (profile-scoped runtime journal) ------------------------------------
    def record_event(self, profile_id: str | None, type_: str, data: dict[str, Any]) -> None:
        with self._connect() as conn:
            if profile_id:
                self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO events (profile_id, type, data, at) VALUES (?, ?, ?, ?)",
                (profile_id, type_, json.dumps(data), now()),
            )

    def list_events(self, profile_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT type, data, at FROM events WHERE profile_id = ? ORDER BY id DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
            return [{"type": row["type"], "data": json.loads(row["data"]), "at": row["at"]} for row in rows]

    # -- global federated view (explicit provenance, read-only) ----------------------
    def global_context(self) -> list[dict[str, Any]]:
        """Every profile's summary for the federated assistant. Each item retains its profile_id."""
        with self._connect() as conn:
            profiles = conn.execute("SELECT * FROM profiles ORDER BY created_at").fetchall()
            result = []
            for profile in profiles:
                profile_id = profile["id"]
                agents = conn.execute(
                    "SELECT name, role FROM agents WHERE profile_id = ?", (profile_id,)
                ).fetchall()
                sources = conn.execute(
                    "SELECT title FROM sources WHERE profile_id = ?", (profile_id,)
                ).fetchall()
                result.append(
                    {
                        "profile_id": profile_id,
                        "name": profile["name"],
                        "kind": profile["kind"],
                        "context": profile["context"],
                        "vault_path": profile["vault_path"],
                        "agents": [{"name": a["name"], "role": a["role"]} for a in agents],
                        "sources": [s["title"] for s in sources],
                    }
                )
            return result
