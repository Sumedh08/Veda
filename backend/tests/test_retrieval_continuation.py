from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from support import add_test_passage

from app.db import Base, get_db
from app.main import app
from app.models import (
    Claim,
    DiscoveryCandidate,
    ResearchJob,
    ResearchReport,
    RetrievedDocument,
    Source,
)
from app.research import workflow
from app.research.safe_fetch import SafeHTMLDocument
from app.security import AuthUser, get_current_user


def _completed_run_with_deferred_source(client, *, due_at, include_successful_source=True):
    project = client.post("/api/v1/projects", json={"title": "Deferred retry", "domain": "testing"})
    assert project.status_code == 201
    created = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={
            "question": "How did the technology affect worker productivity?",
            "depth": "quick",
            "budget_ceiling_usd": 0,
            "idempotency_key": "deferred-retry-parent-01",
        },
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    with client.db_sessions() as db:
        parent = db.get(ResearchJob, job_id)
        parent.status = "completed_with_limitations"
        parent.current_stage = "complete"
        source = Source(
            job_id=job_id,
            external_id="openalex:W-deferred-html",
            title="Deferred Open Access paper",
            doi="10.5555/deferred-html",
            url="https://doi.org/10.5555/deferred-html",
            authors_json=[{"given": "Sam", "family": "Author"}],
            published_year=2025,
            publisher="Fixture Press",
            retrieval_status="abstract_only",
            abstract_excerpt="An abstract passage already saved before the deferred full text.",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/deferred",
                        "pdf_url": None,
                        "license": "cc-by",
                        "version": "publishedVersion",
                    }
                },
                "retrieval": {
                    "status": "deferred",
                    "error_code": "origin_request_deferred",
                    "retry_after_seconds": 0.808,
                    "license": "cc-by",
                    "deferred_retries": {
                        "html": {
                            "status": "pending",
                            "due_at": due_at.isoformat(),
                            "retry_after_seconds": 0.808,
                            "error_code": "origin_request_deferred",
                        }
                    },
                },
            },
        )
        sources = [source]
        if include_successful_source:
            sources.append(
                Source(
                    job_id=job_id,
                    external_id="openalex:W-already-retrieved",
                    title="Previously retrieved paper",
                    url="https://doi.org/10.5555/previously-retrieved",
                    retrieval_status="full_text_html",
                    abstract_excerpt="Previously saved source sentence.",
                    metadata_json={
                        "provider": "OpenAlex",
                        "provider_metadata": {
                            "best_oa_location": {
                                "is_oa": True,
                                "landing_page_url": "https://papers.example/should-not-refetch",
                                "license": "cc-by",
                                "version": "publishedVersion",
                            }
                        },
                        "retrieval": {"status": "retrieved"},
                    },
                )
            )
        db.add_all(sources)
        db.flush()
        for index, item in enumerate(sources):
            passage = add_test_passage(
                db,
                item,
                ordinal=0,
                locator=f"saved source {index + 1}",
                content=f"Saved source {index + 1} reports a measured productivity change.",
                access_level=(
                    "full_text_html"
                    if item.retrieval_status == "full_text_html"
                    else "abstract_only"
                ),
            )
            db.flush()
            db.add(
                Claim(
                    job_id=job_id,
                    source_id=item.id,
                    passage_id=passage.id,
                    text=passage.content,
                    span_start=0,
                    span_end=len(passage.content),
                    atomization_status="whole_sentence",
                    atomization_version=1,
                    appraisal_json={"fixture": "parent evidence"},
                )
            )
        db.add(
            ResearchReport(
                job_id=job_id,
                status="completed_with_limitations",
                body_markdown="Original immutable report body.",
                citation_map_json={"S1": sources[0].id},
                verification_json={"report_schema_version": 2},
            )
        )
        db.commit()
    return created.json(), sources


def _queue_continuation(client, parent_id):
    response = client.post(f"/api/v1/research-jobs/{parent_id}/retry-deferred")
    assert response.status_code == 200, response.text
    return response.json()


