from app.config import Settings
from app.models import ModelCallReservation, ResearchJob
from app.providers.registry import configured_model
from app.research.workflow import job_snapshot


def test_job_provider_and_model_are_persisted_as_the_research_route(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Route pin", "domain": "testing"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Which supported free route should remain pinned for this job?",
            "idempotency_key": "job-model-route-pin-01",
            "model_provider": "openrouter",
            "model_name": "fixture-route:free",
            "budget_ceiling_usd": 0,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["model_provider"] == "openrouter"
    assert response.json()["model_name"] == "fixture-route:free"

    with client.db_sessions() as db:
        job = db.get(ResearchJob, response.json()["id"])
        assert job is not None
        assert job_snapshot(job)["model_provider"] == "openrouter"
        assert job_snapshot(job)["model_name"] == "fixture-route:free"


def test_legacy_job_route_uses_first_persisted_reservation_identity(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Legacy route", "domain": "testing"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Can a legacy job recover its first recorded model identity?",
            "idempotency_key": "legacy-model-route-identity-01",
            "budget_ceiling_usd": 0,
        },
    )
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        job.model_provider = None
        job.model_name = None
        db.add(
            ModelCallReservation(
                job_id=job_id,
                user_id=client.test_user["id"],
                operation="legacy_operation",
                attempt=0,
                provider="openrouter",
                model_name="legacy-route:free",
                request_hash="a" * 64,
                reserved_cost_usd=0,
                reserved_cost_inr=0,
                prompt_characters=10,
                prompt_token_upper_bound=10,
                output_token_cap=10,
                quota_date=job.created_at.date(),
                state="succeeded",
            )
        )
        db.commit()
        snapshot = job_snapshot(job)
        assert snapshot["model_provider"] == "openrouter"
        assert snapshot["model_name"] == "legacy-route:free"


def test_paid_or_unknown_openrouter_model_cannot_be_pinned(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Invalid route", "domain": "testing"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Can an unverified or paid route bypass the model registry?",
            "idempotency_key": "job-model-route-reject-01",
            "model_provider": "openrouter",
            "model_name": "fixture-paid-model",
        },
    )
    assert response.status_code == 422


def test_sarvam_registry_reports_verified_capabilities_but_requires_credential_and_budget_gate():
    profile = configured_model(
        "sarvam",
        "sarvam-105b",
        config=Settings(
            llm_provider="sarvam",
            sarvam_api_key="",
            sarvam_max_job_cost_inr=5.0,
            allow_paid_llm_calls=False,
        ),
    )

    assert profile.supported is True
    assert profile.strict_json_schema is True
    assert profile.max_context_tokens == 128_000
    assert profile.max_completion_tokens == 4_096
    assert profile.currency == "INR"
    assert profile.input_price_per_million == 15.0
    assert profile.output_price_per_million == 60.0
    assert profile.ready is False
    assert profile.credential_available is False


def test_glm53_flash_is_an_explicit_sarvam_route_and_accepts_the_authorized_ceiling():
    config = Settings(
        llm_provider="sarvam",
        sarvam_api_key="fixture-secret",
        sarvam_model="glm5.3-flash",
        sarvam_max_job_cost_inr=20.0,
        allow_paid_llm_calls=True,
    )
    config.validate_security_configuration()
    profile = configured_model("sarvam", "glm5.3-flash", config=config)

    assert profile.ready is True
    assert profile.model == "glm5.3-flash"
    assert profile.supported_reasoning_efforts == {"low", "high", "max"}


def test_sarvam_route_can_be_pinned_to_a_job_with_an_inr_ceiling(client, monkeypatch):
    from app.api import routes

    monkeypatch.setattr(routes, "settings", Settings(sarvam_max_job_cost_inr=5.0))
    project = client.post(
        "/api/v1/projects", json={"title": "Sarvam route", "domain": "testing"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Can the selected provider and INR ceiling be persisted per job?",
            "idempotency_key": "job-sarvam-route-pin-01",
            "model_provider": "sarvam",
            "model_name": "sarvam-105b",
            "budget_ceiling_usd": 0,
            "budget_ceiling_inr": 5,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["model_provider"] == "sarvam"
    assert response.json()["model_name"] == "sarvam-105b"
    assert response.json()["budget_ceiling_inr"] == 5


def test_glm53_job_accepts_the_authorized_twenty_rupee_job_reservation(client, monkeypatch):
    from app.api import routes

    monkeypatch.setattr(
        routes,
        "settings",
        Settings(sarvam_max_job_cost_inr=20.0),
    )
    project = client.post(
        "/api/v1/projects", json={"title": "GLM route", "domain": "testing"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does the GLM route preserve the approved budget ceiling?",
            "idempotency_key": "glm53-budget-ceiling-20",
            "model_provider": "sarvam",
            "model_name": "glm5.3-flash",
            "budget_ceiling_usd": 0,
            "budget_ceiling_inr": 20,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["model_name"] == "glm5.3-flash"
    assert response.json()["budget_ceiling_inr"] == 20
