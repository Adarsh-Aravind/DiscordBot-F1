import discord
from discord.ext import commands
import random
import math

# Level thresholds -> role id awarded on reaching that level.
# Roles are cumulative (a Beast keeps Regular too). Adjust freely.
LEVEL_ROLES = {
    5: 1523428756453199932,   # Regular
    20: 1523428877857325166,  # Beast
}


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _apply_role_rewards(self, member, level):
        """Grant any level-reward roles the member has now earned."""
        if not getattr(member, "guild", None):
            return

        to_add = []
        for threshold, role_id in LEVEL_ROLES.items():
            if level >= threshold:
                role = member.guild.get_role(role_id)
                if role and role not in member.roles:
                    to_add.append(role)

        if not to_add:
            return

        try:
            await member.add_roles(*to_add, reason="Level reward")
        except discord.Forbidden:
            # Bot lacks Manage Roles, or its top role is below the reward role.
            pass
        except discord.HTTPException:
            pass

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
            await self._apply_role_rewards(message.author, level)
            await message.channel.send(
                f"🎉 **{message.author.name}** has reached level **{level}**!"
            )

    @commands.hybrid_command(name="rank", description="Show your (or another member's) level and XP")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author

        async with self.bot.db.execute(
            "SELECT xp, level FROM levels WHERE user_id = ?",
            (member.id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await ctx.send(f"No data yet for {member.display_name}.")
            return

        xp, level = row

        # Rank position = how many users have more XP, +1.
        async with self.bot.db.execute(
            "SELECT COUNT(*) FROM levels WHERE xp > ?",
            (xp,)
        ) as cursor:
            (ahead,) = await cursor.fetchone()

        embed = discord.Embed(title=f"📊 Rank — {member.display_name}", color=discord.Color.blue())
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="XP", value=str(xp), inline=True)
        embed.add_field(name="Position", value=f"#{ahead + 1}", inline=True)
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", aliases=["top"], description="Show the top members by XP")
    async def leaderboard(self, ctx):
        async with self.bot.db.execute(
            "SELECT user_id, xp, level FROM levels ORDER BY xp DESC LIMIT 10"
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("No data yet.")
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (user_id, xp, level) in enumerate(rows):
            rank_str = medals[i] if i < 3 else f"**{i + 1}.**"
            lines.append(f"{rank_str} <@{user_id}> — Level **{level}** ({xp} XP)")

        embed = discord.Embed(
            title="🏆 Leveling Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def levelreset(self, ctx, user: discord.Member = None):
        if not await self.bot.is_owner(ctx.author):
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
