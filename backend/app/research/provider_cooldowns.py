"""Durable account-level model-provider cooldowns for explicit rate limits."""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import ProviderCooldown, utcnow

DEFAULT_ACCOUNT_COOLDOWN_SECONDS = 60.0
MAX_ACCOUNT_COOLDOWN_SECONDS = 86_400.0


def active_provider_cooldown_seconds(
    db: Session, provider: str, *, now: datetime | None = None
) -> float | None:
    row = db.get(ProviderCooldown, provider)
    if row is None:
        return None
    current = now or utcnow()
    blocked_until = row.blocked_until
    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=UTC)
    remaining = (blocked_until - current).total_seconds()
    return max(0.0, min(MAX_ACCOUNT_COOLDOWN_SECONDS, remaining)) if remaining > 0 else None


def record_provider_account_cooldown(
    db: Session,
    provider: str,
    *,
    retry_after_seconds: float | None,
    reason: str = "provider_rate_limited",
    now: datetime | None = None,
) -> float:
    if not provider or len(provider) > 40:
        raise ValueError("Provider cooldown key must be a bounded normalized id")
    duration = retry_after_seconds
    if duration is None:
        duration = DEFAULT_ACCOUNT_COOLDOWN_SECONDS
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise ValueError("Provider cooldown duration must be numeric")
    if not math.isfinite(duration) or not 0 < duration <= MAX_ACCOUNT_COOLDOWN_SECONDS:
        raise ValueError("Provider cooldown duration must be between zero and one day")
    current = now or utcnow()
    blocked_until = current + timedelta(seconds=duration)
    values = {
        "provider": provider,
        "scope": "account",
        "blocked_until": blocked_until,
        "reason": reason[:80],
        "updated_at": current,
    }
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        statement = sqlite_insert(ProviderCooldown).values(**values)
        excluded_until = statement.excluded.blocked_until
        blocked_until_expression = func.max(ProviderCooldown.blocked_until, excluded_until)
    elif dialect == "postgresql":
        statement = postgresql_insert(ProviderCooldown).values(**values)
        excluded_until = statement.excluded.blocked_until
        blocked_until_expression = func.greatest(ProviderCooldown.blocked_until, excluded_until)
    else:
        raise RuntimeError(f"Provider cooldowns are unsupported for database dialect {dialect}.")
    db.execute(
        statement.on_conflict_do_update(
            index_elements=["provider"],
            set_={
                "scope": "account",
                "blocked_until": blocked_until_expression,
                "reason": reason[:80],
                "updated_at": current,
            },
        )
    )
    db.commit()
    return duration


def provider_cooldown_remaining_seconds(db: Session, provider: str) -> int | None:
    remaining = active_provider_cooldown_seconds(db, provider)
    return max(1, math.ceil(remaining)) if remaining is not None else None
