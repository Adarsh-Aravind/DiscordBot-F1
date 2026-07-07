import discord
from discord.ext import commands, tasks
from curl_cffi.requests import AsyncSession
import os
from datetime import datetime

# Kick slug -> Discord channel id to announce in.
# Set KICK_CHANNEL_1 to the Discord channel where "went live" alerts should go.
CHANNELS = {
    "abitbeast": int(os.getenv("KICK_CHANNEL_1", 0)),
}

CHECK_INTERVAL_MINUTES = 2
LOGGING_CHANNEL_ID = 830364694916890674

# Headers are no longer manually needed with curl_cffi as it handles impersonation

class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._session = None
        self.check.start()

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
        # Only check/notify during evening hours (5 PM to 11:59 PM)
        current_hour = datetime.now().hour
        if not (17 <= current_hour <= 23):
            return

        for slug, discord_channel_id in CHANNELS.items():
            channel = self.bot.get_channel(discord_channel_id)
            if not channel:
                continue

            try:
                session = await self._get_session()
                response = await session.get(
                    f"https://kick.com/api/v2/channels/{slug}",
                    timeout=15,
                )
                if response.status_code != 200:
                    msg = f"⚠️ Kick API returned `{response.status_code}` for `{slug}`"
                    print(msg)
                    log_channel = self.bot.get_channel(LOGGING_CHANNEL_ID)
                    if log_channel:
                        await log_channel.send(msg)
                    continue
                data = response.json()
            except Exception as e:
                msg = f"⚠️ Error fetching Kick channel `{slug}`: {e}"
                print(msg)
                log_channel = self.bot.get_channel(LOGGING_CHANNEL_ID)
                if log_channel:
                    await log_channel.send(msg)
                continue

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
                continue

            stream_id = str(livestream.get("id"))

            # Dedup by stream session id so a bot restart mid-stream (or a
            # brief offline flicker Kick reports under the same id) doesn't
            # re-ping @everyone. A genuinely new stream gets a new id.
            if row is not None and row[0] == stream_id:
                continue

            await self.bot.db.execute(
                "INSERT INTO kick_streams (slug, last_stream_id) VALUES (?, ?) "
                "ON CONFLICT(slug) DO UPDATE SET last_stream_id = excluded.last_stream_id",
                (slug, stream_id),
            )
            await self.bot.db.commit()

            # Already live before we started watching -> seeded silently above.
            if first_seen:
                continue

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
