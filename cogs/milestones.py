import discord
from discord.ext import commands, tasks
import aiohttp
import feedparser
import os

# Reuse the single source of truth for which channels/slugs we track.
from cogs.youtube import CHANNELS as YT_CHANNELS
from cogs.kick import CHANNELS as KICK_CHANNELS

# Where milestone announcements are posted.
MILESTONE_CHANNEL_ID = int(os.getenv("MILESTONE_CHANNEL", 730340430155219024))

# YouTube subscriber counts:
#   - If YOUTUBE_API_KEY is set, use the official Data API v3 (exact-ish).
#   - Otherwise fall back to a free, unofficial live-count endpoint (estimate,
#     no key required). YouTube rounds public sub counts either way.
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
SOCIALCOUNTS_URL = "https://api.socialcounts.org/youtube-live-subscriber-count/{id}"

CHECK_INTERVAL_MINUTES = 30

# Ascending milestone thresholds. We announce the highest one newly crossed.
# Dense every-100k steps through the 100k–1M range so a mid-size channel
# (e.g. ~370k) gets meaningful milestones rather than a huge 250k→500k gap.
THRESHOLDS = [
    100, 250, 500,
    1000, 2500, 5000, 10000, 25000, 50000, 75000,
    100000, 200000, 300000, 400000, 500000, 600000, 700000, 800000, 900000,
    1000000, 1500000, 2000000, 3000000, 4000000, 5000000, 7500000, 10000000,
]


def highest_milestone(count):
    """Largest threshold that `count` has reached (0 if none)."""
    reached = 0
    for t in THRESHOLDS:
        if count >= t:
            reached = t
        else:
            break
    return reached


class Milestones(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._session = None
        self._yt_names = {}  # channel_id -> display name (cached from RSS)
        self.check.start()

    async def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def cog_unload(self):
        self.check.cancel()
        if self._session and not self._session.closed:
            self.bot.loop.create_task(self._session.close())

    async def _get_last(self, platform, identifier):
        async with self.bot.db.execute(
            "SELECT last_milestone FROM milestones WHERE platform = ? AND identifier = ?",
            (platform, identifier)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row else None

    async def _set_last(self, platform, identifier, value):
        await self.bot.db.execute(
            "INSERT INTO milestones (platform, identifier, last_milestone) VALUES (?, ?, ?) "
            "ON CONFLICT(platform, identifier) DO UPDATE SET last_milestone = excluded.last_milestone",
            (platform, identifier, value)
        )
        await self.bot.db.commit()

    async def _process(self, channel, platform, identifier, name, count, url, color, unit):
        milestone = highest_milestone(count)
        if milestone == 0:
            return

        last = await self._get_last(platform, identifier)
        if last is None:
            # First time we've seen this account: seed silently so we don't
            # announce milestones that were already passed before monitoring.
            await self._set_last(platform, identifier, milestone)
            return

        if milestone > last:
            await self._set_last(platform, identifier, milestone)
            embed = discord.Embed(
                title=f"🎉 {name} just hit {milestone:,} {unit}!",
                description=f"Huge congrats to **[{name}]({url})**! 🥳",
                color=color,
            )
            await channel.send(embed=embed)

    # ------------------------------------------------------------------ #
    # YouTube
    # ------------------------------------------------------------------ #
    async def _yt_channel_name(self, session, yt_id):
        """Resolve a channel's display name from its RSS feed (cached)."""
        if yt_id in self._yt_names:
            return self._yt_names[yt_id]

        name = None
        try:
            async with session.get(
                f"https://www.youtube.com/feeds/videos.xml?channel_id={yt_id}",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    feed = feedparser.parse(await resp.read())
                    name = feed.feed.get("title")
        except Exception:
            pass

        if name:
            self._yt_names[yt_id] = name
        return name

    async def _yt_subscribers(self, session, yt_id):
        """Return subscriber count via official API if keyed, else the free
        estimate. Returns (count, name) or None on failure."""
        if YOUTUBE_API_KEY:
            async with session.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "statistics,snippet", "id": yt_id, "key": YOUTUBE_API_KEY},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
            items = data.get("items") or []
            if not items:
                return None
            stats = items[0].get("statistics", {})
            if stats.get("hiddenSubscriberCount"):
                return None
            name = items[0].get("snippet", {}).get("title")
            return int(stats.get("subscriberCount", 0)), name

        # No key: free unofficial estimate.
        async with session.get(
            SOCIALCOUNTS_URL.format(id=yt_id),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        count = data.get("est_sub")
        if count is None:
            return None
        name = (data.get("user") or {}).get("name")
        return int(count), name

    async def _check_youtube(self, channel, session):
        for yt_id in YT_CHANNELS:
            try:
                result = await self._yt_subscribers(session, yt_id)
                if result is None:
                    continue
                count, name = result
                if not name:
                    name = await self._yt_channel_name(session, yt_id) or "The channel"
                url = f"https://www.youtube.com/channel/{yt_id}"
                await self._process(
                    channel, "youtube", yt_id, name, count, url,
                    discord.Color.red(), "subscribers"
                )
            except Exception as e:
                print(f"Error checking YouTube milestone for {yt_id}: {e}")

    # ------------------------------------------------------------------ #
    # Kick
    # ------------------------------------------------------------------ #
    async def _check_kick(self, channel, session):
        from curl_cffi.requests import AsyncSession
        # Kick requires curl_cffi to bypass Cloudflare
        async with AsyncSession(impersonate="chrome") as curl_session:
            for slug in KICK_CHANNELS:
                try:
                    resp = await curl_session.get(
                        f"https://kick.com/api/v2/channels/{slug}",
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()

                    # Kick's field naming has varied; accept either form.
                    count = data.get("followersCount")
                    if count is None:
                        count = data.get("followers_count")
                    if count is None:
                        continue

                    user = data.get("user") or {}
                    name = user.get("username") or slug
                    url = f"https://kick.com/{slug}"
                    await self._process(
                        channel, "kick", slug, name, int(count), url,
                        discord.Color.from_rgb(83, 252, 24), "followers"
                    )
            except Exception as e:
                print(f"Error checking Kick milestone for {slug}: {e}")

    @tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
    async def check(self):
        channel = self.bot.get_channel(MILESTONE_CHANNEL_ID)
        if not channel:
            return

        session = await self._get_session()
        await self._check_youtube(channel, session)
        await self._check_kick(channel, session)

    @check.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Milestones(bot))
