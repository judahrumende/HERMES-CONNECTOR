"""Telegram Bot connector.

Long-polls the Telegram Bot API and routes every incoming text message through
the local OrbityLabs runtime, then replies with the agent's response.

Configuration (environment variables):
    ORBITY_TELEGRAM_TOKEN        — bot token from @BotFather
    ORBITY_TELEGRAM_PROFILE_ID   — profile that will handle messages
    ORBITY_TELEGRAM_AGENT_ID     — (optional) specific agent within that profile
    ORBITY_TELEGRAM_ALLOWED_IDS  — comma-separated Telegram user IDs allowed to use the agent.
                                   REQUIRED: the agent has bash/python/file tools, so unknown
                                   senders are refused. Leave empty to allow no one (safe default).
    ORBITY_RUNTIME_URL           — base URL of the local backend (default http://127.0.0.1:8787)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

_POLL_TIMEOUT = 30  # seconds — Telegram long-poll window


class TelegramConnector:
    """Routes Telegram messages through the local AgentRuntime HTTP endpoint."""

    _BOT_BASE = "https://api.telegram.org/bot"

    def __init__(
        self,
        token: str,
        profile_id: str,
        agent_id: str = "",
        runtime_url: str = "http://127.0.0.1:8787",
        allowed_user_ids: set[str] | None = None,
    ) -> None:
        self.token = token
        self.profile_id = profile_id
        self.agent_id = agent_id
        self.runtime_url = runtime_url.rstrip("/")
        self.allowed_user_ids = allowed_user_ids or set()
        self._offset = 0
        self._running = False

    def _is_allowed(self, user_id: str) -> bool:
        # No allowlist configured → refuse everyone. The agent has code-execution
        # tools, so an open bot would be remote code execution for any stranger.
        return bool(user_id) and user_id in self.allowed_user_ids

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        log.info(
            "Telegram connector started (profile=%s agent=%s)",
            self.profile_id,
            self.agent_id or "default",
        )
        async with httpx.AsyncClient(timeout=_POLL_TIMEOUT + 10) as client:
            while self._running:
                try:
                    updates = await self._poll(client)
                    for update in updates:
                        asyncio.create_task(self._dispatch(client, update))
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    log.warning("Telegram poll error: %s — retrying in 5 s", exc)
                    await asyncio.sleep(5)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _poll(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        url = f"{self._BOT_BASE}{self.token}/getUpdates"
        r = await client.get(
            url,
            params={
                "offset": self._offset,
                "timeout": _POLL_TIMEOUT,
                "allowed_updates": ["message"],
            },
            timeout=_POLL_TIMEOUT + 10,
        )
        data: dict[str, Any] = r.json()
        if not data.get("ok"):
            log.warning("Telegram getUpdates: %s", data)
            return []
        updates: list[dict[str, Any]] = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _dispatch(self, client: httpx.AsyncClient, update: dict[str, Any]) -> None:
        msg = update.get("message") or {}
        text: str = (msg.get("text") or "").strip()
        chat: dict[str, Any] = msg.get("chat") or {}
        chat_id = chat.get("id")
        from_id = str((msg.get("from") or {}).get("id", ""))
        if not text or not chat_id:
            return

        # Reject senders not on the allowlist — the runtime has code-execution tools.
        if not self._is_allowed(from_id):
            log.info("Telegram message from unauthorized user %s ignored", from_id or "unknown")
            await self._send(
                client,
                chat_id,
                f"This OrbityLabs agent is private. Your Telegram ID ({from_id}) is not authorized. "
                "Ask the operator to add it to ORBITY_TELEGRAM_ALLOWED_IDS.",
            )
            return

        # Handle /start gracefully; ignore other commands
        if text.startswith("/"):
            if text.startswith("/start"):
                await self._send(client, chat_id, "OrbityLabs agent is ready. Send a message to begin.")
            return

        try:
            r = await client.post(
                f"{self.runtime_url}/api/hermes/runs",
                json={
                    "payload": {
                        "input": text,
                        "session_id": f"telegram:{chat_id}",
                        "metadata": {
                            "profile_id": self.profile_id,
                            "agent_id": self.agent_id,
                            "mode": "chat",
                            "source": "telegram",
                            "from_id": from_id,
                        },
                    }
                },
                timeout=120,
            )
            output: str = r.json().get("output") or ""
        except Exception as exc:
            log.warning("Telegram runtime call failed: %s", exc)
            return

        if output:
            # Telegram message limit is 4096 chars
            for chunk in [output[i : i + 4096] for i in range(0, len(output), 4096)]:
                await self._send(client, chat_id, chunk)

    async def _send(self, client: httpx.AsyncClient, chat_id: int, text: str) -> None:
        try:
            await client.post(
                f"{self._BOT_BASE}{self.token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
        except Exception as exc:
            log.warning("Telegram send error: %s", exc)
