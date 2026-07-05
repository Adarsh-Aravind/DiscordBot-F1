import os
import logging
import discord
from discord.ext import commands
from dotenv import load_dotenv
import aiosqlite

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="#",
    intents=intents,
    help_command=None
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
        "cogs.f1"
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

def run():
    bot.run(TOKEN, reconnect=True)