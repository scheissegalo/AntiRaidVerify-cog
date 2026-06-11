"""Admin configuration and moderation commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Optional

import discord
from redbot.core import commands

from ..constants import DEFAULT_SPAM_USERNAME_PATTERNS

if TYPE_CHECKING:
    from ..antiraidverify import AntiRaidVerify


@commands.cog_mixin()
class AdminCommands:
    """Mixin providing hybrid admin commands for AntiRaidVerify."""

    @commands.hybrid_group(name="antiraidverify", aliases=["arv"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def antiraidverify(self, ctx: commands.Context) -> None:
        """Configure AntiRaidVerify anti-raid verification."""

    @antiraidverify.command(name="setchannel")
    async def arv_setchannel(
        self: "AntiRaidVerify", ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """Set the verification channel for quarantined members."""
        await self.storage.set_guild_value(ctx.guild.id, "verification_channel_id", channel.id)
        await ctx.send(f"Verification channel set to {channel.mention}.")

    @antiraidverify.command(name="setverifiedrole")
    async def arv_setverifiedrole(
        self: "AntiRaidVerify", ctx: commands.Context, role: discord.Role
    ) -> None:
        """Set the role granted after successful verification."""
        await self.storage.set_guild_value(ctx.guild.id, "verified_role_id", role.id)
        await ctx.send(f"Verified role set to {role.mention}.")

    @antiraidverify.command(name="setunverifiedrole")
    async def arv_setunverifiedrole(
        self: "AntiRaidVerify", ctx: commands.Context, role: discord.Role
    ) -> None:
        """Set the quarantine role assigned to suspicious joins."""
        await self.storage.set_guild_value(ctx.guild.id, "unverified_role_id", role.id)
        await ctx.send(f"Unverified role set to {role.mention}.")

    @antiraidverify.command(name="threshold")
    async def arv_threshold(self: "AntiRaidVerify", ctx: commands.Context, score: int) -> None:
        """Set the suspicion score threshold (default: 5)."""
        if score < 1:
            await ctx.send("Threshold must be at least 1.")
            return
        await self.storage.set_guild_value(ctx.guild.id, "score_threshold", score)
        await ctx.send(f"Score threshold set to **{score}**.")

    @antiraidverify.command(name="accountage")
    async def arv_accountage(self: "AntiRaidVerify", ctx: commands.Context, days: int) -> None:
        """Set account age (days) used for the young-account scoring factor."""
        if days < 0:
            await ctx.send("Account age must be 0 or greater.")
            return
        await self.storage.set_guild_value(ctx.guild.id, "account_age_days", days)
        await ctx.send(f"Account age threshold set to **{days}** days.")

    @antiraidverify.command(name="agebypass")
    async def arv_agebypass(self: "AntiRaidVerify", ctx: commands.Context, days: int) -> None:
        """Skip quarantine for accounts older than this many days (0 = disabled)."""
        if days < 0:
            await ctx.send("Age bypass must be 0 or greater.")
            return
        await self.storage.set_guild_value(ctx.guild.id, "account_age_bypass_days", days)
        if days == 0:
            await ctx.send("Account age bypass disabled.")
        else:
            await ctx.send(f"Accounts older than **{days}** days will bypass quarantine.")

    @antiraidverify.command(name="timeout")
    async def arv_timeout(self: "AntiRaidVerify", ctx: commands.Context, hours: int) -> None:
        """Set verification timeout in hours (default: 8)."""
        if hours < 1:
            await ctx.send("Timeout must be at least 1 hour.")
            return
        await self.storage.set_guild_value(ctx.guild.id, "timeout_hours", hours)
        await ctx.send(f"Verification timeout set to **{hours}** hours.")

    @antiraidverify.command(name="timeoutaction")
    async def arv_timeoutaction(
        self: "AntiRaidVerify",
        ctx: commands.Context,
        action: Literal["kick", "ban"],
    ) -> None:
        """Set action when verification times out (kick or ban)."""
        await self.storage.set_guild_value(ctx.guild.id, "timeout_action", action)
        await ctx.send(f"Timeout action set to **{action}**.")

    @antiraidverify.command(name="banduration")
    async def arv_banduration(self: "AntiRaidVerify", ctx: commands.Context, hours: int) -> None:
        """Set temporary ban duration in hours (0 = permanent ban)."""
        if hours < 0:
            await ctx.send("Ban duration must be 0 or greater.")
            return
        await self.storage.set_guild_value(ctx.guild.id, "ban_duration_hours", hours)
        if hours == 0:
            await ctx.send("Timeout bans will be **permanent**.")
        else:
            await ctx.send(f"Timeout bans will last **{hours}** hours.")

    @antiraidverify.group(name="whitelist")
    async def arv_whitelist(self, ctx: commands.Context) -> None:
        """Manage whitelist roles that bypass suspicion scoring."""

    @arv_whitelist.command(name="add")
    async def arv_whitelist_add(
        self: "AntiRaidVerify", ctx: commands.Context, role: discord.Role
    ) -> None:
        """Add a role to the verification whitelist."""
        settings = await self.storage.get_guild_settings(ctx.guild.id)
        ids = list(settings.whitelist_role_ids)
        if role.id in ids:
            await ctx.send(f"{role.mention} is already whitelisted.")
            return
        ids.append(role.id)
        await self.storage.set_guild_value(ctx.guild.id, "whitelist_role_ids", ids)
        await ctx.send(f"Added {role.mention} to the whitelist.")

    @arv_whitelist.command(name="remove")
    async def arv_whitelist_remove(
        self: "AntiRaidVerify", ctx: commands.Context, role: discord.Role
    ) -> None:
        """Remove a role from the verification whitelist."""
        settings = await self.storage.get_guild_settings(ctx.guild.id)
        ids = [rid for rid in settings.whitelist_role_ids if rid != role.id]
        await self.storage.set_guild_value(ctx.guild.id, "whitelist_role_ids", ids)
        await ctx.send(f"Removed {role.mention} from the whitelist.")

    @antiraidverify.command(name="logchannel")
    async def arv_logchannel(
        self: "AntiRaidVerify", ctx: commands.Context, channel: discord.TextChannel
    ) -> None:
        """Set the channel for AntiRaidVerify audit logs."""
        await self.storage.set_guild_value(ctx.guild.id, "log_channel_id", channel.id)
        await ctx.send(f"Log channel set to {channel.mention}.")

    @antiraidverify.command(name="enable")
    async def arv_enable(self: "AntiRaidVerify", ctx: commands.Context) -> None:
        """Enable AntiRaidVerify for this server."""
        await self.storage.set_guild_value(ctx.guild.id, "enabled", True)
        await ctx.send("AntiRaidVerify **enabled**.")

    @antiraidverify.command(name="disable")
    async def arv_disable(self: "AntiRaidVerify", ctx: commands.Context) -> None:
        """Disable AntiRaidVerify for this server."""
        await self.storage.set_guild_value(ctx.guild.id, "enabled", False)
        await ctx.send("AntiRaidVerify **disabled**.")

    @antiraidverify.command(name="config")
    async def arv_config(self: "AntiRaidVerify", ctx: commands.Context) -> None:
        """View current AntiRaidVerify configuration."""
        settings = await self.storage.get_guild_settings(ctx.guild.id)
        guild = ctx.guild

        def mention_channel(cid: Optional[int]) -> str:
            if not cid:
                return "Not set"
            ch = guild.get_channel(cid)
            return ch.mention if ch else f"Missing ({cid})"

        def mention_role(rid: Optional[int]) -> str:
            if not rid:
                return "Not set"
            role = guild.get_role(rid)
            return role.mention if role else f"Missing ({rid})"

        embed = discord.Embed(
            title="AntiRaidVerify Configuration",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Enabled", value=str(settings.enabled), inline=True)
        embed.add_field(name="Score Threshold", value=str(settings.score_threshold), inline=True)
        embed.add_field(name="Account Age (days)", value=str(settings.account_age_days), inline=True)
        embed.add_field(
            name="Age Bypass (days)", value=str(settings.account_age_bypass_days), inline=True
        )
        embed.add_field(name="Timeout (hours)", value=str(settings.timeout_hours), inline=True)
        embed.add_field(name="Timeout Action", value=settings.timeout_action, inline=True)
        embed.add_field(
            name="Ban Duration (hours)", value=str(settings.ban_duration_hours), inline=True
        )
        embed.add_field(name="Verification Channel", value=mention_channel(settings.verification_channel_id), inline=False)
        embed.add_field(name="Verified Role", value=mention_role(settings.verified_role_id), inline=True)
        embed.add_field(name="Unverified Role", value=mention_role(settings.unverified_role_id), inline=True)
        embed.add_field(name="Log Channel", value=mention_channel(settings.log_channel_id), inline=True)
        embed.add_field(
            name="Whitelist Roles",
            value=", ".join(mention_role(r) for r in settings.whitelist_role_ids) or "None",
            inline=False,
        )
        embed.add_field(
            name="Mass Join",
            value=f"{settings.mass_join_threshold} joins / {settings.mass_join_window_seconds}s",
            inline=True,
        )
        embed.add_field(
            name="Verify Cooldown",
            value=f"{settings.verify_cooldown_seconds}s",
            inline=True,
        )
        embed.add_field(
            name="Username Digit Min",
            value=str(settings.username_digit_min),
            inline=True,
        )
        embed.add_field(
            name="Cleanup Messages",
            value=str(settings.cleanup_verification_messages),
            inline=True,
        )
        pattern_count = len(settings.spam_username_patterns or DEFAULT_SPAM_USERNAME_PATTERNS)
        embed.add_field(name="Spam Regex Patterns", value=str(pattern_count), inline=True)
        await ctx.send(embed=embed)

    @antiraidverify.command(name="verify")
    async def arv_verify(
        self: "AntiRaidVerify", ctx: commands.Context, member: discord.Member
    ) -> None:
        """Manually verify a quarantined member."""
        await self.manual_verify(ctx, member)

    @antiraidverify.command(name="quarantine")
    async def arv_quarantine(
        self: "AntiRaidVerify", ctx: commands.Context, member: discord.Member
    ) -> None:
        """Manually quarantine a member and send a verification prompt."""
        await self.manual_quarantine(ctx, member)

    @antiraidverify.command(name="checksetup")
    async def arv_checksetup(self: "AntiRaidVerify", ctx: commands.Context) -> None:
        """Validate roles, hierarchy, and channel configuration."""
        settings = await self.storage.get_guild_settings(ctx.guild.id)
        issues = self.quarantine.validate_settings(ctx.guild, settings)

        embed = discord.Embed(
            title="AntiRaidVerify Setup Check",
            color=discord.Color.green() if not issues else discord.Color.orange(),
        )
        if issues:
            embed.description = "The following issues were found:\n" + "\n".join(
                f"• {issue}" for issue in issues
            )
        else:
            embed.description = "Configuration looks good! Ensure channel permission overwrites are set as documented in the README."

        me = ctx.guild.me
        if me:
            embed.add_field(
                name="Bot Permissions",
                value=(
                    f"Manage Roles: {me.guild_permissions.manage_roles}\n"
                    f"Kick Members: {me.guild_permissions.kick_members}\n"
                    f"Ban Members: {me.guild_permissions.ban_members}\n"
                    f"Manage Messages: {me.guild_permissions.manage_messages}"
                ),
                inline=False,
            )
        await ctx.send(embed=embed)
