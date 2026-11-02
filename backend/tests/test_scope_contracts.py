import pytest
from pydantic import ValidationError

from app.models import JobEvent, ResearchJob, Source
from app.research import workflow
from app.schemas import JobEventDataV1, ResearchScopeV1, versioned_event_data, versioned_scope


def create_job(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Scope contract", "domain": "Research"}
    )
    assert project.status_code == 201, project.text
    response = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={
            "question": "How does the intervention affect the measured outcome?",
            "context": "A bounded decision context",
            "geography": "India",
            "population": "Adults",
            "time_horizon": "2020-2025",
            "decision_objective": "Choose a policy",
            "comparator": "Usual care",
            "target_outcome": "Change in outcome",
            "denominator": "Per participant",
            "assumptions_to_test": "Measurement is comparable",
            "depth": "quick",
            "budget_ceiling_usd": 0,
            "idempotency_key": "scope-contract-001",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_scope_v1_is_bounded_and_rejects_unknown_versioned_fields():
    scope = ResearchScopeV1(geography="India", comparator="Usual care")
    assert scope.schema_version == 1
    assert scope.geography == "India"

    with pytest.raises(ValidationError):
        ResearchScopeV1(geography="x" * 161)
    with pytest.raises(ValidationError):
        ResearchScopeV1(schema_version=2)
    with pytest.raises(ValidationError):
        ResearchScopeV1(unrecognized="must not be silently accepted")


def test_legacy_scope_is_upcast_without_losing_unknown_data():
    legacy = {"geography": "India", "prior_extension": {"source": "legacy"}}

    result = versioned_scope(legacy)

    assert result["schema_version"] == 1
    assert result["geography"] == "India"
    assert result["extensions"] == {"prior_extension": {"source": "legacy"}}
    assert legacy == {"geography": "India", "prior_extension": {"source": "legacy"}}
    with pytest.raises(ValidationError):
        versioned_scope({"schema_version": 2, "geography": "India"})


def test_event_data_v1_validates_known_metrics_and_preserves_extensions():
    payload = versioned_event_data({"claim_count": 2, "legacy_metric": {"raw": True}})

    assert payload == {
        "data_schema_version": 1,
        "claim_count": 2,
        "legacy_metric": {"raw": True},
    }
    with pytest.raises(ValidationError):
        JobEventDataV1(claim_count=-1)
    with pytest.raises(ValidationError):
        versioned_event_data({"data_schema_version": 2, "claim_count": 1})
    with pytest.raises(ValueError):
        versioned_event_data({"legacy_metric": "x" * 16_385})


def test_discovery_event_supports_multiple_federated_provider_metrics():
    providers = [
        "Crossref",
        "OpenAlex",
        "OpenAlex institution identity resolution",
        "OpenAIRE",
        "World Bank Documents & Reports",
        "World Bank Data360",
        "GOV.UK Search API",
        "OpenAIRE organization discovery",
        "ROR exact-name organization resolution",
        "ROR organization verification",
        "Crossref organization-affiliation publications",
        "GOV.UK Organizations API",
        "ROR identity verification",
        "OpenAlex organization publications",
        "ILOSTAT",
    ]

    event_data = versioned_event_data(
        {
            "provider_failures": dict.fromkeys(providers, 0),
            "provider_result_counts": dict.fromkeys(providers, 0),
            "provider_query_counts": dict.fromkeys(providers, 1),
            "provider_query_latencies_ms": {provider: [1] for provider in providers},
            "providers": providers,
        }
    )

    assert event_data["provider_query_counts"] == dict.fromkeys(providers, 1)
    assert event_data["providers"] == providers


def test_job_and_event_api_contracts_are_versioned_and_preserve_metrics(client):
    job = create_job(client)
    assert job["schema_version"] == 1
    assert job["scope"]["schema_version"] == 1
    assert job["scope"]["extensions"] == {}
    assert job["scope"]["geography"] == "India"
    assert job["scope"]["comparator"] == "Usual care"
    assert job["scope"]["target_outcome"] == "Change in outcome"
    assert job["scope"]["denominator"] == "Per participant"

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        legacy_scope = {"geography": "India", "legacy_note": {"kept": True}}
        persisted.scope_json = legacy_scope
        db.commit()
        snapshot = workflow.job_snapshot(persisted)
        assert snapshot["scope"]["schema_version"] == 1
        assert snapshot["scope"]["extensions"] == {"legacy_note": {"kept": True}}

    response = client.get(f"/api/v1/research-jobs/{job['id']}")
    assert response.status_code == 200, response.text
    assert response.json()["scope"]["schema_version"] == 1
    assert response.json()["scope"]["extensions"] == {"legacy_note": {"kept": True}}
    with client.db_sessions() as db:
        assert db.get(ResearchJob, job["id"]).scope_json == legacy_scope

    from app.research.workflow import append_event

    with client.db_sessions() as db:
        append_event(
            db,
            job["id"],
            event_type="step_completed",
            stage="planning",
            message="Planning finished",
            data={"plan_version": 3, "missing_scope_fields": ["population"]},
        )
        db.commit()

    events = client.get(f"/api/v1/research-jobs/{job['id']}/events")
    assert events.status_code == 200, events.text
    event = next(item for item in events.json()["items"] if item["message"] == "Planning finished")
    assert event["schema_version"] == 1
    assert event["data"] == {
        "data_schema_version": 1,
        "plan_version": 3,
        "missing_scope_fields": ["population"],
    }


def test_legacy_event_data_is_upcast_for_api_without_database_rewrite(client):
    job = create_job(client)
    legacy = {"claim_count": 1, "legacy_metric": {"origin": "old-event"}}
    with client.db_sessions() as db:
        db.add(
            JobEvent(
                job_id=job["id"],
                event_type="step_completed",
                stage="extraction",
                message="Legacy extraction event",
                data_json=legacy,
            )
        )
        db.commit()

    response = client.get(f"/api/v1/research-jobs/{job['id']}/events")
    event = next(
        item for item in response.json()["items"] if item["message"] == "Legacy extraction event"
    )
    assert event["data"] == {**legacy, "data_schema_version": 1}
    with client.db_sessions() as db:
        stored = (
            db.query(JobEvent).filter_by(job_id=job["id"], message="Legacy extraction event").one()
        )
        assert stored.data_json == legacy


def test_legacy_provider_metadata_is_upcast_for_source_api_without_database_rewrite(client):
    job = create_job(client)
    legacy = {
        "statistics": {"license": "CC BY-4.0", "legacy_catalog_note": "imported"},
        "historic_parser_note": {"source": "pre-v1"},
    }
    source_id = "10000000-0000-4000-8000-000000000099"
    with client.db_sessions() as db:
        db.add(
            Source(
                id=source_id,
                job_id=job["id"],
                external_id="legacy-statistics-source",
                title="Legacy statistics source",
                authors_json=[],
                source_type="official_statistics",
                retrieval_status="official_statistics",
                metadata_json={"provider": "World Bank Data360", "provider_metadata": legacy},
            )
        )
        db.commit()

    response = client.get(f"/api/v1/sources/{source_id}")

    assert response.status_code == 200, response.text
    assert response.json()["provider_metadata_schema_version"] == 1
    assert response.json()["statistics"]["license"] == "CC BY-4.0"
    assert response.json()["statistics"]["extensions"] == {"legacy_catalog_note": "imported"}
    with client.db_sessions() as db:
        stored = db.get(Source, source_id)
        assert stored.metadata_json["provider_metadata"] == legacy


def test_malformed_legacy_provider_metadata_does_not_hide_source_from_api(client):
    job = create_job(client)
    source_id = "10000000-0000-4000-8000-000000000098"
    legacy = {"statistics": "malformed"}
    with client.db_sessions() as db:
        db.add(
            Source(
                id=source_id,
                job_id=job["id"],
                external_id="malformed-legacy-statistics-source",
                title="Malformed legacy metadata",
                authors_json=[],
                source_type="official_statistics",
                retrieval_status="official_statistics",
                metadata_json={"provider": "ILOSTAT", "provider_metadata": legacy},
            )
        )
        db.commit()

    response = client.get(f"/api/v1/sources/{source_id}")

    assert response.status_code == 200, response.text
    assert response.json()["statistics"] is None
    with client.db_sessions() as db:
        stored = db.get(Source, source_id)
        assert stored.metadata_json["provider_metadata"] == legacy


def test_malformed_legacy_checkpoint_uses_safe_api_fallback_without_database_rewrite(client):
    job = create_job(client)
    legacy = {
        "workflow_version": 1,
        "depth_profile": {"name": "quick", "max_queries": "untrusted"},
        "old_stage_extension": {"history": "retained"},
    }
    with client.db_sessions() as db:
        stored = db.get(ResearchJob, job["id"])
        stored.checkpoint_json = legacy
        db.commit()

    job_response = client.get(f"/api/v1/research-jobs/{job['id']}")
    plan_response = client.get(f"/api/v1/research-jobs/{job['id']}/plan")

    assert job_response.status_code == 200, job_response.text
    assert job_response.json()["resource_limits"]["name"] == "quick"
    assert plan_response.status_code == 200
    assert plan_response.json() == {"status": "not_created"}
    with client.db_sessions() as db:
        stored = db.get(ResearchJob, job["id"])
        assert stored.checkpoint_json == legacy
