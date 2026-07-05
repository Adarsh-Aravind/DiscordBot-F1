import os
import logging
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import aiosqlite

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True

# Both server owners/operators. is_owner() recognises either of these.
OWNER_IDS = {615174036733034538, 506838802317443072}

bot = commands.Bot(
    command_prefix="#",
    intents=intents,
    help_command=None,
    owner_ids=OWNER_IDS
)

@bot.event
async def setup_hook():
    bot.db = await aiosqlite.connect("database.db")

    # WAL + relaxed sync: leveling writes on every message, so avoid an fsync
    # per commit. WAL keeps concurrent reads fast; synchronous=NORMAL stays
    # durable across app crashes (only risks the last commit on OS/power loss).
    await bot.db.execute("PRAGMA journal_mode=WAL")
    await bot.db.execute("PRAGMA synchronous=NORMAL")

    await bot.db.execute("""
    CREATE TABLE IF NOT EXISTS levels (
        user_id INTEGER PRIMARY KEY,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 0
    )
    """)

    await bot.db.execute("""
    CREATE TABLE IF NOT EXISTS youtube (
        channel_id TEXT PRIMARY KEY,
        last_video TEXT
    )
    """)

    await bot.db.execute("""
    CREATE TABLE IF NOT EXISTS youtube_history (
        channel_id TEXT,
        video_id TEXT,
        PRIMARY KEY (channel_id, video_id)
    )
    """)

    await bot.db.execute("""
    CREATE TABLE IF NOT EXISTS kick_streams (
        slug TEXT PRIMARY KEY,
        last_stream_id TEXT
    )
    """)

    await bot.db.execute("""
    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        moderator_id INTEGER NOT NULL,
        reason TEXT,
        timestamp INTEGER NOT NULL
    )
    """)

    await bot.db.execute("""
    CREATE TABLE IF NOT EXISTS milestones (
        platform TEXT NOT NULL,
        identifier TEXT NOT NULL,
        last_milestone INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (platform, identifier)
    )
    """)

    # Migrate existing last_video to history to avoid re-notifying
    await bot.db.execute("""
    INSERT OR IGNORE INTO youtube_history (channel_id, video_id)
    SELECT channel_id, last_video FROM youtube WHERE last_video IS NOT NULL
    """)

    await bot.db.commit()

    for ext in [
        "cogs.general",
        "cogs.messaging",
        "cogs.leveling",
        "cogs.antispam",
        "cogs.youtube",
        "cogs.kick",
        "cogs.f1",
        "cogs.warnings",
        "cogs.milestones"
    ]:
        await bot.load_extension(ext)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# 🔥 ONLY ONE PLACE PROCESSING COMMANDS
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

# ---------------------------------------------------------------------------
# Global error handling
# ---------------------------------------------------------------------------
@bot.event
async def on_command_error(ctx, error):
    # Unwrap errors raised inside command bodies
    error = getattr(error, "original", error)

    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`. See `#help`.")
        return
    if isinstance(error, (commands.BadArgument, commands.UserInputError)):
        await ctx.send("❌ Invalid input. Please check the command and try again.")
        return
    if isinstance(error, commands.MissingPermissions) or isinstance(error, commands.CheckFailure):
        await ctx.send("🚫 You don't have permission to use this command.")
        return
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Slow down! Try again in {error.retry_after:.1f}s.")
        return
    if isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command can only be used in a server.")
        return

    logging.exception("Unhandled command error", exc_info=error)
    await ctx.send("⚠️ Something went wrong running that command.")


async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    if isinstance(error, app_commands.CheckFailure) or isinstance(original, commands.CheckFailure):
        msg = "🚫 You don't have permission to use this command."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"⏳ Slow down! Try again in {error.retry_after:.1f}s."
    else:
        logging.exception("Unhandled app command error", exc_info=error)
        msg = "⚠️ Something went wrong running that command."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass

bot.tree.on_error = on_app_command_error

def run():
    bot.run(TOKEN, reconnect=True)