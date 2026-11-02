"""Check benchmark sample links and fail closed on unsupported quality claims."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "evaluation" / "benchmark-plan.json"
REGISTRY_PATH = ROOT / "evaluation" / "questions" / "ai_economics_cases.json"
EXPECTED_CASE_COUNT = 7


def validate(
    plan: dict[str, object] | None = None, registry: dict[str, object] | None = None
) -> dict[str, object]:
    if plan is None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if registry is None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registered_cases = {
        case["case_id"]: case
        for case in registry.get("cases", [])
        if isinstance(case, dict)
    }
    selected = plan.get("cases")
    errors: list[str] = []
    selected = selected if isinstance(selected, list) else []
    case_ids = [case.get("case_id") for case in selected if isinstance(case, dict)]

    if len(selected) != EXPECTED_CASE_COUNT:
        errors.append(
            f"the pre-registered pilot must contain exactly {EXPECTED_CASE_COUNT} cases"
        )
    if len(case_ids) != len(set(case_ids)):
        errors.append("selected case IDs must be unique")
    selection_method = plan.get("selection_method", {})
    if (
        not isinstance(selection_method, dict)
        or selection_method.get(
            "selection_locked_before_any_new_veda_run_or_annotation"
        )
        is not True
    ):
        errors.append("sample selection must be locked before new runs or annotations")
    current_state = plan.get("current_state", {})
    if not isinstance(current_state, dict):
        errors.append("current_state must be an object")
    else:
        if current_state.get("candidate_source_metadata_screened") is True:
            screen_date = current_state.get("candidate_source_screen_date")
            if not isinstance(screen_date, str) or len(screen_date) != 10:
                errors.append(
                    "a completed candidate source metadata screen needs a dated evidence record"
                )
            screen_note = current_state.get("candidate_source_screen_note")
            if not isinstance(screen_note, str) or not (ROOT / screen_note).is_file():
                errors.append(
                    "a completed candidate source metadata screen needs an existing evidence note"
                )
        if (
            current_state.get("source_set_finalized") is True
            and current_state.get("primary_source_review_complete") is not True
        ):
            errors.append(
                "a finalized source set requires completed primary-source review"
            )
        if current_state.get("quality_scores_reported") is True:
            if current_state.get("primary_source_review_complete") is not True:
                errors.append(
                    "quality scores require a completed primary-source review"
                )
            if current_state.get("source_set_finalized") is not True:
                errors.append("quality scores require a finalized source set")
            if current_state.get("veda_runs_completed") != EXPECTED_CASE_COUNT:
                errors.append(
                    "quality scores require one completed Veda run per selected case"
                )
            if (
                current_state.get("independent_human_reviews_completed", 0)
                < 2 * EXPECTED_CASE_COUNT
            ):
                errors.append(
                    "quality scores require two independent reviews per selected case-run"
                )
            results_path = current_state.get("results_path")
            if not isinstance(results_path, str) or not (ROOT / results_path).is_file():
                errors.append("quality scores require a durable results report")
    evidence_note = plan.get("candidate_evidence_note")
    if not isinstance(evidence_note, str) or not (ROOT / evidence_note).is_file():
        errors.append("the candidate evidence note must exist in the repository")

    reused_sources: dict[str, set[str]] = {}
    for entry in selected:
        if not isinstance(entry, dict):
            errors.append("each selected case must be an object")
            continue
        case_id = entry.get("case_id")
        registry_case = registered_cases.get(case_id)
        if registry_case is None:
            errors.append(f"selected case {case_id!r} is absent from the case registry")
        elif registry_case.get("status") not in {
            "draft",
            "human_reviewed",
            "validated",
        }:
            errors.append(
                f"selected case {case_id} has an invalid registry review status"
            )
        source_entries = entry.get("candidate_primary_sources")
        if not isinstance(source_entries, list) or not source_entries:
            errors.append(
                f"selected case {case_id} must name at least one candidate primary source"
            )
            continue
        for source in source_entries:
            if not isinstance(source, dict):
                errors.append(f"candidate sources for {case_id} must be objects")
                continue
            source_id = source.get("source_id")
            if not isinstance(source_id, str) or not source_id:
                errors.append(
                    f"candidate source for {case_id} needs a stable source_id"
                )
                continue
            reused_sources.setdefault(source_id, set()).add(case_id)
            if not str(source.get("doi", "")).strip() or not str(
                source.get("url", "")
            ).startswith("https://doi.org/"):
                errors.append(
                    f"candidate source {source_id} needs a DOI and canonical DOI URL"
                )
            if not source.get("access_status"):
                errors.append(
                    f"candidate source {source_id} needs an explicit access status"
                )

    duplicate_use = {
        key: sorted(value) for key, value in reused_sources.items() if len(value) > 1
    }
    source_rules = plan.get("source_inclusion_exclusion", {})
    if not isinstance(source_rules, dict) or not source_rules.get("include"):
        errors.append("source inclusion rules must be documented")
    if not isinstance(source_rules, dict) or not source_rules.get(
        "exclude_from_primary_evidence_set"
    ):
        errors.append("source exclusion rules must be documented")
    return {
        "validation": "passed" if not errors else "failed",
        "selected_cases": len(case_ids),
        "selected_case_ids": case_ids,
        "unique_candidate_sources": len(reused_sources),
        "candidate_sources_reused_across_cases": duplicate_use,
        "candidate_source_metadata_screened": (
            current_state.get("candidate_source_metadata_screened") is True
            if isinstance(current_state, dict)
            else False
        ),
        "primary_source_review_complete": (
            current_state.get("primary_source_review_complete") is True
            if isinstance(current_state, dict)
            else False
        ),
        "source_set_finalized": (
            current_state.get("source_set_finalized") is True
            if isinstance(current_state, dict)
            else False
        ),
        "quality_scores_reported": False,
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        result = validate()
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {"validation": "failed", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("validation") == "passed" else 1)
