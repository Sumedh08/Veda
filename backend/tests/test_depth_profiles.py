import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import ModelCallReservation, ResearchJob, Source
from app.providers.scholarly import ScholarlyWork
from app.research import workflow
from app.research.depth import PROFILES
from app.research.safe_fetch import SafeHTMLDocument


def test_depth_profiles_are_distinct_and_increasing():
    profiles = [PROFILES[name] for name in ("quick", "standard", "deep")]
    for field in (
        "max_queries",
        "max_records_per_provider_query",
        "max_sources",
        "max_html_pages",
        "max_passages",
        "max_model_calls",
        "max_prompt_characters_per_call",
        "max_prompt_characters_total",
        "max_output_tokens_per_call",
        "max_output_token_budget_total",
        "max_retries",
        "max_step_seconds",
    ):
        assert [getattr(profile, field) for profile in profiles] == sorted(
            getattr(profile, field) for profile in profiles
        )
    assert len({profile.max_queries for profile in profiles}) == 3
    assert len({profile.max_model_calls for profile in profiles}) == 3


def test_full_structured_pipeline_operation_caps_fit_each_depth_budget():
    for profile in PROFILES.values():
        assert profile.max_output_tokens_per_call == 8192
    assert PROFILES["quick"].max_output_token_budget_total == 16 * 8192
    assert PROFILES["standard"].max_output_token_budget_total == 24 * 8192
    # Deep output allocation is intentionally bounded by the authorized INR
    # reservation ceiling, rather than promising the model-call maximum at every call.
    assert PROFILES["deep"].max_output_token_budget_total < (
        PROFILES["deep"].max_model_calls * PROFILES["deep"].max_output_tokens_per_call
    )
    from app.config import Settings
    from app.providers.registry import configured_model

    glm = configured_model(
        "sarvam",
        "glm5.3-flash",
        config=Settings(
            sarvam_api_key="fixture-secret",
            sarvam_max_job_cost_inr=20.0,
            allow_paid_llm_calls=True,
        ),
    )
    assert glm.maximum_cost(416_000, PROFILES["deep"].max_output_token_budget_total) < 20
    assert [PROFILES[name].max_model_calls for name in ("quick", "standard", "deep")] == [
        16,
        24,
        40,
    ]


@pytest.mark.parametrize(
    ("depth", "expected"),
    [("quick", 3), ("standard", 4), ("deep", 5)],
)
def test_planner_emits_distinct_bounded_query_counts(depth, expected):
    values = {
        "question": "What is the economic effect of AI adoption on worker productivity?",
        "scope": {},
        "depth": depth,
        "checkpoint": {},
    }
    queries, _ = workflow._make_plan(workflow._JobView(values))
    assert len(queries) == expected
    assert len(queries) == len(set(queries))
    assert all(len(query) <= 300 for query in queries)


def test_quick_plan_preserves_counterevidence_and_reports_missing_scope_fields():
    values = {
        "question": "What is the effect of AI adoption on productivity?",
        "scope": {"population": "small firms", "geography": "India"},
        "depth": "quick",
        "checkpoint": {
            "follow_up_context": {
                "parent_question": "How did adoption change after implementation?"
            }
        },
    }

    plan = workflow._build_decision_scoped_plan(workflow._JobView(values))

    assert plan["schema_version"] == plan["version"] == 3
    assert plan["planning_mode"] == "deterministic_bounded_no_model"
    assert plan["scope_status"] == "underspecified"
    assert plan["missing_scope_fields"] == ["decision_objective", "time_horizon"]
    assert plan["decision_context"]["population"] == "small firms"
    assert plan["decision_context"]["geography"] == "India"
    assert len(plan["queries"]) == PROFILES["quick"].max_queries
    assert plan["queries"] == [query["query"] for query in plan["query_rationales"]]
    assert plan["query_rationales"][-1]["focus"] == "counterevidence"
    assert all(len(query) <= 300 for query in plan["queries"])
    assert "Parent claims" in plan["subquestions"][-1]["purpose"]


