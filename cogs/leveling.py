import discord
from discord.ext import commands
import random
import math
import time

# Minimum seconds between two XP-earning messages from the same user. Without
# this, XP tracks raw message count (rewarding one-word spam) and every single
# message costs a database write.
XP_COOLDOWN_SECONDS = 60

# Messages shorter than this earn nothing — stops "a", "b", "c" farming.
MIN_MESSAGE_LENGTH = 3

# Level thresholds -> role id awarded on reaching that level.
# Roles are cumulative (a Beast keeps Regular too). Adjust freely.
LEVEL_ROLES = {
    5: 1523428756453199932,   # Regular
    20: 1523428877857325166,  # Beast
}


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_xp = {}  # user_id -> monotonic timestamp of last XP award

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

        # Commands shouldn't pay XP, and neither should trivial filler.
        if message.content.startswith(self.bot.command_prefix):
            return
        if len(message.content.strip()) < MIN_MESSAGE_LENGTH:
            return

        now = time.monotonic()
        last = self._last_xp.get(message.author.id)
        if last is not None and now - last < XP_COOLDOWN_SECONDS:
            return
        self._last_xp[message.author.id] = now

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
    @commands.is_owner()
    async def levelreset(self, ctx, target: str = None):
        """`#levelreset @user` resets one member; `#levelreset all` wipes everyone."""
        if target is None:
            await ctx.send(
                "Usage: `#levelreset @user` to reset one member, or "
                "`#levelreset all` to wipe **everyone's** progress."
            )
            return

        if target.lower() == "all":
            async with self.bot.db.execute("SELECT COUNT(*) FROM levels") as cursor:
                (count,) = await cursor.fetchone()
            await self.bot.db.execute("DELETE FROM levels")
            await self.bot.db.commit()
            self._last_xp.clear()
            await ctx.send(f"🧹 Reset levels for **{count}** member(s).")
            return

        try:
            member = await commands.MemberConverter().convert(ctx, target)
        except commands.BadArgument:
            await ctx.send("❌ Couldn't find that member. Use a mention, ID, or `all`.")
            return

        await self.bot.db.execute("DELETE FROM levels WHERE user_id = ?", (member.id,))
        await self.bot.db.commit()
        self._last_xp.pop(member.id, None)
        await ctx.send(f"🧹 Reset levels for {member.mention}.")


async def setup(bot):
    await bot.add_cog(Leveling(bot))
