"""Durable laptop-side agent loop scheduler.

The scheduler keeps an explicit record of each attempted loop. It does not
pretend work completed when the configured Hermes runtime is unavailable, and
it only runs while the local OrbityLabs bridge is running.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .hermes import HermesError
from .service import HermesService, Hub
from .store import Store


class AgentLoopScheduler:
    def __init__(self, store: Store, hermes: HermesService, hub: Hub) -> None:
        self.store, self.hermes, self.hub = store, hermes, hub
        self._next_due: dict[tuple[str, str], float] = {}

    async def watch(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(10)

    async def tick(self) -> None:
        now = time.monotonic()
        for loop in self.store.agent_loop_candidates():
            key = (loop["profile_id"], loop["agent_id"])
            if now < self._next_due.get(key, 0):
                continue
            self._next_due[key] = now + max(60, int(loop["interval_seconds"]))
            await self.run_loop(loop)

    async def run_loop(self, loop: dict[str, Any]) -> None:
        profile_id, agent_id = loop["profile_id"], loop["agent_id"]
        if self.hermes.snapshot.get("status") != "online":
            await self.hermes.refresh()
        if self.hermes.snapshot.get("status") != "online":
            detail = "Hermes runtime is not verified online; loop was not started."
            self.store.mark_agent_loop(profile_id, agent_id, error=detail)
            await self.hub.publish("agent.loop_skipped", {"profile_id": profile_id, "agent_id": agent_id, "reason": detail})
            return
        is_ceo = "ceo" in f"{loop['name']} {loop['role']}".lower()
        instruction = (
            "You are the CEO loop for this profile. Review active work, identify the next bounded action, "
            "and delegate through the configured agent system where the runtime supports it. Do not claim actions "
            "you did not execute. Record concise progress and surface any blocked or high-impact decision."
            if is_ceo else
            "You are a continuously running specialist agent. Review your assigned context, take only bounded, "
            "reversible work available through configured tools, and report progress or blockers to the CEO. "
            "Do not claim external work you did not execute."
        )
        payload = {
            "input": f"{instruction}\n\nProfile: {loop['profile_name']}\nContext: {loop['context'] or 'No profile context supplied.'}\nAgent: {loop['name']} ({loop['role'] or 'General'})\nOutput folder: {loop['output_path'] or 'Not configured'}\nVault mirroring: {'enabled' if loop['mirror_to_vault'] else 'disabled'}",
            "session_id": f"orbitylabs:{profile_id}:{agent_id}:loop",
            "metadata": {"profile_id": profile_id, "agent_id": agent_id, "mode": "continuous_loop", "output_path": loop["output_path"], "vault_path": loop["vault_path"], "mirror_to_vault": bool(loop["mirror_to_vault"])},
        }
        try:
            result = await self.hermes.run(payload)
            run_id = str(result.get("run_id") or result.get("id") or "")
            self.store.mark_agent_loop(profile_id, agent_id, run_id=run_id)
            self.store.record_event(profile_id, "agent.loop_started", {"agent_id": agent_id, "run_id": run_id, "ceo": is_ceo})
            await self.hub.publish("agent.loop_started", {"profile_id": profile_id, "agent_id": agent_id, "run_id": run_id, "ceo": is_ceo})
        except HermesError as exc:
            detail = str(exc)
            self.store.mark_agent_loop(profile_id, agent_id, error=detail)
            await self.hub.publish("agent.loop_failed", {"profile_id": profile_id, "agent_id": agent_id, "error": detail})
