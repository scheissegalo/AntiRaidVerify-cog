"""Typed data models for AntiRaidVerify."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class ScoreResult:
    """Result of suspicion scoring for a member."""

    total: int
    factors: dict[str, int]
    triggered: bool
    account_age_days: int


@dataclass
class PendingVerification:
    """Persisted pending verification state for a member."""

    guild_id: int
    user_id: int
    message_id: int
    channel_id: int
    score: int
    factors: dict[str, int]
    joined_at: float
    expires_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "score": self.score,
            "factors": self.factors,
            "joined_at": self.joined_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(
        cls, guild_id: int, user_id: int, data: dict[str, Any]
    ) -> "PendingVerification":
        return cls(
            guild_id=guild_id,
            user_id=user_id,
            message_id=int(data["message_id"]),
            channel_id=int(data["channel_id"]),
            score=int(data.get("score", 0)),
            factors=dict(data.get("factors", {})),
            joined_at=float(data["joined_at"]),
            expires_at=float(data["expires_at"]),
        )


@dataclass
class GuildSettings:
    """Guild configuration snapshot."""

    enabled: bool = True
    verification_channel_id: Optional[int] = None
    verified_role_id: Optional[int] = None
    unverified_role_id: Optional[int] = None
    score_threshold: int = 5
    account_age_days: int = 7
    account_age_bypass_days: int = 0
    timeout_hours: int = 8
    timeout_action: Literal["kick", "ban"] = "kick"
    ban_duration_hours: int = 0
    log_channel_id: Optional[int] = None
    whitelist_role_ids: list[int] = field(default_factory=list)
    mass_join_threshold: int = 10
    mass_join_window_seconds: int = 60
    verify_cooldown_seconds: int = 30
    username_digit_min: int = 4
    spam_username_patterns: list[str] = field(default_factory=list)
    cleanup_verification_messages: bool = True

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "GuildSettings":
        timeout_action = data.get("timeout_action", "kick")
        if timeout_action not in ("kick", "ban"):
            timeout_action = "kick"
        return cls(
            enabled=bool(data.get("enabled", True)),
            verification_channel_id=data.get("verification_channel_id"),
            verified_role_id=data.get("verified_role_id"),
            unverified_role_id=data.get("unverified_role_id"),
            score_threshold=int(data.get("score_threshold", 5)),
            account_age_days=int(data.get("account_age_days", 7)),
            account_age_bypass_days=int(data.get("account_age_bypass_days", 0)),
            timeout_hours=int(data.get("timeout_hours", 8)),
            timeout_action=timeout_action,  # type: ignore[arg-type]
            ban_duration_hours=int(data.get("ban_duration_hours", 0)),
            log_channel_id=data.get("log_channel_id"),
            whitelist_role_ids=list(data.get("whitelist_role_ids", [])),
            mass_join_threshold=int(data.get("mass_join_threshold", 10)),
            mass_join_window_seconds=int(data.get("mass_join_window_seconds", 60)),
            verify_cooldown_seconds=int(data.get("verify_cooldown_seconds", 30)),
            username_digit_min=int(data.get("username_digit_min", 4)),
            spam_username_patterns=list(data.get("spam_username_patterns", [])),
            cleanup_verification_messages=bool(
                data.get("cleanup_verification_messages", True)
            ),
        )
