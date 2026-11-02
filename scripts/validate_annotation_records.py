"""Validate human-annotation record structure without authenticating reviewers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "evaluation" / "schemas" / "annotation-record.schema.json"
FIXTURE_PATH = ROOT / "evaluation" / "annotations" / "schema-only-example.json"
RECORDS_DIR = ROOT / "evaluation" / "annotations" / "records"
REQUIRED_SCORE_KEYS = {
    "question_scope_fit",
    "source_provenance_access",
    "claim_passage_support",
    "study_design_interpretation",
    "outcome_denominator",
    "uncertainty_limitations",
    "counterevidence_heterogeneity",
    "conclusion_calibration",
    "usefulness_traceability",
}


def validate_record(record: object, validator: Draft202012Validator) -> list[str]:
    errors = [
        f"{list(error.absolute_path) or ['<root>']}: {error.message}"
        for error in validator.iter_errors(record)
    ]
    if not isinstance(record, dict):
        return errors

    if record.get("review_status") == "complete":
        rationales = record.get("score_rationales")
        na_rationales = record.get("na_rationales")
        scores = record.get("scores", {})
        if isinstance(rationales, dict):
            for key in REQUIRED_SCORE_KEYS:
                if scores.get(key) != "N/A" and not rationales.get(key):
                    errors.append(f"score_rationales.{key} is required for a scored dimension")
        if isinstance(na_rationales, dict):
            for key in REQUIRED_SCORE_KEYS:
                if scores.get(key) == "N/A" and not na_rationales.get(key):
                    errors.append(f"na_rationales.{key} must explain N/A")

    finding_ids: list[str] = []
    for field in ("citation_findings", "uncited_claim_findings"):
        findings = record.get(field, [])
        if isinstance(findings, list):
            finding_ids.extend(
                item["finding_id"]
                for item in findings
                if isinstance(item, dict) and isinstance(item.get("finding_id"), str)
            )
    if len(finding_ids) != len(set(finding_ids)):
        errors.append("finding_id values must be unique within a review record")
    return errors


def validate() -> dict[str, object]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    paths = [FIXTURE_PATH]
    if RECORDS_DIR.exists():
        paths.extend(sorted(RECORDS_DIR.glob("*.json")))
    errors: list[str] = []
    statuses: dict[str, int] = {}
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: cannot read JSON ({type(exc).__name__})")
            continue
        record_errors = validate_record(record, validator)
        errors.extend(f"{path.relative_to(ROOT)}: {error}" for error in record_errors)
        if isinstance(record, dict):
            status = str(record.get("review_status", "invalid"))
            statuses[status] = statuses.get(status, 0) + 1
    return {
        "validation": "passed" if not errors else "failed",
        "records_checked": len(paths),
        "review_status_counts": dict(sorted(statuses.items())),
        "human_review_results_counted": False,
        "reviewer_identity_authenticated": False,
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        result = validate()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {"validation": "failed", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("validation") == "passed" else 1)
