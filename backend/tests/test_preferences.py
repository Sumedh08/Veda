from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from support import add_test_passage

import app.api.routes as routes
from app.maintenance.retention import count_expired_projects, purge_expired_projects
from app.models import (
    Claim,
    Conversation,
    DiscoveryCandidate,
    EvidenceRelationship,
    Hypothesis,
    JobEvent,
    Message,
    ModelCallReservation,
    Passage,
    Project,
    ResearchJob,
    ResearchReport,
    RetrievedDocument,
    Source,
    UsageEntry,
    utcnow,
)


def test_user_preferences_are_persistent_and_isolated_by_authenticated_identity(client):
    default_response = client.get("/api/v1/me/preferences")
    assert default_response.status_code == 200
    assert default_response.json() == {
        "default_depth": "standard",
        "default_budget_ceiling_usd": 0.0,
        "retention_days": None,
        "is_customized": False,
        "updated_at": None,
    }

    updated = client.patch(
        "/api/v1/me/preferences",
        json={"default_depth": "deep", "default_budget_ceiling_usd": 1.25},
    )
    assert updated.status_code == 200
    assert updated.json()["default_depth"] == "deep"
    assert updated.json()["default_budget_ceiling_usd"] == 1.25
    assert updated.json()["retention_days"] is None
    assert updated.json()["is_customized"] is True
    assert "user_id" not in updated.json()

    owner_a = client.test_user["id"]
    client.test_user["id"] = "20000000-0000-4000-8000-000000000002"
    owner_b_default = client.get("/api/v1/me/preferences").json()
    assert owner_b_default["default_depth"] == "standard"
    assert owner_b_default["retention_days"] is None
    assert owner_b_default["is_customized"] is False
    client.patch("/api/v1/me/preferences", json={"default_depth": "quick"})

    client.test_user["id"] = owner_a
    assert client.get("/api/v1/me/preferences").json()["default_depth"] == "deep"
    assert client.get("/api/v1/me/preferences").json()["retention_days"] is None


def test_preferences_validate_updates_and_reset_to_defaults(client):
    assert client.patch("/api/v1/me/preferences", json={}).status_code == 422
    assert (
        client.patch("/api/v1/me/preferences", json={"default_depth": "unbounded"}).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/v1/me/preferences", json={"default_budget_ceiling_usd": 2.01}
        ).status_code
        == 422
    )
    assert client.patch("/api/v1/me/preferences", json={"retention_days": 14}).status_code == 422

    client.patch("/api/v1/me/preferences", json={"default_depth": "quick"})
    reset = client.delete("/api/v1/me/preferences")
    assert reset.status_code == 200
    assert reset.json()["default_depth"] == "standard"
    assert reset.json()["default_budget_ceiling_usd"] == 0.0
    assert reset.json()["retention_days"] is None
    assert reset.json()["is_customized"] is False


def test_data_lifecycle_api_states_supported_and_external_operations_disclosed(client):
    response = client.get("/api/v1/me/data-lifecycle")
    assert response.status_code == 200
    lifecycle = response.json()
    assert lifecycle["report_exports"]["formats"] == ["markdown", "json"]
    assert lifecycle["project_archive"]["status"] == "available"
    assert lifecycle["project_archive"]["restore_supported"] is True
    assert lifecycle["project_permanent_deletion"]["status"] == "available"
    assert lifecycle["veda_data_deletion"]["status"] == "available"
    assert lifecycle["veda_data_deletion"]["confirmation_phrase"] == "DELETE VEDA DATA"
    assert lifecycle["full_account_export"]["status"] == "available"
    assert lifecycle["full_account_export"]["format"] == "json"
    assert lifecycle["account_deletion"]["status"] == "unsupported"
    assert lifecycle["retention"]["status"] == "configurable_archived_project_retention"
    assert lifecycle["retention"]["options_days"] == [30, 90, 365]
    assert "no scheduler is configured" in lifecycle["retention"]["detail"].lower()


