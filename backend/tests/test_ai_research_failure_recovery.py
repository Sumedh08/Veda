from datetime import UTC, datetime

from sqlalchemy import select

from app.config import Settings
from app.models import Claim, ResearchReport, Source, UsageEntry
from app.providers.llm import LLMProviderError
from app.providers.scholarly import ScholarlyWork
from app.research import workflow
from app.research.safe_fetch import SafeHTMLDocument


class FailureFixtureCrossref:
    def __init__(self):
        pass

    def search(self, query, *, limit=5):
        return []

    def close(self):
        pass


class FailureFixtureOpenAlex:
    def __init__(self, **kwargs):
        pass

    def search(self, query, *, limit=5):
        return [
            ScholarlyWork(
                external_id="doi:10.5555/ai-productivity-recovery",
                title="AI assistance and task productivity in a randomized worker study",
                doi="10.5555/ai-productivity-recovery",
                url="https://doi.org/10.5555/ai-productivity-recovery",
                authors=[],
                published_year=2025,
                publisher="Fixture Academic Press",
                abstract_excerpt=None,
                query=query,
                provider="OpenAlex",
                provider_metadata={
                    "openalex_id": "https://openalex.org/W10001",
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/recovery",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    },
                },
            )
        ]

    def close(self):
        pass


class FailureFixtureHTMLFetcher:
    def __init__(self, *, origin_request_limiter=None):
        pass

    def fetch_html(self, url, *, license_name):
        return SafeHTMLDocument(
            text=(
                "Methods: A randomized study assigned 120 workers to an AI assistance workflow.\n\n"
                "Results: Task completion speed increased by 14 percent for participating workers.\n\n"
                "Limitations: The effect varied by worker experience."
            ),
            sha256="b" * 64,
            media_type="text/html",
            final_host="papers.example",
            retrieved_at=datetime.now(UTC),
            truncated=False,
            host_policy_id="fixture-reviewed-host-v1",
            host_terms_url="https://papers.example/terms",
            robots_status="rules_checked",
        )


