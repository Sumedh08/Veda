from datetime import timedelta

from sqlalchemy import func, or_, select
from support import add_test_passage

from app.models import (
    Claim,
    Conversation,
    DailyModelQuota,
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
    UserPreference,
    utcnow,
)


def _create_project_and_job(client, title: str, idempotency_key: str):
    project_response = client.post("/api/v1/projects", json={"title": title, "domain": "testing"})
    assert project_response.status_code == 201
    project = project_response.json()
    job_response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Should Veda data deletion preserve safety counters?",
            "idempotency_key": idempotency_key,
        },
    )
    assert job_response.status_code == 201
    return project, job_response.json()


def test_veda_data_purge_requires_confirmation_and_isolates_owner(client):
    owner_id = client.test_user["id"]
    owner_project, owner_job = _create_project_and_job(
        client, "Owner data to erase", "owner-data-purge-01"
    )
    other_user_id = "40000000-0000-4000-8000-000000000004"
    client.test_user["id"] = other_user_id
    other_project, _ = _create_project_and_job(
        client, "Other user's data to keep", "other-data-purge-01"
    )
    client.test_user["id"] = owner_id

    today = utcnow().date()
    with client.db_sessions() as db:
        db.add_all(
            [
                UserPreference(user_id=owner_id, retention_days=90),
                UserPreference(user_id=other_user_id, retention_days=30),
                DailyModelQuota(scope="user", scope_id=owner_id, quota_date=today, calls_used=4),
                DailyModelQuota(
                    scope="user",
                    scope_id=owner_id,
                    quota_date=today - timedelta(days=1),
                    calls_used=8,
                ),
                DailyModelQuota(
                    scope="user", scope_id=other_user_id, quota_date=today, calls_used=3
                ),
                DailyModelQuota(
                    scope="global", scope_id="all-users", quota_date=today, calls_used=9
                ),
            ]
        )
        db.commit()

    invalid = client.request(
        "DELETE", "/api/v1/me/data", json={"confirmation": "DELETE EVERYTHING"}
    )
    assert invalid.status_code == 422
    extra_field = client.request(
        "DELETE",
        "/api/v1/me/data",
        json={"confirmation": "DELETE VEDA DATA", "owner_id": other_user_id},
    )
    assert extra_field.status_code == 422

    deleted = client.request("DELETE", "/api/v1/me/data", json={"confirmation": "DELETE VEDA DATA"})
    assert deleted.status_code == 200
    assert deleted.json() == {
        "deleted_projects": 1,
        "deleted_preferences": True,
        "daily_quota_counters_preserved_until_utc_date": today.isoformat(),
        "identity_provider_account_deleted": False,
    }

    with client.db_sessions() as db:
        assert db.get(Project, owner_project["id"]) is None
        assert db.get(ResearchJob, owner_job["id"]) is None
        assert db.get(Project, other_project["id"]) is not None
        assert db.get(UserPreference, owner_id) is None
        assert db.get(UserPreference, other_user_id) is not None
        quotas = list(db.scalars(select(DailyModelQuota)).all())
        assert {
            (item.scope, item.scope_id, item.quota_date, item.calls_used) for item in quotas
        } == {
            ("user", owner_id, today, 4),
            ("user", other_user_id, today, 3),
            ("global", "all-users", today, 9),
        }

    replay = client.request("DELETE", "/api/v1/me/data", json={"confirmation": "DELETE VEDA DATA"})
    assert replay.status_code == 200
    assert replay.json()["deleted_projects"] == 0
    assert replay.json()["deleted_preferences"] is False


