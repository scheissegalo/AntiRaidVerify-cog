"""Verification embeds, persistent views, and verification flow."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

import discord

from .constants import COLOR_INFO, VERIFY_CUSTOM_ID
from .models import GuildSettings, PendingVerification, ScoreResult
from .quarantine import SetupError

if TYPE_CHECKING:
    from .antiraidverify import AntiRaidVerify


def build_verification_embed(
    member: discord.Member,
    score: ScoreResult,
    expires_at: float,
) -> discord.Embed:
    """Build the verification prompt embed shown in the quarantine channel."""
    deadline_dt = discord.utils.utcnow() + timedelta(seconds=max(0, expires_at - time.time()))
    deadline = discord.utils.format_dt(deadline_dt, style="R")

    embed = discord.Embed(
        title="Account Verification Required",
        description=(
            f"{member.mention}, your account triggered our anti-spam protection.\n\n"
            "Please press **Verify Account** below to confirm you are human and gain "
            "access to the server."
        ),
        color=COLOR_INFO,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(
        name="Why was I flagged?",
        value=(
            "New or suspicious-looking accounts are temporarily restricted to prevent raids."
        ),
        inline=False,
    )
    if score.factors:
        factors_text = ", ".join(name.replace("_", " ") for name in score.factors)
        embed.add_field(name="Signals detected", value=factors_text, inline=False)
    embed.add_field(name="Verify before", value=deadline, inline=False)
    embed.set_footer(text="AntiRaidVerify • Only you can press this button")
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    return embed


def build_verified_embed(member: discord.Member) -> discord.Embed:
    return discord.Embed(
        title="Verified",
        description=f"{member.mention} has been verified.",
        color=0x2ECC71,
        timestamp=discord.utils.utcnow(),
    )


class VerifyView(discord.ui.View):
    """Persistent verification button view."""

    def __init__(self, cog: "AntiRaidVerify") -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Verify Account",
        style=discord.ButtonStyle.green,
        custom_id=VERIFY_CUSTOM_ID,
    )
    async def verify_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self.cog.handle_verification(interaction)


class VerificationManager:
    """Create verification messages and process verification requests."""

    def __init__(self, cog: "AntiRaidVerify") -> None:
        self.cog = cog

    async def send_verification_message(
        self,
        member: discord.Member,
        settings: GuildSettings,
        score: ScoreResult,
    ) -> PendingVerification:
        if await self.cog.storage.is_pending(member.guild.id, member.id):
            existing = await self.cog.storage.get_pending(member.guild.id, member.id)
            if existing is not None:
                return existing

        channel = self.cog.quarantine.get_verification_channel(member.guild, settings)
        if channel is None:
            raise SetupError("Verification channel is not configured.")

        joined_at = time.time()
        expires_at = joined_at + (settings.timeout_hours * 3600)
        embed = build_verification_embed(member, score, expires_at)

        try:
            message = await channel.send(content=member.mention, embed=embed, view=self.cog.verify_view)
        except discord.HTTPException as exc:
            raise SetupError(f"Failed to send verification message: {exc}") from exc

        pending = PendingVerification(
            guild_id=member.guild.id,
            user_id=member.id,
            message_id=message.id,
            channel_id=channel.id,
            score=score.total,
            factors=score.factors,
            joined_at=joined_at,
            expires_at=expires_at,
        )
        await self.cog.storage.save_pending(pending)
        return pending

    async def cleanup_message(
        self,
        guild: discord.Guild,
        pending: PendingVerification,
        settings: GuildSettings,
        *,
        verified: bool = False,
        member: Optional[discord.Member] = None,
    ) -> None:
        channel = guild.get_channel(pending.channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            message = await channel.fetch_message(pending.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        try:
            if settings.cleanup_verification_messages:
                await message.delete()
            elif verified and member is not None:
                await message.edit(embed=build_verified_embed(member), view=None)
            else:
                await message.edit(content="Verification expired.", embed=None, view=None)
        except discord.HTTPException:
            pass

    async def process_verification(
        self,
        interaction: discord.Interaction,
        *,
        manual: bool = False,
        moderator: Optional[discord.Member] = None,
    ) -> None:
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message(
                "This button can only be used in a server.", ephemeral=True
            )
            return

        lookup = await self.cog.storage.lookup_by_message(interaction.message.id)
        if lookup is None:
            await interaction.response.send_message(
                "This verification session is no longer active.", ephemeral=True
            )
            return

        guild_id, target_user_id = lookup

        if interaction.guild.id != guild_id:
            await interaction.response.send_message(
                "This verification belongs to another server.", ephemeral=True
            )
            return

        if not manual:
            if interaction.user.id != target_user_id:
                await interaction.response.send_message(
                    "You can only verify your own account.", ephemeral=True
                )
                return
            if interaction.user.bot:
                await interaction.response.send_message(
                    "Bots cannot verify.", ephemeral=True
                )
                return

            cooldown = self.cog.verify_cooldowns.get(target_user_id, 0)
            settings = await self.cog.storage.get_guild_settings(guild_id)
            if time.time() - cooldown < settings.verify_cooldown_seconds:
                await interaction.response.send_message(
                    "Please wait before trying again.", ephemeral=True
                )
                return
            self.cog.verify_cooldowns[target_user_id] = time.time()

        pending = await self.cog.storage.get_pending(guild_id, target_user_id)
        if pending is None:
            await interaction.response.send_message(
                "No pending verification found for this message.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        member = interaction.guild.get_member(target_user_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(target_user_id)
            except discord.NotFound:
                await self.cog.storage.clear_pending(guild_id, target_user_id)
                await interaction.followup.send(
                    "Member is no longer in the server.", ephemeral=True
                )
                return

        settings = await self.cog.storage.get_guild_settings(guild_id)

        try:
            await self.cog.quarantine.release_quarantine(member, settings)
        except SetupError as exc:
            await interaction.followup.send(
                f"Verification failed: {exc.message}", ephemeral=True
            )
            await self.cog.event_logger.log_error(interaction.guild, "verify roles", exc)
            return

        await self.cog.storage.clear_pending(guild_id, target_user_id)
        await self.cleanup_message(interaction.guild, pending, settings, verified=True, member=member)
        await self.cog.event_logger.log_verification_success(
            interaction.guild, member, pending, manual=manual, moderator=moderator
        )

        if manual:
            await interaction.followup.send(
                f"{member.mention} has been manually verified.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "You have been verified! Welcome to the server.", ephemeral=True
            )