def test_retention_preference_applies_to_new_archives_and_restore_cancels_it(client, monkeypatch):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    monkeypatch.setattr(routes, "utcnow", lambda: now)
    project = client.post(
        "/api/v1/projects", json={"title": "Scheduled project", "domain": "testing"}
    ).json()

    updated = client.patch("/api/v1/me/preferences", json={"retention_days": 30})
    assert updated.status_code == 200
    assert updated.json()["retention_days"] == 30
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    archived = client.get("/api/v1/projects?archived_only=true").json()["items"][0]
    archived_at = datetime.fromisoformat(archived["archived_at"])
    purge_at = datetime.fromisoformat(archived["purge_at"])
    assert archived_at.replace(tzinfo=UTC) == now
    assert purge_at.replace(tzinfo=UTC) == now + timedelta(days=30)

    restored = client.post(f"/api/v1/projects/{project['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["purge_at"] is None

    cleared = client.patch("/api/v1/me/preferences", json={"retention_days": None})
    assert cleared.status_code == 200
    assert cleared.json()["retention_days"] is None
    assert client.get("/api/v1/me/preferences").json()["retention_days"] is None


def test_retention_purger_only_removes_due_archived_projects_in_batches(client):
    now = datetime(2026, 10, 29, tzinfo=UTC)
    owner = client.test_user["id"]
    due = [
        Project(
            owner_id=owner,
            title=f"Expired {index}",
            domain="testing",
            archived_at=now - timedelta(days=31),
            purge_at=now - timedelta(seconds=1),
        )
        for index in range(2)
    ]
    future = Project(
        owner_id=owner,
        title="Not due",
        domain="testing",
        archived_at=now - timedelta(days=2),
        purge_at=now + timedelta(days=1),
    )
    never = Project(
        owner_id=owner,
        title="Keep indefinitely",
        domain="testing",
        archived_at=now - timedelta(days=365),
        purge_at=None,
    )
    active = Project(
        owner_id=owner,
        title="Active project with stale field",
        domain="testing",
        archived_at=None,
        purge_at=now - timedelta(days=1),
    )
    with client.db_sessions() as db:
        db.add_all([*due, future, never, active])
        db.commit()
        assert count_expired_projects(db, now=now) == 2
        assert purge_expired_projects(db, now=now, batch_size=1) == 2
        assert purge_expired_projects(db, now=now, batch_size=1) == 0
        assert db.get(Project, future.id) is not None
        assert db.get(Project, never.id) is not None
        assert db.get(Project, active.id) is not None


def test_full_account_export_streams_owned_records_and_redacts_credential_shaped_values(client):
    owner_id = client.test_user["id"]
    project = client.post(
        "/api/v1/projects",
        json={"title": "Exported project", "domain": "testing"},
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How did the pilot affect reported productivity?",
            "idempotency_key": "account-export-job-01",
        },
    ).json()
    client.patch("/api/v1/me/preferences", json={"default_depth": "deep"})
    with client.db_sessions() as db:
        persisted_project = db.get(Project, project["id"])
        persisted_project.settings_json = {"api_key": "fixture-secret-never-export"}
        source = Source(
            job_id=job["id"],
            external_id="fixture:account-export-source",
            title="Export source",
            metadata_json={"provider_metadata": {"client_secret": "nested-secret"}},
        )
        db.add(source)
        db.flush()
        passage = add_test_passage(
            db,
            source,
            ordinal=0,
            locator="abstract sentence 1",
            content="The study reports an association.",
        )
        db.add(
            Claim(
                job_id=job["id"], source_id=source.id, passage_id=passage.id, text=passage.content
            )
        )
        db.add(
            ResearchReport(
                job_id=job["id"],
                status="completed_with_limitations",
                body_markdown="An exported report.",
                citation_map_json={},
                verification_json={},
            )
        )
        db.add(
            UsageEntry(
                job_id=job["id"],
                operation="veda_appraisal_batch_v2",
                provider="openrouter",
                model_name="example/free-model:free",
                reported_cost_usd=0,
                estimated_cost_usd=0,
                finish_reason="length",
                error_class="provider_output_truncated",
                succeeded=False,
            )
        )
        db.commit()

    client.test_user["id"] = "20000000-0000-4000-8000-000000000002"
    other_project = client.post(
        "/api/v1/projects",
        json={"title": "Another owner's project", "domain": "testing"},
    ).json()
    client.test_user["id"] = owner_id

    response = client.get("/api/v1/me/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    exported = response.json()
    assert exported["export"]["schema_version"] == 1
    assert exported["export"]["account_user_id"] == owner_id
    assert exported["export"]["excludes"]
    collections = exported["collections"]
    assert [item["id"] for item in collections["projects"]] == [project["id"]]
    assert [item["id"] for item in collections["research_jobs"]] == [job["id"]]
    assert len(collections["conversations"]) == 1
    assert len(collections["messages"]) == 1
    assert len(collections["sources"]) == 1
    assert len(collections["retrieved_documents"]) == 1
    assert len(collections["passages"]) == 1
    assert len(collections["claims"]) == 1
    assert len(collections["reports"]) == 1
    assert collections["usage_ledger"][0]["finish_reason"] == "length"
    assert collections["usage_ledger"][0]["error_class"] == "provider_output_truncated"
    exported_report = collections["reports"][0]
    assert exported_report["citation_map_json"]["schema_version"] == 1
    assert exported_report["citation_map_json"]["citations"] == {}
    assert exported_report["verification_json"]["schema_version"] == 1
    assert exported_report["verification_json"]["record"]["report_schema_version"] == 1
    assert collections["user_preferences"][0]["user_id"] == owner_id
    assert "[redacted]" in response.text
    assert "fixture-secret-never-export" not in response.text
    assert "nested-secret" not in response.text
    assert other_project["id"] not in response.text


def test_permanent_project_deletion_requires_typed_confirmation_and_cascades_owned_data(client):
    title = "Project to permanently remove"
    project = client.post("/api/v1/projects", json={"title": title, "domain": "testing"}).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What does this project retain for deletion?",
            "idempotency_key": "purge-project-job-01",
        },
    ).json()
    with client.db_sessions() as db:
        conversation = Conversation(project_id=project["id"], title=title)
        db.add(conversation)
        db.flush()
        db.get(ResearchJob, job["id"]).conversation_id = conversation.id
        db.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=job["question"],
                related_job_id=job["id"],
            )
        )
        db.add(
            JobEvent(job_id=job["id"], event_type="fixture", stage="planning", message="Purge test")
        )
        source = Source(job_id=job["id"], external_id="fixture:purge-source", title="Purge source")
        db.add(source)
        db.flush()
        db.add(
            DiscoveryCandidate(
                job_id=job["id"],
                candidate_key="a" * 64,
                provider="Crossref",
                provider_record_id="fixture:purge-candidate",
                canonical_identity="Crossref:fixture:purge-candidate",
                title="Purge candidate",
                query_text="purge cascade",
                disposition="selected",
                reason_code="selected_by_rank",
                canonical_source_id=source.id,
                discovered_at=utcnow(),
            )
        )
        passage = add_test_passage(
            db,
            source,
            ordinal=0,
            locator="abstract sentence 1",
            content="A passage that must be deleted with its project.",
        )
        db.add(
            Claim(
                job_id=job["id"], source_id=source.id, passage_id=passage.id, text=passage.content
            )
        )
        db.flush()
        claim = db.scalar(select(Claim).where(Claim.job_id == job["id"]))
        assert claim is not None
        db.add(
            EvidenceRelationship(
                job_id=job["id"],
                claim_a_id=claim.id,
                claim_b_id=claim.id,
                relationship_type="supports",
                scope_alignment="same",
                rationale="Fixture relation for project cascade.",
                status="fixture",
            )
        )
        db.add(
            Hypothesis(
                job_id=job["id"],
                comparison_group_id="purge-comparison-group",
                side="A",
                statement="Fixture hypothesis for project cascade.",
                uncertainty="Fixture only.",
                why_competing="Fixture only.",
                status="fixture",
            )
        )
        reservation = ModelCallReservation(
            job_id=job["id"],
            user_id=client.test_user["id"],
            operation="fixture_export",
            attempt=0,
            provider="openrouter",
            request_hash="b" * 64,
            quota_date=date.today(),
        )
        db.add(reservation)
        db.flush()
        db.add(
            UsageEntry(
                job_id=job["id"],
                quota_reservation_id=reservation.id,
                operation="fixture_export",
                provider="openrouter",
                succeeded=True,
            )
        )
        db.add(
            ResearchReport(
                job_id=job["id"],
                status="completed_with_limitations",
                body_markdown="A report to purge.",
                citation_map_json={},
                verification_json={},
            )
        )
        db.commit()

    active_purge = client.request(
        "DELETE",
        f"/api/v1/projects/{project['id']}/permanent",
        json={"confirmation": "DELETE", "project_title": project["title"]},
    )
    assert active_purge.status_code == 409
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    missing_confirmation = client.request(
        "DELETE",
        f"/api/v1/projects/{project['id']}/permanent",
        json={"confirmation": "DELETE", "project_title": "wrong title"},
    )
    assert missing_confirmation.status_code == 409
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404

    owner_id = client.test_user["id"]
    client.test_user["id"] = "30000000-0000-4000-8000-000000000003"
    foreign_delete = client.request(
        "DELETE",
        f"/api/v1/projects/{project['id']}/permanent",
        json={"confirmation": "DELETE", "project_title": title},
    )
    assert foreign_delete.status_code == 404
    client.test_user["id"] = owner_id

    deleted = client.request(
        "DELETE",
        f"/api/v1/projects/{project['id']}/permanent",
        json={"confirmation": "DELETE", "project_title": title},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    with client.db_sessions() as db:
        for model in (
            Project,
            Conversation,
            Message,
            ResearchJob,
            JobEvent,
            Source,
            DiscoveryCandidate,
            RetrievedDocument,
            Passage,
            Claim,
            EvidenceRelationship,
            Hypothesis,
            ResearchReport,
            ModelCallReservation,
            UsageEntry,
        ):
            assert db.scalar(select(func.count()).select_from(model)) == 0
