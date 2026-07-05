import discord
from discord.ext import commands, tasks
import feedparser
import aiohttp
import asyncio

import os

CHANNELS = {
    "UCWOMTp0BLi41FTn6ouh_mdg": int(os.getenv("YT_CHANNEL_1", 0)),
    "UCCYq8CHiJR3Y8IEME0SgNUQ": int(os.getenv("YT_CHANNEL_2", 0)),
    "UCKK4jwSOaKBSTqQjNRbndng": int(os.getenv("YT_CHANNEL_3", 0))
}

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
        for yt_id, discord_channel_id in CHANNELS.items():
            channel = self.bot.get_channel(discord_channel_id)
            if not channel:
                continue

            content = await self._fetch_feed(yt_id)
            if content is None:
                continue

            feed = feedparser.parse(content)

            if not feed.entries:
                continue

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

                if row is None:
                    await self.bot.db.execute(
                        "INSERT INTO youtube_history (channel_id, video_id) VALUES (?, ?)",
                        (yt_id, video_id)
                    )
                    await self.bot.db.execute(
                        "INSERT OR REPLACE INTO youtube (channel_id, last_video) VALUES (?, ?)",
                        (yt_id, video_id)
                    )
                    await self.bot.db.commit()

                    if has_history is None:
                        continue

                    embed = discord.Embed(
                        title=f"🎥 {entry.author} just posted a video! Go check it out!",
                        description=f"**[{entry.title}](https://www.youtube.com/watch?v={video_id})**",
                        color=discord.Color.red()
                    )
                    embed.set_image(url=f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg")

                    await channel.send(content="Hey! @everyone", embed=embed)

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(YouTube(bot))