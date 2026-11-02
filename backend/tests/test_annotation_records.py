import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.validate_annotation_records import validate_record  # noqa: E402


def load_schema_and_fixture():
    schema = json.loads(
        (REPOSITORY_ROOT / "evaluation/schemas/annotation-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    fixture = json.loads(
        (REPOSITORY_ROOT / "evaluation/annotations/schema-only-example.json").read_text(
            encoding="utf-8"
        )
    )
    return Draft202012Validator(schema, format_checker=FormatChecker()), fixture


def test_schema_only_annotation_fixture_validates_without_claiming_review():
    validator, fixture = load_schema_and_fixture()

    assert validate_record(fixture, validator) == []
    assert fixture["review_status"] == "not_reviewed"
    assert all(value is None for value in fixture["scores"].values())


def test_complete_record_requires_immutable_run_and_review_metadata():
    validator, fixture = load_schema_and_fixture()
    record = copy.deepcopy(fixture)
    record["review_status"] = "complete"

    errors = validate_record(record, validator)

    assert any("run_id" in error for error in errors)
    assert any("run_manifest_sha256" in error for error in errors)
    assert any("review_date" in error for error in errors)
    assert any("provider" in error for error in errors)


def test_completed_scores_need_rationales_and_na_explanations():
    validator, fixture = load_schema_and_fixture()
    record = copy.deepcopy(fixture)
    record.update(
        {
            "review_status": "complete",
            "run_id": "job-123",
            "run_manifest_sha256": "a" * 64,
            "review_date": "2026-10-29",
            "provider": "test-fixture",
            "model": "fixture-only",
            "model_version": "fixture-only-v1",
            "source_set_version": "candidate-set-v1",
            "score_rationales": {},
            "na_rationales": {},
        }
    )
    record["reviewer"].update(
        {
            "pseudonym": "reviewer-a",
            "role": "domain reviewer",
            "expertise_area": "labor economics",
            "conflict_declared": False,
            "conflict_notes": "No conflicts declared.",
        }
    )
    record["scores"]["question_scope_fit"] = 2
    record["scores"]["source_provenance_access"] = "N/A"

    errors = validate_record(record, validator)

    assert "score_rationales.question_scope_fit is required for a scored dimension" in errors
    assert "na_rationales.source_provenance_access must explain N/A" in errors


def test_duplicate_finding_ids_are_rejected():
    validator, fixture = load_schema_and_fixture()
    record = copy.deepcopy(fixture)
    finding = {
        "finding_id": "F-1",
        "kind": "unsupported_claim",
        "report_item_id": "claim-1",
        "source_id": "source-1",
        "passage_id": "passage-1",
        "severity": "major",
        "description": "The saved passage does not support the report item.",
        "reviewer_quote": "Claim text",
    }
    record["citation_findings"] = [finding]
    record["uncited_claim_findings"] = [copy.deepcopy(finding)]

    assert "finding_id values must be unique within a review record" in validate_record(
        record, validator
    )
