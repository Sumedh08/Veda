"""Validate and score adjudicated human review packets for immutable Veda runs.

With no input packet this reports NOT_EVALUATED. JSON shape alone does not
authenticate a reviewer; scientific-quality scores are emitted only for a
two-reviewer packet whose adjudication and run-manifest identity are recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "evaluation" / "schemas" / "quality-review-packet-v1.schema.json"
METRIC_FORMULAS = {
    "known_study_recall": "adjudicated eligible reference studies retrieved / all adjudicated eligible reference studies",
    "selected_source_precision": "selected studies adjudicated eligible / all selected studies",
    "counterevidence_recall": "eligible contrary or qualifying reference studies retrieved / all such reference studies",
    "critical_full_text_coverage": "selected critical eligible studies with usable Methods/Results text / selected critical eligible studies",
    "material_claim_support_precision": "material claims adjudicated supported / all declared material claims",
    "methodological_appraisal_accuracy": "adjudicated appraisal fields judged correct / all declared appraisal fields",
    "citation_completeness": "material claims with adequate cited source and passage / all declared material claims",
    "abstention_appropriateness": "case-runs adjudicated with appropriate abstention behavior / adjudicated case-runs",
    "inter_reviewer_disagreement": "independent label fields that differ / independent label fields compared",
}


class QualityPacketError(ValueError):
    """Sanitized quality-packet input failure."""


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_packet(packet: object) -> list[str]:
    errors = [
        f"{list(error.absolute_path) or ['<root>']}: {error.message}"
        for error in _schema_validator().iter_errors(packet)
    ]
    if not isinstance(packet, dict):
        return errors
    reviews = packet.get("independent_reviews", [])
    if isinstance(reviews, list):
        pseudonyms = [
            row.get("reviewer_pseudonym")
            for row in reviews
            if isinstance(row, dict) and isinstance(row.get("reviewer_pseudonym"), str)
        ]
        if len(pseudonyms) != len(set(pseudonyms)):
            errors.append("independent review pseudonyms must be unique")
    run = packet.get("run")
    if not isinstance(run, dict):
        return errors
    retrieved = set(run.get("retrieved_study_ids", []))
    selected = set(run.get("selected_study_ids", []))
    if not selected <= retrieved:
        errors.append("selected studies must be a subset of retrieved study IDs")
    references = set(packet.get("reference_study_ids", []))
    if not selected <= references:
        errors.append("every selected study must appear in the reviewer reference set")
    access = run.get("full_text_access", [])
    if isinstance(access, list):
        access_ids = [item.get("study_id") for item in access if isinstance(item, dict)]
        if len(access_ids) != len(set(access_ids)):
            errors.append("full-text access records must have unique study IDs")
        if not set(access_ids) <= selected:
            errors.append("full-text access records must refer to selected studies")
        if any(
            item.get("usable_methods_results") is True and item.get("usable_full_text") is not True
            for item in access
            if isinstance(item, dict)
        ):
            errors.append("usable Methods/Results evidence requires usable full text")
    expected_ids = {
        "study_judgments": (references, "study_id"),
        "claim_judgments": (set(packet.get("material_claim_ids", [])), "claim_id"),
        "appraisal_judgments": (set(packet.get("appraisal_field_ids", [])), "field_id"),
    }
    for index, review in enumerate([*reviews, packet.get("adjudication", {})]):
        if not isinstance(review, dict):
            continue
        label_specs = (
            ("study_judgments", "study_id"),
            ("claim_judgments", "claim_id"),
            ("appraisal_judgments", "field_id"),
        )
        for collection, key in label_specs:
            rows = review.get(collection, [])
            ids = (
                [row.get(key) for row in rows if isinstance(row, dict)]
                if isinstance(rows, list)
                else []
            )
            if len(ids) != len(set(ids)):
                errors.append(f"review[{index}].{collection} IDs must be unique")
            allowed_ids, _ = expected_ids[collection]
            if not set(ids) <= allowed_ids:
                errors.append(f"review[{index}].{collection} contains an unexpected ID")
    adjudication = packet.get("adjudication")
    if (
        isinstance(adjudication, dict)
        and adjudication.get("status") == "adjudicated"
        and adjudication.get("reviewer_count") != len(reviews)
    ):
        errors.append("adjudicated reviewer_count must equal independent review count")
    return errors


def _count_metric(
    numerator: int, denominator: int, missing_ids: Iterable[str] = ()
) -> dict[str, Any]:
    missing = sorted(set(missing_ids))
    if denominator == 0:
        status = "NOT_EVALUATED"
        rate = None
    else:
        status = "PARTIAL" if missing else "SCORED"
        rate = round(numerator / denominator, 6)
    return {
        "status": status,
        "numerator": numerator if denominator else None,
        "denominator": denominator if denominator else None,
        "rate": rate,
        "missing_annotation_count": len(missing),
        "missing_item_ids": missing,
        "confidence_interval": None,
        "confidence_interval_note": "Not calculated for this small purposive pilot; no population-level inference is intended.",
    }


def _index(rows: object, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        row[key]: row for row in rows if isinstance(row, dict) and isinstance(row.get(key), str)
    }


def _disagreements(first: dict[str, Any], second: dict[str, Any]) -> tuple[int, int, int]:
    disagreements = 0
    compared = 0
    missing = 0
    for collection, key, fields in (
        ("study_judgments", "study_id", ("eligible", "counterevidence", "critical")),
        ("claim_judgments", "claim_id", ("support_status", "citation_adequate")),
        ("appraisal_judgments", "field_id", ("study_design", "correct")),
    ):
        left = _index(first.get(collection), key)
        right = _index(second.get(collection), key)
        all_ids = set(left) | set(right)
        for item_id in all_ids:
            if item_id not in left or item_id not in right:
                missing += len(fields)
                continue
            for field in fields:
                compared += 1
                disagreements += int(left[item_id].get(field) != right[item_id].get(field))
    left_abstention = first.get("abstention_judgment", {})
    right_abstention = second.get("abstention_judgment", {})
    for field in ("required", "produced", "appropriate"):
        if field not in left_abstention or field not in right_abstention:
            missing += 1
        else:
            compared += 1
            disagreements += int(left_abstention[field] != right_abstention[field])
    return disagreements, compared, missing


def not_evaluated(
    *, reason: str = "No adjudicated two-reviewer packet was supplied."
) -> dict[str, Any]:
    return {
        "evaluation_status": "NOT_EVALUATED",
        "evaluation_type": "human_review_quality",
        "scientific_quality_scored": False,
        "reviewer_authenticity_verified": False,
        "reviewers_required": 2,
        "adjudication_required": True,
        "human_review_results": "none",
        "reason": reason,
        "metrics": {name: _count_metric(0, 0) for name in METRIC_FORMULAS},
        "metric_formulas": METRIC_FORMULAS,
    }


def evaluate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    errors = validate_packet(packet)
    if errors:
        raise QualityPacketError("; ".join(errors))
    adjudication = packet["adjudication"]
    if adjudication["status"] != "adjudicated":
        result = not_evaluated(reason="The packet is awaiting human adjudication.")
        result.update(
            packet_id=packet["packet_id"],
            dataset_id=packet["dataset_id"],
            dataset_version=packet["dataset_version"],
            case_id=packet["case_id"],
            reviewer_count=len(packet["independent_reviews"]),
        )
        result["evaluation_status"] = "PENDING_ADJUDICATION"
        return result

    run = packet["run"]
    references = set(packet["reference_study_ids"])
    claims = set(packet["material_claim_ids"])
    fields = set(packet["appraisal_field_ids"])
    adjudicated_studies = _index(adjudication["study_judgments"], "study_id")
    adjudicated_claims = _index(adjudication["claim_judgments"], "claim_id")
    adjudicated_fields = _index(adjudication["appraisal_judgments"], "field_id")
    retrieved = set(run["retrieved_study_ids"])
    selected = set(run["selected_study_ids"])
    missing_studies = references - set(adjudicated_studies)
    eligible = {
        study_id
        for study_id, label in adjudicated_studies.items()
        if study_id in references and label["eligible"]
    }
    counterevidence = {
        study_id
        for study_id, label in adjudicated_studies.items()
        if study_id in references and label["eligible"] and label["counterevidence"]
    }
    selected_eligible = {
        study_id
        for study_id in selected
        if study_id in adjudicated_studies and adjudicated_studies[study_id]["eligible"]
    }
    selected_critical = {
        study_id
        for study_id in selected
        if study_id in adjudicated_studies
        and adjudicated_studies[study_id]["eligible"]
        and adjudicated_studies[study_id]["critical"]
    }
    access_by_id = {
        item["study_id"]: item
        for item in run["full_text_access"]
        if item["study_id"] in selected_critical
    }
    usable_critical = {
        study_id
        for study_id, access in access_by_id.items()
        if access["usable_full_text"] and access["usable_methods_results"]
    }
    adjudicated_claim_ids = claims & set(adjudicated_claims)
    adjudicated_field_ids = fields & set(adjudicated_fields)
    claim_missing = claims - set(adjudicated_claims)
    field_missing = fields - set(adjudicated_fields)
    disagreement_count, compared_count, disagreement_missing = _disagreements(
        packet["independent_reviews"][0], packet["independent_reviews"][1]
    )
    abstention = adjudication["abstention_judgment"]
    metrics = {
        "known_study_recall": _count_metric(
            len(eligible & retrieved), len(eligible), missing_studies
        ),
        "selected_source_precision": _count_metric(len(selected_eligible), len(selected)),
        "counterevidence_recall": _count_metric(
            len(counterevidence & retrieved), len(counterevidence), missing_studies
        ),
        "critical_full_text_coverage": _count_metric(
            len(usable_critical),
            len(selected_critical),
            selected_critical - set(access_by_id),
        ),
        "material_claim_support_precision": _count_metric(
            sum(
                adjudicated_claims[item_id]["support_status"] == "supported"
                for item_id in adjudicated_claim_ids
            ),
            len(adjudicated_claim_ids),
            claim_missing,
        ),
        "methodological_appraisal_accuracy": _count_metric(
            sum(adjudicated_fields[item_id]["correct"] for item_id in adjudicated_field_ids),
            len(adjudicated_field_ids),
            field_missing,
        ),
        "citation_completeness": _count_metric(
            sum(
                adjudicated_claims[item_id]["citation_adequate"]
                for item_id in adjudicated_claim_ids
            ),
            len(adjudicated_claim_ids),
            claim_missing,
        ),
        "abstention_appropriateness": _count_metric(int(abstention["appropriate"]), 1),
        "inter_reviewer_disagreement": _count_metric(
            disagreement_count,
            compared_count,
            [f"unmatched_review_labels:{disagreement_missing}"] if disagreement_missing else (),
        ),
    }
    is_fixture = packet["fixture_only"]
    partial = any(metric["status"] == "PARTIAL" for metric in metrics.values())
    return {
        "evaluation_status": (
            "PARTIAL" if partial else "SYNTHETIC_LOGIC_FIXTURE" if is_fixture else "SCORED"
        ),
        "evaluation_type": "synthetic_quality_logic_fixture"
        if is_fixture
        else "human_review_quality",
        "scientific_quality_scored": not is_fixture,
        "reviewer_authenticity_verified": False,
        "reviewers_required": 2,
        "reviewer_count": len(packet["independent_reviews"]),
        "adjudication_status": adjudication["status"],
        "human_review_results": "synthetic fixture labels only"
        if is_fixture
        else "adjudicated labels; reviewer identity not authenticated",
        "packet_id": packet["packet_id"],
        "dataset_id": packet["dataset_id"],
        "dataset_version": packet["dataset_version"],
        "evaluation_date": packet["evaluation_date"],
        "case_id": packet["case_id"],
        "job_id": run["job_id"],
        "report_id": run["report_id"],
        "run_manifest_sha256": run["run_manifest_sha256"],
        "metrics": metrics,
        "metric_formulas": METRIC_FORMULAS,
        "limitations": [
            "Two distinct pseudonyms and a schema-valid adjudication do not authenticate reviewer qualifications or independence.",
            "Scores apply only to this declared reference set and immutable run; they are not global literature recall or population accuracy.",
            "No confidence intervals are calculated for this small purposive pilot.",
        ],
    }


def evaluate_file(input_path: Path | None) -> dict[str, Any]:
    if input_path is None:
        return not_evaluated()
    try:
        packet = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualityPacketError(f"Cannot read review packet ({type(exc).__name__}).") from None
    if not isinstance(packet, dict):
        raise QualityPacketError("Review packet must be a JSON object.")
    return evaluate_packet(packet)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Adjudicated review packet JSON")
    parser.add_argument("--output", type=Path, help="Optional output JSON path")
    arguments = parser.parse_args()
    try:
        result = evaluate_file(arguments.input)
    except QualityPacketError as exc:
        result = {"evaluation_status": "INVALID_PACKET", "error": str(exc)}
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if result["evaluation_status"] == "INVALID_PACKET" else 0


if __name__ == "__main__":
    sys.exit(main())
