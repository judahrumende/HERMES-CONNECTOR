"""Discord bot connector.

Connects to Discord using the Gateway WebSocket and routes mentions and DMs
through the local OrbityLabs runtime.

Requires:  pip install "hermes-jarvis[discord]"   (installs discord.py)

Configuration (environment variables):
    ORBITY_DISCORD_TOKEN        — bot token from Discord Developer Portal
    ORBITY_DISCORD_PROFILE_ID   — profile that will handle messages
    ORBITY_DISCORD_AGENT_ID     — (optional) specific agent within that profile
    ORBITY_DISCORD_CHANNEL_IDS  — comma-separated channel IDs to listen in (empty = mentions everywhere)
    ORBITY_DISCORD_ALLOWED_IDS  — comma-separated Discord user IDs allowed to use the agent.
                                  REQUIRED: the agent has bash/python/file tools, so unknown
                                  senders are refused. Leave empty to allow no one (safe default).
    ORBITY_RUNTIME_URL          — base URL of the local backend (default http://127.0.0.1:8787)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


def _discord_available() -> bool:
    try:
        import discord  # noqa: F401
        return True
    except ImportError:
        return False


class DiscordConnector:
    """Routes Discord DMs and mentions through the local AgentRuntime HTTP endpoint."""

    def __init__(
        self,
        token: str,
        profile_id: str,
        agent_id: str = "",
        runtime_url: str = "http://127.0.0.1:8787",
        allowed_channel_ids: list[int] | None = None,
        allowed_user_ids: set[str] | None = None,
    ) -> None:
        self.token = token
        self.profile_id = profile_id
        self.agent_id = agent_id
        self.runtime_url = runtime_url.rstrip("/")
        self.allowed_channel_ids = set(allowed_channel_ids or [])
        self.allowed_user_ids = allowed_user_ids or set()
        self._client: Any = None

    def _is_allowed(self, user_id: str) -> bool:
        # No allowlist configured → refuse everyone. The agent has code-execution tools.
        return bool(user_id) and user_id in self.allowed_user_ids

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        if not _discord_available():
            log.warning(
                "discord.py is not installed. "
                "Run: pip install 'hermes-jarvis[discord]' to enable the Discord connector."
            )
            return

        import discord  # type: ignore[import-untyped]

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            log.info(
                "Discord connector ready as %s (profile=%s agent=%s)",
                client.user,
                self.profile_id,
                self.agent_id or "default",
            )

        @client.event
        async def on_message(message: discord.Message) -> None:  # type: ignore[type-arg]
            if message.author.bot:
                return
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = client.user in (message.mentions or [])
            if not is_dm and not is_mentioned:
                return
            if self.allowed_channel_ids and not is_dm and message.channel.id not in self.allowed_channel_ids:
                return

            # Reject senders not on the allowlist — the runtime has code-execution tools.
            if not self._is_allowed(str(message.author.id)):
                log.info("Discord message from unauthorized user %s ignored", message.author.id)
                await message.reply(
                    f"This OrbityLabs agent is private. Your Discord ID ({message.author.id}) is not "
                    "authorized. Ask the operator to add it to ORBITY_DISCORD_ALLOWED_IDS."
                )
                return

            text: str = message.content.strip()
            if client.user:
                text = (
                    text.replace(f"<@{client.user.id}>", "")
                    .replace(f"<@!{client.user.id}>", "")
                    .strip()
                )
            if not text:
                return

            async with message.channel.typing():
                output = await self._call_runtime(
                    text=text,
                    session_id=f"discord:{message.channel.id}:{message.author.id}",
                    from_id=str(message.author.id),
                )
            if output:
                for chunk in [output[i : i + 2000] for i in range(0, len(output), 2000)]:
                    await message.reply(chunk)

        try:
            await client.start(self.token)
        except asyncio.CancelledError:
            await client.close()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()

    # ------------------------------------------------------------------
    # Runtime bridge
    # ------------------------------------------------------------------

    async def _call_runtime(self, text: str, session_id: str, from_id: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=120) as http:
                r = await http.post(
                    f"{self.runtime_url}/api/hermes/runs",
                    json={
                        "payload": {
                            "input": text,
                            "session_id": session_id,
                            "metadata": {
                                "profile_id": self.profile_id,
                                "agent_id": self.agent_id,
                                "mode": "chat",
                                "source": "discord",
                                "from_id": from_id,
                            },
                        }
                    },
                )
            return r.json().get("output") or ""
        except Exception as exc:
            log.warning("Discord runtime call failed: %s", exc)
            return ""
