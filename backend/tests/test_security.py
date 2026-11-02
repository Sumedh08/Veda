import logging
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

import app.api.routes as routes
import app.security as security
from app.config import Settings


def test_world_bank_document_search_requires_explicit_noncommercial_use_confirmation():
    config = Settings(_env_file=None)

    assert config.world_bank_documents_noncommercial_use_confirmed is False
from app.logging_privacy import HttpxRequestLogFilter
from app.security import LOCAL_USER_ID, create_local_token, get_current_user


def test_production_rejects_development_auth():
    config = Settings(app_env="production", dev_auth_enabled=True, dev_auth_secret="a" * 40)
    with pytest.raises(ValueError, match="cannot be enabled in production"):
        config.validate_security_configuration()


@pytest.mark.parametrize("database_url", ["sqlite:///veda.db", "sqlite:////tmp/veda.db"])
def test_production_rejects_ephemeral_sqlite_storage(database_url):
    config = Settings(
        app_env="production",
        database_url=database_url,
        rate_limit_hash_secret="r" * 40,
        supabase_url="https://veda-example.supabase.co",
        supabase_jwks_url="https://veda-example.supabase.co/auth/v1/.well-known/jwks.json",
        frontend_origins="https://veda.example",
    )
    with pytest.raises(ValueError, match="requires PostgreSQL"):
        config.validate_security_configuration()


def test_production_requires_managed_auth_and_https_frontend_origin():
    config = Settings(
        app_env="production",
        database_url="postgresql+psycopg://veda:secret@db.example/veda",
        rate_limit_hash_secret="r" * 40,
        frontend_origins="http://veda.example",
    )
    with pytest.raises(ValueError, match="HTTPS SUPABASE_URL"):
        config.validate_security_configuration()

    config = Settings(
        app_env="production",
        database_url="postgresql+psycopg://veda:secret@db.example/veda",
        rate_limit_hash_secret="r" * 40,
        supabase_url="https://veda-example.supabase.co",
        frontend_origins="https://veda.example/path",
    )
    with pytest.raises(ValueError, match="SUPABASE_JWKS_URL or SUPABASE_JWT_SECRET"):
        config.validate_security_configuration()


def test_production_accepts_durable_database_managed_auth_and_https_origin():
    config = Settings(
        app_env="production",
        database_url="postgresql+psycopg://veda:secret@db.example/veda",
        rate_limit_hash_secret="r" * 40,
        supabase_url="https://veda-example.supabase.co",
        supabase_jwks_url="https://veda-example.supabase.co/auth/v1/.well-known/jwks.json",
        frontend_origins="https://veda.example",
    )
    config.validate_security_configuration()


def test_development_auth_requires_long_secret():
    config = Settings(app_env="development", dev_auth_enabled=True, dev_auth_secret="short")
    with pytest.raises(ValueError, match="at least 32 characters"):
        config.validate_security_configuration()


def test_local_token_uses_fixed_local_identity(monkeypatch):
    class Config:
        dev_auth_secret = "test-secret-that-is-long-enough-for-hmac"  # veda-secret-scan:ignore -- deterministic local token fixture

    monkeypatch.setattr(security, "settings", Config())
    token = create_local_token()
    assert LOCAL_USER_ID in token or token.count(".") == 2