def test_veda_data_purge_blocks_live_lease_without_mutation_then_allows_expired_lease(client):
    owner_id = client.test_user["id"]
    project, job = _create_project_and_job(client, "Active run to protect", "active-purge-01")
    with client.db_sessions() as db:
        db.add(UserPreference(user_id=owner_id, retention_days=30))
        stored_job = db.get(ResearchJob, job["id"])
        assert stored_job is not None
        stored_job.status = "active"
        stored_job.lease_owner = "active-purge-test-worker"
        stored_job.lease_expires_at = utcnow() + timedelta(minutes=2)
        db.commit()

    path = "/api/v1/me/data"
    payload = {"confirmation": "DELETE VEDA DATA"}
    blocked = client.request("DELETE", path, json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == (
        "A research step is still running. Wait for it to save or finish before deleting Veda data."
    )
    with client.db_sessions() as db:
        assert db.get(Project, project["id"]) is not None
        assert db.get(ResearchJob, job["id"]) is not None
        assert db.get(UserPreference, owner_id) is not None

    with client.db_sessions() as db:
        stored_job = db.get(ResearchJob, job["id"])
        assert stored_job is not None
        stored_job.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    deleted = client.request("DELETE", path, json=payload)
    assert deleted.status_code == 200
    assert deleted.json()["deleted_projects"] == 1
    with client.db_sessions() as db:
        assert db.get(Project, project["id"]) is None
        assert db.get(ResearchJob, job["id"]) is None
        assert db.get(UserPreference, owner_id) is None


def test_veda_data_purge_cascades_all_research_artifacts_without_touching_other_owner(client):
    owner_id = client.test_user["id"]
    project, job = _create_project_and_job(client, "Complete purge cascade", "purge-cascade-owner")
    client.test_user["id"] = "50000000-0000-4000-8000-000000000005"
    other_project, other_job = _create_project_and_job(
        client, "Foreign project to retain", "purge-cascade-foreign"
    )
    client.test_user["id"] = owner_id

    with client.db_sessions() as db:
        db.add(UserPreference(user_id=owner_id, retention_days=90))
        conversation = Conversation(project_id=project["id"], title="Purge conversation")
        db.add(conversation)
        db.flush()
        stored_job = db.get(ResearchJob, job["id"])
        assert stored_job is not None
        stored_job.conversation_id = conversation.id
        db.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=job["question"],
                    related_job_id=job["id"],
                ),
                JobEvent(
                    job_id=job["id"],
                    event_type="fixture",
                    stage="planning",
                    message="Veda-data purge cascade fixture",
                ),
            ]
        )
        source = Source(
            job_id=job["id"],
            external_id="fixture:veda-data-purge-source",
            title="Synthetic purge cascade source",
        )
        db.add(source)
        db.flush()
        db.add(
            DiscoveryCandidate(
                job_id=job["id"],
                candidate_key="d" * 64,
                provider="Crossref",
                provider_record_id="fixture:veda-data-purge-candidate",
                canonical_identity="Crossref:fixture:veda-data-purge-candidate",
                title="Synthetic purge cascade candidate",
                query_text="purge cascade fixture",
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
            content="Synthetic passage used only to verify erasure cascades.",
        )
        db.add(
            Claim(
                job_id=job["id"], source_id=source.id, passage_id=passage.id, text=passage.content
            )
        )
        db.flush()
        claim = db.scalar(select(Claim).where(Claim.job_id == job["id"]))
        assert claim is not None
        db.add_all(
            [
                EvidenceRelationship(
                    job_id=job["id"],
                    claim_a_id=claim.id,
                    claim_b_id=claim.id,
                    relationship_type="supports",
                    scope_alignment="same",
                    rationale="Synthetic cascade fixture.",
                    status="fixture",
                ),
                Hypothesis(
                    job_id=job["id"],
                    comparison_group_id="veda-data-purge-group",
                    side="A",
                    statement="Synthetic hypothesis used only to verify cascade deletion.",
                    uncertainty="Fixture only.",
                    why_competing="Fixture only.",
                    status="fixture",
                ),
                ResearchReport(
                    job_id=job["id"],
                    status="completed_with_limitations",
                    body_markdown="Synthetic report used only to verify cascade deletion.",
                    citation_map_json={},
                    verification_json={},
                ),
            ]
        )
        reservation = ModelCallReservation(
            job_id=job["id"],
            user_id=owner_id,
            operation="fixture_purge_cascade",
            attempt=0,
            provider="openrouter",
            request_hash="e" * 64,
            quota_date=utcnow().date(),
        )
        db.add(reservation)
        db.flush()
        db.add(
            UsageEntry(
                job_id=job["id"],
                quota_reservation_id=reservation.id,
                operation="fixture_purge_cascade",
                provider="openrouter",
                succeeded=True,
            )
        )
        db.commit()

    response = client.request(
        "DELETE", "/api/v1/me/data", json={"confirmation": "DELETE VEDA DATA"}
    )
    assert response.status_code == 200
    assert response.json()["deleted_projects"] == 1

    with client.db_sessions() as db:
        assert db.get(Project, project["id"]) is None
        assert db.get(ResearchJob, job["id"]) is None
        assert db.get(Project, other_project["id"]) is not None
        assert db.get(ResearchJob, other_job["id"]) is not None
        owner_conversations = select(Conversation.id).where(
            Conversation.project_id == project["id"]
        )
        owner_sources = select(Source.id).where(Source.job_id == job["id"])
        owner_artifacts = (
            (Conversation, Conversation.project_id == project["id"]),
            (
                Message,
                or_(
                    Message.conversation_id.in_(owner_conversations),
                    Message.related_job_id == job["id"],
                ),
            ),
            (JobEvent, JobEvent.job_id == job["id"]),
            (Source, Source.job_id == job["id"]),
            (DiscoveryCandidate, DiscoveryCandidate.job_id == job["id"]),
            (RetrievedDocument, RetrievedDocument.source_id.in_(owner_sources)),
            (Passage, Passage.source_id.in_(owner_sources)),
            (Claim, Claim.job_id == job["id"]),
            (EvidenceRelationship, EvidenceRelationship.job_id == job["id"]),
            (Hypothesis, Hypothesis.job_id == job["id"]),
            (ResearchReport, ResearchReport.job_id == job["id"]),
            (ModelCallReservation, ModelCallReservation.job_id == job["id"]),
            (UsageEntry, UsageEntry.job_id == job["id"]),
        )
        for model, owner_filter in owner_artifacts:
            assert db.scalar(select(func.count()).select_from(model).where(owner_filter)) == 0, (
                model.__tablename__
            )


def test_lifecycle_separates_veda_data_purge_from_identity_provider_deletion(client):
    lifecycle = client.get("/api/v1/me/data-lifecycle").json()
    assert lifecycle["veda_data_deletion"]["status"] == "available"
    assert lifecycle["veda_data_deletion"]["confirmation_phrase"] == "DELETE VEDA DATA"
    assert "current UTC day's quota safety counter" in lifecycle["veda_data_deletion"]["detail"]
    assert lifecycle["account_deletion"]["status"] == "unsupported"
    assert "does not remove your sign-in account" in lifecycle["account_deletion"]["detail"]
