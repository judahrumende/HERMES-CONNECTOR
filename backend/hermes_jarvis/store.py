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

CREATE TABLE IF NOT EXISTS skill_drafts (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    request TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS messages (
    id TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT '',
    direction TEXT NOT NULL DEFAULT 'outgoing',
    text TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL,
    PRIMARY KEY (profile_id, id)
);
CREATE INDEX IF NOT EXISTS idx_messages_agent ON messages(profile_id, agent_id, at);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'run',
    summary TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'pending',
    decided_at TEXT,
    run_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_approvals_profile ON approvals(profile_id, state, created_at);

CREATE TABLE IF NOT EXISTS tool_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT REFERENCES profiles(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL,
    input TEXT NOT NULL DEFAULT '{}',
    output TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'ok',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_events_profile ON tool_events(profile_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_tool_events_run ON tool_events(run_id, id);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    input_preview TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_profile ON runs(profile_id, started_at DESC);

CREATE TABLE IF NOT EXISTS scheduled_directives (
    id TEXT NOT NULL,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT '',
    directive TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 3600,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_run_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, id)
);
CREATE INDEX IF NOT EXISTS idx_directives_profile ON scheduled_directives(profile_id, enabled);

CREATE TABLE IF NOT EXISTS memories (
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT '',
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, agent_id, key)
);

CREATE TABLE IF NOT EXISTS sessions (
    profile_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    messages_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, session_id)
);

