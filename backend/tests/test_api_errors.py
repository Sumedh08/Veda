import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError

from app.db import get_db


@pytest.mark.parametrize(
    ("failure_type", "expected_status", "expected_code", "expected_message"),
    [
        (
            OperationalError,
            503,
            "storage_unavailable",
            "Storage is temporarily unavailable. Please retry.",
        ),
        (
            IntegrityError,
            500,
            "storage_error",
            "The storage operation could not be completed.",
        ),
    ],
)
def test_route_database_failure_returns_stable_sanitized_response(
    client, caplog, failure_type, expected_status, expected_code, expected_message
):
    request_id = f"route-db-failure-{expected_status}"
    database_secret = "postgresql://veda:password=secret@db.example/private"

    def failing_route_database():
        db = client.db_sessions()

        def fail_scalar(*_args, **_kwargs):
            raise failure_type("SELECT projects", {}, RuntimeError(database_secret))

        db.scalar = fail_scalar
        try:
            yield db
        finally:
            db.close()

    client.app.dependency_overrides[get_db] = failing_route_database

    with caplog.at_level(logging.ERROR):
        response = client.get(
            "/api/v1/projects",
            headers={
                "X-Request-ID": request_id,
                "Origin": "http://localhost:5173",
            },
        )

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {
            "code": expected_code,
            "message": expected_message,
            "request_id": request_id,
        }
    }
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "password=secret" not in response.text
    assert "password=secret" not in caplog.text
    assert f"error_class={failure_type.__name__}" in caplog.text


def test_unhandled_route_failure_returns_generic_error_with_request_metadata(client, caplog):
    request_id = "route-unhandled-500"
    exception_secret = "postgresql://veda:password=secret@db.example/private"

    def failing_route_database():
        db = client.db_sessions()

        def fail_scalar(*_args, **_kwargs):
            raise RuntimeError(exception_secret)

        db.scalar = fail_scalar
        try:
            yield db
        finally:
            db.close()

    client.app.dependency_overrides[get_db] = failing_route_database
    no_raise_client = TestClient(client.app, raise_server_exceptions=False)

    with caplog.at_level(logging.ERROR):
        response = no_raise_client.get(
            "/api/v1/projects",
            headers={
                "X-Request-ID": request_id,
                "Origin": "http://localhost:5173",
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "The request could not be completed.",
            "request_id": request_id,
        }
    }
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "password=secret" not in response.text
    assert "password=secret" not in caplog.text
    assert "error_class=RuntimeError" in caplog.text
