import discord
from discord.ext import commands
import asyncio
import logging
import os
import time

# Primary owner: DMs sent to the bot are relayed to this user.
OWNER_ID = int(os.getenv("RELAY_OWNER", 615174036733034538))

# Anyone who can find the bot can DM it, and every DM pings the owner. Rather
# than dropping rapid messages (which loses the sender's actual question and
# tells nobody), buffer them and relay the batch once the window expires: the
# owner gets at most one ping per window and still sees every message.
RELAY_COOLDOWN_SECONDS = 10

# Hard ceiling on a single user's buffer. Past this we count overflow instead
# of storing it, and say so in the relay, so a flood can't grow memory.
MAX_BUFFERED_MESSAGES = 20

# Forget per-user relay timestamps this long after their last DM.
STATE_TTL_SECONDS = 3600

# Only bother sweeping the timestamp map once it has grown past this many users.
SWEEP_THRESHOLD = 500


class Messaging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_relay = {}    # user_id -> monotonic timestamp of last relay
        self._pending = {}       # user_id -> [formatted message, ...]
        self._overflow = {}      # user_id -> count of messages past the cap
        self._flush_tasks = {}   # user_id -> asyncio.Task

    def cog_unload(self):
        # Copy first: each cancelled task pops itself from the dict.
        for task in list(self._flush_tasks.values()):
            task.cancel()

    def _sweep(self, now):
        """Drop timestamps for users who haven't DMed in a while, so the dict
        doesn't accumulate an entry for every user who ever messaged the bot."""
        if len(self._last_relay) < SWEEP_THRESHOLD:
            return
        stale = [
            uid for uid, ts in self._last_relay.items()
            if now - ts > STATE_TTL_SECONDS and uid not in self._pending
        ]
        for uid in stale:
            del self._last_relay[uid]

    @staticmethod
    def _format(message):
        """One DM rendered as a text block, attachments included."""
        parts = [message.content.strip() or "*No text*"]
        if message.attachments:
            parts.extend(a.url for a in message.attachments)
        return "\n".join(parts)

    def _build_embed(self, author, blocks, overflow):
        if len(blocks) == 1:
            title = f"📩 DM from {author}"
            body = blocks[0]
        else:
            title = f"📩 {len(blocks)} DMs from {author}"
            body = "\n\n".join(f"**{i}.** {b}" for i, b in enumerate(blocks, 1))

        if overflow:
            body += f"\n\n*…and {overflow} more sent too quickly to include.*"

        embed = discord.Embed(
            title=title,
            description=body[:4000],
            color=discord.Color.gold()
        )
        # Included so `#reply <id> ...` can be copy-pasted straight back.
        embed.set_footer(text=f"User ID: {author.id}")
        return embed

    async def _send_to_owner(self, embed):
        try:
            owner = self.bot.get_user(OWNER_ID) or await self.bot.fetch_user(OWNER_ID)
            await owner.send(embed=embed)
        except discord.HTTPException:
            # Owner has DMs closed or the relay failed; don't kill the listener.
            logging.exception("Failed to relay a DM to the owner")

    async def _flush_later(self, author, delay):
        """Wait out the remaining cooldown, then relay everything buffered."""
        try:
            await asyncio.sleep(delay)
            blocks = self._pending.pop(author.id, [])
            overflow = self._overflow.pop(author.id, 0)
            if blocks:
                self._last_relay[author.id] = time.monotonic()
                await self._send_to_owner(self._build_embed(author, blocks, overflow))
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Failed to flush buffered DMs")
        finally:
            self._flush_tasks.pop(author.id, None)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not isinstance(message.channel, discord.DMChannel):
            return

        # An owner's own DMs to the bot don't need relaying back to them.
        if await self.bot.is_owner(message.author):
            return

        author = message.author
        now = time.monotonic()
        self._sweep(now)

        last = self._last_relay.get(author.id)
        if last is None or now - last >= RELAY_COOLDOWN_SECONDS:
            self._last_relay[author.id] = now
            await self._send_to_owner(
                self._build_embed(author, [self._format(message)], 0)
            )
            return

        # Inside the cooldown: buffer rather than discard.
        buffered = self._pending.setdefault(author.id, [])
        if len(buffered) < MAX_BUFFERED_MESSAGES:
            buffered.append(self._format(message))
        else:
            self._overflow[author.id] = self._overflow.get(author.id, 0) + 1

        if author.id not in self._flush_tasks:
            delay = RELAY_COOLDOWN_SECONDS - (now - last)
            self._flush_tasks[author.id] = asyncio.create_task(
                self._flush_later(author, delay)
            )

    @commands.command()
    @commands.is_owner()
    async def reply(self, ctx, user_id: int, *, content):
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(content)
        except discord.NotFound:
            await ctx.send("❌ No user with that ID.")
            return
        except discord.Forbidden:
            await ctx.send("❌ Can't DM that user (DMs closed or no shared server).")
            return
        await ctx.send(f"✅ Sent to **{user}**.")

    @commands.command()
    @commands.is_owner()
    async def say(self, ctx, channel_id: int, *, content):
        try:
            channel = await self.bot.fetch_channel(channel_id)
        except discord.NotFound:
            await ctx.send("❌ No channel with that ID.")
            return
        except discord.Forbidden:
            await ctx.send("❌ I can't see that channel.")
            return

        # Categories, voice-without-chat and forum channels have no send().
        if not hasattr(channel, "send"):
            await ctx.send("❌ That channel can't receive messages.")
            return

        try:
            await channel.send(content)
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to post in that channel.")
            return
        await ctx.send(f"✅ Message sent to {getattr(channel, 'mention', channel_id)}.")


async def setup(bot):
    await bot.add_cog(Messaging(bot))
