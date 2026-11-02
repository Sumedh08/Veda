from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import settings

bearer = HTTPBearer(auto_error=False)
LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"


@dataclass(frozen=True)
class AuthUser:
    id: str
    provider: str


@lru_cache(maxsize=2)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300, timeout=5)


def create_local_token() -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": LOCAL_USER_ID,
            "aud": "veda-local",
            "iss": "veda-local",
            "iat": now,
            "exp": now + timedelta(hours=12),
        },
        settings.dev_auth_secret,
        algorithm="HS256",
    )


def _verify_managed_token(token: str) -> AuthUser:
    issuer = settings.supabase_url.rstrip("/") + "/auth/v1"
    try:
        if settings.supabase_jwt_secret:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        elif settings.supabase_jwks_url:
            signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience="authenticated",
                issuer=issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        else:
            raise HTTPException(status_code=503, detail="Managed authentication is not configured")
        user_id = str(UUID(str(payload["sub"])))
        return AuthUser(id=user_id, provider="supabase")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> AuthUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required")
    token = credentials.credentials
    if settings.dev_auth_enabled:
        try:
            payload = jwt.decode(
                token,
                settings.dev_auth_secret,
                algorithms=["HS256"],
                audience="veda-local",
                issuer="veda-local",
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
            if payload["sub"] == LOCAL_USER_ID:
                return AuthUser(id=LOCAL_USER_ID, provider="local-development")
        except Exception:
            pass
    return _verify_managed_token(token)


def require_loopback_dev_request(request: Request) -> None:
    if not settings.dev_auth_enabled or settings.app_env.lower() not in {
        "development",
        "dev",
        "test",
    }:
        raise HTTPException(status_code=404, detail="Not found")
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=404, detail="Not found")