CREATE TABLE IF NOT EXISTS skill_docs (
    profile_id TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (profile_id, name)
);
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
        agent_cols = {row["name"] for row in conn.execute("PRAGMA table_info(agents)").fetchall()}
        if "output_path" not in agent_cols:
            conn.execute("ALTER TABLE agents ADD COLUMN output_path TEXT NOT NULL DEFAULT ''")
        if "mirror_to_vault" not in agent_cols:
            conn.execute("ALTER TABLE agents ADD COLUMN mirror_to_vault INTEGER NOT NULL DEFAULT 1")
        if "notes" not in agent_cols:
            conn.execute("ALTER TABLE agents ADD COLUMN notes TEXT NOT NULL DEFAULT ''")

        skill_cols = {row["name"] for row in conn.execute("PRAGMA table_info(skill_sources)").fetchall()}
        if "installed" not in skill_cols:
            conn.execute("ALTER TABLE skill_sources ADD COLUMN installed INTEGER NOT NULL DEFAULT 0")
        if "installed_at" not in skill_cols:
            conn.execute("ALTER TABLE skill_sources ADD COLUMN installed_at TEXT")
        if "version" not in skill_cols:
            conn.execute("ALTER TABLE skill_sources ADD COLUMN version TEXT NOT NULL DEFAULT ''")
        if "sha" not in skill_cols:
            conn.execute("ALTER TABLE skill_sources ADD COLUMN sha TEXT NOT NULL DEFAULT ''")

        approval_cols = {row["name"] for row in conn.execute("PRAGMA table_info(approvals)").fetchall()} if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='approvals'").fetchone() else set()
        if "run_id" not in approval_cols and approval_cols:
            conn.execute("ALTER TABLE approvals ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")

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

    def get_agent_notes(self, profile_id: str, agent_id: str) -> str:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            row = conn.execute(
                "SELECT notes FROM agents WHERE profile_id = ? AND id = ?", (profile_id, agent_id)
            ).fetchone()
            return row["notes"] if row else ""

    def set_agent_notes(self, profile_id: str, agent_id: str, notes: str) -> None:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "UPDATE agents SET notes = ? WHERE profile_id = ? AND id = ?",
                (notes, profile_id, agent_id),
            )

    def agent_loop_candidates(self) -> list[dict[str, Any]]:
        """Return enabled loops. The scheduler, not this storage method, owns timing."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT l.*, a.name, a.role, a.output_path, a.mirror_to_vault, a.notes, p.name AS profile_name, p.context, p.vault_path "
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
                "SELECT id, name, repository, description, is_default, installed, installed_at, version, sha, created_at FROM skill_sources WHERE profile_id = ? ORDER BY is_default DESC, created_at",
                (profile_id,),
            ).fetchall()
            return [{**dict(row), "default": bool(row["is_default"]), "status": "installed" if row["installed"] else "source"} for row in rows]

    def match_skills(self, profile_id: str, request: str, limit: int = 6) -> list[dict[str, Any]]:
        """Rank profile skill sources using transparent token overlap, never hidden capability claims."""
        query = {part.lower() for part in request.split() if len(part) >= 3}
        skills = self.list_skills(profile_id)
        scored: list[tuple[int, dict[str, Any]]] = []
        for skill in skills:
            text = f"{skill['name']} {skill['description']} {skill['repository']}".lower()
            score = sum(1 for token in query if token in text)
            if score:
                scored.append((score, skill))
        return [skill for _, skill in sorted(scored, key=lambda row: (-row[0], row[1]["name"]))[:limit]]

    def create_skill_draft(self, profile_id: str, agent_id: str, request: str, run_id: str = "") -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            exists = conn.execute("SELECT 1 FROM agents WHERE profile_id = ? AND id = ?", (profile_id, agent_id)).fetchone()
            if exists is None:
                raise LookupError(agent_id)
            draft_id = f"draft-{created_at}-{agent_id}".replace(":", "-")
            conn.execute("INSERT INTO skill_drafts (id, profile_id, agent_id, request, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?)", (draft_id, profile_id, agent_id, request, run_id or None, created_at))
            return {"id": draft_id, "profile_id": profile_id, "agent_id": agent_id, "request": request, "run_id": run_id or None, "created_at": created_at, "status": "requested"}

    def list_agent_loops(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT l.*, a.name, a.role, a.initials FROM agent_loops l JOIN agents a ON a.profile_id = l.profile_id AND a.id = l.agent_id WHERE l.profile_id = ? ORDER BY a.created_at",
                (profile_id,),
            ).fetchall()
            return [{**dict(row), "enabled": bool(row["enabled"])} for row in rows]

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

    # -- skill install state -------------------------------------------------------
    def install_skill(self, profile_id: str, skill_id: str, version: str = "", sha: str = "") -> dict[str, Any]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "UPDATE skill_sources SET installed = 1, installed_at = ?, version = ?, sha = ? WHERE profile_id = ? AND id = ?",
                (now(), version, sha, profile_id, skill_id),
            )
            row = conn.execute("SELECT * FROM skill_sources WHERE profile_id = ? AND id = ?", (profile_id, skill_id)).fetchone()
            if row is None:
                raise LookupError(skill_id)
            return {**dict(row), "default": bool(row["is_default"]), "status": "installed" if row["installed"] else "source"}

    def uninstall_skill(self, profile_id: str, skill_id: str) -> None:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "UPDATE skill_sources SET installed = 0, installed_at = NULL WHERE profile_id = ? AND id = ?",
                (profile_id, skill_id),
            )

    # -- messages -----------------------------------------------------------------
    def save_message(self, profile_id: str, id: str, agent_id: str, direction: str, text: str, run_id: str = "") -> dict[str, Any]:
        at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO messages (id, profile_id, agent_id, direction, text, run_id, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id, profile_id, agent_id, direction, text, run_id, at),
            )
        return {"id": id, "profile_id": profile_id, "agent_id": agent_id, "direction": direction, "text": text, "run_id": run_id, "at": at}

    def list_messages(self, profile_id: str, agent_id: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT * FROM messages WHERE profile_id = ? AND agent_id = ? ORDER BY at LIMIT ?",
                (profile_id, agent_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def search_messages(self, profile_id: str, query: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT * FROM messages WHERE profile_id = ? AND text LIKE ? ORDER BY at DESC LIMIT ?",
                (profile_id, f"%{query}%", limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def message_previews(self, profile_id: str) -> list[dict[str, Any]]:
        """Last message per agent for conversation list."""
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT agent_id, text, direction, at FROM messages WHERE profile_id = ? AND id IN (SELECT id FROM messages WHERE profile_id = ? GROUP BY agent_id HAVING at = MAX(at)) ORDER BY at DESC",
                (profile_id, profile_id),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- approvals ----------------------------------------------------------------
    def create_approval(self, profile_id: str, id: str, agent_id: str, session_id: str, kind: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
        created_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO approvals (id, profile_id, agent_id, session_id, kind, summary, payload, state, run_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)",
                (id, profile_id, agent_id, session_id, kind, summary, json.dumps(payload), created_at),
            )
        return {"id": id, "profile_id": profile_id, "agent_id": agent_id, "session_id": session_id, "kind": kind, "summary": summary, "payload": payload, "state": "pending", "run_id": "", "decided_at": None, "created_at": created_at}

    def list_approvals(self, profile_id: str, state: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            if state:
                rows = conn.execute("SELECT * FROM approvals WHERE profile_id = ? AND state = ? ORDER BY created_at DESC", (profile_id, state)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM approvals WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                try:
                    item["payload"] = json.loads(item["payload"])
                except (ValueError, TypeError):
                    item["payload"] = {}
                result.append(item)
            return result

    def decide_approval(self, profile_id: str, approval_id: str, state: str, run_id: str = "") -> dict[str, Any]:
        if state not in ("approved", "denied"):
            raise ValueError("state must be 'approved' or 'denied'")
        decided_at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            cursor = conn.execute(
                "UPDATE approvals SET state = ?, decided_at = ?, run_id = ? WHERE id = ? AND profile_id = ?",
                (state, decided_at, run_id, approval_id, profile_id),
            )
            if cursor.rowcount == 0:
                raise LookupError(approval_id)
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except (ValueError, TypeError):
                item["payload"] = {}
            return item

    def get_approval(self, profile_id: str, approval_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            row = conn.execute("SELECT * FROM approvals WHERE id = ? AND profile_id = ?", (approval_id, profile_id)).fetchone()
            if row is None:
                raise LookupError(approval_id)
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except (ValueError, TypeError):
                item["payload"] = {}
            return item

    # -- tool events --------------------------------------------------------------
    def record_tool_event(self, profile_id: str | None, run_id: str, agent_id: str, tool_name: str, input_data: dict[str, Any], output_data: dict[str, Any], status: str = "ok", duration_ms: int = 0) -> None:
        at = now()
        with self._connect() as conn:
            if profile_id:
                self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO tool_events (profile_id, run_id, agent_id, tool_name, input, output, status, duration_ms, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (profile_id, run_id, agent_id, tool_name, json.dumps(input_data), json.dumps(output_data), status, duration_ms, at),
            )

    def list_tool_events(self, profile_id: str, limit: int = 50, run_id: str = "") -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            if run_id:
                rows = conn.execute("SELECT * FROM tool_events WHERE profile_id = ? AND run_id = ? ORDER BY id DESC LIMIT ?", (profile_id, run_id, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tool_events WHERE profile_id = ? ORDER BY id DESC LIMIT ?", (profile_id, limit)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                for key in ("input", "output"):
                    try:
                        item[key] = json.loads(item[key])
                    except (ValueError, TypeError):
                        item[key] = {}
                result.append(item)
            return result

    def db_stats(self) -> dict[str, int]:
        """Row counts for the doctor view."""
        tables = ("profiles", "agents", "messages", "approvals", "tool_events", "events", "tasks", "sources", "skill_sources", "runs", "scheduled_directives")
        with self._connect() as conn:
            return {table: (conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}

    # -- runs timeline ----------------------------------------------------------------
    def save_run(self, run_id: str, profile_id: str, agent_id: str = "", session_id: str = "", input_preview: str = "") -> None:
        at = now()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO runs (id, profile_id, agent_id, session_id, status, input_preview, started_at) VALUES (?, ?, ?, ?, 'running', ?, ?)",
                (run_id, profile_id, agent_id, session_id, input_preview[:500], at),
            )

    def finish_run(self, run_id: str, status: str = "done") -> None:
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status = ?, ended_at = ? WHERE id = ?", (status, now(), run_id))

    def list_runs(self, profile_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute(
                "SELECT r.*, COUNT(te.id) AS tool_count FROM runs r LEFT JOIN tool_events te ON te.run_id = r.id WHERE r.profile_id = ? GROUP BY r.id ORDER BY r.started_at DESC LIMIT ?",
                (profile_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- scheduled directives -------------------------------------------------------
    def create_scheduled_directive(self, profile_id: str, agent_id: str, directive: str, interval_seconds: int = 3600) -> dict[str, Any]:
        import uuid
        directive_id = str(uuid.uuid4())
        at = now()
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            conn.execute(
                "INSERT INTO scheduled_directives (id, profile_id, agent_id, directive, interval_seconds, enabled, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
                (directive_id, profile_id, agent_id, directive, max(60, interval_seconds), at),
            )
        return {"id": directive_id, "profile_id": profile_id, "agent_id": agent_id, "directive": directive, "interval_seconds": interval_seconds, "enabled": True, "last_run_at": None, "last_run_id": None, "last_error": None, "created_at": at}

    def list_scheduled_directives(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            rows = conn.execute("SELECT * FROM scheduled_directives WHERE profile_id = ? ORDER BY created_at DESC", (profile_id,)).fetchall()
            return [dict(row) for row in rows]

    def update_scheduled_directive(self, profile_id: str, directive_id: str, **kwargs: Any) -> dict[str, Any] | None:
        allowed = {"directive", "agent_id", "interval_seconds", "enabled"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return None
        sets = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [profile_id, directive_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE scheduled_directives SET {sets} WHERE profile_id = ? AND id = ?", values)
            row = conn.execute("SELECT * FROM scheduled_directives WHERE profile_id = ? AND id = ?", (profile_id, directive_id)).fetchone()
            return dict(row) if row else None

    def delete_scheduled_directive(self, profile_id: str, directive_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM scheduled_directives WHERE profile_id = ? AND id = ?", (profile_id, directive_id))

    def due_scheduled_directives(self) -> list[dict[str, Any]]:
        """Returns enabled directives whose last_run_at is older than interval_seconds (or never run)."""
        at = now()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT sd.*, p.name AS profile_name, p.context, p.vault_path, a.name AS agent_name, a.role AS agent_role FROM scheduled_directives sd JOIN profiles p ON p.id = sd.profile_id LEFT JOIN agents a ON a.profile_id = sd.profile_id AND a.id = sd.agent_id WHERE sd.enabled = 1 AND (sd.last_run_at IS NULL OR datetime(sd.last_run_at, '+' || sd.interval_seconds || ' seconds') <= datetime(?))",
                (at,),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_directive_run(self, profile_id: str, directive_id: str, run_id: str = "", error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE scheduled_directives SET last_run_at = ?, last_run_id = ?, last_error = ? WHERE profile_id = ? AND id = ?",
                (now(), run_id or None, error, profile_id, directive_id),
            )

    # -- profile export / import ----------------------------------------------------
    def export_profile(self, profile_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            self._require_profile(conn, profile_id)
            profile = dict(conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone())
            agents = [dict(r) for r in conn.execute("SELECT * FROM agents WHERE profile_id = ?", (profile_id,)).fetchall()]
            tasks = [dict(r) for r in conn.execute("SELECT * FROM tasks WHERE profile_id = ?", (profile_id,)).fetchall()]
            sources = [dict(r) for r in conn.execute("SELECT * FROM sources WHERE profile_id = ?", (profile_id,)).fetchall()]
            skills = [dict(r) for r in conn.execute("SELECT * FROM skill_sources WHERE profile_id = ?", (profile_id,)).fetchall()]
            policy_row = conn.execute("SELECT * FROM policy WHERE profile_id = ?", (profile_id,)).fetchone()
            policy = dict(policy_row) if policy_row else {}
            routes = [dict(r) for r in conn.execute("SELECT * FROM model_routes WHERE profile_id = ?", (profile_id,)).fetchall()]
            directives = [dict(r) for r in conn.execute("SELECT * FROM scheduled_directives WHERE profile_id = ?", (profile_id,)).fetchall()]
        return {"schema_version": 1, "profile": profile, "agents": agents, "tasks": tasks, "sources": sources, "skills": skills, "policy": policy, "routes": routes, "directives": directives, "exported_at": now()}

    def import_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        import uuid
        profile_data = data.get("profile", {})
        new_id = str(uuid.uuid4())
        at = now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO profiles (id, name, kind, context, vault_path, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, profile_data.get("name", "Imported profile"), profile_data.get("kind", ""), profile_data.get("context", ""), profile_data.get("vault_path", ""), at),
            )
            for agent in data.get("agents", []):
                agent_id = str(uuid.uuid4())
                conn.execute("INSERT INTO agents (id, profile_id, name, role, initials, output_path, mirror_to_vault, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (agent_id, new_id, agent.get("name", "Agent"), agent.get("role", ""), agent.get("initials", ""), agent.get("output_path", ""), agent.get("mirror_to_vault", 1), at))
            for task in data.get("tasks", []):
                conn.execute("INSERT INTO tasks (id, profile_id, title, area, state, created_at) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), new_id, task.get("title", ""), task.get("area", ""), task.get("state", "draft"), at))
            for source in data.get("sources", []):
                conn.execute("INSERT INTO sources (id, profile_id, title, detail, created_at) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), new_id, source.get("title", ""), source.get("detail", ""), at))
            for skill in data.get("skills", []):
                try:
                    conn.execute("INSERT INTO skill_sources (id, profile_id, name, repository, description, is_default, installed, installed_at, version, sha, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), new_id, skill.get("name", ""), skill.get("repository", ""), skill.get("description", ""), 0, 0, None, "", "", at))
                except Exception:
                    pass
            for route in data.get("routes", []):
                conn.execute("INSERT OR IGNORE INTO model_routes (profile_id, agent_id, provider, model) VALUES (?, ?, ?, ?)", (new_id, route.get("agent_id", ""), route.get("provider", ""), route.get("model", "")))
            policy = data.get("policy", {})
            conn.execute("INSERT OR IGNORE INTO policy (profile_id, autonomy) VALUES (?, ?)", (new_id, policy.get("autonomy", "manual")))
            for directive in data.get("directives", []):
                conn.execute("INSERT INTO scheduled_directives (id, profile_id, agent_id, directive, interval_seconds, enabled, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)", (str(uuid.uuid4()), new_id, directive.get("agent_id", ""), directive.get("directive", ""), directive.get("interval_seconds", 3600), at))
        return {"id": new_id, "name": profile_data.get("name", "Imported profile")}

    # -- vault diff -----------------------------------------------------------------
    def vault_diff(self, vault_path: str, since_iso: str | None = None) -> list[dict[str, Any]]:
        import os
        import stat
        from pathlib import Path as FsPath
        vault = FsPath(vault_path)
        if not vault.is_dir():
            return []
        cutoff = 0.0
        if since_iso:
            from datetime import datetime, timezone
            try:
                cutoff = datetime.fromisoformat(since_iso.replace("Z", "+00:00")).timestamp()
            except ValueError:
                cutoff = 0.0
        changed = []
        for root, _, files in os.walk(vault):
            for fname in files:
                if fname.startswith("."):
                    continue
                fp = FsPath(root) / fname
                try:
                    mtime = fp.stat().st_mtime
                    if mtime > cutoff:
                        rel = str(fp.relative_to(vault))
                        changed.append({"path": rel, "modified_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z"), "size": fp.stat().st_size})
                except OSError:
                    pass
        changed.sort(key=lambda x: x["modified_at"], reverse=True)
        return changed[:200]

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

    # -- agent memory (Hermes-style persistent notes) --------------------------------

    def upsert_memory(self, profile_id: str, agent_id: str, key: str, content: str) -> None:
        at = now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memories (profile_id, agent_id, key, content, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(profile_id, agent_id, key) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
                (profile_id, agent_id, key, content, at),
            )

    def list_memories(self, profile_id: str, agent_id: str, prefix: str = "") -> list[dict[str, Any]]:
        with self._connect() as conn:
            if prefix:
                rows = conn.execute(
                    "SELECT key, content, updated_at FROM memories WHERE profile_id = ? AND agent_id = ? AND key LIKE ? ORDER BY updated_at DESC",
                    (profile_id, agent_id, f"{prefix}%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT key, content, updated_at FROM memories WHERE profile_id = ? AND agent_id = ? ORDER BY updated_at DESC",
                    (profile_id, agent_id),
                ).fetchall()
            return [dict(row) for row in rows]

    def delete_memory(self, profile_id: str, agent_id: str, key: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM memories WHERE profile_id = ? AND agent_id = ? AND key = ?",
                (profile_id, agent_id, key),
            )

    # -- conversation session history ------------------------------------------------

    def get_session(self, profile_id: str, session_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT messages_json FROM sessions WHERE profile_id = ? AND session_id = ?",
                (profile_id, session_id),
            ).fetchone()
            return row["messages_json"] if row else "[]"

    def save_session(self, profile_id: str, session_id: str, messages_json: str) -> None:
        at = now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (profile_id, session_id, messages_json, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(profile_id, session_id) DO UPDATE SET messages_json = excluded.messages_json, updated_at = excluded.updated_at",
                (profile_id, session_id, messages_json, at),
            )

    def list_sessions(self, profile_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, updated_at FROM sessions WHERE profile_id = ? ORDER BY updated_at DESC LIMIT 50",
                (profile_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- agent-created skill docs (Hermes learning loop) -----------------------------

    def upsert_skill_doc(self, profile_id: str, agent_id: str, name: str, description: str, content: str) -> None:
        at = now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO skill_docs (profile_id, agent_id, name, description, content, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(profile_id, name) DO UPDATE SET agent_id = excluded.agent_id, description = excluded.description, content = excluded.content, updated_at = excluded.updated_at",
                (profile_id, agent_id, name, description, content, at),
            )

    def list_skill_docs(self, profile_id: str, agent_id: str = "") -> list[dict[str, Any]]:
        with self._connect() as conn:
            if agent_id:
                rows = conn.execute(
                    "SELECT name, description, updated_at FROM skill_docs WHERE profile_id = ? AND agent_id = ? ORDER BY updated_at DESC",
                    (profile_id, agent_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT name, description, agent_id, updated_at FROM skill_docs WHERE profile_id = ? ORDER BY updated_at DESC",
                    (profile_id,),
                ).fetchall()
            return [dict(row) for row in rows]

    def get_skill_doc(self, profile_id: str, name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_docs WHERE profile_id = ? AND name = ?",
                (profile_id, name),
            ).fetchone()
            return dict(row) if row else None

    def delete_skill_doc(self, profile_id: str, name: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM skill_docs WHERE profile_id = ? AND name = ?", (profile_id, name))