def test_scope_complete_plan_and_long_question_keep_scope_terms_in_query():
    long_question = "What is the effect of AI on productivity? " + ("additional detail " * 35)
    values = {
        "question": long_question,
        "scope": {
            "population": "small firms",
            "geography": "India",
            "time_horizon": "2022 through 2026",
            "decision_objective": "adoption investment",
            "context": "compare observed costs and returns",
        },
        "depth": "deep",
        "checkpoint": {},
    }

    plan = workflow._build_decision_scoped_plan(workflow._JobView(values))

    assert plan["scope_status"] == "specified"
    assert plan["missing_scope_fields"] == []
    scoped_query = next(
        item["query"] for item in plan["query_rationales"] if item["focus"] == "requested_scope"
    )
    assert "small firms" in scoped_query
    assert "india" in scoped_query
    assert "2022 2026" in scoped_query
    assert "adoption investment" not in scoped_query
    assert plan["decision_context"]["decision_objective"] == "adoption investment"
    assert "additional detail" in scoped_query
    assert len(scoped_query) <= 300
    assert plan["subquestions"][0]["text"] == long_question[:300]
    counter_query = next(
        item["query"] for item in plan["query_rationales"] if item["focus"] == "counterevidence"
    )
    assert "null" in counter_query or "negative" in counter_query
    assert "developer" not in counter_query
    assert plan["stopping_criteria"]["insufficient_evidence"]


def test_plan_stage_persists_versioned_plan_and_reasons_in_event():
    result = workflow.execute_stage(
        None,
        {
            "id": "plan-contract-job",
            "question": "What evidence informs this bounded decision?",
            "scope": {"decision_objective": "consider pilot investment"},
            "depth": "quick",
            "depth_profile": PROFILES["quick"].as_dict(),
            "attempt": 0,
            "current_stage": "planning",
            "checkpoint": {},
        },
    )
    plan = result.checkpoint_update.model_dump(mode="json")["plan"]

    assert plan["version"] == 4
    assert plan["planning_mode"] == "deterministic_fallback"
    assert plan["planning_provenance"]["fallback_reason"] == "provider_disabled"
    assert result.event_data["plan_version"] == 4
    assert result.event_data["planning_mode"] == "deterministic_fallback"
    assert result.event_data["query_rationales"] == plan["query_rationales"]
    assert result.event_data["missing_scope_fields"] == ["population", "geography", "time_horizon"]


def test_planning_stage_exposes_the_persisted_v2_plan_through_owned_api(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Decision plan", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Should this team run a bounded AI productivity pilot?",
            "geography": "India",
            "population": "Customer support teams",
            "comparator": "teams not using the tool",
            "target_outcome": "completed tasks per worker-hour",
            "denominator": "worker-hours observed over 12 weeks",
            "assumptions_to_test": "Recorded work is comparable across teams",
            "idempotency_key": "plan-v2-api-contract",
        },
    ).json()
    assert job["scope"]["comparator"] == "teams not using the tool"
    assert job["scope"]["target_outcome"] == "completed tasks per worker-hour"
    assert job["scope"]["denominator"] == "worker-hours observed over 12 weeks"
    assert job["scope"]["assumptions_to_test"] == "Recorded work is comparable across teams"
    pending = client.get(f"/api/v1/research-jobs/{job['id']}/plan")
    assert pending.json() == {"status": "not_created"}

    advanced = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "plan-v2-api-operation"},
    )
    assert advanced.status_code == 200, advanced.text
    plan_response = client.get(f"/api/v1/research-jobs/{job['id']}/plan")
    assert plan_response.status_code == 200
    plan = plan_response.json()
    assert plan["schema_version"] == 4
    assert plan["planning_mode"] == "deterministic_fallback"
    assert plan["planning_provenance"]["fallback_reason"] == "provider_disabled"
    assert plan["decision_context"]["geography"] == "India"
    assert plan["decision_context"]["population"] == "Customer support teams"
    assert (
        plan["planning_lenses"]["comparator_or_counterfactual"]["user_statement"]
        == "teams not using the tool"
    )
    assert (
        plan["planning_lenses"]["outcomes"]["target_outcome"] == "completed tasks per worker-hour"
    )
    assert (
        plan["planning_lenses"]["outcomes"]["denominator"] == "worker-hours observed over 12 weeks"
    )
    assert (
        plan["planning_lenses"]["assumptions"]["user_supplied_text"]
        == "Recorded work is comparable across teams"
    )
    assert plan["planning_lenses"]["assumptions"]["system_inferred_assumptions"] == []
    assert plan["planning_lenses"]["evidence_types"]["provider_type_filter_applied"] is False
    assert plan["scope_status"] == "underspecified"
    assert "counterevidence" in {item["focus"] for item in plan["query_rationales"]}
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    planning_event = next(
        event
        for event in events
        if event["stage"] == "planning" and event["event_type"] == "step_completed"
    )
    assert planning_event["data"]["plan_version"] == 4
    assert planning_event["data"]["planning_mode"] == "deterministic_fallback"
    assert planning_event["data"]["missing_scope_fields"] == [
        "decision_objective",
        "time_horizon",
    ]


