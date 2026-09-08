import discord
from discord.ext import commands
import re
import datetime
import time
from collections import defaultdict, deque

from cogs.alerts import send_alert

INVITE_PATTERN = re.compile(r"(discord\.gg/|discord\.com/invite/)")
YOUTUBE_PATTERN = re.compile(r"(youtube\.com|youtu\.be)")

# --- Scam / phishing links -------------------------------------------------
# Creator communities are a standing target for "free Nitro" and fake-collab
# phishing, and a young audience is exactly who falls for it. Three signals,
# cheapest first, all of which require an *external* link to fire at all.

URL_PATTERN = re.compile(r"\b(?:https?://|www\.)([a-z0-9.-]+\.[a-z]{2,})", re.I)

# Hosts never treated as scams. Matched as an exact host or a subdomain of it,
# never as a substring — "discord.com.evil.ru" must not pass as discord.com.
LINK_ALLOWLIST = (
    "youtube.com", "youtu.be", "kick.com", "twitch.tv", "twitter.com", "x.com",
    "instagram.com", "tiktok.com", "reddit.com", "github.com", "imgur.com",
    "tenor.com", "giphy.com", "spotify.com", "open.spotify.com",
    "discord.com", "discordapp.com", "discordapp.net", "discord.gg",
    "google.com", "wikipedia.org", "roblox.com", "minecraft.net",
)

# Hostnames dressed up as a brand they aren't. Typosquatting is the vector:
# dlscord.gift, discrod-nitro.xyz, st3amcommunity.ru. Anything matching this
# that isn't on the allowlist above is hostile by construction.
IMPERSONATION_PATTERN = re.compile(
    r"(d[i1l]s[ck]o?rd|dlscord|discrod|disc0rd|dicord|"
    r"st[e3]am(community|powered)?|nitro|"
    r"robux|freerobux)",
    re.I,
)

# Bait phrasing. Harmless alone; paired with an off-allowlist link it isn't.
SCAM_BAIT_PATTERN = re.compile(
    r"(free\s*nitro|nitro\s*(for\s*free|gift|giveaway|drop)|"
    r"steam\s*(gift|key|skin)|free\s*robux|"
    r"claim\s*(your|it|free|now)|"
    r"airdrop|crypto\s*(giveaway|gift)|"
    r"gift\s*card\s*(free|generator)|"
    r"first\s*\d+\s*(people|users)\s*only)",
    re.I,
)
CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:\w+:\d+>")
UNICODE_EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"  # emoticons
    r"\U0001F300-\U0001F5FF"  # symbols & pictographs
    r"\U0001F680-\U0001F6FF"  # transport & map
    r"\U0001F1E0-\U0001F1FF]+",  # flags
    flags=re.UNICODE
)

import os

ALLOWED_YT_CHANNEL = int(os.getenv("ALLOWED_YT_CHANNEL", 0))
PROMO_CHANNEL_ID = int(os.getenv("PROMO_CHANNEL", 764832907260198965))
ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE", 666859807877365801))
MAX_USER_MENTIONS = 4
MAX_EMOJIS = 8
TIMEOUT_DURATION = 5  # minutes
WARNING_DELETE_AFTER = 30  # seconds

# Scam links get a much longer timeout than ordinary spam: a compromised or
# throwaway account posting phishing will keep going until it's stopped, and
# a mod alert goes out so a human can decide on a ban.
SCAM_TIMEOUT_DURATION = 60  # minutes

# Flood detection: more than FLOOD_MAX_MESSAGES within FLOOD_WINDOW_SECONDS,
# or the same text DUPLICATE_LIMIT times in that window, counts as spam.
FLOOD_WINDOW_SECONDS = 8
FLOOD_MAX_MESSAGES = 6
DUPLICATE_LIMIT = 3

# Only bother sweeping the per-user history map once it has grown past this.
SWEEP_THRESHOLD = 500


def is_staff(author):
    """Moderators bypass the automated filters — the bot shouldn't police its
    own mods. Deliberately narrower than "any staff perm": manage_messages is
    routinely handed to trial helpers and shouldn't buy a blanket bypass.

    Shared with the raid guard so the two can't drift apart.
    """
    perms = getattr(author, "guild_permissions", None)
    if perms and (perms.administrator or perms.moderate_members):
        return True
    return any(role.id == ADMIN_ROLE_ID for role in getattr(author, "roles", []))


def external_hosts(content):
    """Hostnames linked in a message that aren't on the allowlist."""
    hosts = []
    for raw in URL_PATTERN.findall(content):
        host = raw.lower().rstrip(".")
        if host.startswith("www."):
            host = host[4:]
        if not any(host == good or host.endswith("." + good) for good in LINK_ALLOWLIST):
            hosts.append(host)
    return hosts


def scam_reason(content):
    """Why this message looks like phishing, or None. Requires an external
    link in every branch, so ordinary chat can never trip it."""
    hosts = external_hosts(content)
    if not hosts:
        return None

    for host in hosts:
        if IMPERSONATION_PATTERN.search(host):
            return f"Phishing link — `{host}` is impersonating a known brand"

    if SCAM_BAIT_PATTERN.search(content):
        return f"Scam link — free-gift bait pointing at `{hosts[0]}`"

    return None