def test_early_deferred_retry_is_rejected_without_creating_a_child(client):
    parent, _sources = _completed_run_with_deferred_source(
        client,
        due_at=datetime.now(UTC) + timedelta(minutes=5),
        include_successful_source=False,
    )

    response = client.post(f"/api/v1/research-jobs/{parent['id']}/retry-deferred")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "deferred_retrieval_not_due"
    assert response.json()["detail"]["retry_after_seconds"] > 0
    jobs = client.get(f"/api/v1/projects/{parent['project_id']}/research-jobs").json()["items"]
    assert len(jobs) == 1


def test_workflow_persists_deferred_retry_due_time_from_fetcher(client, monkeypatch):
    from app.research.safe_fetch import SafeFetchError

    project = client.post(
        "/api/v1/projects", json={"title": "Persist due time", "domain": "testing"}
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How does this study measure productivity?",
            "depth": "quick",
            "idempotency_key": "persist-deferred-due-time-01",
        },
    ).json()

    class DeferringFetcher:
        def __init__(self, *, origin_request_limiter=None):
            self.timeout_seconds = 4

        def fetch_html(self, url, *, license_name):
            raise SafeFetchError(
                "origin_request_deferred",
                "The host request interval exceeds this retrieval step's deadline.",
                retry_after_seconds=12.5,
            )

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", DeferringFetcher)
    with client.db_sessions() as db:
        job = db.get(ResearchJob, created["id"])
        job.current_stage = "extraction"
        source = Source(
            job_id=job.id,
            external_id="openalex:W-persist-deferred",
            title="Deferred scholarly source",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/deferred-again",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    }
                },
            },
        )
        db.add(source)
        db.commit()
        before = datetime.now(UTC)

        result = workflow.execute_stage(db, workflow.job_snapshot(job))
        workflow.persist_result(db, job, result)
        db.commit()
        db.refresh(source)

        retry = source.metadata_json["retrieval"]["deferred_retries"]["html"]
        due_at = datetime.fromisoformat(retry["due_at"])
        assert retry["status"] == "pending"
        assert retry["retry_after_seconds"] == 12.5
        assert (
            source.metadata_json["retrieval"]["outcomes"]["by_format"]["html"]["outcome"]
            == "deferred"
        )
        assert due_at >= before + timedelta(seconds=12)
        assert result.event_data["licensed_html_deferred"] == 1


