"""Suspicion scoring for newly joined members."""

from __future__ import annotations

import re
from datetime import timezone
from typing import Optional

import discord

from .constants import DEFAULT_SPAM_USERNAME_PATTERNS
from .models import GuildSettings, ScoreResult


def _account_age_days(member: discord.Member) -> int:
    now = discord.utils.utcnow()
    created = member.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).days


def _has_default_avatar(member: discord.Member) -> bool:
    return member.avatar is None


def _is_embed_default_avatar(member: discord.Member) -> bool:
    try:
        return member.display_avatar.key.startswith("embed/avatars/")
    except AttributeError:
        return _has_default_avatar(member)


def _display_name_equals_username(member: discord.Member) -> bool:
    if member.display_name == member.name:
        return True
    if member.global_name and member.display_name == member.global_name:
        if member.global_name == member.name:
            return True
    return False


def _username_has_many_digits(name: str, minimum: int) -> bool:
    return len(re.findall(r"\d", name)) >= minimum


def _matches_spam_patterns(name: str, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        try:
            if re.search(pattern, name, re.IGNORECASE):
                return pattern
        except re.error:
            continue
    return None


def score_member(member: discord.Member, settings: GuildSettings) -> ScoreResult:
    """
    Compute a suspicion score for a member based on guild settings.

    Returns a ScoreResult with total score, contributing factors, and trigger flag.
    """
    age_days = _account_age_days(member)

    if settings.account_age_bypass_days > 0 and age_days >= settings.account_age_bypass_days:
        return ScoreResult(
            total=0,
            factors={},
            triggered=False,
            account_age_days=age_days,
        )

    factors: dict[str, int] = {}

    if _has_default_avatar(member):
        factors["no_custom_avatar"] = 2

    if _is_embed_default_avatar(member):
        factors["default_discord_avatar"] = 1

    if _display_name_equals_username(member):
        factors["display_name_equals_username"] = 2

    if age_days < settings.account_age_days:
        factors["account_younger_than_threshold"] = 4

    username = member.name
    if _username_has_many_digits(username, settings.username_digit_min):
        factors["username_many_digits"] = 2

    matched = _matches_spam_patterns(
        username,
        settings.spam_username_patterns or DEFAULT_SPAM_USERNAME_PATTERNS,
    )
    if matched is not None:
        factors["spam_username_pattern"] = 2

    total = sum(factors.values())
    triggered = total >= settings.score_threshold

    return ScoreResult(
        total=total,
        factors=factors,
        triggered=triggered,
        account_age_days=age_days,
    )
