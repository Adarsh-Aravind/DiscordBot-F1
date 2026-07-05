import discord
from discord.ext import commands
import random
import math

OWNER_ID = 615174036733034538


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        xp_gain = random.randint(5, 10)

        async with self.bot.db.execute(
            "SELECT xp, level FROM levels WHERE user_id = ?",
            (message.author.id,)
        ) as cursor:
            row = await cursor.fetchone()

        xp, level = row if row else (0, 0)
        xp += xp_gain

        new_level = int(math.sqrt(xp) // 10)
        leveled_up = new_level > level
        if leveled_up:
            level = new_level

        # Single upsert handles both new and existing users (no redundant
        # INSERT + UPDATE for first-time messagers).
        await self.bot.db.execute(
            "INSERT INTO levels (user_id, xp, level) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET xp = excluded.xp, level = excluded.level",
            (message.author.id, xp, level)
        )
        await self.bot.db.commit()

        # 🔥 Level Up Notification (after the write is committed)
        if leveled_up:
            await message.channel.send(
                f"🎉 **{message.author.name}** has reached level **{level}**!"
            )

    @commands.command()
    async def rank(self, ctx):
        async with self.bot.db.execute(
            "SELECT xp, level FROM levels WHERE user_id = ?",
            (ctx.author.id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await ctx.send("No data yet.")
            return

        xp, level = row
        await ctx.send(f"Level: {level} | XP: {xp}")

    @commands.command()
    async def levelreset(self, ctx, user: discord.Member = None):
        if ctx.author.id != OWNER_ID:
            return

        if user:
            await self.bot.db.execute(
                "DELETE FROM levels WHERE user_id = ?",
                (user.id,)
            )
        else:
            await self.bot.db.execute("DELETE FROM levels")

        await self.bot.db.commit()
        await ctx.send("Levels reset.")


async def setup(bot):
    await bot.add_cog(Leveling(bot))