from app.db import get_db


def test_readiness_reports_database_reachable(client):
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "reachable"}


def test_readiness_returns_sanitized_unavailable_when_database_query_fails(client):
    class UnavailableDatabase:
        def execute(self, _statement):
            raise RuntimeError("postgresql://user:password=secret@db.example/private")

    def unavailable_database():
        yield UnavailableDatabase()

    client.app.dependency_overrides[get_db] = unavailable_database

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is not ready"}
    assert "password=secret" not in response.text


def test_liveness_remains_healthy_when_database_dependency_is_unavailable(client):
    dependency_attempts = 0

    def unavailable_database():
        nonlocal dependency_attempts
        dependency_attempts += 1
        raise RuntimeError("database should not be touched by liveness")
        yield  # Make this a dependency generator without opening a connection.

    client.app.dependency_overrides[get_db] = unavailable_database

    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert dependency_attempts == 0
