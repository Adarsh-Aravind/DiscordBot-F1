import discord
from discord.ext import commands, tasks
import feedparser
import aiohttp
import asyncio
import logging

import os

from cogs.notifications import UPLOAD_ROLE_ID, role_mention

# YouTube channel id -> Discord channel id to announce uploads in.
# Names are verified against each feed's title; don't reorder these by eye.
# A Bit-Beast and ByteBeast intentionally share one Discord channel.
CHANNELS = {
    "UCWOMTp0BLi41FTn6ouh_mdg": int(os.getenv("YT_ABITBEAST", 0)),  # A Bit-Beast
    "UCCYq8CHiJR3Y8IEME0SgNUQ": int(os.getenv("YT_LETSBEAST", 0)),  # Let's Beast
    "UCrFnDVz-JgIUdyizwd6YX9g": int(os.getenv("YT_BYTEBEAST", 0)),  # ByteBeast
    "UCKK4jwSOaKBSTqQjNRbndng": int(os.getenv("YT_REDSHIF8", 0)),   # Redshif8
}

# Unconfigured entries (env var missing -> 0) are skipped rather than logged
# as a missing channel every cycle.
_CONFIGURED = {yt: ch for yt, ch in CHANNELS.items() if ch}
_MISSING = [yt for yt in CHANNELS if yt not in _CONFIGURED]
CHANNELS = _CONFIGURED

# Retry transient failures (e.g. DNS blips) before giving up on this cycle
FETCH_RETRIES = 3
RETRY_BACKOFF = 3  # seconds between attempts

# --- Shorts handling -------------------------------------------------------
# The RSS feed doesn't say whether an entry is a Short, so a channel posting
# Shorts daily and long-form weekly would ping the same way for both and train
# people to ignore the pings. Optionally route Shorts to their own channel;
# either way they don't ping by default.
SHORTS_CHANNEL_ID = int(os.getenv("YT_SHORTS_CHANNEL", 0))
PING_ON_SHORTS = os.getenv("YT_PING_ON_SHORTS", "false").lower() in ("1", "true", "yes")

# --- Discussion threads ----------------------------------------------------
# One thread per upload keeps video talk out of general chat and gives each
# video a lasting home. Shorts are excluded by default: too many, too small.
AUTO_THREAD = os.getenv("YT_AUTO_THREAD", "true").lower() in ("1", "true", "yes")
AUTO_THREAD_SHORTS = os.getenv("YT_AUTO_THREAD_SHORTS", "false").lower() in ("1", "true", "yes")
# 1440 = 24h. 4320/10080 need a boosted server on older guilds; 1440 always works.
THREAD_ARCHIVE_MINUTES = 1440

