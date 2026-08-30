"""Self-contained agent runtime.

Replaces the external Hermes Agent dependency with a local agentic loop:
  1. Build context from profile, agent notes, memories, and loaded skills.
  2. Call the configured LLM with the full tool set.
  3. Execute tool calls, feed results back.
  4. Repeat until end_turn or max iterations.
  5. Persist the run, conversation history, and any generated messages.

Inspired by the Hermes Agent (NousResearch) and OpenClaw architectures.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anthropic
import httpx

from .tools import TOOL_DEFINITIONS, execute_tool

if TYPE_CHECKING:
    from .service import Hub
    from .store import Store

MAX_TOOL_ITERATIONS = 12
MAX_TOKENS = 4096
MAX_SUBAGENT_DEPTH = 2  # how deep spawn_agent delegation may recurse

SYSTEM_BASE = """\
You are a powerful autonomous agent running inside OrbityLabs, a personal agent OS.
You have access to a rich tool set: file system, shell execution, web fetching, persistent memory,
skill creation, and Python scripting. You operate continuously on behalf of your operator.

Ground rules:
- Only claim actions you have actually taken via a tool call.
- Do not fabricate results, file contents, API responses, or web data.
- When you write to disk, use write_file so the operator can verify.
- Prefer bounded, reversible actions. Ask before irreversible operations.
- After a complex task, use create_skill to persist what you learned.
- Use memory_write to remember anything that should survive across sessions.
"""


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RuntimeConfig:
    """Runtime configuration loaded from env and config file."""

    def __init__(self) -> None:
        self.provider = os.getenv("ORBITY_PROVIDER", "anthropic")
        self.model = os.getenv("ORBITY_MODEL", "claude-opus-4-5")
        self.api_key = os.getenv("ORBITY_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = os.getenv("ORBITY_BASE_URL", "")
        self.telegram_token = os.getenv("ORBITY_TELEGRAM_TOKEN", "")
        self.discord_token = os.getenv("ORBITY_DISCORD_TOKEN", "")

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.model)

    def update(self, provider: str, model: str, api_key: str, base_url: str = "") -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url


class AgentRuntime:
    """Local agent runtime — no external process required."""

    def __init__(self, store: "Store", hub: "Hub", config: RuntimeConfig) -> None:
        self.store = store
        self.hub = hub
        self.config = config
        self._active_runs: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API (matches HermesService.run() signature)
    # ------------------------------------------------------------------

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.config.ready:
            raise RuntimeError(
                "Agent runtime is not configured. Set an API key and model in Settings → Runtime."
            )
        run_id = str(uuid.uuid4())
        meta = payload.get("metadata") or {}
        profile_id = str(meta.get("profile_id") or "")
        agent_id = str(meta.get("agent_id") or "")
        session_id = str(payload.get("session_id") or f"session:{run_id}")
        input_text = str(payload.get("input") or "")
        mode = str(meta.get("mode") or "chat")

        self._active_runs[run_id] = True
        self.store.save_run(run_id, profile_id, agent_id, session_id, input_text[:200])
        await self.hub.publish("run.created", {"run": {"run_id": run_id, "session_id": session_id}})

        try:
            output = await self._agentic_loop(
                run_id=run_id,
                profile_id=profile_id,
                agent_id=agent_id,
                session_id=session_id,
                input_text=input_text,
                mode=mode,
                depth=0,
            )
        except asyncio.CancelledError:
            output = "[Run cancelled by operator]"
            self.store.finish_run(run_id, "cancelled")
            raise
        except Exception as exc:
            output = f"[Runtime error: {exc}]"
            self.store.finish_run(run_id, "failed")
            await self.hub.publish("run.event", {
                "run_id": run_id, "event": "run.failed", "data": {"error": str(exc)},
            })
            return {"run_id": run_id, "output": output, "session_id": session_id, "error": str(exc)}
        finally:
            self._active_runs.pop(run_id, None)

        self.store.finish_run(run_id, "completed")

        if output and profile_id and agent_id:
            self.store.save_message(profile_id, str(uuid.uuid4()), agent_id, "incoming", output, run_id)

        await self.hub.publish("run.event", {
            "run_id": run_id, "event": "run.completed",
            "data": {"run_id": run_id, "output": output[:500]},
        })
        return {"run_id": run_id, "output": output, "session_id": session_id}

    async def stop(self, run_id: str) -> None:
        self._active_runs[run_id] = False

    # ------------------------------------------------------------------
    # Core agentic loop
    # ------------------------------------------------------------------

    async def _agentic_loop(
        self,
        *,
        run_id: str,
        profile_id: str,
        agent_id: str,
        session_id: str,
        input_text: str,
        mode: str,
        depth: int = 0,
    ) -> str:
        system = self._build_system(profile_id, agent_id)
        messages = self._load_session(profile_id, session_id)
        messages.append({"role": "user", "content": input_text})

        client = self._make_client()
        final_text = ""

        for iteration in range(MAX_TOOL_ITERATIONS):
            if not self._active_runs.get(run_id, True):
                break

            response = await client.messages.create(
                model=self.config.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )

            # Collect text from response
            for block in response.content:
                if block.type == "text" and block.text:
                    final_text = block.text
                    await self.hub.publish("run.event", {
                        "run_id": run_id, "event": "text_delta",
                        "data": {"text": block.text, "iteration": iteration},
                    })

            tool_calls = [b for b in response.content if b.type == "tool_use"]

            # No tool calls → agent is done
            if not tool_calls or response.stop_reason == "end_turn":
                messages.append({"role": "assistant", "content": _blocks_to_serializable(response.content)})
                break

            # Add the assistant turn with tool calls
            messages.append({"role": "assistant", "content": _blocks_to_serializable(response.content)})

            # Execute all tools in parallel
            skills_dir = self._skills_dir(profile_id)
            tool_results = await asyncio.gather(*[
                self._run_tool(tc, run_id, profile_id, agent_id, skills_dir, session_id, depth)
                for tc in tool_calls
            ])

            messages.append({"role": "user", "content": list(tool_results)})

        # Persist updated conversation (safely trimmed so history never starts
        # with an orphaned tool_result, which the Anthropic API rejects).
        self._save_session(profile_id, session_id, _trim_history(messages, 40))
        return final_text

    async def _run_tool(
        self,
        tc: Any,
        run_id: str,
        profile_id: str,
        agent_id: str,
        skills_dir: Path | None,
        session_id: str = "",
        depth: int = 0,
    ) -> dict[str, Any]:
        # Outward/irreversible actions (sending messages, external writes) are never
        # executed silently — they queue for explicit operator approval regardless of
        # the profile's autonomy mode, honoring the auto_safe safety contract.
        needs, summary = _needs_approval(tc.name, tc.input)
        if needs:
            gated = await self._gate_for_approval(tc, run_id, profile_id, agent_id, session_id, summary)
            if gated is not None:
                return gated

        # Give the tool layer a spawn callback only while we're within the depth budget,
        # so spawn_agent can delegate but never recurse without bound.
        spawn = None
        if depth < MAX_SUBAGENT_DEPTH:
            async def spawn(task: str) -> str:
                return await self._spawn(task, profile_id, agent_id, session_id, depth)

        t0 = time.monotonic()
        result_str = await execute_tool(tc.name, tc.input, profile_id, agent_id, self.store, skills_dir, spawn)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        self.store.record_tool_event(
            profile_id, run_id, agent_id, tc.name,
            tc.input, {"result": result_str[:2000]}, "ok", elapsed_ms,
        )
        await self.hub.publish("run.event", {
            "run_id": run_id, "event": "tool_use",
            "data": {"tool": tc.name, "input": tc.input, "result": result_str[:500], "ms": elapsed_ms},
        })
        return {"type": "tool_result", "tool_use_id": tc.id, "content": result_str}

    # ------------------------------------------------------------------
    # Approval gate for outward/irreversible actions
    # ------------------------------------------------------------------

    async def _gate_for_approval(
        self, tc: Any, run_id: str, profile_id: str, agent_id: str, session_id: str, summary: str,
    ) -> dict[str, Any] | None:
        """Queue a sensitive tool call for operator approval instead of running it.

        Returns a tool_result to hand back to the model, or None to let it run (only
        when there is no profile context to attach an approval to — then we refuse).
        """
        if not profile_id:
            return {"type": "tool_result", "tool_use_id": tc.id, "content": (
                f"[refused] '{tc.name}' is an outward action and requires a profile with an "
                "approvals policy, but this run has none. Not executed."
            )}
        approval_id = str(uuid.uuid4())
        self.store.create_approval(
            profile_id, approval_id, agent_id, session_id, "tool_action", summary,
            {"tool": tc.name, "inputs": tc.input, "run_id": run_id},
        )
        self.store.record_tool_event(
            profile_id, run_id, agent_id, tc.name, tc.input,
            {"status": "pending_approval", "approval_id": approval_id}, "pending", 0,
        )
        await self.hub.publish("approval.requested", {
            "profile_id": profile_id, "approval_id": approval_id,
            "agent_id": agent_id, "summary": summary, "tool": tc.name,
        })
        return {"type": "tool_result", "tool_use_id": tc.id, "content": (
            f"[pending_approval id={approval_id}] '{tc.name}' is an outward action and requires "
            "operator approval. It has NOT run. It will execute automatically once the operator "
            "approves it in the Approvals view — do not retry it."
        )}

    async def execute_approved(
        self, profile_id: str, agent_id: str, tool_name: str, inputs: dict[str, Any], run_id: str = "",
    ) -> str:
        """Run a previously-gated tool call after the operator approved it, and record the result."""
        skills_dir = self._skills_dir(profile_id)
        t0 = time.monotonic()
        result_str = await execute_tool(tool_name, inputs, profile_id, agent_id, self.store, skills_dir, None)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        self.store.record_tool_event(
            profile_id, run_id, agent_id, tool_name, inputs,
            {"result": result_str[:2000], "approved": True}, "ok", elapsed_ms,
        )
        if profile_id and agent_id:
            self.store.save_message(
                profile_id, str(uuid.uuid4()), agent_id, "incoming",
                f"[approved action · {tool_name}]\n{result_str}", run_id,
            )
        await self.hub.publish("run.event", {
            "run_id": run_id, "event": "tool_use",
            "data": {"tool": tool_name, "approved": True, "result": result_str[:500], "ms": elapsed_ms},
        })
        return result_str

    # ------------------------------------------------------------------
    # Subagent delegation
    # ------------------------------------------------------------------

    async def _spawn(self, task: str, profile_id: str, agent_id: str, parent_session: str, depth: int) -> str:
        """Run an isolated subagent loop for a bounded delegated task.

        The subagent has the full tool set but a fresh, isolated session — it does not
        see the parent conversation. Depth is bounded by MAX_SUBAGENT_DEPTH.
        """
        if depth + 1 > MAX_SUBAGENT_DEPTH:
            return "[subagent refused] Maximum delegation depth reached."
        sub_run_id = str(uuid.uuid4())
        sub_session = f"{parent_session}:sub:{sub_run_id[:8]}"
        self._active_runs[sub_run_id] = True
        self.store.save_run(sub_run_id, profile_id, agent_id, sub_session, task[:200])
        await self.hub.publish("run.event", {
            "run_id": sub_run_id, "event": "subagent.started",
            "data": {"task": task[:200], "depth": depth + 1, "parent_session": parent_session},
        })
        try:
            output = await self._agentic_loop(
                run_id=sub_run_id,
                profile_id=profile_id,
                agent_id=agent_id,
                session_id=sub_session,
                input_text=task,
                mode="subagent",
                depth=depth + 1,
            )
            self.store.finish_run(sub_run_id, "completed")
            return output or "(subagent produced no text output)"
        except Exception as exc:
            self.store.finish_run(sub_run_id, "failed")
            return f"[subagent error] {exc}"
        finally:
            self._active_runs.pop(sub_run_id, None)

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def _build_system(self, profile_id: str, agent_id: str) -> str:
        parts = [SYSTEM_BASE]

        # Agent notes
        if profile_id and agent_id:
            notes = self.store.get_agent_notes(profile_id, agent_id)
            if notes.strip():
                parts.append(f"\n## Agent context notes\n{notes}")

        # Persistent memories
        if profile_id and agent_id:
            memories = self.store.list_memories(profile_id, agent_id, "")
            if memories:
                mem_text = "\n".join(f"- [{m['key']}] {m['content']}" for m in memories[:20])
                parts.append(f"\n## Persistent memory\n{mem_text}")

        # Skills
        if profile_id:
            skills = self.store.list_skill_docs(profile_id, agent_id)
            if skills:
                skill_text = "\n".join(f"- **{s['name']}**: {s['description']}" for s in skills[:10])
                parts.append(f"\n## Loaded skills\n{skill_text}")

        parts.append(f"\nCurrent time: {_now()}")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _load_session(self, profile_id: str, session_id: str) -> list[dict[str, Any]]:
        if not profile_id:
            return []
        try:
            raw = self.store.get_session(profile_id, session_id)
            return json.loads(raw) if raw else []
        except Exception:
            return []

    def _save_session(self, profile_id: str, session_id: str, messages: list[dict[str, Any]]) -> None:
        if not profile_id:
            return
        try:
            self.store.save_session(profile_id, session_id, json.dumps(messages))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # LLM client factory
    # ------------------------------------------------------------------

    def _make_client(self) -> anthropic.AsyncAnthropic:
        kwargs: dict[str, Any] = {"api_key": self.config.api_key}
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return anthropic.AsyncAnthropic(**kwargs)

    def _skills_dir(self, profile_id: str) -> Path | None:
        if not profile_id:
            return None
        try:
            agents = self.store.list_agents(profile_id)
            for a in agents:
                if a.get("output_path"):
                    return Path(a["output_path"]) / "skills"
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Status / probe (replaces HermesClient.probe)
    # ------------------------------------------------------------------

    async def probe(self) -> dict[str, Any]:
        if not self.config.api_key:
            return {"status": "not_configured", "error": "No API key set. Configure in Settings → Runtime."}
        try:
            client = self._make_client()
            # Lightweight probe — list models or send a tiny message
            msg = await client.messages.create(
                model=self.config.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "ping"}],
            )
            return {
                "status": "online",
                "provider": self.config.provider,
                "model": self.config.model,
                "probe_response": msg.id,
            }
        except anthropic.AuthenticationError:
            return {"status": "offline", "error": "Invalid API key."}
        except anthropic.NotFoundError:
            return {"status": "offline", "error": f"Model not found: {self.config.model}"}
        except Exception as exc:
            return {"status": "offline", "error": str(exc)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _needs_approval(tool_name: str, inputs: dict[str, Any]) -> tuple[bool, str]:
    """Classify a tool call as outward/irreversible → requires explicit operator approval.

    These are never auto-authorized, even in auto_safe mode: sending messages, posting,
    or changing external data on the operator's behalf.
    """
    if tool_name == "composio_action":
        return True, f"Composio action: {inputs.get('action', '?')} (outward / external app)"
    if tool_name == "shopify" and str(inputs.get("method", "GET")).upper() != "GET":
        return True, f"Shopify write: {str(inputs.get('method', '')).upper()} {inputs.get('resource', '')}"
    return False, ""


def _starts_with_tool_result(msg: dict[str, Any]) -> bool:
    """True if a message is a user turn whose content contains a tool_result block."""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    return False


def _trim_history(messages: list[dict[str, Any]], keep: int) -> list[dict[str, Any]]:
    """Keep the last `keep` messages, but never begin the window with an orphaned
    tool_result (a user tool_result with no preceding assistant tool_use). The
    Anthropic API rejects such sequences with a 400.
    """
    window = messages[-keep:]
    # Drop leading messages until the first is a clean user turn (a real prompt),
    # so the reloaded history always opens on a valid boundary.
    while window and (window[0].get("role") != "user" or _starts_with_tool_result(window[0])):
        window.pop(0)
    return window


def _blocks_to_serializable(blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert anthropic content blocks to JSON-serializable dicts for message history."""
    out = []
    for b in blocks:
        if b.type == "text":
            out.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            out.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        else:
            out.append({"type": b.type})
    return out
