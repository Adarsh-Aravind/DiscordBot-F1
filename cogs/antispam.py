import discord
from discord.ext import commands
import re
import datetime
import time
from collections import defaultdict, deque

INVITE_PATTERN = re.compile(r"(discord\.gg/|discord\.com/invite/)")
YOUTUBE_PATTERN = re.compile(r"(youtube\.com|youtu\.be)")
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

# Flood detection: more than FLOOD_MAX_MESSAGES within FLOOD_WINDOW_SECONDS,
# or the same text DUPLICATE_LIMIT times in that window, counts as spam.
FLOOD_WINDOW_SECONDS = 8
FLOOD_MAX_MESSAGES = 6
DUPLICATE_LIMIT = 3


class AntiSpam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # user_id -> recent (timestamp, text). Bounded so it can't grow forever.
        self._recent = defaultdict(lambda: deque(maxlen=FLOOD_MAX_MESSAGES + 2))

    @staticmethod
    def _is_exempt(message):
        """Staff bypass every filter — the bot shouldn't police its own mods."""
        perms = getattr(message.author, "guild_permissions", None)
        if perms and (perms.administrator or perms.manage_messages or perms.moderate_members):
            return True
        return any(role.id == ADMIN_ROLE_ID for role in getattr(message.author, "roles", []))

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

    async def punish(self, message, reason):
        # Delete violation message
        try:
            await message.delete()
        except Exception:
            pass

        # Timeout user
        try:
            await message.author.timeout(
                datetime.timedelta(minutes=TIMEOUT_DURATION),
                reason=reason
            )
        except Exception:
            pass

        # Send warning message (auto delete)
        try:
            await message.channel.send(
                f"{message.author.mention} ⚠ {reason}. "
                f"You have been timed out for {TIMEOUT_DURATION} minutes.",
                delete_after=WARNING_DELETE_AFTER
            )
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(AntiSpam(bot))