import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config import Settings
from app.models import ResearchReport, UsageEntry
from app.providers.llm import ProviderUsage
from app.providers.scholarly import ScholarlyWork
from app.research import workflow
from app.research.llm_tasks import (
    AppraisalField,
    ClaimAssessment,
    ResearchAppraisalBatch,
    ResearchComparisonBatch,
    ResearchPlanSelectionDraftV1,
    ResearchReportDraft,
    SemanticReportAudit,
    SemanticSupportAssessment,
    SourceAppraisal,
)
from app.research.safe_fetch import SafeHTMLDocument


def test_report_draft_v4_enforces_compact_output_bounds():
    valid = {
        "schema_version": 4,
        "findings": [],
        "qualifications": [],
        "decision_implications": [],
        "unanswered_questions": ["Which outcomes persist after follow-up?"],
        "company_specific_inputs": [],
    }
    assert ResearchReportDraft.model_validate(valid).schema_version == 4

    overlong_text = {**valid, "unanswered_questions": ["x" * 181]}
    with pytest.raises(ValidationError):
        ResearchReportDraft.model_validate(overlong_text)

    too_many_findings = {
        **valid,
        "unanswered_questions": [],
        "findings": [
            {"heading": "Finding", "statement": "Supported", "claim_ids": ["claim-1"]}
            for _ in range(6)
        ],
    }
    with pytest.raises(ValidationError):
        ResearchReportDraft.model_validate(too_many_findings)


def test_provider_json_schema_matches_report_field_validators():
    schema = ResearchReportDraft.model_json_schema()
    definitions = schema["$defs"]
    assert definitions["ReportFinding"]["properties"]["statement"]["maxLength"] == 239
    assert definitions["ReportFinding"]["properties"]["statement"]["pattern"] == r".*[.!?]$"
    assert definitions["ReportQualification"]["properties"]["statement"]["maxLength"] == 219
    assert definitions["ReportQualification"]["properties"]["statement"]["pattern"] == r".*[.!?]$"

    comparison_schema = ResearchComparisonBatch.model_json_schema()
    rationale = comparison_schema["$defs"]["ClaimRelationshipDraft"]["properties"]["rationale"]
    assert rationale["maxLength"] == 159
    assert rationale["pattern"] == r".*[.!?]$"


def test_measurement_absence_requires_explicit_same_outcome_passage():
    unsupported_claim = SimpleNamespace(
        text="A randomized study measured task completion speed and found a 14 percent increase."
    )
    statement = "The study did not measure task productivity outcomes."
    assert workflow._unsupported_unmeasured_outcome_statement(statement, [unsupported_claim])
    paraphrased_absence = (
        "Field studies discuss experience rather than measured productivity outcomes."
    )
    assert workflow._unsupported_unmeasured_outcome_statement(
        paraphrased_absence, [unsupported_claim]
    )

    explicit_claim = SimpleNamespace(text="The study did not measure task productivity outcomes.")
    assert not workflow._unsupported_unmeasured_outcome_statement(statement, [explicit_claim])
    explicit_paraphrase = SimpleNamespace(
        text="The study discusses experience rather than measuring productivity outcomes."
    )
    assert not workflow._unsupported_unmeasured_outcome_statement(
        paraphrased_absence, [explicit_paraphrase]
    )


class PipelineFixtureCrossref:
    def __init__(self):
        pass

    def search(self, query, *, limit=5):
        return []

    def close(self):
        pass


class PipelineFixtureOpenAlex:
    def __init__(self, **kwargs):
        pass

    def search(self, query, *, limit=5):
        return [
            ScholarlyWork(
                external_id="doi:10.5555/ai-productivity-fixture",
                title="AI assistance and task productivity in a randomized worker study",
                doi="10.5555/ai-productivity-fixture",
                url="https://doi.org/10.5555/ai-productivity-fixture",
                authors=[],
                published_year=2025,
                publisher="Fixture Academic Press",
                abstract_excerpt=None,
                query=query,
                provider="OpenAlex",
                provider_metadata={
                    "openalex_id": "https://openalex.org/W10002",
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/pipeline",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    },
                },
            )
        ]

    def close(self):
        pass


class PipelineFixtureHTMLFetcher:
    def __init__(self, *, origin_request_limiter=None):
        pass

    def fetch_html(self, url, *, license_name):
        return SafeHTMLDocument(
            text=(
                "Methods: A randomized study assigned 120 workers to an AI assistance workflow.\n\n"
                "Results: Task completion speed increased by 14 percent for participating workers.\n\n"
                "Limitations: The effect varied by worker experience."
            ),
            sha256="c" * 64,
            media_type="text/html",
            final_host="papers.example",
            retrieved_at=datetime.now(UTC),
            truncated=False,
            host_policy_id="fixture-reviewed-host-v1",
            host_terms_url="https://papers.example/terms",
            robots_status="rules_checked",
        )