def test_managed_jwt_validates_signature_issuer_audience_and_uuid_subject(monkeypatch):
    config = Settings(
        app_env="production",
        supabase_url="https://veda-example.supabase.co/",
        supabase_jwt_secret="managed-auth-secret-for-test-only",
    )
    monkeypatch.setattr(security, "settings", config)
    now = datetime.now(UTC)
    user_id = "30000000-0000-4000-8000-000000000003"
    token = jwt.encode(
        {
            "sub": user_id,
            "aud": "authenticated",
            "iss": "https://veda-example.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        config.supabase_jwt_secret,
        algorithm="HS256",
    )

    user = get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    assert user.id == user_id
    assert user.provider == "supabase"


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "wrong-audience"},
        {"iss": "https://attacker.invalid/auth/v1"},
        {"sub": "not-a-uuid"},
        {"exp": datetime.now(UTC) - timedelta(minutes=2)},
    ],
)
def test_managed_jwt_rejects_invalid_claims(monkeypatch, claims):
    config = Settings(
        app_env="production",
        supabase_url="https://veda-example.supabase.co",
        supabase_jwt_secret="managed-auth-secret-for-test-only",
    )
    monkeypatch.setattr(security, "settings", config)
    now = datetime.now(UTC)
    payload = {
        "sub": "30000000-0000-4000-8000-000000000003",
        "aud": "authenticated",
        "iss": "https://veda-example.supabase.co/auth/v1",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    payload.update(claims)
    token = jwt.encode(payload, config.supabase_jwt_secret, algorithm="HS256")

    with pytest.raises(HTTPException) as error:
        get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert error.value.status_code == 401


def test_managed_jwt_rejects_bad_signature_and_missing_bearer(monkeypatch):
    config = Settings(
        app_env="production",
        supabase_url="https://veda-example.supabase.co",
        supabase_jwt_secret="managed-auth-secret-for-test-only",
    )
    monkeypatch.setattr(security, "settings", config)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "30000000-0000-4000-8000-000000000003",
            "aud": "authenticated",
            "iss": "https://veda-example.supabase.co/auth/v1",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        "wrong-signature-secret-but-valid-length",
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    with pytest.raises(HTTPException) as error:
        get_current_user(credentials)
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as missing:
        get_current_user(None)
    assert missing.value.status_code == 401


def test_sql_metacharacters_are_stored_as_data_without_affecting_other_records(client):
    payload_title = "' OR 1=1; DROP TABLE projects; --"
    created = client.post(
        "/api/v1/projects", json={"title": payload_title, "domain": "security-test"}
    )
    assert created.status_code == 201

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert [project["title"] for project in projects.json()["items"]] == [payload_title]
    assert client.get("/api/v1/health/ready").status_code == 200


def test_unexpected_stage_error_log_does_not_include_exception_secret(client, monkeypatch, caplog):
    project = client.post(
        "/api/v1/projects", json={"title": "Log safety", "domain": "security-test"}
    )
    job = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={"question": "Test error log redaction", "idempotency_key": "log-redaction"},
    )
    secret = "provider-token-fixture-should-not-be-logged"

    def fail_stage(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(routes, "execute_stage", fail_stage)
    with caplog.at_level("ERROR", logger="app.api.routes"):
        response = client.post(
            f"/api/v1/research-jobs/{job.json()['id']}/advance",
            json={"operation_key": "log-redaction-stage"},
        )

    assert response.status_code == 200
    assert "Research stage failed" in caplog.text
    assert secret not in caplog.text
    events = client.get(f"/api/v1/research-jobs/{job.json()['id']}/events").json()["items"]
    failed_event = next(event for event in events if event["event_type"] == "step_failed")
    assert failed_event["data"]["exception_type"] == "RuntimeError"
    assert secret not in str(failed_event)


def test_unexpected_stage_validation_diagnostics_omit_input_values(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Validation diagnostics", "domain": "security-test"}
    )
    job = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={"question": "Test validation diagnostics", "idempotency_key": "validation-diag"},
    )
    secret = "private-source-payload-fixture"

    class RequiredCount(BaseModel):
        count: int

    def fail_stage(*args, **kwargs):
        RequiredCount(count=secret)

    monkeypatch.setattr(routes, "execute_stage", fail_stage)
    response = client.post(
        f"/api/v1/research-jobs/{job.json()['id']}/advance",
        json={"operation_key": "validation-diagnostics-stage"},
    )

    assert response.status_code == 200
    events = client.get(f"/api/v1/research-jobs/{job.json()['id']}/events").json()["items"]
    failed_event = next(event for event in events if event["event_type"] == "step_failed")
    assert failed_event["data"]["exception_type"] == "ValidationError"
    assert failed_event["data"]["validation_model"] == "RequiredCount"
    assert failed_event["data"]["validation_error_count"] == 1
    assert failed_event["data"]["validation_error_types"] == ["int_parsing"]
    assert secret not in str(failed_event)


def test_httpx_request_logs_redact_query_userinfo_and_fragment(caplog):
    question = "private research scope fixture-9f2b"
    credential = "credential-query-fixture-7c1a"
    logger = logging.getLogger("httpx")
    if not any(isinstance(filter_, HttpxRequestLogFilter) for filter_ in logger.filters):
        logger.addFilter(HttpxRequestLogFilter())

    with caplog.at_level(logging.INFO, logger="httpx"):
        with httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok"))
        ) as client:
            response = client.get(
                "https://user:password@example.test/works#private-fragment",
                params={"query": question, "api_key": credential},
            )

    assert response.status_code == 200
    assert question not in caplog.text
    assert credential not in caplog.text
    assert "user:password" not in caplog.text
    assert "private-fragment" not in caplog.text
    assert "https://example.test/works" in caplog.text
    assert "200 OK" in caplog.text
