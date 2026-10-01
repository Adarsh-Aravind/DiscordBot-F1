"""Status heartbeat for the "Live Ops" panel on adarsharavind.com.

Every minute the bot POSTs a small "I'm alive" ping to the ops-status server
on the home server. The portfolio shows the bot as offline once pings stop for ~3
minutes, so a crashed process or a dropped gateway connection both show up.

Disabled unless STATUS_HEARTBEAT_URL and STATUS_HEARTBEAT_TOKEN are set.
"""

import logging
import math
import os
from datetime import datetime, timezone

import aiohttp
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60
TIMEOUT = aiohttp.ClientTimeout(total=10)


class Heartbeat(commands.Cog):
    def __init__(self, bot, url: str, token: str, bot_id: str):
        self.bot = bot
        self.url = url
        self.token = token
        self.bot_id = bot_id
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.session: aiohttp.ClientSession | None = None
        self.failing = False

    async def cog_load(self):
        self.session = aiohttp.ClientSession(timeout=TIMEOUT)
        self.beat.start()

    async def cog_unload(self):
        self.beat.cancel()
        # Bot.close() unloads every extension, so this runs on a clean
        # shutdown and the portfolio flips to offline straight away instead of
        # waiting for the heartbeat to go stale.
        await self._send(stopping=True)
        if self.session:
            await self.session.close()

    def _payload(self, stopping: bool) -> dict:
        user = self.bot.user
        latency = self.bot.latency
        return {
            "id": self.bot_id,
            "username": user.name if user else None,
            "avatar_url": user.display_avatar.url if user else None,
            "guilds": len(self.bot.guilds),
            "members": sum(g.member_count or 0 for g in self.bot.guilds),
            "latency_ms": round(latency * 1000) if math.isfinite(latency) else None,
            "started_at": self.started_at,
            "stopping": stopping,
        }

    async def _send(self, stopping: bool = False):
        if not self.session or self.session.closed:
            return
        try:
            async with self.session.post(
                self.url,
                json=self._payload(stopping),
                headers={"Authorization": f"Bearer {self.token}"},
            ) as resp:
                if resp.status >= 400:
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=resp.status
                    )
            if self.failing:
                log.info("Status heartbeat recovered")
                self.failing = False
        except Exception as exc:
            # Log once per outage, not once a minute.
            if not self.failing:
                log.warning("Status heartbeat failed: %s", exc)
                self.failing = True

    @tasks.loop(seconds=INTERVAL_SECONDS)
    async def beat(self):
        # Only report alive while actually connected to Discord, so a gateway
        # outage shows as offline even though the process is still running.
        if not self.bot.is_ready() or self.bot.is_closed() or not math.isfinite(self.bot.latency):
            return
        await self._send()

    @beat.before_loop
    async def before_beat(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    url = os.getenv("STATUS_HEARTBEAT_URL", "").strip()
    token = os.getenv("STATUS_HEARTBEAT_TOKEN", "").strip()
    bot_id = os.getenv("STATUS_BOT_ID", "bitbot").strip()
    if not url or not token:
        log.info("Status heartbeat disabled (STATUS_HEARTBEAT_URL / STATUS_HEARTBEAT_TOKEN not set)")
        return
    await bot.add_cog(Heartbeat(bot, url, token, bot_id))
