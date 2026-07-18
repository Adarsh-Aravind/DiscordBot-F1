import discord
from discord.ext import commands, tasks
from curl_cffi.requests import AsyncSession
import os
import time
import logging
from datetime import datetime
import pytz

# Don't re-post the same class of failure to the log channel more than once
# per half hour.
ERROR_LOG_COOLDOWN_SECONDS = 1800

# Kick slug -> Discord channel id to announce in.
# Set KICK_CHANNEL_1 to the Discord channel where "went live" alerts should go.
CHANNELS = {
    "abitbeast": int(os.getenv("KICK_CHANNEL_1", 0)),
}

CHECK_INTERVAL_MINUTES = 2
LOGGING_CHANNEL_ID = int(os.getenv("LOGGING_CHANNEL", 830364694916890674))

# Only poll during the streamer's usual hours. This MUST be timezone-anchored:
# a Linux VPS normally runs on UTC, so a naive datetime.now() would have made
# "evening" mean 22:30–05:30 IST and miss every real stream.
STREAM_TIMEZONE = pytz.timezone(os.getenv("STREAM_TIMEZONE", "Asia/Kolkata"))
ACTIVE_HOUR_START = int(os.getenv("KICK_ACTIVE_START", 17))
ACTIVE_HOUR_END = int(os.getenv("KICK_ACTIVE_END", 23))

# Headers are no longer manually needed with curl_cffi as it handles impersonation

class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._session = None
        self._last_error_log = 0.0
        self.check.start()

    async def _log_error(self, msg):
        """Print always, but only re-post to Discord occasionally — a Kick
        outage would otherwise flood the log channel every 2 minutes."""
        print(msg)
        now = time.monotonic()
        if now - self._last_error_log < ERROR_LOG_COOLDOWN_SECONDS:
            return
        self._last_error_log = now
        log_channel = self.bot.get_channel(LOGGING_CHANNEL_ID)
        if log_channel:
            try:
                await log_channel.send(msg)
            except discord.HTTPException:
                pass

    async def _get_session(self):
        if self._session is None or getattr(self._session, "closed", False):
            self._session = AsyncSession(impersonate="chrome")
        return self._session

    def cog_unload(self):
        self.check.cancel()
        if self._session and not getattr(self._session, "closed", False):
            # Try to close safely if it has a close method
            if hasattr(self._session, "close"):
                if __import__("asyncio").iscoroutinefunction(self._session.close):
                    self.bot.loop.create_task(self._session.close())
                else:
                    self._session.close()

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check(self):
        # Only check/notify during the streamer's evening hours, in their
        # local timezone rather than whatever the host machine is set to.
        current_hour = datetime.now(STREAM_TIMEZONE).hour
        if not (ACTIVE_HOUR_START <= current_hour <= ACTIVE_HOUR_END):
            return

        for slug, discord_channel_id in CHANNELS.items():
            try:
                await self._check_slug(slug, discord_channel_id)
            except Exception:
                # An unhandled exception here would kill the loop for good.
                logging.exception("Kick check failed for %s", slug)

    async def _check_slug(self, slug, discord_channel_id):
        channel = self.bot.get_channel(discord_channel_id)
        if not channel:
            return

        try:
            session = await self._get_session()
            response = await session.get(
                f"https://kick.com/api/v2/channels/{slug}",
                timeout=15,
            )
            if response.status_code != 200:
                await self._log_error(f"⚠️ Kick API returned `{response.status_code}` for `{slug}`")
                return
            data = response.json()
        except Exception as e:
            await self._log_error(f"⚠️ Error fetching Kick channel `{slug}`: {e}")
            return

        livestream = data.get("livestream")
        is_live = bool(livestream and livestream.get("is_live", True))

        async with self.bot.db.execute(
            "SELECT last_stream_id FROM kick_streams WHERE slug = ?",
            (slug,),
        ) as cursor:
            row = await cursor.fetchone()

        # First time we've ever observed this channel. If it's already
        # live now, that live session predates monitoring, so we seed it
        # silently rather than pinging @everyone on startup.
        first_seen = row is None

        if not is_live:
            # Record an offline marker so that when the channel later goes
            # live for the first time we still recognise it as a new stream
            # and announce it (a "no row" alone can't tell startup-while-
            # live apart from a genuine go-live transition).
            if first_seen:
                await self.bot.db.execute(
                    "INSERT OR IGNORE INTO kick_streams (slug, last_stream_id) VALUES (?, NULL)",
                    (slug,),
                )
                await self.bot.db.commit()
            return

        stream_id = str(livestream.get("id"))

        # Dedup by stream session id so a bot restart mid-stream (or a
        # brief offline flicker Kick reports under the same id) doesn't
        # re-ping @everyone. A genuinely new stream gets a new id.
        if row is not None and row[0] == stream_id:
            return

        await self.bot.db.execute(
            "INSERT INTO kick_streams (slug, last_stream_id) VALUES (?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET last_stream_id = excluded.last_stream_id",
            (slug, stream_id),
        )
        await self.bot.db.commit()

        # Already live before we started watching -> seeded silently above.
        if first_seen:
            return

        await channel.send(content="Hey! @everyone", embed=self._build_embed(slug, data, livestream))

    def _build_embed(self, slug, data, livestream):
        user = data.get("user") or {}
        username = user.get("username") or slug
        title = livestream.get("session_title") or "Live now!"
        url = f"https://kick.com/{slug}"

        embed = discord.Embed(
            title=f"🔴 {username} is now LIVE on Kick!",
            description=f"**[{title}]({url})**",
            color=discord.Color.from_rgb(83, 252, 24),  # Kick green
        )

        categories = livestream.get("categories") or []
        if categories:
            embed.add_field(name="Category", value=categories[0].get("name", "N/A"), inline=True)

        viewers = livestream.get("viewer_count")
        if viewers is not None:
            embed.add_field(name="Viewers", value=str(viewers), inline=True)

        thumb = (livestream.get("thumbnail") or {}).get("url")
        if thumb:
            embed.set_image(url=thumb)
        if user.get("profile_pic"):
            embed.set_thumbnail(url=user["profile_pic"])

        embed.url = url
        return embed

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Kick(bot))