def test_broad_question_plan_labels_lenses_as_unknown_and_non_filtering():
    plan = workflow._build_decision_scoped_plan(
        workflow._JobView(
            {
                "question": "How do people make decisions under uncertainty?",
                "scope": {},
                "depth": "quick",
                "checkpoint": {},
            }
        )
    )

    lenses = plan["planning_lenses"]
    assert lenses["comparator_or_counterfactual"]["status"] == "unspecified"
    assert lenses["comparator_or_counterfactual"]["user_statement"] is None
    assert lenses["outcomes"]["status"] == "unspecified"
    assert lenses["outcomes"]["target_outcome"] is None
    assert lenses["outcomes"]["denominator"] is None
    assert lenses["assumptions"]["status"] == "not_provided"
    assert lenses["assumptions"]["user_supplied_text"] is None
    assert lenses["assumptions"]["system_inferred_assumptions"] == []
    assert (
        lenses["confounding"]["applicability"]
        == "evaluate_if_nonrandomized_or_observational_evidence"
    )
    assert lenses["evidence_types"]["provider_type_filter_applied"] is False
    assert len(plan["subquestions"]) <= 8


def test_profile_endpoint_and_job_output_use_the_same_saved_limits(client):
    profiles_response = client.get("/api/v1/settings/depth-profiles")
    assert profiles_response.status_code == 200
    profiles = profiles_response.json()["profiles"]
    project = client.post(
        "/api/v1/projects", json={"title": "Depth policy", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How does a persisted depth profile bound this run?",
            "depth": "quick",
            "idempotency_key": "depth-profile-snapshot-01",
        },
    ).json()
    assert job["resource_limits"] == profiles["quick"]
    assert job["model_calls_reserved"] == 0
    assert job["prompt_characters_reserved"] == 0
    assert job["output_token_budget_reserved"] == 0

    refreshed = client.get(f"/api/v1/research-jobs/{job['id']}").json()
    assert refreshed["resource_limits"] == profiles["quick"]
    assert refreshed["prompt_token_budget_reserved"] == 0
    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        report, _citations, _verification, _model = workflow._build_limited_report(
            db, workflow.job_snapshot(persisted)
        )
    assert "Applied research-depth limits and observed resource use" in report
    assert "quick: caps 3 planned queries" in report


def test_stage_records_elapsed_time_and_applied_depth_profile(monkeypatch):
    ticks = iter((0.0, 61.25))
    monkeypatch.setattr(workflow.time, "monotonic", lambda: next(ticks))
    result = workflow.execute_stage(
        None,
        {
            "id": "fixture-job",
            "question": "What evidence informs the policy question?",
            "scope": {},
            "depth": "quick",
            "depth_profile": PROFILES["quick"].as_dict(),
            "attempt": 0,
            "current_stage": "planning",
            "checkpoint": {},
        },
    )
    assert result.event_data["resource_limits"] == PROFILES["quick"].as_dict()
    assert result.event_data["elapsed_seconds"] == 61.25
    assert result.event_data["elapsed_limit_reached"] is True
    assert result.event_data["elapsed_limit_enforcement"] == (
        "cooperative_with_one_blocking_request_overrun"
    )


