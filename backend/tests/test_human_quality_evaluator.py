import copy
import hashlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.evaluate_human_quality import (  # noqa: E402
    evaluate_packet,
    not_evaluated,
    validate_packet,
)


def _labels(support_status="supported"):
    return {
        "study_judgments": [
            {"study_id": "S1", "eligible": True, "counterevidence": True, "critical": True},
            {"study_id": "S2", "eligible": True, "counterevidence": False, "critical": False},
            {"study_id": "S3", "eligible": False, "counterevidence": False, "critical": False},
        ],
        "claim_judgments": [
            {"claim_id": "C1", "support_status": support_status, "citation_adequate": True},
            {"claim_id": "C2", "support_status": "partially_supported", "citation_adequate": False},
        ],
        "appraisal_judgments": [
            {"field_id": "A1", "study_design": "randomized", "correct": True},
            {"field_id": "A2", "study_design": "observational", "correct": False},
        ],
        "abstention_judgment": {"required": False, "produced": False, "appropriate": True},
    }


def _packet(*, fixture_only=True):
    first = _labels()
    second = _labels(support_status="partially_supported")
    adjudicated = _labels()
    return {
        "schema_version": 1,
        "packet_id": "packet-dev01-r1",
        "fixture_only": fixture_only,
        "dataset_id": "veda-pilot",
        "dataset_version": "1.0.0",
        "evaluation_date": "2026-10-31",
        "case_id": "DEV01",
        "run": {
            "job_id": "job-fixture",
            "report_id": "report-fixture",
            "run_manifest_sha256": "a" * 64,
            "retrieved_study_ids": ["S1", "S2"],
            "selected_study_ids": ["S1", "S2"],
            "full_text_access": [
                {"study_id": "S1", "usable_full_text": True, "usable_methods_results": True},
                {"study_id": "S2", "usable_full_text": False, "usable_methods_results": False},
            ],
            "model_and_cost_recording": "Fixture only; no provider operation or cost was observed.",
        },
        "reference_study_ids": ["S1", "S2", "S3"],
        "material_claim_ids": ["C1", "C2"],
        "appraisal_field_ids": ["A1", "A2"],
        "independent_reviews": [
            {
                "reviewer_pseudonym": "reviewer-alpha",
                "role": "subject reviewer",
                "expertise_area": "software productivity",
                "conflict_declared": False,
                "completed_date": "2026-10-30",
                **first,
            },
            {
                "reviewer_pseudonym": "reviewer-beta",
                "role": "methods reviewer",
                "expertise_area": "research methods",
                "conflict_declared": False,
                "completed_date": "2026-10-31",
                **second,
            },
        ],
        "adjudication": {
            "status": "adjudicated",
            "reviewer_count": 2,
            **adjudicated,
            "notes": "Synthetic test labels only.",
        },
    }


def test_missing_human_review_returns_not_evaluated_not_zero():
    result = not_evaluated()

    assert result["evaluation_status"] == "NOT_EVALUATED"
    assert result["scientific_quality_scored"] is False
    assert result["metrics"]["known_study_recall"] == {
        "status": "NOT_EVALUATED",
        "numerator": None,
        "denominator": None,
        "rate": None,
        "missing_annotation_count": 0,
        "missing_item_ids": [],
        "confidence_interval": None,
        "confidence_interval_note": "Not calculated for this small purposive pilot; no population-level inference is intended.",
    }


def test_adjudicated_packet_uses_declared_metric_denominators_and_discloses_fixture():
    packet = _packet()

    assert validate_packet(packet) == []
    result = evaluate_packet(packet)

    assert result["evaluation_status"] == "SYNTHETIC_LOGIC_FIXTURE"
    assert result["scientific_quality_scored"] is False
    assert result["metrics"]["known_study_recall"]["numerator"] == 2
    assert result["metrics"]["known_study_recall"]["denominator"] == 2
    assert result["metrics"]["selected_source_precision"]["rate"] == 1.0
    assert result["metrics"]["counterevidence_recall"]["rate"] == 1.0
    assert result["metrics"]["critical_full_text_coverage"]["rate"] == 1.0
    assert result["metrics"]["material_claim_support_precision"]["rate"] == 0.5
    assert result["metrics"]["methodological_appraisal_accuracy"]["rate"] == 0.5
    assert result["metrics"]["citation_completeness"]["rate"] == 0.5
    assert result["metrics"]["inter_reviewer_disagreement"]["numerator"] > 0
    assert result["reviewer_authenticity_verified"] is False


def test_incomplete_adjudicated_labels_produce_partial_metric_with_missing_ids():
    packet = _packet()
    packet["adjudication"]["claim_judgments"].pop()

    assert validate_packet(packet) == []
    result = evaluate_packet(packet)
    metric = result["metrics"]["material_claim_support_precision"]

    assert result["evaluation_status"] == "PARTIAL"
    assert metric["status"] == "PARTIAL"
    assert metric["numerator"] == 1
    assert metric["denominator"] == 1
    assert metric["missing_item_ids"] == ["C2"]


def test_duplicate_reviewer_identity_and_unknown_source_labels_are_rejected():
    packet = _packet()
    packet["independent_reviews"][1]["reviewer_pseudonym"] = "reviewer-alpha"
    packet["adjudication"]["study_judgments"].append(
        {"study_id": "S404", "eligible": True, "counterevidence": False, "critical": False}
    )

    errors = validate_packet(packet)

    assert any("pseudonyms must be unique" in item for item in errors)
    assert any("unexpected ID" in item for item in errors)


def test_pending_adjudication_never_produces_quality_scores():
    packet = copy.deepcopy(_packet())
    packet["adjudication"]["status"] = "pending"

    result = evaluate_packet(packet)

    assert result["evaluation_status"] == "PENDING_ADJUDICATION"
    assert result["scientific_quality_scored"] is False


def test_t126_baseline_artifact_hashes_remain_unchanged():
    manifest = json.loads(
        (REPOSITORY_ROOT / "evaluation/baselines/t126-baseline-manifest.json").read_text(
            encoding="utf-8"
        )
    )

    for artifact in manifest["artifacts"]:
        path = REPOSITORY_ROOT / artifact["path"]
        data = path.read_bytes()
        assert len(data) == artifact["bytes"]
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