class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # user_id -> recent (timestamp, text). Each deque is capped, and the
        # map itself is swept so it doesn't keep an entry per user forever.
        self._recent = defaultdict(lambda: deque(maxlen=FLOOD_MAX_MESSAGES + 2))

    def _sweep(self, now):
        """Users whose last message fell out of the flood window can't trip any
        check, so forget them rather than holding a deque per lifetime user."""
        if len(self._recent) < SWEEP_THRESHOLD:
            return
        stale = [
            uid for uid, hist in self._recent.items()
            if not hist or now - hist[-1][0] > FLOOD_WINDOW_SECONDS
        ]
        for uid in stale:
            del self._recent[uid]

    @staticmethod
    def _is_exempt(message):
        return is_staff(message.author)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Filters are guild rules; DMs (relayed to the owner by the messaging
        # cog) have no channel to moderate and no member to time out.
        if not message.guild:
            return

        if self._is_exempt(message):
            return

        if message.channel.id == PROMO_CHANNEL_ID:
            # Links can arrive as an attachment or embed-only post, so only
            # enforce the YouTube-link rule on messages that have text.
            if message.content.strip() and not YOUTUBE_PATTERN.search(message.content):
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention} This channel is a promotion channel for YouTube links only.",
                        delete_after=WARNING_DELETE_AFTER
                    )
                except Exception:
                    pass
                return

        # -------------------------
        # Scam / phishing links (checked first — highest harm)
        # -------------------------
        reason = scam_reason(message.content)
        if reason:
            await self.punish(message, reason, minutes=SCAM_TIMEOUT_DURATION)
            await send_alert(
                self.bot,
                f"🚨 Removed a scam link from **{message.author}** (`{message.author.id}`) "
                f"in {message.channel.mention} and timed them out for "
                f"{SCAM_TIMEOUT_DURATION} minutes.\n{reason}",
                ping_mods=True,
                guild=message.guild,
            )
            return

        # -------------------------
        # Block @everyone / @here  (staff already returned above)
        # -------------------------
        if message.mention_everyone:
            await self.punish(message, "Mass mention (@everyone / @here) is only allowed for admins")
            return

        # -------------------------
        # Block mass user mentions
        # -------------------------
        if len(message.mentions) > MAX_USER_MENTIONS:
            await self.punish(message, "Mass user mentions are not allowed")
            return

        # -------------------------
        # Block invite links
        # -------------------------
        if INVITE_PATTERN.search(message.content):
            await self.punish(message, "Discord invite links are not allowed")
            return

        # -------------------------
        # Restrict YouTube links
        # -------------------------
        if YOUTUBE_PATTERN.search(message.content):
            if message.channel.id not in (ALLOWED_YT_CHANNEL, PROMO_CHANNEL_ID):
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass
                await message.channel.send(
                    f"{message.author.mention} YouTube links are only allowed in the designated channel.",
                    delete_after=WARNING_DELETE_AFTER
                )
                return

        # -------------------------
        # Block mass emoji spam
        # -------------------------
        emoji_count = 0
        emoji_count += len(CUSTOM_EMOJI_PATTERN.findall(message.content))
        emoji_count += len(UNICODE_EMOJI_PATTERN.findall(message.content))

        if emoji_count > MAX_EMOJIS:
            await self.punish(message, "Mass emoji spam is not allowed")
            return

        # -------------------------
        # Message flooding / copy-paste repetition
        # -------------------------
        await self._check_flood(message)

    async def _check_flood(self, message):
        """Catch raw message floods and the same text posted over and over."""
        now = time.monotonic()
        self._sweep(now)
        history = self._recent[message.author.id]
        history.append((now, message.content.strip().lower()))

        # Drop anything outside the sliding window.
        while history and now - history[0][0] > FLOOD_WINDOW_SECONDS:
            history.popleft()

        if len(history) >= FLOOD_MAX_MESSAGES:
            history.clear()
            await self.punish(message, f"Sending messages too quickly ({FLOOD_MAX_MESSAGES} in {FLOOD_WINDOW_SECONDS}s)")
            return

        text = message.content.strip().lower()
        if text:
            repeats = sum(1 for _, content in history if content == text)
            if repeats >= DUPLICATE_LIMIT:
                history.clear()
                await self.punish(message, "Repeating the same message")

    async def punish(self, message, reason, minutes=TIMEOUT_DURATION):
        # Delete violation message
        try:
            await message.delete()
        except Exception:
            pass

        # Timeout user
        try:
            await message.author.timeout(
                datetime.timedelta(minutes=minutes),
                reason=reason
            )
        except Exception:
            pass

        # Send warning message (auto delete)
        try:
            await message.channel.send(
                f"{message.author.mention} ⚠ {reason}. "
                f"You have been timed out for {minutes} minutes.",
                delete_after=WARNING_DELETE_AFTER
            )
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))