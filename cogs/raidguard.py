"""Raid detection.

Deliberately does NOT gate on account age. The audience here is largely kids
who make a Discord account on the spot to join after watching a video — an
account-age wall would block exactly the people the server wants, and a raider
can buy aged accounts anyway. Age is a bad signal for this community.

What's used instead:

  A. Join rate — many joins in a short window. On a 300k-sub channel this fires
     on legitimate traffic too (a video goes live, people flood in), so it is
     an ALERT and a heightened-alert period, never an automatic punishment.

  B. Coordinated content — the same message from several *different* accounts
     within seconds. The existing anti-spam is per-user, so 40 accounts posting
     once each sail straight through it; this is the signal that catches them,
     and it doesn't care how old any account is.

Nothing here kicks or bans. Timeouts are reversible and a human decides the
rest, which matters when the cost of a false positive is banning a 12-year-old
fan for posting a copypasta.
"""

import discord
from discord.ext import commands
import datetime
import logging
import os
import re
import time
from collections import deque

from cogs.alerts import send_alert
from cogs.antispam import is_staff

# --- Signal A: join rate ---------------------------------------------------
JOIN_BURST_COUNT = int(os.getenv("RAID_JOIN_COUNT", 10))
JOIN_BURST_SECONDS = int(os.getenv("RAID_JOIN_WINDOW", 30))

# How long heightened checks stay on after a burst.
RAID_WATCH_MINUTES = int(os.getenv("RAID_WATCH_MINUTES", 10))

# Don't re-alert about the same ongoing burst every few seconds.
JOIN_ALERT_COOLDOWN_SECONDS = 300

# --- Signal B: coordinated content -----------------------------------------
COORDINATED_USERS = int(os.getenv("RAID_COORD_USERS", 4))
COORDINATED_WINDOW_SECONDS = int(os.getenv("RAID_COORD_WINDOW", 20))

# Short messages are excluded — a dozen people saying "gg" at once is a
# community, not a raid. Links are checked regardless of length, since scam
# raids post nothing but a short URL.
COORDINATED_MIN_LENGTH = 12

RAID_TIMEOUT_MINUTES = 60

# Don't act twice on the same text, but don't remember it forever either.
HANDLED_TTL_SECONDS = 600

LINK_PATTERN = re.compile(r"(https?://|www\.|discord\.gg/)", re.I)
WHITESPACE = re.compile(r"\s+")


def normalize(content):
    return WHITESPACE.sub(" ", content.strip().lower())


