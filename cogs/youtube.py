import discord
from discord.ext import commands, tasks
import feedparser
import aiohttp
import asyncio
import logging

import os

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
CHANNELS = {yt: ch for yt, ch in CHANNELS.items() if ch}

# Retry transient failures (e.g. DNS blips) before giving up on this cycle
FETCH_RETRIES = 3
RETRY_BACKOFF = 3  # seconds between attempts

class YouTube(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
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

            embed = discord.Embed(
                title=f"🎥 {entry.author} just posted a video! Go check it out!",
                description=f"**[{entry.title}](https://www.youtube.com/watch?v={video_id})**",
                color=discord.Color.red()
            )
            embed.set_image(url=await self._thumbnail_url(video_id))

            await channel.send(content="Hey! @everyone", embed=embed)

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