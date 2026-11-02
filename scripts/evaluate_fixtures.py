"""Exercise research-quality metric calculations on explicitly synthetic fixtures.

This runner checks evaluation logic only. It does not load production reports, score
the draft research-question registry, contact a model, or evaluate scientific truth.
"""

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "evaluation" / "fixtures" / "quality-metric-fixtures.json"
REGISTRY_PATH = ROOT / "evaluation" / "questions" / "ai_economics_cases.json"
METRIC_NAMES = (
    "passage_support_label_accuracy",
    "citation_link_integrity",
    "material_claim_coverage",
    "material_claim_citation_coverage",
    "scope_field_coverage",
    "scope_safe_relationship_classification",
    "competing_hypothesis_evidence_disjointness",
    "provider_call_budget_compliance",
)


class FixtureError(ValueError):
    pass


def _counter() -> dict[str, int]:
    return {"numerator": 0, "denominator": 0}


def _add(count: dict[str, int], passed: bool) -> None:
    count["denominator"] += 1
    count["numerator"] += int(passed)


def _relationship_after_scope_guard(relation: dict[str, Any]) -> str:
    raw = relation["raw_relationship"]
    alignment = relation["scope_alignment"]
    differences = relation["scope_differences"]
    if raw == "contradicts" and (alignment != "same" or differences):
        return "heterogeneous" if alignment == "different" and differences else "incomparable"
    if raw == "heterogeneous" and (alignment != "different" or not differences):
        return "incomparable"
    return raw


def _validate_fixture_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("fixture_version") != 1 or document.get("fixture_only") is not True:
        raise FixtureError("fixture document must declare fixture_version 1 and fixture_only true")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise FixtureError("fixture document must contain at least one case")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or len(set(case_ids)) != len(case_ids):
        raise FixtureError("fixture cases must be objects with unique case_id values")
    if not all(case.get("synthetic") is True for case in cases):
        raise FixtureError("all metric cases must be explicitly marked synthetic")
    return cases


def evaluate() -> dict[str, Any]:
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cases = _validate_fixture_document(document)
    counts = {name: _counter() for name in METRIC_NAMES}

    for case in cases:
        claim_passages = case.get("claim_passage_ids", {})
        citation_claims = case.get("citation_claim_ids", {})
        items = case.get("report_items", [])
        item_ids = [item.get("item_id") for item in items]
        if len(item_ids) != len(set(item_ids)):
            raise FixtureError(f"{case['case_id']}: report item IDs must be unique")
        item_by_id = {item["item_id"]: item for item in items}

        for item in items:
            if "expected_support" in item or "reported_support" in item:
                if not {"expected_support", "reported_support"} <= item.keys():
                    raise FixtureError(f"{case['case_id']}: support labels require expected and reported values")
                _add(
                    counts["passage_support_label_accuracy"],
                    item["expected_support"] == item["reported_support"],
                )
            for citation_id in item.get("citation_ids", []):
                cited_claims = set(citation_claims.get(citation_id, []))
                item_claims = set(item.get("claim_ids", []))
                passage_linked_claims = {
                    claim_id for claim_id in cited_claims if claim_passages.get(claim_id)
                }
                _add(
                    counts["citation_link_integrity"],
                    bool(citation_id in citation_claims and item_claims & passage_linked_claims),
                )

        required_material = set(case.get("required_material_item_ids", []))
        reported_material = {
            item["item_id"] for item in items if item.get("material") is True
        }
        for item_id in required_material:
            _add(counts["material_claim_coverage"], item_id in reported_material)
        for item_id in reported_material:
            item = item_by_id[item_id]
            has_valid_citation = any(
                citation_id in citation_claims
                and any(
                    claim_id in citation_claims[citation_id] and claim_passages.get(claim_id)
                    for claim_id in item.get("claim_ids", [])
                )
                for citation_id in item.get("citation_ids", [])
            )
            _add(counts["material_claim_citation_coverage"], has_valid_citation)

        expected_scope = set(case.get("expected_scope_fields", []))
        reported_scope = set(case.get("reported_scope_fields", []))
        for field in expected_scope:
            _add(counts["scope_field_coverage"], field in reported_scope)

        for relation in case.get("relationships", []):
            _add(
                counts["scope_safe_relationship_classification"],
                relation.get("stored_relationship") == _relationship_after_scope_guard(relation),
            )

        for pair in case.get("competing_hypothesis_pairs", []):
            side_a = set(pair.get("claim_ids_a", []))
            side_b = set(pair.get("claim_ids_b", []))
            _add(
                counts["competing_hypothesis_evidence_disjointness"],
                bool(side_a) and bool(side_b) and not (side_a & side_b),
            )

        for call in case.get("provider_calls", []):
            try:
                cost = float(call["cost_usd"])
                ceiling = float(call["budget_ceiling_usd"])
            except (KeyError, TypeError, ValueError) as exc:
                raise FixtureError(f"{case['case_id']}: provider call needs numeric cost and ceiling") from exc
            if cost < 0 or ceiling < 0:
                raise FixtureError(f"{case['case_id']}: provider cost and ceiling cannot be negative")
            _add(counts["provider_call_budget_compliance"], cost <= ceiling + 1e-12)

    expected_counts = document.get("expected_metric_counts", {})
    if expected_counts != counts:
        raise FixtureError(
            f"metric counts differ from fixture expectations: expected {expected_counts}, observed {counts}"
        )

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    for case in registry.get("cases", []):
        statuses[case["status"]] = statuses.get(case["status"], 0) + 1
    gold_answers = sum(case.get("gold_answer") is not None for case in registry.get("cases", []))
    metrics = {
        name: {
            **counts[name],
            "rate": round(counts[name]["numerator"] / counts[name]["denominator"], 6)
            if counts[name]["denominator"]
            else None,
        }
        for name in METRIC_NAMES
    }
    return {
        "evaluation_status": "passed",
        "evaluation_type": "synthetic_fixture_metric_logic",
        "fixture_set_id": document["fixture_set_id"],
        "fixture_cases": len(cases),
        "metrics": metrics,
        "draft_registry_case_status_counts": dict(sorted(statuses.items())),
        "draft_registry_gold_answers_present": gold_answers,
        "scientific_quality_scored": False,
        "human_review_results": "none",
        "provider_calls": 0,
        "database": "none",
        "limitations": [
            "All records are synthetic logic fixtures, not Veda research outputs.",
            "Fixture expectations are not evidence about real-world accuracy, groundedness, retrieval recall, or economic truth.",
            "The draft question registry is summarized only to demonstrate that draft cases remain unscored.",
        ],
    }


if __name__ == "__main__":
    try:
        result = evaluate()
    except (FixtureError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"evaluation_status": "failed", "error": str(exc)}, indent=2))
        sys.exit(1)
    print(json.dumps(result, indent=2, sort_keys=True))