def test_uncertain_appraisal_preserves_evidence_and_completes_a_limited_report(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FailureFixtureCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FailureFixtureOpenAlex)
    monkeypatch.setattr(workflow, "SafeHTMLFetcher", FailureFixtureHTMLFetcher)
    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openrouter",
            openrouter_api_key="fixture-only",
            openrouter_model="openrouter/free",
            max_daily_model_calls=20,
            max_daily_model_calls_per_user=20,
        ),
    )
    provider_calls = []

    class FailureProvider:
        def complete_json(self, **kwargs):
            provider_calls.append(kwargs["schema_name"])
            if kwargs["schema_name"] == "veda_research_plan_selection_v1":
                raise LLMProviderError(
                    "fixture response format rejection",
                    code="unsupported_response_format",
                )
            if kwargs["schema_name"] == "veda_appraisal_batch_v2":
                raise LLMProviderError(
                    "fixture timeout",
                    code="provider_timeout",
                    outcome_uncertain=True,
                )
            raise LLMProviderError(
                "fixture route guard",
                code="free_route_guard_tripped",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", FailureProvider)

    project = client.post(
        "/api/v1/projects", json={"title": "AI productivity", "domain": "labor economics"}
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What study evidence measures AI task productivity for workers?",
            "depth": "quick",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "budget_ceiling_usd": 0,
            "idempotency_key": "uncertain-appraisal-recovery",
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    final = None
    for index in range(1, 8):
        advanced = client.post(
            f"/api/v1/research-jobs/{job_id}/advance",
            json={"operation_key": f"recovery-step-{index}"},
        )
        assert advanced.status_code == 200, advanced.text
        final = advanced.json()
        if final["status"] in {"completed", "completed_with_limitations", "terminal_failure"}:
            break

    assert final is not None
    assert final["status"] == "completed_with_limitations"
    assert final["error_class"] is None
    assert final["unknown_cost_calls"] == 2
    assert final["cost_estimate_complete"] is False
    assert provider_calls == ["veda_research_plan_selection_v1", "veda_appraisal_batch_v2"]

    sources = client.get(f"/api/v1/research-jobs/{job_id}/sources").json()["items"]
    claims = client.get(f"/api/v1/research-jobs/{job_id}/claims").json()["items"]
    report_response = client.get(f"/api/v1/research-jobs/{job_id}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert sources and claims
    assert all(source["appraisal"]["status"] == "not_performed" for source in sources)
    assert all(
        claim["appraisal"]["methodology_appraisal"]["status"] == "not_performed" for claim in claims
    )
    assert report["verification"]["model_assisted_synthesis"] == "not_performed"
    assert "did not run" in report["body_markdown"].lower()
    assert all(claim["text"] in report["body_markdown"] for claim in claims)
    assert all(
        any(
            citation["source_id"] == claim["source_id"]
            and claim["passage_id"] in citation["passages"]
            for citation in report["citation_map"].values()
        )
        for claim in claims
    )

    with client.db_sessions() as db:
        usage = db.scalar(
            select(UsageEntry).where(
                UsageEntry.job_id == job_id,
                UsageEntry.operation == "veda_appraisal_batch_v2",
            )
        )
        saved_sources = list(db.scalars(select(Source).where(Source.job_id == job_id)))
        saved_claims = list(db.scalars(select(Claim).where(Claim.job_id == job_id)))
        saved_report = db.scalar(select(ResearchReport).where(ResearchReport.job_id == job_id))
        assert usage is not None
        assert usage.error_class == "provider_timeout"
        assert usage.reported_cost_usd is None
        assert usage.estimated_cost_usd is None
        planning_usage = db.scalar(
            select(UsageEntry).where(
                UsageEntry.job_id == job_id,
                UsageEntry.operation == "veda_research_plan_selection_v1",
            )
        )
        assert planning_usage is not None
        assert planning_usage.error_class == "unsupported_response_format"
        assert planning_usage.reported_cost_usd is None
        assert planning_usage.estimated_cost_usd is None
        project_usage = client.get(f"/api/v1/projects/{project['id']}/usage").json()
        assert project_usage["unknown_cost_calls"] == 2
        assert project_usage["cost_estimate_complete"] is False
        assert saved_sources and saved_claims and saved_report is not None
        assert saved_report.citation_map_json["citations"]


def test_truncated_openrouter_finish_reason_is_persisted_without_raw_response(client, monkeypatch):
    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openrouter",
            openrouter_api_key="fixture-only",
            openrouter_model="openrouter/free",
            max_daily_model_calls=20,
            max_daily_model_calls_per_user=20,
        ),
    )

    class TruncatedProvider:
        def complete_json(self, **kwargs):
            assert kwargs["schema_name"] == "veda_research_plan_selection_v1"
            raise LLMProviderError(
                "fixture response ended at the output limit",
                reported_cost_usd=0,
                estimated_cost_usd=0,
                code="provider_output_truncated",
                finish_reason="length",
                model_name="provider/example:free",
                input_tokens=321,
                output_tokens=1400,
                reasoning_tokens=975,
                latency_ms=845,
                validation_error_types=("value_error",),
                validation_error_paths=("findings.3.statement", "fixture-secret:must-not-persist"),
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", TruncatedProvider)
    project = client.post(
        "/api/v1/projects", json={"title": "Finish reason fixture", "domain": "testing"}
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What output does this fixture report?",
            "depth": "quick",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "budget_ceiling_usd": 0,
            "idempotency_key": "finish-reason-persistence",
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    advanced = client.post(
        f"/api/v1/research-jobs/{job_id}/advance",
        json={"operation_key": "finish-reason-planning"},
    )
    assert advanced.status_code == 200, advanced.text

    with client.db_sessions() as db:
        usage = db.scalar(select(UsageEntry).where(UsageEntry.job_id == job_id))
        assert usage is not None
        assert usage.error_class == "provider_output_truncated"
        assert usage.finish_reason == "length"
        assert usage.reported_cost_usd == 0
        assert usage.estimated_cost_usd == 0
        assert usage.model_name == "provider/example:free"
        assert usage.prompt_tokens == 321
        assert usage.completion_tokens == 1400
        assert usage.reasoning_tokens == 975
        assert usage.latency_ms == 845
        assert usage.validation_error_types_json == ["value_error"]
        assert usage.validation_error_paths_json == ["findings.3.statement"]
        assert not hasattr(usage, "raw_response")
