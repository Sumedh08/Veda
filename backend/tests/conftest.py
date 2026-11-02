import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.research import workflow
from app.security import AuthUser, get_current_user


class EmptyOpenAlex:
    def __init__(self, *args, **kwargs):
        pass

    def search(self, query, *, limit=5):
        return []

    def close(self):
        pass


@pytest.fixture(autouse=True)
def disable_live_openalex_calls(monkeypatch):
    monkeypatch.setattr(workflow, "OpenAlexProvider", EmptyOpenAlex)


@pytest.fixture(autouse=True)
def disable_live_crawl4ai_calls(monkeypatch):
    monkeypatch.setattr(workflow.settings, "crawl4ai_enabled", False)


@pytest.fixture(autouse=True)
def disable_live_europe_pmc_calls(monkeypatch):
    class UnavailableEuropePMC:
        requests_attempted = 0

        def __init__(self, *args, **kwargs):
            pass

        def resolve_full_text(self, pmcid, *, expected_doi=None):
            return workflow.EuropePMCResolution(
                status="unavailable",
                reason_code="offline_fixture",
                metadata=None,
                requests_attempted=0,
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "EuropePMCProvider", UnavailableEuropePMC)


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    testing_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    current = {"id": "10000000-0000-4000-8000-000000000001"}

    def override_db():
        session = testing_sessions()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        return AuthUser(id=current["id"], provider="test")

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as test_client:
        test_client.test_user = current
        test_client.db_sessions = testing_sessions
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_user(client):
    return client.test_user
