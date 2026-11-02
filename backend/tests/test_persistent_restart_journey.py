"""End-to-end persistence, resume, report and follow-up journey without live providers."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.providers.scholarly import ScholarlyWork
from app.research import workflow
from app.research.safe_fetch import SafeHTMLDocument
from app.security import AuthUser, get_current_user

USER_ID = "50000000-0000-4000-8000-000000000005"


class JourneyCrossrefFixture:
    def search(self, query: str, *, limit: int = 5):
        assert limit > 0
        return []

    def close(self):
        pass


class JourneyOpenAlexFixture:
    def __init__(self, **kwargs):
        pass

    def search(self, query: str, *, limit: int = 5):
        return [
            ScholarlyWork(
                external_id="doi:10.5555/veda-persistent-journey",
                title="AI tools and productivity for support workers",
                doi="10.5555/veda-persistent-journey",
                url="https://doi.org/10.5555/veda-persistent-journey",
                authors=[{"name": "Asha Researcher"}],
                published_year=2025,
                publisher="Fixture Press",
                abstract_excerpt=None,
                query=query,
                provider="OpenAlex",
                provider_metadata={
                    "openalex_id": "https://openalex.org/W10003",
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/persistent-journey",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    },
                },
            )
        ]

    def close(self):
        pass


class JourneyHTMLFetcher:
    def __init__(self, *, origin_request_limiter=None):
        pass

    def fetch_html(self, url: str, *, license_name: str):
        return SafeHTMLDocument(
            text=(
                "Methods: The workplace study followed customer support workers using an AI tool.\n\n"
                "Results: The study reports that AI tools changed measured productivity for customer support workers."
            ),
            sha256="d" * 64,
            media_type="text/html",
            final_host="papers.example",
            retrieved_at=datetime.now(UTC),
            truncated=False,
            host_policy_id="fixture-reviewed-host-v1",
            host_terms_url="https://papers.example/terms",
            robots_status="rules_checked",
        )


def _new_engine(database_url: str):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    return engine


def _bind_test_runtime(engine):
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: AuthUser(id=USER_ID, provider="test")
    return sessions


def _advance(client, job_id: str, operation: str):
    response = client.post(
        f"/api/v1/research-jobs/{job_id}/advance",
        json={"operation_key": operation},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_reopen_resume_report_citation_and_follow_up_are_one_persistent_journey(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(workflow, "CrossrefProvider", JourneyCrossrefFixture)
    monkeypatch.setattr(workflow, "OpenAlexProvider", JourneyOpenAlexFixture)
    monkeypatch.setattr(workflow, "SafeHTMLFetcher", JourneyHTMLFetcher)
    monkeypatch.setattr(workflow.settings, "llm_provider", "disabled")
    database_url = f"sqlite:///{tmp_path / 'persistent-journey.sqlite'}"
    first_engine = _new_engine(database_url)
    Base.metadata.create_all(first_engine)
    _bind_test_runtime(first_engine)
    reopened_engine = None

    try:
        # First application/client lifetime: plan and discover, then pause before extraction.
        with TestClient(app) as first_client:
            project_response = first_client.post(
                "/api/v1/projects",
                json={"title": "Persistent evidence journey", "domain": "AI economics"},
            )
            assert project_response.status_code == 201, project_response.text
            project = project_response.json()
            job_response = first_client.post(
                f"/api/v1/projects/{project['id']}/research-jobs",
                json={
                    "question": "How does AI affect productivity for customer support workers?",
                    "population": "Customer support workers",
                    "geography": "United States",
                    "depth": "quick",
                    "budget_ceiling_usd": 0,
                    "idempotency_key": "persistent-journey-parent-01",
                },
            )
            assert job_response.status_code == 201, job_response.text
            parent = job_response.json()
            _advance(first_client, parent["id"], "persistent-journey-plan-01")
            discovered = _advance(first_client, parent["id"], "persistent-journey-search-01")
            assert discovered["current_stage"] == "extraction"
            assert discovered["status"] == "active"
            paused = first_client.post(f"/api/v1/research-jobs/{parent['id']}/pause")
            assert paused.status_code == 200, paused.text
            assert paused.json()["status"] == "paused"

        # Recreate the database engine and API client as a local service-restart boundary.
        first_engine.dispose()
        first_engine = None
        reopened_engine = _new_engine(database_url)
        _bind_test_runtime(reopened_engine)

        with TestClient(app) as reopened_client:
            recovered = reopened_client.get(f"/api/v1/research-jobs/{parent['id']}")
            assert recovered.status_code == 200
            assert recovered.json()["current_stage"] == "extraction"
            assert recovered.json()["status"] == "paused"
            assert (
                reopened_client.get(f"/api/v1/research-jobs/{parent['id']}/sources").json()[
                    "items"
                ][0]["title"]
                == "AI tools and productivity for support workers"
            )

            resumed = reopened_client.post(f"/api/v1/research-jobs/{parent['id']}/resume")
            assert resumed.status_code == 200, resumed.text
            assert resumed.json()["status"] == "queued"

            state = resumed.json()
            for step_number in range(1, 10):
                if state["status"] in {"completed", "completed_with_limitations", "cancelled"}:
                    break
                state = _advance(
                    reopened_client,
                    parent["id"],
                    f"persistent-journey-resume-{step_number:02d}",
                )
            assert state["status"] == "completed_with_limitations"
            assert state["current_stage"] == "complete"

            report_response = reopened_client.get(f"/api/v1/research-jobs/{parent['id']}/report")
            assert report_response.status_code == 200
            report = report_response.json()
            assert report["citation_map"]
            assert "[S1]" in report["body_markdown"]
            claims = reopened_client.get(f"/api/v1/research-jobs/{parent['id']}/claims").json()[
                "items"
            ]
            assert claims
            claim = claims[0]
            evidence_response = reopened_client.get(f"/api/v1/claims/{claim['id']}/evidence")
            assert evidence_response.status_code == 200
            evidence = evidence_response.json()
            assert evidence["passage"]["source_id"] == evidence["source"]["id"]
            assert evidence["passage"]["content"] in report["body_markdown"]

            child_response = reopened_client.post(
                f"/api/v1/projects/{project['id']}/research-jobs",
                json={
                    "question": "What new evidence measures AI productivity for customer support workers?",
                    "depth": "quick",
                    "budget_ceiling_usd": 0,
                    "idempotency_key": "persistent-journey-followup-01",
                    "parent_job_id": parent["id"],
                },
            )
            assert child_response.status_code == 201, child_response.text
            child = child_response.json()
            assert child["parent_job_id"] == parent["id"]
            assert child["conversation_id"] == parent["conversation_id"]
            follow_up = reopened_client.get(
                f"/api/v1/research-jobs/{child['id']}/follow-up-context"
            )
            assert follow_up.status_code == 200
            assert follow_up.json()["status"] == "context_attached"
            inherited_claim = next(
                item for item in follow_up.json()["claims"] if item["claim"]["id"] == claim["id"]
            )
            assert inherited_claim["passage"]["id"] == evidence["passage"]["id"]
            assert (
                reopened_client.get(f"/api/v1/research-jobs/{child['id']}/claims").json()["items"]
                == []
            )

            child_plan = _advance(reopened_client, child["id"], "persistent-journey-child-plan-01")
            assert child_plan["current_stage"] == "discovery"
            plan = reopened_client.get(f"/api/v1/research-jobs/{child['id']}/plan").json()
            assert any("newly retrieved evidence" in item["text"] for item in plan["subquestions"])

            messages = reopened_client.get(
                f"/api/v1/conversations/{parent['conversation_id']}/messages?limit=20&offset=0"
            ).json()["items"]
            assert [item["role"] for item in messages] == ["user", "assistant", "user"]
            assert [item["related_job_id"] for item in messages] == [
                parent["id"],
                parent["id"],
                child["id"],
            ]
    finally:
        app.dependency_overrides.clear()
        if reopened_engine is not None:
            reopened_engine.dispose()
        if first_engine is not None:
            first_engine.dispose()
