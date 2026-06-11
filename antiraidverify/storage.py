"""Red Config storage layer and pending verification CRUD."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from redbot.core import Config

from .constants import (
    DEFAULT_ACCOUNT_AGE_DAYS,
    DEFAULT_BAN_DURATION_HOURS,
    DEFAULT_MASS_JOIN_THRESHOLD,
    DEFAULT_MASS_JOIN_WINDOW_SECONDS,
    DEFAULT_SCORE_THRESHOLD,
    DEFAULT_SPAM_USERNAME_PATTERNS,
    DEFAULT_TIMEOUT_ACTION,
    DEFAULT_TIMEOUT_HOURS,
    DEFAULT_USERNAME_DIGIT_MIN,
    DEFAULT_VERIFY_COOLDOWN_SECONDS,
)
from .models import GuildSettings, PendingVerification

if TYPE_CHECKING:
    from .antiraidverify import AntiRaidVerify

log = logging.getLogger("red.antiraidverify.storage")

CONFIG_IDENTIFIER = 0x41525631  # "ARV1"


class Storage:
    """Wraps Red Config for guild settings and pending verification state."""

    def __init__(self, cog) -> None:
        self.config = Config.get_conf(
            cog, identifier=CONFIG_IDENTIFIER, force_registration=True
        )
        self.config.register_guild(
            enabled=True,
            verification_channel_id=None,
            verified_role_id=None,
            unverified_role_id=None,
            score_threshold=DEFAULT_SCORE_THRESHOLD,
            account_age_days=DEFAULT_ACCOUNT_AGE_DAYS,
            account_age_bypass_days=0,
            timeout_hours=DEFAULT_TIMEOUT_HOURS,
            timeout_action=DEFAULT_TIMEOUT_ACTION,
            ban_duration_hours=DEFAULT_BAN_DURATION_HOURS,
            log_channel_id=None,
            whitelist_role_ids=[],
            mass_join_threshold=DEFAULT_MASS_JOIN_THRESHOLD,
            mass_join_window_seconds=DEFAULT_MASS_JOIN_WINDOW_SECONDS,
            verify_cooldown_seconds=DEFAULT_VERIFY_COOLDOWN_SECONDS,
            username_digit_min=DEFAULT_USERNAME_DIGIT_MIN,
            spam_username_patterns=list(DEFAULT_SPAM_USERNAME_PATTERNS),
            cleanup_verification_messages=True,
        )
        self.config.init_custom("PendingVerification", 2)
        self.config.register_custom(
            "PendingVerification",
            message_id=0,
            channel_id=0,
            score=0,
            factors={},
            joined_at=0.0,
            expires_at=0.0,
        )
        self.config.init_custom("MessageIndex", 1)
        self.config.register_custom("MessageIndex", guild_id=0, user_id=0)

    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        data = await self.config.guild_from_id(guild_id).all()
        return GuildSettings.from_config(data)

    async def is_enabled(self, guild_id: int) -> bool:
        return await self.config.guild_from_id(guild_id).enabled()

    async def set_guild_value(self, guild_id: int, key: str, value: Any) -> None:
        await getattr(self.config.guild_from_id(guild_id), key).set(value)

    async def get_pending(
        self, guild_id: int, user_id: int
    ) -> Optional[PendingVerification]:
        data = await self.config.custom("PendingVerification", guild_id, user_id).all()
        if not data or not data.get("message_id"):
            return None
        return PendingVerification.from_dict(guild_id, user_id, data)

    async def is_pending(self, guild_id: int, user_id: int) -> bool:
        pending = await self.get_pending(guild_id, user_id)
        return pending is not None

    async def save_pending(self, pending: PendingVerification) -> None:
        group = self.config.custom(
            "PendingVerification", pending.guild_id, pending.user_id
        )
        await group.set_raw(
            message_id=pending.message_id,
            channel_id=pending.channel_id,
            score=pending.score,
            factors=pending.factors,
            joined_at=pending.joined_at,
            expires_at=pending.expires_at,
        )
        index = self.config.custom("MessageIndex", pending.message_id)
        await index.set_raw(guild_id=pending.guild_id, user_id=pending.user_id)

    async def clear_pending(self, guild_id: int, user_id: int) -> None:
        pending = await self.get_pending(guild_id, user_id)
        if pending is not None:
            await self.config.custom("MessageIndex", pending.message_id).clear()
        await self.config.custom("PendingVerification", guild_id, user_id).clear()

    async def lookup_by_message(self, message_id: int) -> Optional[tuple[int, int]]:
        data = await self.config.custom("MessageIndex", message_id).all()
        if not data or not data.get("guild_id"):
            return None
        return int(data["guild_id"]), int(data["user_id"])

    async def get_all_pending(self) -> list[PendingVerification]:
        raw = await self.config.custom("PendingVerification").all()
        results: list[PendingVerification] = []
        for guild_key, users in raw.items():
            guild_id = int(guild_key)
            if not isinstance(users, dict):
                continue
            for user_key, data in users.items():
                user_id = int(user_key)
                if not data or not data.get("message_id"):
                    continue
                results.append(PendingVerification.from_dict(guild_id, user_id, data))
        return results

    async def reconcile_pending_messages(self, cog: "AntiRaidVerify") -> None:
        """Remove stale pending entries whose messages no longer exist."""
        pending_list = await self.get_all_pending()
        for pending in pending_list:
            guild = cog.bot.get_guild(pending.guild_id)
            if guild is None:
                await self.clear_pending(pending.guild_id, pending.user_id)
                continue
            channel = guild.get_channel(pending.channel_id)
            if channel is None:
                await self.clear_pending(pending.guild_id, pending.user_id)
                continue
            try:
                await channel.fetch_message(pending.message_id)
            except Exception:
                log.debug(
                    "Removing stale pending verification for user %s in guild %s",
                    pending.user_id,
                    pending.guild_id,
                )
                await self.clear_pending(pending.guild_id, pending.user_id)