def test_remaining_stage_time_is_monotonic_and_never_negative():
    profile = PROFILES["quick"]
    job = {
        "depth": "quick",
        "depth_profile": profile.as_dict(),
        "_stage_started_monotonic": time.monotonic() - (profile.max_step_seconds - 1),
    }

    remaining = workflow._stage_time_remaining(job)
    assert 0 < remaining <= 1

    job["_stage_started_monotonic"] = time.monotonic() - profile.max_step_seconds - 1
    assert workflow._stage_time_remaining(job) == 0


def test_discovery_enforces_query_result_and_source_caps(client, monkeypatch):
    searches = []

    class CrossrefFixture:
        def search(self, query, *, limit):
            searches.append((query, limit))
            return [
                ScholarlyWork(
                    external_id=f"{query}:{index}",
                    title=f"Policy question evidence review {query} {index}",
                    doi=None,
                    url=None,
                    authors=[],
                    published_year=2025,
                    publisher="Fixture",
                    abstract_excerpt=None,
                    query=query,
                    provider="Crossref",
                )
                for index in range(limit)
            ]

        def close(self):
            pass

    class EmptyOpenAlex:
        def __init__(self, **kwargs):
            pass

        def search(self, query, *, limit):
            return []

        def close(self):
            pass

    class EmptyData360:
        provider_name = "World Bank Data360"

        def search(self, query, *, limit, geography=None):
            return []

    class EmptyOpenAIRE:
        def __init__(self, *, before_request=None):
            pass

        def search(self, query, *, limit):
            return []

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", CrossrefFixture)
    monkeypatch.setattr(workflow, "OpenAlexProvider", EmptyOpenAlex)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", EmptyData360)
    monkeypatch.setattr(workflow, "OpenAIREProvider", EmptyOpenAIRE)
    project = client.post(
        "/api/v1/projects", json={"title": "Discovery caps", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What evidence informs the policy question?",
            "depth": "quick",
            "idempotency_key": "depth-discovery-cap-01",
        },
    ).json()
    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        result = workflow.execute_stage(
            db,
            {
                "id": persisted.id,
                "question": persisted.question,
                "scope": persisted.scope_json,
                "depth": persisted.depth,
                "depth_profile": PROFILES["quick"].as_dict(),
                "attempt": 0,
                "current_stage": "discovery",
                "checkpoint": {"plan": {"queries": [f"query {index}" for index in range(1, 6)]}},
            },
        )
    assert len(searches) == PROFILES["quick"].max_queries
    assert all(limit == PROFILES["quick"].max_records_per_provider_query for _, limit in searches)
    assert len(result.sources or []) == PROFILES["quick"].max_sources
    assert result.event_data["queries_planned"] == PROFILES["quick"].max_queries
    assert result.event_data["provider_queries_attempted"] == (
        2 * PROFILES["quick"].max_queries + 1
    )


