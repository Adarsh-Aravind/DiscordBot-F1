"""Shared mod-alert helper.

The server's modlog is handled by other bots, so this is deliberately narrow:
it is only for things this bot decides on its own and a human needs to see —
scam links it removed, and raids it reacted to. Nothing routine goes here, so
a message in the alert channel always means "look at this".
"""

import discord
import logging
import os

def _channel_id():
    """Alert channel, falling back to the Kick error log so alerts always land
    somewhere. An unset OR zero value both mean "use the fallback" — a literal
    ALERT_CHANNEL=0 in .env would otherwise route every scam and raid alert
    into a channel that doesn't exist, and drop them silently."""
    for name in ("ALERT_CHANNEL", "LOGGING_CHANNEL"):
        try:
            value = int(os.getenv(name, 0))
        except ValueError:
            value = 0
        if value:
            return value
    return 830364694916890674


ALERT_CHANNEL_ID = _channel_id()

# Optional role to ping for raid-level events. Left unset, alerts stay quiet.
MOD_PING_ROLE_ID = int(os.getenv("MOD_PING_ROLE", 0))


async def send_alert(bot, text, ping_mods=False, guild=None):
    """Post a mod alert. Never raises — an alert failing must not take down
    the filter that raised it."""
    logging.warning("ALERT: %s", text)

    channel = bot.get_channel(ALERT_CHANNEL_ID)
    if channel is None:
        return

    content = text
    if ping_mods and MOD_PING_ROLE_ID:
        target = guild or getattr(channel, "guild", None)
        role = target.get_role(MOD_PING_ROLE_ID) if target else None
        if role:
            content = f"{role.mention} {text}"

    try:
        await channel.send(
            content[:2000],
            allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
        )
    except discord.HTTPException:
        logging.exception("Failed to post mod alert")
