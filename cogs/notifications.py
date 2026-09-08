"""Opt-in notification roles.

Upload and live alerts used to fire @everyone. On a server this size that is
the fastest way to get people to mute the server outright — and a muted member
never sees the next announcement either. These roles invert it: only people who
asked for the ping get it, so the ping actually reaches an audience that wants
it.

Post the self-assign panel once with `#notifypanel` in whatever channel you use
for roles. The panel is persistent: its buttons keep working across restarts,
so you never have to re-post it.
"""

import discord
from discord.ext import commands
import logging
import os

UPLOAD_ROLE_ID = int(os.getenv("UPLOAD_ROLE", 1546795007040552990))
STREAM_ROLE_ID = int(os.getenv("STREAM_ROLE", 1546795078931062825))


def role_mention(guild, role_id):
    """Ping text for an announcement, or "" when the role is missing.

    Deliberately never falls back to @everyone — a deleted role should make an
    announcement quiet, not make it ping the whole server.
    """
    if not guild or not role_id:
        return ""
    role = guild.get_role(role_id)
    if role is None:
        logging.warning("Notification role %s not found in %s", role_id, guild.id)
        return ""
    return role.mention


class NotificationRolesView(discord.ui.View):
    """Persistent view — timeout=None plus fixed custom_ids means the buttons
    survive a bot restart without the panel needing to be re-posted."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _toggle(self, interaction, role_id, label):
        role = interaction.guild.get_role(role_id) if interaction.guild else None
        if role is None:
            await interaction.response.send_message(
                "That role doesn't exist any more — please tell an admin.",
                ephemeral=True,
            )
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Self-assigned notification role")
                await interaction.response.send_message(
                    f"🔕 Removed **{label}**. You won't be pinged any more.",
                    ephemeral=True,
                )
            else:
                await member.add_roles(role, reason="Self-assigned notification role")
                await interaction.response.send_message(
                    f"🔔 You've got **{label}**! You'll be pinged from now on.",
                    ephemeral=True,
                )
        except discord.Forbidden:
            # Almost always the role hierarchy rather than a missing permission.
            await interaction.response.send_message(
                "I can't manage that role. An admin needs to drag my role above "
                "it in Server Settings → Roles.",
                ephemeral=True,
            )
        except discord.HTTPException:
            logging.exception("Failed to toggle notification role")
            await interaction.response.send_message(
                "Something went wrong — try again in a moment.", ephemeral=True
            )

    @discord.ui.button(
        label="Upload Squad",
        emoji="🎥",
        style=discord.ButtonStyle.secondary,
        custom_id="notify:upload",
    )
    async def upload(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, UPLOAD_ROLE_ID, "Upload Squad")

    @discord.ui.button(
        label="Stream Squad",
        emoji="🔴",
        style=discord.ButtonStyle.secondary,
        custom_id="notify:stream",
    )
    async def stream(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._toggle(interaction, STREAM_ROLE_ID, "Stream Squad")


class Notifications(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        # Registering the view here (not on the panel message) is what makes
        # the buttons keep working after a restart.
        self.bot.add_view(NotificationRolesView())

    @commands.command(name="notifypanel")
    @commands.is_owner()
    async def notifypanel(self, ctx):
        """Post the role self-assign panel. Run once, in your roles channel."""
        embed = discord.Embed(
            title="🔔 Get notified",
            description=(
                "Pick what you want to be pinged for. Click again to turn it off.\n\n"
                "🎥 **Upload Squad** — new YouTube videos\n"
                "🔴 **Stream Squad** — going live on Kick"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Only people with the role get pinged — no more @everyone.")
        await ctx.send(embed=embed, view=NotificationRolesView())

    @commands.command(name="notifycount")
    @commands.is_owner()
    async def notifycount(self, ctx):
        """How many people opted in — useful for judging announcement reach."""
        lines = []
        for role_id, label in ((UPLOAD_ROLE_ID, "Upload Squad"), (STREAM_ROLE_ID, "Stream Squad")):
            role = ctx.guild.get_role(role_id)
            lines.append(
                f"**{label}**: {len(role.members)} member(s)" if role
                else f"**{label}**: ⚠️ role not found (`{role_id}`)"
            )
        await ctx.send("\n".join(lines))


async def setup(bot):
    await bot.add_cog(Notifications(bot))