class YouTube(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None

        # The YT_* env vars were renamed from YT_CHANNEL_1/2/3. A stale .env
        # leaves CHANNELS empty, which would otherwise disable upload alerts
        # with no sign anything was wrong.
        if not CHANNELS:
            logging.warning(
                "YouTube: no channels configured - upload alerts are DISABLED. "
                "Set YT_ABITBEAST / YT_LETSBEAST / YT_BYTEBEAST / YT_REDSHIF8 "
                "in .env (these replaced YT_CHANNEL_1/2/3)."
            )
        elif _MISSING:
            logging.warning(
                "YouTube: %d of %d channels unconfigured, skipping: %s",
                len(_MISSING), len(_MISSING) + len(CHANNELS), ", ".join(_MISSING)
            )

        self.check.start()

    async def cog_load(self):
        # One shared session so aiohttp can cache DNS and reuse connections
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.check.cancel()
        if self.session:
            asyncio.create_task(self.session.close())

    async def _fetch_feed(self, yt_id):
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_id}"
        last_error = None
        for attempt in range(FETCH_RETRIES):
            try:
                async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        return None
                    return await response.read()
            except Exception as e:
                last_error = e
                if attempt < FETCH_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF)
        print(f"Error fetching YouTube feed for {yt_id} after {FETCH_RETRIES} attempts: {last_error}")
        return None

    @tasks.loop(minutes=5)
    async def check(self):
        # A tasks.loop dies permanently on an unhandled exception, which would
        # silently stop all upload alerts. Isolate each channel's failure.
        for yt_id, discord_channel_id in CHANNELS.items():
            try:
                await self._check_channel(yt_id, discord_channel_id)
            except Exception:
                logging.exception("YouTube check failed for %s", yt_id)

    async def _check_channel(self, yt_id, discord_channel_id):
        channel = self.bot.get_channel(discord_channel_id)
        if not channel:
            return

        content = await self._fetch_feed(yt_id)
        if content is None:
            return

        feed = feedparser.parse(content)
        if not feed.entries:
            return

        async with self.bot.db.execute(
            "SELECT channel_id FROM youtube_history WHERE channel_id = ?",
            (yt_id,)
        ) as cursor:
            has_history = await cursor.fetchone()

        # Process all entries in reverse order (oldest to newest) to handle any missed videos
        for entry in reversed(feed.entries):
            video_id = entry.get("yt_videoid")
            if not video_id:
                continue

            async with self.bot.db.execute(
                "SELECT video_id FROM youtube_history WHERE channel_id = ? AND video_id = ?",
                (yt_id, video_id)
            ) as cursor:
                row = await cursor.fetchone()

            if row is not None:
                continue

            await self.bot.db.execute(
                "INSERT INTO youtube_history (channel_id, video_id) VALUES (?, ?)",
                (yt_id, video_id)
            )
            await self.bot.db.execute(
                "INSERT OR REPLACE INTO youtube (channel_id, last_video) VALUES (?, ?)",
                (yt_id, video_id)
            )
            await self.bot.db.commit()

            # First run for this channel: backfill history silently instead of
            # announcing the entire existing feed.
            if has_history is None:
                continue

            await self._announce(channel, entry, video_id)

    async def _announce(self, channel, entry, video_id):
        is_short = await self._is_short(video_id)

        # Shorts get their own channel when one is configured, otherwise they
        # sit alongside uploads but stay quiet.
        target = channel
        if is_short and SHORTS_CHANNEL_ID:
            target = self.bot.get_channel(SHORTS_CHANNEL_ID) or channel

        if is_short:
            title = f"📱 {entry.author} posted a Short!"
            url = f"https://www.youtube.com/shorts/{video_id}"
            color = discord.Color.from_rgb(255, 0, 80)
        else:
            title = f"🎥 {entry.author} just posted a video! Go check it out!"
            url = f"https://www.youtube.com/watch?v={video_id}"
            color = discord.Color.red()

        embed = discord.Embed(
            title=title,
            description=f"**[{entry.title}]({url})**",
            color=color,
        )
        embed.set_image(url=await self._thumbnail_url(video_id))

        ping = "" if (is_short and not PING_ON_SHORTS) else role_mention(target.guild, UPLOAD_ROLE_ID)

        message = await target.send(
            content=ping or None,
            embed=embed,
            # Belt and braces: even if a ping string were ever wrong, this
            # makes it impossible for an announcement to hit @everyone.
            allowed_mentions=discord.AllowedMentions(roles=True, everyone=False, users=False),
        )
        await self._open_thread(message, entry.title, is_short)

    async def _open_thread(self, message, video_title, is_short):
        if not AUTO_THREAD or (is_short and not AUTO_THREAD_SHORTS):
            return
        try:
            await message.create_thread(
                name=(video_title or "New upload")[:90],
                auto_archive_duration=THREAD_ARCHIVE_MINUTES,
            )
        except discord.HTTPException:
            # Missing Create Public Threads, or the channel type can't host
            # them. Not worth failing the announcement over.
            logging.warning("Could not open a discussion thread for %s", video_title)

    async def _is_short(self, video_id):
        """youtube.com/shorts/<id> answers 200 for a real Short and redirects
        to /watch for anything else, so a non-following HEAD tells them apart
        without an API key. On any error assume long-form — a Short announced
        as a video is a much smaller problem than a video announced silently."""
        try:
            async with self.session.head(
                f"https://www.youtube.com/shorts/{video_id}",
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def _thumbnail_url(self, video_id):
        """maxresdefault doesn't exist for every upload (notably Shorts and
        older videos) and 404s into a broken embed image, so fall back."""
        maxres = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        try:
            async with self.session.head(
                maxres, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return maxres
        except Exception:
            pass
        return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(YouTube(bot))