class RaidGuard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._joins = deque(maxlen=200)          # (timestamp, member_id)
        self._recent = deque(maxlen=300)         # (timestamp, user_id, text, message)
        self._raid_watch_until = 0.0
        self._last_join_alert = 0.0
        self._burst_members = {}                 # member_id -> monotonic join time
        self._handled = {}                       # normalized text -> when acted on

    def _expire(self, now):
        """Everything here is short-lived by design; drop it once it can no
        longer influence a decision so nothing accumulates for the process
        lifetime."""
        for text, ts in list(self._handled.items()):
            if now - ts > HANDLED_TTL_SECONDS:
                del self._handled[text]
        if not self.raid_watch_active and self._burst_members:
            self._burst_members.clear()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def raid_watch_active(self):
        return time.monotonic() < self._raid_watch_until

    def _start_raid_watch(self):
        self._raid_watch_until = time.monotonic() + RAID_WATCH_MINUTES * 60

    # ------------------------------------------------------------------
    # Signal A — join rate
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_member_join(self, member):
        now = time.monotonic()
        self._joins.append((now, member.id))

        while self._joins and now - self._joins[0][0] > JOIN_BURST_SECONDS:
            self._joins.popleft()

        if len(self._joins) < JOIN_BURST_COUNT:
            return

        # Remember who arrived in the burst so their links can be watched more
        # closely for a while, without punishing them for merely joining.
        self._burst_members.update({uid: now for _, uid in self._joins})
        self._start_raid_watch()

        if now - self._last_join_alert < JOIN_ALERT_COOLDOWN_SECONDS:
            return
        self._last_join_alert = now

        await send_alert(
            self.bot,
            f"⚠️ **Join spike** — {len(self._joins)} members joined in "
            f"{JOIN_BURST_SECONDS}s. Heightened checks on for {RAID_WATCH_MINUTES} min.\n"
            f"This is often just a video going live. Nobody has been actioned. "
            f"If it *is* a raid, use `#raidmode on`.",
            ping_mods=True,
            guild=member.guild,
        )

    # ------------------------------------------------------------------
    # Signal B — the same message from several different accounts
    # ------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if is_staff(message.author):
            return

        now = time.monotonic()
        self._expire(now)
        text = normalize(message.content)
        has_link = bool(LINK_PATTERN.search(message.content))

        # Heightened check: during a raid watch, a link from someone who
        # arrived in the join burst gets held for review. Deleted, not punished
        # — a new fan posting a link is normal, and if this was a legitimate
        # join spike the only cost is one removed message and a mod alert.
        if has_link and self.raid_watch_active and message.author.id in self._burst_members:
            await self._hold_link(message)
            return

        if not text or (len(text) < COORDINATED_MIN_LENGTH and not has_link):
            return

        self._recent.append((now, message.author.id, text, message))
        while self._recent and now - self._recent[0][0] > COORDINATED_WINDOW_SECONDS:
            self._recent.popleft()

        matches = [item for item in self._recent if item[2] == text]
        senders = {item[1] for item in matches}

        if len(senders) < COORDINATED_USERS or text in self._handled:
            return

        self._handled[text] = now
        self._start_raid_watch()
        await self._respond_to_coordinated(message, matches, senders, has_link)

    async def _hold_link(self, message):
        """Remove a link posted by a burst arrival during a raid watch and tell
        the mods, so a human can restore it if the spike was legitimate."""
        preview = message.content.strip().replace("`", "'")[:150]
        try:
            await message.delete()
        except discord.HTTPException:
            return

        try:
            await message.channel.send(
                f"{message.author.mention} links are held for review for a few "
                f"minutes after joining. A mod will take a look — nothing to worry about!",
                delete_after=20,
            )
        except discord.HTTPException:
            pass

        await send_alert(
            self.bot,
            f"🔍 Held a link from **{message.author}** (`{message.author.id}`), who joined "
            f"during a join spike, in {message.channel.mention}. No timeout was applied.\n"
            f"Content: ```{preview}```",
            guild=message.guild,
        )

    async def _respond_to_coordinated(self, message, matches, senders, has_link):
        """Delete the burst. Time the senders out only when it carries a link —
        a shared copypasta is annoying, a coordinated link drop is an attack."""
        deleted = 0
        for _, _, _, msg in matches:
            try:
                await msg.delete()
                deleted += 1
            except discord.HTTPException:
                pass

        timed_out = 0
        if has_link:
            for _, _, _, msg in matches:
                member = msg.author
                if not isinstance(member, discord.Member):
                    continue
                try:
                    await member.timeout(
                        datetime.timedelta(minutes=RAID_TIMEOUT_MINUTES),
                        reason="Coordinated link spam from multiple accounts",
                    )
                    timed_out += 1
                except discord.HTTPException:
                    pass

        preview = message.content.strip().replace("`", "'")[:150]
        action = (
            f"Timed out {timed_out} account(s) for {RAID_TIMEOUT_MINUTES} min."
            if has_link
            else "No timeouts — the message had no link, so it may just be a copypasta."
        )
        await send_alert(
            self.bot,
            f"🚨 **Coordinated spam** — the same message from {len(senders)} different "
            f"accounts in under {COORDINATED_WINDOW_SECONDS}s.\n"
            f"Deleted {deleted} message(s). {action}\n"
            f"Content: ```{preview}```",
            ping_mods=True,
            guild=message.guild,
        )

    # ------------------------------------------------------------------
    # Manual control
    # ------------------------------------------------------------------
    @commands.command(name="raidmode")
    @commands.has_permissions(moderate_members=True)
    async def raidmode(self, ctx, state: str = None):
        """`#raidmode on` forces heightened checks; `off` clears them."""
        if state is None:
            remaining = max(0, int(self._raid_watch_until - time.monotonic()))
            await ctx.send(
                f"Raid watch is **{'ON' if self.raid_watch_active else 'OFF'}**"
                + (f" ({remaining // 60}m {remaining % 60}s left)." if remaining else ".")
                + "\nUse `#raidmode on` or `#raidmode off`."
            )
            return

        if state.lower() in ("on", "enable", "start"):
            self._start_raid_watch()
            await ctx.send(f"🛡️ Raid watch **ON** for {RAID_WATCH_MINUTES} minutes.")
        elif state.lower() in ("off", "disable", "stop"):
            self._raid_watch_until = 0.0
            self._burst_members.clear()
            await ctx.send("🛡️ Raid watch **OFF**.")
        else:
            await ctx.send("Use `#raidmode on` or `#raidmode off`.")

    @commands.command(name="raidstatus")
    @commands.has_permissions(moderate_members=True)
    async def raidstatus(self, ctx):
        now = time.monotonic()
        recent_joins = sum(1 for ts, _ in self._joins if now - ts <= JOIN_BURST_SECONDS)
        await ctx.send(
            f"**Raid watch:** {'ON' if self.raid_watch_active else 'OFF'}\n"
            f"**Joins in last {JOIN_BURST_SECONDS}s:** {recent_joins} "
            f"(alerts at {JOIN_BURST_COUNT})\n"
            f"**Tracked messages:** {len(self._recent)}\n"
            f"**Burst arrivals being watched:** {len(self._burst_members)}"
        )


async def setup(bot):
    await bot.add_cog(RaidGuard(bot))
