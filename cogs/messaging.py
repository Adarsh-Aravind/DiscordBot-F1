import discord
from discord.ext import commands

OWNER_ID = 615174036733034538

class Messaging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if isinstance(message.channel, discord.DMChannel):
            # Prefer the cache; only hit the API if the owner isn't cached.
            owner = self.bot.get_user(OWNER_ID) or await self.bot.fetch_user(OWNER_ID)

            embed = discord.Embed(
                title=f"📩 DM from {message.author}",
                description=message.content or "*No text*",
                color=discord.Color.gold()
            )

            if message.attachments:
                embed.add_field(
                    name="Attachments",
                    value="\n".join(a.url for a in message.attachments),
                    inline=False
                )

            await owner.send(embed=embed)

    @commands.command()
    async def reply(self, ctx, user_id: int, *, content):
        if ctx.author.id != OWNER_ID:
            return

        user = await self.bot.fetch_user(user_id)
        await user.send(content)
        await ctx.send("Sent.")

    @commands.command()
    async def say(self, ctx, channel_id: int, *, content):
        if ctx.author.id != OWNER_ID:
            return

        channel = await self.bot.fetch_channel(channel_id)
        await channel.send(content)
        await ctx.send("Message sent.")

async def setup(bot):
    await bot.add_cog(Messaging(bot))