def test_extraction_enforces_total_passage_cap(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Passage cap", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does quick depth cap extracted source passages?",
            "depth": "quick",
            "idempotency_key": "depth-passage-cap-01",
        },
    ).json()

    class PassageCapHTMLFetcher:
        def __init__(self, *, origin_request_limiter=None):
            pass

        def fetch_html(self, url, *, license_name):
            text = "\n\n".join(
                f"Study reports measured outcome {sentence} with a documented result."
                for sentence in range(20)
            )
            return SafeHTMLDocument(
                text=text,
                sha256="e" * 64,
                media_type="text/html",
                final_host="papers.example",
                retrieved_at=datetime.now(UTC),
                truncated=False,
                host_policy_id="fixture-reviewed-host-v1",
                host_terms_url="https://papers.example/terms",
                robots_status="rules_checked",
            )

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", PassageCapHTMLFetcher)
    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        for index in range(2):
            db.add(
                Source(
                    job_id=job["id"],
                    external_id=f"depth-passage-source-{index}",
                    title=f"Licensed open study {index}",
                    retrieval_status="metadata_only",
                    abstract_excerpt=None,
                    metadata_json={
                        "provider": "OpenAlex",
                        "provider_metadata": {
                            "best_oa_location": {
                                "is_oa": True,
                                "landing_page_url": f"https://papers.example/study-{index}",
                                "license": "cc-by",
                                "version": "publishedVersion",
                            }
                        },
                    },
                )
            )
        db.commit()
        snapshot = workflow.job_snapshot(persisted)
        snapshot["current_stage"] = "extraction"
        profile = PROFILES["quick"].as_dict()
        profile["max_html_pages"] = 2
        profile["max_html_passages"] = 30
        profile["max_passages"] = 20
        snapshot["depth_profile"] = profile
        result = workflow.execute_stage(db, snapshot)
    assert len(result.passages or []) == profile["max_passages"]
    assert len(result.claims or []) == profile["max_passages"]


