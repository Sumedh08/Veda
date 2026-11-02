import copy

import pytest
from pydantic import ValidationError
from support import add_test_passage

from app.models import Claim, ResearchJob, ResearchReport, Source
from app.research import workflow
from app.schemas import (
    ReportCitationMapV1,
    ReportVerificationEnvelopeV1,
    build_report_stage_result,
    report_citation_map_for_api,
    report_verification_for_api,
    versioned_report_citation_map,
    versioned_report_verification,
)


def _citation_map() -> dict:
    return {
        "S1": {
            "source_id": "source-1",
            "title": "A source",
            "doi": None,
            "url": "https://example.org/paper",
            "passages": ["passage-1"],
        }
    }


def _verification() -> dict:
    return {
        "report_schema_version": 2,
        "level": "deterministic_link_integrity_only",
        "status": "passed",
        "claims_checked": 1,
        "claims_with_valid_source_and_passage": 1,
        "semantic_support_check": "performed_model_assisted_not_independently_verified",
        "uncited_material_claim_scan": "performed_model_assisted_not_guaranteed",
        "semantic_audit_provider": "openrouter",
        "semantic_audit_model": "fixture-model",
        "semantic_audit_schema_version": 1,
        "semantic_audit_items": [
            {
                "item_id": "F1",
                "kind": "finding",
                "status": "model_assessed_not_independently_verified",
                "verdict": "partially_supported",
                "rationale": "The passage covers the population but not the full outcome.",
                "passage_ids": ["passage-1"],
            }
        ],
        "uncited_material_claims": [],
        "rejected_semantic_audit_records": 0,
        "uncited_scan_input_truncated": False,
        "semantic_audit_skip_reason": None,
        "model_assisted_appraisal": "not_performed",
        "model_assisted_synthesis": "performed_not_independently_verified",
        "finding_to_claim_links": "deterministic_checked",
        "comparison_section": {"status": "rendered", "relationships_rendered": 1},
        "search_coverage": {"status": "recorded", "providers": ["openalex"]},
        "findings_with_valid_claim_links": 1,
        "qualifications_with_valid_claim_links": 0,
        "rejected_findings_with_unsupported_numbers": 0,
        "rejected_qualifications_with_unsupported_numbers": 0,
        "decision_implication_status": "not_in_scope",
        "decision_implications": [],
        "rejected_decision_implications": 0,
        "claim_units": [],
    }


def test_report_citation_map_v1_upcasts_legacy_without_mutating_or_changing_api_shape():
    legacy = _citation_map()
    legacy["S1"]["future_provider_note"] = {"retained": True}
    legacy["future_root_field"] = "retained as extension"
    before = copy.deepcopy(legacy)

    stored = versioned_report_citation_map(legacy)

    assert legacy == before
    assert ReportCitationMapV1.model_validate(stored)
    assert stored["schema_version"] == 1
    assert stored["citations"]["S1"]["extensions"] == {"future_provider_note": {"retained": True}}
    assert stored["extensions"]["future_root_field"] == "retained as extension"
    assert report_citation_map_for_api(stored)["S1"]["source_id"] == "source-1"


def test_report_citation_map_strict_write_rejects_bad_labels_records_and_versions():
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_citation_map({"other": _citation_map()["S1"]}, strict=True)
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_citation_map({"S1": {"source_id": "source-1"}}, strict=True)
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_citation_map(
            {"schema_version": 2, "citations": _citation_map()}, strict=True
        )
    assert report_citation_map_for_api({"schema_version": 99, "citations": {}}) == {}


def test_report_verification_v1_separates_deterministic_and_model_assisted_checks():
    legacy = _verification()
    legacy["future_policy_metric"] = {"version": 2}
    before = copy.deepcopy(legacy)

    stored = versioned_report_verification(legacy)
    record = stored["record"]
    api_record = report_verification_for_api(stored)

    assert legacy == before
    assert ReportVerificationEnvelopeV1.model_validate(stored)
    assert stored["schema_version"] == 1
    assert record["citation_link_integrity"] == {
        "schema_version": 1,
        "level": "deterministic_link_integrity_only",
        "status": "passed",
        "claims_checked": 1,
        "claims_with_valid_source_and_passage": 1,
    }
    assert record["semantic_assessment"]["method"] == ("model_assisted_not_independently_verified")
    assert record["semantic_assessment"]["support_check"] == legacy["semantic_support_check"]
    assert api_record["report_schema_version"] == 2
    assert api_record["semantic_support_check"] == legacy["semantic_support_check"]
    assert api_record["future_policy_metric"] == {"version": 2}


def test_report_verification_strict_write_checks_versions_status_and_nested_consistency():
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_verification({**_verification(), "report_schema_version": 3}, strict=True)
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_verification({**_verification(), "level": "model_semantic"}, strict=True)
    envelope = versioned_report_verification(_verification(), strict=True)
    corrupted = copy.deepcopy(envelope)
    corrupted["record"]["citation_link_integrity"]["status"] = "needs_review"
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_verification(corrupted, strict=True)
    assert report_verification_for_api({"schema_version": 99, "record": {}})["status"] == (
        "needs_review"
    )


