import asyncio
import json
import multiprocessing
import queue
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import app.security as auth_security
import app.security_rate_limits as rate_limits
from app.config import Settings
from app.db import Base, get_db
from app.models import RequestRateWindow
from app.request_size import RequestBodyLimitMiddleware
from app.security_rate_limits import _count_request


def _process_rate_counter(database_url, bucket_hash, window_start, barrier, results):
    engine = create_engine(database_url, connect_args={"timeout": 10})
    sessions = sessionmaker(bind=engine)
    try:
        with sessions() as db:
            barrier.wait(timeout=10)
            count = _count_request(db, bucket_hash, window_start)
            db.commit()
        results.put(("count", count))
    except Exception as exc:
        results.put(("error", type(exc).__name__, str(exc)[:300]))
        raise
    finally:
        engine.dispose()


def _tight_limits(**overrides):
    values = {
        "rate_limit_hash_secret": "local-test-rate-limit-hash-secret",
        "rate_limit_user_per_minute": 100,
        "rate_limit_ip_per_minute": 100,
        "rate_limit_user_job_creates_per_hour": 10,
        "rate_limit_ip_job_creates_per_hour": 100,
        "rate_limit_user_advances_per_minute": 100,
        "rate_limit_ip_advances_per_minute": 100,
        "rate_limit_dev_sessions_per_minute": 10,
    }
    values.update(overrides)
    return Settings(**values)


def _local_bearer(subject: str, secret: str, nonce: str = "") -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": subject,
            "aud": "veda-local",
            "iss": "veda-local",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "nonce": nonce,
        },
        secret,
        algorithm="HS256",
    )


def test_ip_rate_limit_returns_retry_after_and_persists_only_hashed_identity(client, monkeypatch):
    monkeypatch.setattr(
        rate_limits,
        "settings",
        _tight_limits(rate_limit_ip_per_minute=2),
    )

    assert client.get("/api/v1/projects").status_code == 200
    assert client.get("/api/v1/projects").status_code == 200
    limited = client.get("/api/v1/projects")

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    with client.db_sessions() as db:
        rows = db.scalars(select(RequestRateWindow)).all()
        assert rows
        assert all("testclient" not in row.bucket_hash for row in rows)


def test_rate_limit_database_failure_returns_sanitized_503_and_stops_route(client):
    calls = {"execute": 0, "rollback": 0}
    database_secret = "postgresql://veda:password=secret@db.example/private"

    class UnavailableDatabase:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def execute(self, _statement):
            calls["execute"] += 1
            raise OperationalError("INSERT request_rate_window", {}, RuntimeError(database_secret))

        def rollback(self):
            calls["rollback"] += 1

        def close(self):
            pass

    def unavailable_database():
        yield UnavailableDatabase()

    client.app.dependency_overrides[get_db] = unavailable_database

    response = client.get("/api/v1/projects")

    assert response.status_code == 503
    assert response.json() == {"detail": "Request protection is temporarily unavailable."}
    assert "password=secret" not in response.text
    assert calls == {"execute": 1, "rollback": 1}


def test_user_rate_limit_groups_distinct_tokens_by_subject(client, monkeypatch):
    secret = "not-used-for-throttle-verification-test-secret"  # veda-secret-scan:ignore -- synthetic local JWT signing fixture
    config = _tight_limits(
        rate_limit_user_per_minute=1,
        dev_auth_enabled=True,
        dev_auth_secret=secret,
    )
    monkeypatch.setattr(rate_limits, "settings", config)
    monkeypatch.setattr(auth_security, "settings", config)
    token_a = _local_bearer(auth_security.LOCAL_USER_ID, secret, "a")
    token_b = _local_bearer(auth_security.LOCAL_USER_ID, secret, "b")

    assert (
        client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_a}"}).status_code
        == 200
    )
    limited = client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token_b}"})
    assert limited.status_code == 429


def test_forged_subject_cannot_consume_verified_users_quota(client, monkeypatch):
    secret = "verified-subject-rate-limit-secret-long-enough"  # veda-secret-scan:ignore -- synthetic local JWT signing fixture
    config = _tight_limits(
        rate_limit_user_per_minute=1,
        dev_auth_enabled=True,
        dev_auth_secret=secret,
    )
    monkeypatch.setattr(rate_limits, "settings", config)
    monkeypatch.setattr(auth_security, "settings", config)
    valid = _local_bearer(auth_security.LOCAL_USER_ID, secret, "valid")
    forged = _local_bearer(
        auth_security.LOCAL_USER_ID,
        "attacker-forged-token-secret-is-over-thirty-two-bytes",
        "forged",
    )

    assert (
        client.get("/api/v1/projects", headers={"Authorization": f"Bearer {valid}"}).status_code
        == 200
    )
    assert (
        client.get("/api/v1/projects", headers={"Authorization": f"Bearer {forged}"}).status_code
        == 200
    )
    valid_again = _local_bearer(auth_security.LOCAL_USER_ID, secret, "valid-again")
    assert (
        client.get(
            "/api/v1/projects", headers={"Authorization": f"Bearer {valid_again}"}
        ).status_code
        == 429
    )