def test_retry_endpoint_terminalizes_job_after_depth_retry_cap(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Retry cap", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does the quick profile cap repeated failed attempts?",
            "depth": "quick",
            "idempotency_key": "depth-retry-cap-01",
        },
    ).json()
    with client.db_sessions() as db:
        persisted = db.get(workflow.ResearchJob, job["id"])
        persisted.status = "retryable_failure"
        persisted.attempt = PROFILES["quick"].max_retries + 1
        db.commit()

    response = client.post(f"/api/v1/research-jobs/{job['id']}/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "terminal_failure"
    assert response.json()["error_class"] == "depth_retry_limit"


def test_model_call_preserves_operation_capacity_and_rejects_underallocated_appraisal(
    client, monkeypatch
):
    from app.config import Settings
    from app.providers.llm import ProviderUsage, StructuredResult
    from app.research.llm_tasks import ResearchAppraisalBatch

    project = client.post(
        "/api/v1/projects", json={"title": "Token bounds", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does the selected profile cap provider output tokens?",
            "depth": "quick",
            "idempotency_key": "depth-output-token-cap-01",
        },
    ).json()
    openrouter_settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="fixture-only",
        openrouter_model="openrouter/free",
        max_daily_model_calls=10,
        max_daily_model_calls_per_user=10,
    )
    monkeypatch.setattr(workflow, "settings", openrouter_settings)
    captured = {"output_tokens": None, "calls": 0}

    class Provider:
        def complete_json(self, **kwargs):
            captured["calls"] += 1
            captured["output_tokens"] = kwargs["max_output_tokens"]
            return StructuredResult(
                value=ResearchAppraisalBatch(
                    schema_version=2, source_appraisals=[], claim_assessments=[]
                ),
                usage=ProviderUsage(
                    provider="openrouter",
                    model="openrouter/free",
                    input_tokens=20,
                    output_tokens=10,
                    reported_cost_usd=0.0,
                    estimated_cost_usd=0.0,
                    latency_ms=1,
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", Provider)
    snapshot = {"id": job["id"], "depth": "quick", "depth_profile": PROFILES["quick"].as_dict()}
    kwargs = {
        "schema_name": "veda_appraisal_batch_v2",
        "schema_model": ResearchAppraisalBatch,
        "system": "Return the strict schema.",
        "user": "A bounded fixture request.",
        "max_output_tokens": 4096,
    }
    with client.db_sessions() as db:
        workflow._call_structured(db, snapshot, **kwargs)
        reservation = db.scalar(
            select(ModelCallReservation).where(ModelCallReservation.job_id == job["id"])
        )
        assert reservation.output_token_cap == 4096
        assert db.get(ResearchJob, job["id"]).prompt_token_budget_reserved == (
            reservation.prompt_token_upper_bound
        )
    assert captured["calls"] == 1
    assert captured["output_tokens"] == 4096

    captured["calls"] = 0
    with client.db_sessions() as db:
        with pytest.raises(workflow.WorkflowError) as error:
            workflow._call_structured(
                db,
                snapshot,
                **{
                    **kwargs,
                    "user": "A fresh appraisal whose output cap is too small.",
                    "max_output_tokens": 256,
                },
            )
        assert error.value.code == "depth_limit_exceeded"
    assert captured["calls"] == 0

    captured["calls"] = 0
    constrained_profile = {
        **PROFILES["quick"].as_dict(),
        "max_prompt_tokens_per_call": 10,
    }
    with client.db_sessions() as db:
        with pytest.raises(workflow.WorkflowError) as error:
            workflow._call_structured(
                db,
                {**snapshot, "depth_profile": constrained_profile},
                **{**kwargs, "user": "A changed request that cannot use the prior cache."},
            )
        assert error.value.code == "depth_limit_exceeded"
    assert captured["calls"] == 0


def test_glm_workflow_passes_declared_low_effort_and_pins_it_in_replay_hash(client, monkeypatch):
    from app.api import routes
    from app.config import Settings
    from app.providers.contracts import ProviderIdentity
    from app.providers.llm import ProviderUsage, StructuredResult
    from app.research.llm_tasks import ResearchAppraisalBatch

    model_settings = Settings(
        app_env="test",
        llm_provider="sarvam",
        sarvam_api_key="fixture-secret",
        sarvam_model="glm5.3-flash",
        sarvam_max_job_cost_inr=20.0,
        allow_paid_llm_calls=True,
        max_daily_model_calls=24,
        max_daily_model_calls_per_user=24,
    )
    monkeypatch.setattr(routes, "settings", model_settings)
    monkeypatch.setattr(workflow, "settings", model_settings)
    project = client.post(
        "/api/v1/projects", json={"title": "GLM workflow", "domain": "testing"}
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Can an explicit model profile control a structured workflow call?",
            "idempotency_key": "glm53-workflow-reasoning-01",
            "model_provider": "sarvam",
            "model_name": "glm5.3-flash",
            "depth": "quick",
            "budget_ceiling_usd": 0,
            "budget_ceiling_inr": 20,
        },
    )
    assert response.status_code == 201, response.text
    captured = {}

    class Provider:
        identity = ProviderIdentity("sarvam", "glm5.3-flash")

        def complete_json(self, **kwargs):
            captured.update(kwargs)
            return StructuredResult(
                value=ResearchAppraisalBatch(
                    schema_version=2, source_appraisals=[], claim_assessments=[]
                ),
                usage=ProviderUsage(
                    provider="sarvam",
                    model="glm5.3-flash",
                    input_tokens=20,
                    output_tokens=10,
                    reported_cost_usd=None,
                    estimated_cost_usd=None,
                    latency_ms=1,
                    estimated_cost_amount=0.001,
                    cost_currency="INR",
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", Provider)
    snapshot = {
        **response.json(),
        "id": response.json()["id"],
        "depth": "quick",
        "depth_profile": PROFILES["quick"].as_dict(),
        "attempt": 0,
        "checkpoint": {},
    }
    schema = ResearchAppraisalBatch
    with client.db_sessions() as db:
        workflow._call_structured(
            db,
            snapshot,
            schema_name="veda_appraisal_batch_v2",
            schema_model=schema,
            system="Return only the requested appraisal structure.",
            user="No methods are reported in this fixture.",
            max_output_tokens=8192,
        )
        reservation = db.scalar(
            select(ModelCallReservation).where(ModelCallReservation.job_id == snapshot["id"])
        )
        assert reservation is not None
        assert reservation.output_token_cap == 8192
        assert reservation.request_hash == workflow._structured_request_hash(
            snapshot,
            schema_name="veda_appraisal_batch_v2",
            schema_model=schema,
            system="Return only the requested appraisal structure.",
            user="No methods are reported in this fixture.",
            max_output_tokens=8192,
            reasoning_effort="low",
        )

    assert captured["reasoning_effort"] == "low"
    assert captured["max_output_tokens"] == 8192
