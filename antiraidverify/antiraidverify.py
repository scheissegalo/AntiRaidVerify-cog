"""Main AntiRaidVerify cog."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

import discord
from redbot.core import commands

from .commands.admin import AdminCommands
from .logging import EventLogger
from .massjoin import MassJoinTracker
from .models import ScoreResult
from .quarantine import QuarantineManager, SetupError
from .scoring import score_member
from .storage import Storage
from .timeout import TimeoutManager
from .verification import VerificationManager, VerifyView

log = logging.getLogger("red.antiraidverify")


class AntiRaidVerify(AdminCommands, commands.Cog):
    """Detect suspicious joins and quarantine members until verified.

    AdminCommands is a plain Python mixin; commands.Cog must remain the final
    base class so Red registers listeners and command metadata correctly.
    """

    __version__ = "1.0.0"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.storage = Storage(self)
        self.event_logger = EventLogger(self.storage)
        self.quarantine = QuarantineManager(self.storage, self.event_logger)
        self.mass_join_tracker = MassJoinTracker()
        self.verify_cooldowns: Dict[int, float] = {}
        self.verify_view: VerifyView | None = None
        self.verification: VerificationManager | None = None
        self.timeout_manager: TimeoutManager | None = None
        self._timeout_task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        self.verify_view = VerifyView(self)
        self.verification = VerificationManager(self)
        self.timeout_manager = TimeoutManager(self)
        self.bot.add_view(self.verify_view)
        await self.storage.reconcile_pending_messages(self)
        self._timeout_task = asyncio.create_task(self.timeout_manager.run())
        log.info("AntiRaidVerify loaded; persistent verification view registered.")

    async def cog_unload(self) -> None:
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or member.guild is None:
            return

        guild = member.guild
        if not await self.storage.is_enabled(guild.id):
            return

        settings = await self.storage.get_guild_settings(guild.id)
        if self.quarantine.member_has_whitelist_role(member, settings):
            return

        self.mass_join_tracker.record_join(guild.id)
        mass_join = self.mass_join_tracker.is_mass_join(
            guild.id,
            settings.mass_join_threshold,
            settings.mass_join_window_seconds,
        )

        score = score_member(member, settings)
        effective_threshold = self.mass_join_tracker.effective_threshold(
            settings.score_threshold, mass_join
        )
        if score.total < effective_threshold:
            return

        await self._quarantine_member(
            member,
            settings,
            score,
            mass_join=mass_join,
        )

    async def _quarantine_member(
        self,
        member: discord.Member,
        settings,
        score: ScoreResult,
        *,
        mass_join: bool = False,
        moderator: discord.Member | None = None,
        manual: bool = False,
    ) -> None:
        if self.verification is None:
            return

        if await self.storage.is_pending(member.guild.id, member.id):
            return

        try:
            await self.quarantine.apply_quarantine(member, settings)
        except SetupError as exc:
            await self.event_logger.log_error(member.guild, "quarantine", exc)
            return

        try:
            pending = await self.verification.send_verification_message(
                member, settings, score
            )
        except SetupError as exc:
            await self.event_logger.log_error(member.guild, "verification message", exc)
            return

        if manual and moderator:
            await self.event_logger.log_manual_quarantine(member.guild, member, moderator)
        else:
            await self.event_logger.log_suspicious_join(
                member.guild, member, score, mass_join=mass_join
            )

        log.info(
            "Quarantined %s in guild %s (score=%s, expires=%s)",
            member.id,
            member.guild.id,
            pending.score,
            pending.expires_at,
        )

    async def handle_verification(self, interaction: discord.Interaction) -> None:
        if self.verification is None:
            await interaction.response.send_message(
                "Verification is unavailable right now.", ephemeral=True
            )
            return
        await self.verification.process_verification(interaction)

    async def manual_verify(
        self,
        ctx: commands.Context,
        member: discord.Member,
    ) -> None:
        if self.verification is None:
            await ctx.send("Verification manager is not ready.")
            return

        pending = await self.storage.get_pending(ctx.guild.id, member.id)
        if pending is None:
            settings = await self.storage.get_guild_settings(ctx.guild.id)
            try:
                await self.quarantine.release_quarantine(member, settings)
            except SetupError as exc:
                await ctx.send(f"Failed to verify: {exc.message}")
                return
            await self.event_logger.log_verification_success(
                ctx.guild, member, None, manual=True, moderator=ctx.author
            )
            await ctx.send(f"{member.mention} has been verified (was not pending).")
            return

        settings = await self.storage.get_guild_settings(ctx.guild.id)
        try:
            await self.quarantine.release_quarantine(member, settings)
        except SetupError as exc:
            await ctx.send(f"Failed to verify: {exc.message}")
            return

        await self.verification.cleanup_message(
            ctx.guild, pending, settings, verified=True, member=member
        )
        await self.storage.clear_pending(ctx.guild.id, member.id)
        await self.event_logger.log_verification_success(
            ctx.guild, member, pending, manual=True, moderator=ctx.author
        )
        await ctx.send(f"{member.mention} has been manually verified.")

    async def manual_quarantine(
        self,
        ctx: commands.Context,
        member: discord.Member,
    ) -> None:
        if member.bot:
            await ctx.send("Bots cannot be quarantined.")
            return
        settings = await self.storage.get_guild_settings(ctx.guild.id)
        score = score_member(member, settings)
        score.triggered = True
        await self._quarantine_member(
            member,
            settings,
            score,
            manual=True,
            moderator=ctx.author,
        )
        await ctx.send(f"{member.mention} has been manually quarantined.")