def test_report_search_coverage_typed_routing_requires_both_provider_outcomes():
    verification = _verification()
    verification["search_coverage"]["conditional_statistics_routing"] = {
        "status": "recorded",
        "schema_version": 1,
        "world_bank_data360": {
            "schema_version": 1,
            "status": "not_applicable",
            "reason_code": "unsupported_topic",
        },
        "ilostat": {
            "schema_version": 1,
            "status": "not_attempted",
            "reason_code": "deadline_elapsed",
        },
    }

    saved = versioned_report_verification(verification, strict=True)
    assert (
        saved["record"]["search_coverage"]["conditional_statistics_routing"]["ilostat"][
            "reason_code"
        ]
        == "deadline_elapsed"
    )

    malformed = copy.deepcopy(verification)
    del malformed["search_coverage"]["conditional_statistics_routing"]["ilostat"]
    with pytest.raises((ValidationError, ValueError)):
        versioned_report_verification(malformed, strict=True)


def test_malformed_legacy_verification_degrades_in_memory_without_mutation():
    malformed = {"report_schema_version": 2, "claims_checked": "not-a-number"}
    before = copy.deepcopy(malformed)

    result = versioned_report_verification(malformed)

    assert malformed == before
    assert result["record"]["status"] == "needs_review"
    assert result["extensions"]["legacy_read_status"] == "malformed_or_unsupported"


def test_synthesis_stage_result_is_typed_before_persistence():
    result = build_report_stage_result("# Evidence map", _citation_map(), _verification(), "test")

    assert result.schema_version == 1
    assert result.citation_map.citations["S1"].source_id == "source-1"
    assert result.verification.citation_link_integrity.status == "passed"
    assert result.verification.semantic_assessment.method == (
        "model_assisted_not_independently_verified"
    )
    with pytest.raises((ValidationError, ValueError)):
        build_report_stage_result(
            "# Evidence map",
            _citation_map(),
            {**_verification(), "semantic_support_check": "not_performed"},
            "test",
        )


def test_model_assisted_workflow_report_uses_envelopes_at_storage_and_api(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Report contracts", "domain": "testing"}
    ).json()
    job_response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What does this evidence report?",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "idempotency_key": "report-contract-model-path",
        },
    )
    assert job_response.status_code == 201, job_response.text
    job_id = job_response.json()["id"]
    monkeypatch.setattr(workflow.settings, "llm_provider", "openrouter")

    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        source = Source(
            job_id=job_id,
            external_id="fixture:report-contract-source",
            title="Report contract source",
            retrieval_status="abstract_only",
        )
        db.add(source)
        db.flush()
        content = "The source reports an observed outcome for workers."
        passage = add_test_passage(db, source, ordinal=0, locator="p. 1", content=content)
        db.add(
            Claim(
                job_id=job_id,
                source_id=source.id,
                passage_id=passage.id,
                text=content,
                span_start=0,
                span_end=len(content),
                atomization_status="whole_sentence",
                atomization_version=1,
                claim_type="source_reported",
                evidence_status="not_independently_verified",
            )
        )
        db.flush()
        citation_map = {
            "S1": {
                "source_id": source.id,
                "title": source.title,
                "doi": None,
                "url": "https://example.org/report-contract",
                "passages": [passage.id],
            }
        }
        job.current_stage = "synthesis"
        job.checkpoint_json = {"citation_map": citation_map}

        def build_report(*_args, **_kwargs):
            return (
                ("# Model-assisted report", citation_map, _verification(), "fixture-model"),
                None,
                None,
            )

        monkeypatch.setattr(workflow, "_build_model_report", build_report)
        result = workflow.execute_stage(db, workflow.job_snapshot(job))
        assert result.report is not None
        workflow.persist_result(db, job, result)
        db.commit()
        persisted = db.query(ResearchReport).filter_by(job_id=job_id).one()
        report_id = persisted.id
        assert persisted.citation_map_json["schema_version"] == 1
        assert persisted.verification_json["schema_version"] == 1
        assert persisted.verification_json["record"]["semantic_assessment"]["method"] == (
            "model_assisted_not_independently_verified"
        )
        sufficiency = persisted.verification_json["record"]["extensions"]["evidence_sufficiency_v1"]
        assert sufficiency["status"] == "PROVISIONAL"
        assert sufficiency["human_review_status"] == "not_performed"
        assert "## Evidence sufficiency" in persisted.body_markdown

    response = client.get(f"/api/v1/reports/{report_id}")
    assert response.status_code == 200, response.text
    api_report = response.json()
    assert api_report["model_name"] == "fixture-model"
    assert api_report["citation_map"]["S1"]["source_id"] == source.id
    assert api_report["verification"]["citation_link_integrity"]["status"] == "passed"
    assert api_report["verification"]["semantic_assessment"]["method"] == (
        "model_assisted_not_independently_verified"
    )
    assert api_report["verification"]["evidence_sufficiency_v1"]["status"] == "PROVISIONAL"
