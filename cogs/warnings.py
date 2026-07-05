import discord
from discord.ext import commands
import time
import datetime

# Number of warnings -> timeout minutes applied automatically on reaching it.
ESCALATION = {
    3: 10,   # 3rd warning -> 10 minute timeout
    5: 60,   # 5th warning -> 1 hour timeout
}


def is_mod():
    """Allow bot owners or members with moderation permissions."""
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        perms = getattr(ctx.author, "guild_permissions", None)
        return bool(perms and (perms.moderate_members or perms.kick_members or perms.administrator))
    return commands.check(predicate)


class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="warn", description="Warn a member")
    @commands.guild_only()
    @is_mod()
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member.bot:
            await ctx.send("You can't warn a bot.")
            return
        if member.id == ctx.author.id:
            await ctx.send("You can't warn yourself.")
            return

        await self.bot.db.execute(
            "INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (member.id, ctx.guild.id, ctx.author.id, reason, int(time.time()))
        )
        await self.bot.db.commit()

        async with self.bot.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?",
            (member.id, ctx.guild.id)
        ) as cursor:
            (count,) = await cursor.fetchone()

        embed = discord.Embed(title="⚠️ Member Warned", color=discord.Color.orange())
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=True)
        embed.add_field(name="Total Warnings", value=str(count), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

        # Best-effort DM to the warned member.
        try:
            await member.send(
                f"You were warned in **{ctx.guild.name}**.\n"
                f"**Reason:** {reason}\n**Warning #{count}**"
            )
        except discord.HTTPException:
            pass

        # Auto-escalation.
        minutes = ESCALATION.get(count)
        if minutes:
            try:
                await member.timeout(
                    datetime.timedelta(minutes=minutes),
                    reason=f"Reached {count} warnings"
                )
                await ctx.send(
                    f"🚨 {member.mention} reached **{count}** warnings and was "
                    f"timed out for **{minutes} minutes**."
                )
            except discord.Forbidden:
                await ctx.send(
                    "⚠️ I couldn't time out this member (missing permission or their "
                    "role is above mine)."
                )
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="warnings", description="List a member's warnings")
    @commands.guild_only()
    @is_mod()
    async def warnings(self, ctx, member: discord.Member):
        async with self.bot.db.execute(
            "SELECT id, moderator_id, reason, timestamp FROM warnings "
            "WHERE user_id = ? AND guild_id = ? ORDER BY id DESC",
            (member.id, ctx.guild.id)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send(f"✅ {member.display_name} has no warnings.")
            return

        embed = discord.Embed(
            title=f"⚠️ Warnings for {member.display_name}",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Total: {len(rows)}")
        for wid, mod_id, reason, ts in rows[:15]:
            embed.add_field(
                name=f"#{wid} • by <@{mod_id}> • <t:{ts}:R>",
                value=reason or "No reason provided",
                inline=False
            )
        if len(rows) > 15:
            embed.description = f"Showing the 15 most recent of {len(rows)}."
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="clearwarns", description="Clear all warnings for a member")
    @commands.guild_only()
    @is_mod()
    async def clearwarns(self, ctx, member: discord.Member):
        async with self.bot.db.execute(
            "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?",
            (member.id, ctx.guild.id)
        ) as cursor:
            (count,) = await cursor.fetchone()

        if not count:
            await ctx.send(f"{member.display_name} has no warnings to clear.")
            return

        await self.bot.db.execute(
            "DELETE FROM warnings WHERE user_id = ? AND guild_id = ?",
            (member.id, ctx.guild.id)
        )
        await self.bot.db.commit()
        await ctx.send(f"🧹 Cleared **{count}** warning(s) for {member.mention}.")

    @commands.hybrid_command(name="delwarn", description="Delete a single warning by its ID")
    @commands.guild_only()
    @is_mod()
    async def delwarn(self, ctx, warning_id: int):
        async with self.bot.db.execute(
            "SELECT user_id FROM warnings WHERE id = ? AND guild_id = ?",
            (warning_id, ctx.guild.id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await ctx.send("No warning with that ID in this server.")
            return

        await self.bot.db.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        await self.bot.db.commit()
        await ctx.send(f"🗑️ Removed warning #{warning_id}.")


async def setup(bot):
    await bot.add_cog(Warnings(bot))
