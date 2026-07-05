import discord
from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Show the bot's latency")
    async def ping(self, ctx):
        await ctx.send(f"Pong! {round(self.bot.latency * 1000)}ms")

    @commands.command()
    async def help(self, ctx):
        embed = discord.Embed(
            title="🤖 Bit Beast Bot Commands",
            color=discord.Color.blue()
        )

        embed.add_field(name="🏎️ F1 Commands", value="`#f1` - Shows current season info (Drivers, Constructors, Next Race)\n`#f1next` - Shows info and a picture of the next race circuit\n`#f1last` - Shows info and results of the latest race\n`#f1c {circuit}` - Shows information and previous winner for a specific circuit\n`#f1con` - Shows only constructor standings\n`#f1dri` - Shows only driver standings", inline=False)
        embed.add_field(name="📊 Leveling", value="`#rank [@user]` - Show level, XP and position\n`#leaderboard` (`#top`) - Top 10 members by XP", inline=False)
        embed.add_field(name="🛡️ Moderation", value="`#warn @user [reason]` - Warn a member\n`#warnings @user` - List a member's warnings\n`#clearwarns @user` - Clear all warnings\n`#delwarn <id>` - Remove a single warning", inline=False)
        embed.add_field(name="⚙️ General", value="`#status` - Shows the status of the server\n`#ping` - Shows the bot's latency\n*Most commands also work as `/` slash commands.*", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    async def status(self, ctx):
        # Shows status of the server
        guild = ctx.guild
        if not guild:
            await ctx.send("This command can only be used in a server.")
            return
            
        embed = discord.Embed(title=f"Server Status: {guild.name}", color=discord.Color.green())
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Created At", value=guild.created_at.strftime("%d %b %Y"), inline=False)
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        await ctx.send(embed=embed)

    @commands.command(name="sync")
    async def sync(self, ctx):
        """Register slash commands. Run once (owner only) after deploying."""
        if not await self.bot.is_owner(ctx.author):
            return

        if ctx.guild:
            # Guild sync is instant (global sync can take up to an hour).
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
        else:
            synced = await self.bot.tree.sync()

        await ctx.send(f"✅ Synced {len(synced)} slash command(s).")

    @commands.command(name="setpresence")
    async def set_presence(self, ctx, activity_type: str, *, text: str):
        if not await self.bot.is_owner(ctx.author):
            return

        activity_type = activity_type.lower()

        if activity_type == "playing":
            activity = discord.Game(name=text)
        elif activity_type == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        elif activity_type == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=text)
        elif activity_type == "competing":
            activity = discord.Activity(type=discord.ActivityType.competing, name=text)
        else:
            await ctx.send("Invalid type.")
            return

        await self.bot.change_presence(activity=activity)
        await ctx.send("Status updated.")

async def setup(bot):
    await bot.add_cog(General(bot))