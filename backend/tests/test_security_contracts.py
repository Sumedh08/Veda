from datetime import UTC, datetime

import app.security as auth
import app.security_rate_limits as rate_limits
from app.config import Settings

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "strict-origin-when-cross-origin",
    "x-frame-options": "DENY",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


def test_security_headers_cover_success_validation_and_oversized_request(client):
    success = client.get("/api/v1/health/live")
    invalid = client.post("/api/v1/projects", json={"unexpected": "field"})
    oversized = client.post(
        "/api/v1/projects",
        json={"title": "x" * (1_048_576 + 10), "domain": "testing"},
    )

    for response in (success, invalid, oversized):
        for name, value in SECURITY_HEADERS.items():
            assert response.headers.get(name) == value
        assert response.headers.get("x-request-id")
    assert invalid.status_code == 422
    assert invalid.json()["error"]["message"] == "The request did not pass validation."
    assert oversized.status_code == 413
    assert oversized.json()["error"]["message"] == "Request body exceeds the configured size limit."


def test_cors_allows_only_the_configured_development_origin(client):
    readable_response = client.get(
        "/api/v1/health/live", headers={"Origin": "http://localhost:5173"}
    )
    allowed = client.options(
        "/api/v1/projects",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    denied = client.options(
        "/api/v1/projects",
        headers={
            "Origin": "https://attacker.invalid",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert denied.headers.get("access-control-allow-origin") is None
    assert (
        readable_response.headers.get("access-control-expose-headers")
        == "Content-Disposition, X-Request-ID"
    )


def test_missing_authentication_returns_a_sanitized_401(client, monkeypatch):
    client.app.dependency_overrides.pop(auth.get_current_user, None)
    monkeypatch.setattr(
        auth,
        "settings",
        Settings(app_env="test", dev_auth_enabled=False, supabase_url=""),
    )
    response = client.get("/api/v1/projects")
    assert response.status_code == 401
    assert response.json() == {"detail": "Sign in is required"}
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get(name) == value


def test_untrusted_forwarded_for_does_not_change_rate_limit_identity(client, monkeypatch):
    fixed_window = datetime(2026, 10, 29, tzinfo=UTC)
    monkeypatch.setattr(rate_limits, "_window_start", lambda _now, _seconds: fixed_window)
    monkeypatch.setattr(
        rate_limits,
        "settings",
        Settings(
            rate_limit_hash_secret="local-proxy-fixture-secret-long-enough",
            rate_limit_ip_per_minute=1,
            rate_limit_user_per_minute=100,
        ),
    )
    first = client.get("/api/v1/projects", headers={"X-Forwarded-For": "198.51.100.11"})
    spoofed = client.get("/api/v1/projects", headers={"X-Forwarded-For": "203.0.113.99"})
    assert first.status_code == 200
    assert spoofed.status_code == 429
    assert spoofed.headers.get("retry-after")