class PipelineFixtureOpenAIRE:
    """Keep the end-to-end fixture deterministic and free of external metadata calls."""

    def __init__(self, *args, **kwargs):
        pass

    def search(self, *args, **kwargs):
        return []

    def search_organizations(self, *args, **kwargs):
        return []

    def close(self):
        pass


class PipelineFixtureROR:
    def __init__(self, *args, **kwargs):
        pass

    def search_exact_id(self, *args, **kwargs):
        return None

    def search_exact_domain(self, *args, **kwargs):
        return None

    def verify(self, *args, **kwargs):
        return None

    def close(self):
        pass


def test_deterministic_provider_fixtures_complete_and_persist_ai_pipeline(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", PipelineFixtureCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", PipelineFixtureOpenAlex)
    monkeypatch.setattr(workflow, "OpenAIREProvider", PipelineFixtureOpenAIRE)
    monkeypatch.setattr(workflow, "RORProvider", PipelineFixtureROR)
    monkeypatch.setattr(workflow, "SafeHTMLFetcher", PipelineFixtureHTMLFetcher)
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
    provider_operations = []

    class PipelineFixtureProvider:
        def complete_json(self, **kwargs):
            operation = kwargs["schema_name"]
            provider_operations.append(operation)
            usage = ProviderUsage(
                provider="openrouter",
                model="fixture/structured-output:free",
                input_tokens=450,
                output_tokens=100,
                reported_cost_usd=0.0,
                estimated_cost_usd=0.0,
                latency_ms=3,
            )
            submitted = json.loads(kwargs["user"])

            if operation == "veda_research_plan_selection_v1":
                return SimpleNamespace(
                    value=ResearchPlanSelectionDraftV1(
                        schema_version=1,
                        query_indices=[0, 1, 2],
                        additional_subquestions=[],
                    ),
                    usage=usage,
                )

            if operation == "veda_appraisal_batch_v2":
                passage_by_source = {}
                for passage in submitted["sources"]:
                    passage_by_source.setdefault(passage["source_id"], passage["passage_id"])
                source_appraisals = [
                    SourceAppraisal(
                        source_id=source_id,
                        fields=(
                            [
                                AppraisalField(
                                    name="design_type",
                                    value="Randomized study",
                                    passage_ids=[passage_id],
                                )
                            ]
                            if "randomized"
                            in " ".join(
                                item["text"]
                                for item in submitted["sources"]
                                if item["source_id"] == source_id
                            ).casefold()
                            else []
                        ),
                    )
                    for source_id, passage_id in passage_by_source.items()
                ]
                claims = [
                    ClaimAssessment(
                        claim_id=claim["claim_id"],
                        relationship="supports",
                        rationale="The linked source passage reports this result.",
                        passage_ids=[claim["passage_id"]],
                        evidence_kind="other_study_result",
                        economic_facets=[],
                    )
                    for claim in submitted["claims"]
                ]
                return SimpleNamespace(
                    value=ResearchAppraisalBatch(
                        schema_version=2,
                        source_appraisals=source_appraisals,
                        claim_assessments=claims,
                    ),
                    usage=usage,
                )

            if operation == "veda_comparison_batch_v1":
                return SimpleNamespace(
                    value=ResearchComparisonBatch(
                        schema_version=1,
                        relationships=[],
                        competing_hypotheses=[],
                    ),
                    usage=usage,
                )

            if operation == "veda_report_draft_v4":
                assert (
                    "an outcome absent from an abstract/metadata record is unknown"
                    in kwargs["system"].casefold()
                )
                assert (
                    "say 'not measured' only if a supplied passage says so"
                    in kwargs["system"].casefold()
                )
                evidence = submitted["evidence"]
                assert submitted["material_evidence_requirements"]
                assert all(
                    requirement["requirement_id"].startswith("Q")
                    for requirement in submitted["material_evidence_requirements"]
                )
                assert evidence["sources"] and evidence["claims"]
                assert len(evidence["claims"]) > 1
                source_by_id = {source["source_id"]: source for source in evidence["sources"]}
                assert all(
                    any(
                        passage["passage_id"] == claim["passage_id"]
                        for passage in source_by_id[claim["source_id"]]["passages"]
                    )
                    for claim in evidence["claims"]
                )
                assert all(
                    kwargs["user"].count(passage["text"]) == 1
                    for source in evidence["sources"]
                    for passage in source["passages"]
                )
                first_claim = evidence["claims"][0]
                first_source = source_by_id[first_claim["source_id"]]
                first_passage = next(
                    passage
                    for passage in first_source["passages"]
                    if passage["passage_id"] == first_claim["passage_id"]
                )
                assert any(
                    source["source_id"] == first_claim["source_id"]
                    and any(
                        passage["passage_id"] == first_claim["passage_id"]
                        for passage in source["passages"]
                    )
                    for source in evidence["sources"]
                )
                return SimpleNamespace(
                    value=ResearchReportDraft(
                        schema_version=4,
                        findings=[
                            {
                                "heading": "Source-reported result",
                                "statement": first_claim.get("claim_text", first_passage["text"]),
                                "claim_ids": [first_claim["claim_id"]],
                                "requirement_ids": ["Q1"],
                            },
                            {
                                "heading": "Unsupported absence claim",
                                "statement": "The study did not measure productivity outcomes.",
                                "claim_ids": [first_claim["claim_id"]],
                            },
                        ],
                        qualifications=[],
                        decision_implications=[],
                        unanswered_questions=["Do the measured results generalize to other roles?"],
                        company_specific_inputs=[],
                    ),
                    usage=usage,
                )

            if operation == "veda_semantic_report_audit_v1":
                assert (
                    "do not infer that an outcome was not measured" in kwargs["system"].casefold()
                )
                items = submitted["items_for_passage_support_review"]
                return SimpleNamespace(
                    value=SemanticReportAudit(
                        schema_version=1,
                        support_assessments=[
                            SemanticSupportAssessment(
                                item_id=item["item_id"],
                                verdict="supported",
                                rationale="The cited passage contains the reported statement.",
                                passage_ids=[
                                    evidence["passage_id"] for evidence in item["evidence"]
                                ],
                            )
                            for item in items
                        ],
                        uncited_material_claims=[],
                    ),
                    usage=usage,
                )

            raise AssertionError(f"unexpected structured operation: {operation}")

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", PipelineFixtureProvider)
    project = client.post(
        "/api/v1/projects", json={"title": "AI productivity evidence", "domain": "labor"}
    ).json()
    created = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What randomized studies report about AI task productivity for workers?",
            "depth": "standard",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "budget_ceiling_usd": 0,
            "idempotency_key": "offline-ai-pipeline-fixture",
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]

    final = None
    for index in range(1, 8):
        advanced = client.post(
            f"/api/v1/research-jobs/{job_id}/advance",
            json={"operation_key": f"fixture-pipeline-step-{index}"},
        )
        assert advanced.status_code == 200, advanced.text
        final = advanced.json()
        if final["status"] in {"completed", "completed_with_limitations", "terminal_failure"}:
            break

    assert final is not None
    assert final["status"] == "completed_with_limitations", (
        final.get("error_class"),
        final.get("error_message"),
    )
    assert provider_operations == [
        "veda_research_plan_selection_v1",
        "veda_appraisal_batch_v2",
        "veda_comparison_batch_v1",
        "veda_report_draft_v4",
        "veda_semantic_report_audit_v1",
    ]

    sources = client.get(f"/api/v1/research-jobs/{job_id}/sources").json()["items"]
    claims = client.get(f"/api/v1/research-jobs/{job_id}/claims").json()["items"]
    report_response = client.get(f"/api/v1/research-jobs/{job_id}/report")
    assert report_response.status_code == 200
    report = report_response.json()
    assert sources and claims
    assert any(
        source["appraisal"]["status"] == "model_assessed_not_independently_verified"
        and source["appraisal"]["fields"]["design_type"]["value"] == "Randomized study"
        for source in sources
    )
    assert all(
        claim["appraisal"]["methodology_appraisal"]["status"]
        == "model_assessed_not_independently_verified"
        for claim in claims
    )
    assert (
        report["verification"]["model_assisted_synthesis"] == "performed_not_independently_verified"
    )
    assert report["verification"]["semantic_support_check"] == (
        "performed_model_assisted_not_independently_verified"
    )
    assert report["citation_map"]
    assert report["body_markdown"]
    assert report["verification"]["semantic_audit_items"][0]["requirement_ids"] == ["Q1"]
    assert report["verification"]["evidence_sufficiency_v2"]["status"] == (
        "PRELIMINARY_EVIDENCE_MAP"
    )
    assert "did not measure productivity outcomes" not in report["body_markdown"]
    assert report["verification"]["measurement_absence_guard_v1"]["rejected_findings"] == 1

    for claim in claims:
        assert any(
            citation["source_id"] == claim["source_id"]
            and claim["passage_id"] in citation["passages"]
            for citation in report["citation_map"].values()
        )

    with client.db_sessions() as db:
        persisted_report = db.scalar(select(ResearchReport).where(ResearchReport.job_id == job_id))
        usages = list(
            db.scalars(
                select(UsageEntry).where(UsageEntry.job_id == job_id).order_by(UsageEntry.id)
            )
        )
        assert persisted_report is not None
        assert persisted_report.verification_json["record"]["semantic_assessment"]["method"] == (
            "model_assisted_not_independently_verified"
        )
        assert len(usages) == 5
        assert all(item.succeeded and item.reported_cost_usd == 0 for item in usages)
