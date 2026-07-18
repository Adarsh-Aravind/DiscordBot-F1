import discord
from discord.ext import commands
import logging
import time

# Primary owner: DMs sent to the bot are relayed to this user.
OWNER_ID = 615174036733034538

# Anyone who can find the bot can DM it, and every DM pings the owner. Limit
# how often a single user's DMs get relayed so the owner can't be flooded.
RELAY_COOLDOWN_SECONDS = 10


class Messaging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_relay = {}  # user_id -> monotonic timestamp

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not isinstance(message.channel, discord.DMChannel):
            return

        # The owner's own DMs to the bot don't need relaying back to them.
        if message.author.id == OWNER_ID:
            return

        now = time.monotonic()
        last = self._last_relay.get(message.author.id)
        if last is not None and now - last < RELAY_COOLDOWN_SECONDS:
            return
        self._last_relay[message.author.id] = now

        embed = discord.Embed(
            title=f"📩 DM from {message.author}",
            description=(message.content or "*No text*")[:4000],
            color=discord.Color.gold()
        )
        # Included so `#reply <id> ...` can be copy-pasted straight back.
        embed.set_footer(text=f"User ID: {message.author.id}")

        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.url for a in message.attachments)[:1024],
                inline=False
            )

        try:
            owner = self.bot.get_user(OWNER_ID) or await self.bot.fetch_user(OWNER_ID)
            await owner.send(embed=embed)
        except discord.HTTPException:
            # Owner has DMs closed or the relay failed; don't kill the listener.
            logging.exception("Failed to relay a DM to the owner")

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
            await channel.send(content)
        except discord.NotFound:
            await ctx.send("❌ No channel with that ID.")
            return
        except discord.Forbidden:
            await ctx.send("❌ I don't have permission to post in that channel.")
            return
        await ctx.send(f"✅ Message sent to {getattr(channel, 'mention', channel_id)}.")

async def setup(bot):
    await bot.add_cog(Messaging(bot))