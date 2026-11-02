"""Database-backed API request limits shared across service processes."""

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import RequestRateWindow
from app.security import get_current_user

_cleanup_lock = Lock()
_last_cleanup_monotonic = 0.0


def _identity_subject(request: Request) -> str | None:
    """Use only a verified subject; forged tokens must not consume another user's quota."""
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        user = get_current_user(HTTPAuthorizationCredentials(scheme=scheme, credentials=token))
        return str(UUID(user.id))
    except HTTPException:
        return None


def _identity_hash(category: str, identity: str) -> str:
    configured_secret = (
        settings.rate_limit_hash_secret
        or settings.dev_auth_secret
        or settings.supabase_jwt_secret
        or "veda-development-rate-limit-key"
    )
    message = f"{category}\0{identity}".encode()
    return hmac.new(configured_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _window_start(now: datetime, seconds: int) -> datetime:
    timestamp = int(now.timestamp())
    return datetime.fromtimestamp(timestamp - timestamp % seconds, tz=UTC)


def _count_request(db: Session, bucket_hash: str, window_start: datetime) -> int:
    dialect = db.get_bind().dialect.name
    values = {
        "id": str(uuid4()),
        "bucket_hash": bucket_hash,
        "window_start": window_start,
        "request_count": 1,
        "updated_at": datetime.now(UTC),
    }
    if dialect == "sqlite":
        statement = sqlite_insert(RequestRateWindow).values(**values)
    elif dialect == "postgresql":
        statement = postgresql_insert(RequestRateWindow).values(**values)
    else:
        raise RuntimeError(f"Request rate limits do not support database dialect {dialect}.")
    result = db.execute(
        statement.on_conflict_do_update(
            index_elements=["bucket_hash", "window_start"],
            set_={
                "request_count": RequestRateWindow.request_count + 1,
                "updated_at": datetime.now(UTC),
            },
        ).returning(RequestRateWindow.request_count)
    )
    return int(result.scalar_one())


def _cleanup_expired_windows(db: Session, now: datetime) -> None:
    global _last_cleanup_monotonic
    current = time.monotonic()
    if current - _last_cleanup_monotonic < 3600:
        return
    with _cleanup_lock:
        current = time.monotonic()
        if current - _last_cleanup_monotonic >= 3600:
            db.execute(
                delete(RequestRateWindow).where(
                    RequestRateWindow.window_start < now - timedelta(days=2)
                )
            )
            _last_cleanup_monotonic = current


def enforce_request_rate_limit(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """Enforce atomic per-IP and per-user fixed-window limits on API routes."""
    now = datetime.now(UTC)
    client_host = request.client.host if request.client else "unknown"
    identities = [("ip", client_host)]
    subject = _identity_subject(request)
    if subject is not None:
        identities.append(("user", subject))

    policy_limits: dict[tuple[str, str, int], int] = {}
    method = request.method.upper()
    path = request.url.path
    if method == "POST" and path == "/api/v1/auth/dev-session":
        policy_limits[("ip", "dev-session", 60)] = settings.rate_limit_dev_sessions_per_minute
    else:
        policy_limits[("ip", "api", 60)] = settings.rate_limit_ip_per_minute
        policy_limits[("user", "api", 60)] = settings.rate_limit_user_per_minute
        if method == "POST" and path.endswith("/research-jobs"):
            policy_limits[("ip", "job-create", 3600)] = settings.rate_limit_ip_job_creates_per_hour
            policy_limits[("user", "job-create", 3600)] = (
                settings.rate_limit_user_job_creates_per_hour
            )
        elif method == "POST" and path.endswith(("/advance", "/resume")):
            policy_limits[("ip", "advance", 60)] = settings.rate_limit_ip_advances_per_minute
            policy_limits[("user", "advance", 60)] = settings.rate_limit_user_advances_per_minute

    try:
        _cleanup_expired_windows(db, now)
        exceeded: list[tuple[int, str]] = []
        for (identity_category, rate_class, window_seconds), limit in policy_limits.items():
            identity = next(
                (value for kind, value in identities if kind == identity_category), None
            )
            if identity is None:
                continue
            window = _window_start(now, window_seconds)
            bucket_hash = _identity_hash(
                f"{identity_category}:{rate_class}:{window_seconds}", identity
            )
            count = _count_request(db, bucket_hash, window)
            if count > limit:
                retry_after = max(
                    1, int((window + timedelta(seconds=window_seconds) - now).total_seconds()) + 1
                )
                exceeded.append((retry_after, identity_category))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Request protection is temporarily unavailable.",
        ) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Request protection is not supported by the configured database.",
        ) from exc

    if exceeded:
        retry_after = max(value for value, _ in exceeded)
        raise HTTPException(
            status_code=429,
            detail="Request rate limit exceeded. Please retry after the current limit window.",
            headers={"Retry-After": str(retry_after)},
        )