def test_due_retry_creates_owner_scoped_idempotent_child_and_copies_lineage(client):
    parent, parent_sources = _completed_run_with_deferred_source(
        client, due_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    parent_report = client.get(f"/api/v1/research-jobs/{parent['id']}/report").json()
    parent_claims = client.get(f"/api/v1/research-jobs/{parent['id']}/claims").json()["items"]
    assert parent_claims
    eligible_parent_source_ids = {
        source.id for source in parent_sources if source.retrieval_status != "abstract_only"
    }
    eligible_parent_claims = [
        claim for claim in parent_claims if claim["source_id"] in eligible_parent_source_ids
    ]

    continuation = _queue_continuation(client, parent["id"])
    child = continuation["job"]
    assert continuation["queued_retry_count"] == 1
    assert continuation["idempotent_replay"] is False
    assert child["parent_job_id"] == parent["id"]
    assert child["current_stage"] == "extraction"
    assert child["status"] == "queued"
    assert child["budget_ceiling_usd"] == parent["budget_ceiling_usd"]
    assert client.get(f"/api/v1/research-jobs/{child['id']}/report").status_code == 404

    replay = _queue_continuation(client, parent["id"])
    assert replay["job"]["id"] == child["id"]
    assert replay["idempotent_replay"] is True

    parent_source = client.get(f"/api/v1/sources/{parent_sources[0].id}").json()
    assert parent_source["retrieval"]["deferred_retries"]["html"]["status"] == "scheduled"
    assert parent_source["retrieval"]["outcomes"]["by_format"]["html"]["outcome"] == "deferred"
    child_sources = client.get(f"/api/v1/research-jobs/{child['id']}/sources").json()["items"]
    assert len(child_sources) == len(parent_sources)
    child_target = next(
        source for source in child_sources if source["doi"] == "10.5555/deferred-html"
    )
    assert child_target["retrieval"]["deferred_retries"]["html"]["status"] == "pending"
    assert child_target["retrieval"]["outcomes"]["by_format"]["html"]["outcome"] == "deferred"

    child_claims = client.get(f"/api/v1/research-jobs/{child['id']}/claims").json()["items"]
    assert len(child_claims) == len(eligible_parent_claims)
    assert {claim["text"] for claim in child_claims} == {
        claim["text"] for claim in eligible_parent_claims
    }
    assert {claim["id"] for claim in child_claims}.isdisjoint(
        {claim["id"] for claim in parent_claims}
    )
    context = client.get(f"/api/v1/research-jobs/{child['id']}/follow-up-context").json()
    assert context["status"] == "retrieval_continuation"
    assert "copied" in context["reuse_boundary"]

    parent_report_after = client.get(f"/api/v1/research-jobs/{parent['id']}/report").json()
    assert parent_report_after["id"] == parent_report["id"]
    assert parent_report_after["body_markdown"] == parent_report["body_markdown"]
    assert parent_report_after["evidence_content_withheld"] is True
    with client.db_sessions() as db:
        persisted_parent_report = db.get(ResearchReport, parent_report["id"])
        assert persisted_parent_report.body_markdown == "Original immutable report body."

    previous_user = client.test_user["id"]
    client.test_user["id"] = "20000000-0000-4000-8000-000000000002"
    assert client.get(f"/api/v1/research-jobs/{child['id']}").status_code == 404
    assert client.post(f"/api/v1/research-jobs/{parent['id']}/retry-deferred").status_code == 404
    client.test_user["id"] = previous_user


def test_continuation_does_not_copy_legacy_candidate_abstract_without_item_rights(client):
    parent, _sources = _completed_run_with_deferred_source(
        client, due_at=datetime.now(UTC) - timedelta(seconds=1), include_successful_source=False
    )
    with client.db_sessions() as db:
        db.add(
            DiscoveryCandidate(
                job_id=parent["id"],
                candidate_key="c" * 64,
                provider="OpenAlex",
                provider_record_id="openalex:W-legacy-candidate",
                canonical_identity="openalex:w-legacy-candidate",
                title="Legacy candidate with an unverified abstract snapshot",
                abstract_excerpt="Previously persisted text without item-level rights.",
                abstract_excerpt_retention_status="retained_openalex_metadata_cc0_v1",
                doi="10.5555/legacy-candidate",
                url="https://openalex.org/W-legacy-candidate",
                published_year=2025,
                query_text="developer productivity field study",
                ranking_order=1,
                relevance_score=0.5,
                relevance_json=None,
                disposition="excluded",
                reason_code="source_limit",
                canonical_source_id=None,
                discovered_at=datetime.now(UTC),
            )
        )
        db.commit()

    parent_candidate = client.get(f"/api/v1/research-jobs/{parent['id']}/candidates").json()[
        "items"
    ][0]
    assert parent_candidate["abstract_excerpt"] is None

    continuation = _queue_continuation(client, parent["id"])
    child_candidate = client.get(
        f"/api/v1/research-jobs/{continuation['job']['id']}/candidates"
    ).json()["items"][0]

    assert child_candidate["abstract_excerpt"] is None
    assert (
        child_candidate["abstract_excerpt_retention_status"]
        == "not_retained_item_text_rights_unverified"
    )


def test_continuation_does_not_reuse_legacy_abstract_passages_or_claims(client):
    parent, parent_sources = _completed_run_with_deferred_source(
        client, due_at=datetime.now(UTC) - timedelta(seconds=1), include_successful_source=False
    )
    parent_source = parent_sources[0]
    parent_report = client.get(f"/api/v1/research-jobs/{parent['id']}/report").json()
    parent_claims = client.get(f"/api/v1/research-jobs/{parent['id']}/claims").json()["items"]
    assert parent_source.abstract_excerpt
    assert parent_claims

    child = _queue_continuation(client, parent["id"])["job"]
    child_source = client.get(f"/api/v1/research-jobs/{child['id']}/sources").json()["items"][0]
    child_detail = client.get(f"/api/v1/sources/{child_source['id']}").json()
    child_claims = client.get(f"/api/v1/research-jobs/{child['id']}/claims").json()["items"]

    assert child_source["abstract_excerpt"] is None
    assert child_source["retrieval_status"] == "metadata_only"
    assert child_source["abstract_text_retention_status"] == (
        "not_retained_item_text_rights_unverified"
    )
    assert child_detail["passages"] == []
    assert child_claims == []
    assert (
        client.get(f"/api/v1/research-jobs/{parent['id']}/claims").json()["items"] == parent_claims
    )
    assert (
        client.get(f"/api/v1/research-jobs/{parent['id']}/report").json()["id"]
        == parent_report["id"]
    )


def test_due_continuation_retries_only_deferred_source_and_keeps_reports_versioned(
    client, monkeypatch
):
    monkeypatch.setattr(workflow.settings, "llm_provider", "disabled")
    parent, parent_sources = _completed_run_with_deferred_source(
        client, due_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    original_parent_claims = client.get(f"/api/v1/research-jobs/{parent['id']}/claims").json()[
        "items"
    ]
    eligible_parent_source_ids = {
        source.id for source in parent_sources if source.retrieval_status != "abstract_only"
    }
    eligible_parent_claims = [
        claim
        for claim in original_parent_claims
        if claim["source_id"] in eligible_parent_source_ids
    ]
    original_parent_report = client.get(f"/api/v1/research-jobs/{parent['id']}/report").json()
    continuation = _queue_continuation(client, parent["id"])
    child = continuation["job"]
    fetched_urls = []

    class RecordingFetcher:
        def __init__(self, *, origin_request_limiter=None):
            self.timeout_seconds = 4

        def fetch_html(self, url, *, license_name):
            fetched_urls.append((url, license_name))
            return SafeHTMLDocument(
                text="A newly retrieved licensed paragraph reports higher output per worker-hour.",
                sha256="c" * 64,
                media_type="text/html",
                final_host="papers.example",
                retrieved_at=datetime.now(UTC),
                truncated=False,
                host_policy_id="fixture-reviewed-host-v1",
                host_terms_url="https://papers.example/terms",
                robots_status="rules_checked",
            )

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", RecordingFetcher)
    extraction = client.post(
        f"/api/v1/research-jobs/{child['id']}/advance",
        json={"operation_key": "continue-deferred-extraction-01"},
    )
    assert extraction.status_code == 200, extraction.text
    assert extraction.json()["current_stage"] == "appraisal"
    assert fetched_urls == [("https://papers.example/deferred", "cc-by")]

    child_sources = client.get(f"/api/v1/research-jobs/{child['id']}/sources").json()["items"]
    retried_source = next(
        source for source in child_sources if source["doi"] == "10.5555/deferred-html"
    )
    assert retried_source["retrieval"]["deferred_retries"]["html"]["status"] == "completed"
    assert retried_source["retrieval"]["outcomes"]["by_format"]["html"]["outcome"] == "retrieved"
    assert retried_source["retrieval_status"] == "full_text_html"
    assert retried_source["retrieval"].get("error_code") is None
    assert retried_source["retrieval"].get("retry_after_seconds") is None
    assert not any(url.endswith("should-not-refetch") for url, _license in fetched_urls)

    child_claims = client.get(f"/api/v1/research-jobs/{child['id']}/claims").json()["items"]
    assert len(child_claims) > len(eligible_parent_claims)
    assert {claim["text"] for claim in eligible_parent_claims}.issubset(
        {claim["text"] for claim in child_claims}
    )
    with client.db_sessions() as db:
        documents = list(
            db.scalars(
                select(RetrievedDocument).where(RetrievedDocument.source_id == retried_source["id"])
            )
        )
        assert len(documents) == 1

    state = extraction.json()
    for index in range(1, 10):
        if state["status"] in {"completed", "completed_with_limitations", "terminal_failure"}:
            break
        advanced = client.post(
            f"/api/v1/research-jobs/{child['id']}/advance",
            json={"operation_key": f"continue-deferred-stage-{index:02d}"},
        )
        assert advanced.status_code == 200, advanced.text
        state = advanced.json()
    assert state["status"] == "completed_with_limitations"
    child_report = client.get(f"/api/v1/research-jobs/{child['id']}/report").json()
    parent_report_after = client.get(f"/api/v1/research-jobs/{parent['id']}/report").json()
    assert child_report["id"] != original_parent_report["id"]
    assert child_report["job_id"] == child["id"]
    assert parent_report_after["id"] == original_parent_report["id"]
    assert parent_report_after["body_markdown"] == original_parent_report["body_markdown"]
    final_parent_claims = client.get(f"/api/v1/research-jobs/{parent['id']}/claims").json()["items"]
    assert len(final_parent_claims) == len(original_parent_claims)


def test_deferred_continuation_survives_database_engine_restart(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'deferred-continuation.sqlite'}"
    user_id = "30000000-0000-4000-8000-000000000003"

    def open_database():
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 10},
        )
        event.listen(
            engine,
            "connect",
            lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
        )
        Base.metadata.create_all(engine)
        return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def bind_sessions(sessions):
        def override_db():
            with sessions() as db:
                yield db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: AuthUser(id=user_id, provider="test")

    first_engine, first_sessions = open_database()
    bind_sessions(first_sessions)
    try:
        with TestClient(app) as first_client:
            project = first_client.post(
                "/api/v1/projects", json={"title": "Restart queue", "domain": "testing"}
            ).json()
            parent = first_client.post(
                f"/api/v1/projects/{project['id']}/research-jobs",
                json={
                    "question": "Can this source be retrieved after host pacing?",
                    "depth": "quick",
                    "idempotency_key": "restart-deferred-parent-01",
                },
            ).json()
            with first_sessions() as db:
                job = db.get(ResearchJob, parent["id"])
                job.status = "completed_with_limitations"
                job.current_stage = "complete"
                db.add(
                    Source(
                        job_id=job.id,
                        external_id="openalex:W-restart-deferred",
                        title="Restart deferred source",
                        retrieval_status="metadata_only",
                        metadata_json={
                            "provider": "OpenAlex",
                            "provider_metadata": {
                                "best_oa_location": {
                                    "is_oa": True,
                                    "landing_page_url": "https://papers.example/restart",
                                    "license": "cc-by",
                                    "version": "publishedVersion",
                                }
                            },
                            "retrieval": {
                                "status": "deferred",
                                "deferred_retries": {
                                    "html": {
                                        "status": "pending",
                                        "due_at": (
                                            datetime.now(UTC) - timedelta(seconds=1)
                                        ).isoformat(),
                                        "retry_after_seconds": 0,
                                    }
                                },
                            },
                        },
                    )
                )
                db.commit()
            queued = first_client.post(f"/api/v1/research-jobs/{parent['id']}/retry-deferred")
            assert queued.status_code == 200, queued.text
            child_id = queued.json()["job"]["id"]
    finally:
        first_engine.dispose()

    reopened_engine, reopened_sessions = open_database()
    bind_sessions(reopened_sessions)
    fetched = []

    class RestartFetcher:
        def __init__(self, *, origin_request_limiter=None):
            self.timeout_seconds = 4

        def fetch_html(self, url, *, license_name):
            fetched.append((url, license_name))
            return SafeHTMLDocument(
                text="The restarted continuation retrieved this source sentence.",
                sha256="d" * 64,
                media_type="text/html",
                final_host="papers.example",
                retrieved_at=datetime.now(UTC),
                truncated=False,
                host_policy_id="fixture-reviewed-host-v1",
                host_terms_url="https://papers.example/terms",
                robots_status="rules_checked",
            )

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", RestartFetcher)
    try:
        with TestClient(app) as reopened_client:
            recovered = reopened_client.get(f"/api/v1/research-jobs/{child_id}")
            assert recovered.status_code == 200
            assert recovered.json()["status"] == "queued"
            assert recovered.json()["current_stage"] == "extraction"
            source = reopened_client.get(f"/api/v1/research-jobs/{child_id}/sources").json()[
                "items"
            ][0]
            assert source["retrieval"]["deferred_retries"]["html"]["status"] == "pending"

            advanced = reopened_client.post(
                f"/api/v1/research-jobs/{child_id}/advance",
                json={"operation_key": "restart-retrieval-extraction-01"},
            )
            assert advanced.status_code == 200, advanced.text
            assert advanced.json()["current_stage"] == "appraisal"
            assert fetched == [("https://papers.example/restart", "cc-by")]
    finally:
        app.dependency_overrides.clear()
        reopened_engine.dispose()