def test_job_creation_has_a_separate_hourly_cap(client, monkeypatch):
    secret = "request-limit-fixture-secret-is-long-enough"
    config = _tight_limits(
        rate_limit_user_job_creates_per_hour=1,
        dev_auth_enabled=True,
        dev_auth_secret=secret,
    )
    monkeypatch.setattr(rate_limits, "settings", config)
    monkeypatch.setattr(auth_security, "settings", config)
    project = client.post("/api/v1/projects", json={"title": "Rate limits", "domain": "test"})
    assert project.status_code == 201
    path = f"/api/v1/projects/{project.json()['id']}/research-jobs"
    payload = {"question": "A request quota test", "idempotency_key": "rate-limit-job-1"}
    token = _local_bearer(auth_security.LOCAL_USER_ID, secret)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post(path, json=payload, headers=headers).status_code == 201
    blocked = client.post(
        path,
        json={"question": "A second request", "idempotency_key": "rate-limit-job-2"},
        headers=headers,
    )
    assert blocked.status_code == 429


def test_stage_advance_has_a_separate_per_user_minute_cap(client, monkeypatch):
    secret = "advance-limit-fixture-secret-is-long-enough"
    config = _tight_limits(
        rate_limit_user_advances_per_minute=1,
        dev_auth_enabled=True,
        dev_auth_secret=secret,
    )
    monkeypatch.setattr(rate_limits, "settings", config)
    monkeypatch.setattr(auth_security, "settings", config)
    project = client.post("/api/v1/projects", json={"title": "Advance cap", "domain": "test"})
    token = _local_bearer(auth_security.LOCAL_USER_ID, secret)
    headers = {"Authorization": f"Bearer {token}"}
    job = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={"question": "Test stage limits", "idempotency_key": "advance-limit"},
        headers=headers,
    )
    path = f"/api/v1/research-jobs/{job.json()['id']}/advance"
    first = client.post(path, json={"operation_key": "advance-limit-1"}, headers=headers)
    blocked = client.post(path, json={"operation_key": "advance-limit-2"}, headers=headers)
    assert first.status_code == 200
    assert blocked.status_code == 429


def test_large_request_body_is_rejected_before_json_validation(client):
    response = client.post(
        "/api/v1/projects",
        headers={
            "Origin": "http://localhost:5173",
            "X-Request-ID": "body-limit-client-42",
        },
        json={"title": "x" * (1_048_576 + 10), "domain": "test"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert response.headers["x-request-id"] == "body-limit-client-42"
    assert response.json()["error"]["request_id"] == "body-limit-client-42"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-expose-headers"] == "Content-Disposition, X-Request-ID"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_oversized_request_replaces_invalid_id_once_for_header_and_error_body(client):
    response = client.post(
        "/api/v1/projects",
        headers={"X-Request-ID": "invalid request id"},
        json={"title": "x" * (1_048_576 + 10), "domain": "test"},
    )
    assert response.status_code == 413
    request_id = response.headers["x-request-id"]
    assert request_id != "invalid request id"
    assert response.json()["error"]["request_id"] == request_id


def test_invalid_request_id_is_replaced_before_response_and_validation_echo(client):
    response = client.post(
        "/api/v1/projects",
        headers={"X-Request-ID": "caller supplied id with spaces"},
        json={"unexpected": "field"},
    )
    assert response.status_code == 422
    assert response.headers["x-request-id"] != "caller supplied id with spaces"
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_production_requires_private_rate_limit_hash_secret():
    config = Settings(app_env="production", rate_limit_hash_secret="short")
    try:
        config.validate_security_configuration()
    except ValueError as exc:
        assert "RATE_LIMIT_HASH_SECRET" in str(exc)
    else:
        raise AssertionError("production configuration accepted a short hash secret")


def test_streaming_request_body_without_content_length_is_still_bounded():
    response_messages = []
    route_called = False
    request_messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"45", "more_body": False},
        ]
    )

    async def receive():
        return next(request_messages)

    async def send(message):
        response_messages.append(message)

    async def downstream(scope, receive, send):
        nonlocal route_called
        route_called = True

    middleware = RequestBodyLimitMiddleware(downstream, max_body_bytes=4)
    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/test",
                "headers": [],
                "state": {"request_id": "stream-body-limit-7"},
            },
            receive,
            send,
        )
    )

    assert not route_called
    assert response_messages[0]["status"] == 413
    assert response_messages[1]["body"]
    body = json.loads(response_messages[1]["body"])
    response_headers = dict(response_messages[0]["headers"])
    assert body["error"]["request_id"] == "stream-body-limit-7"
    assert response_headers[b"x-request-id"] == b"stream-body-limit-7"


def test_request_rate_counter_is_atomic_across_processes(tmp_path):
    database_url = str(URL.create("sqlite", database=str(tmp_path / "rate-limit-race.sqlite")))
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    bucket = "a" * 64
    window = datetime.now(UTC).replace(second=0, microsecond=0)
    processes = [
        context.Process(
            target=_process_rate_counter,
            args=(database_url, bucket, window, barrier, results),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    worker_results = []
    for _ in processes:
        try:
            worker_results.append(results.get(timeout=5))
        except queue.Empty:
            break
    exit_codes = [process.exitcode for process in processes]
    assert all(code == 0 for code in exit_codes), (exit_codes, worker_results)
    assert sorted(value for kind, value, *_ in worker_results if kind == "count") == [1, 2], (
        exit_codes,
        worker_results,
    )

    engine = create_engine(database_url)
    with sessionmaker(bind=engine)() as db:
        row = db.scalar(select(RequestRateWindow).where(RequestRateWindow.bucket_hash == bucket))
        assert row is not None
        assert row.request_count == 2
    engine.dispose()
