"""Build typed audit records for bounded planned scholarly query execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas import SearchLensExecutionV1

_CATEGORY_BY_FOCUS = {
    "direct_evidence": "DIRECT_QUESTION",
    "requested_scope": "SUBGROUP_OR_POPULATION",
    "follow_up_update": "TERMINOLOGY_EXPANSION",
    "counterevidence": "CONTRARY_OR_NULL_EVIDENCE",
    "limitations_and_measurement": "STUDY_DESIGN",
    "design_and_scope": "STUDY_DESIGN",
    "heterogeneity": "ALTERNATIVE_EXPLANATION",
}


def build_search_lens_execution(
    *,
    index: int,
    rationale: dict[str, Any],
    provider_outcomes: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    started_at: datetime,
    completed_at: datetime | None,
) -> SearchLensExecutionV1:
    """Preserve exact query, provider outcomes, and candidate inclusion lineage."""
    query = rationale["query"]
    focus = rationale["focus"]
    if focus not in _CATEGORY_BY_FOCUS:
        raise ValueError("planned query has no supported search-lens category")
    matching_candidates = [
        candidate for candidate in candidates if candidate["record"].query == query
    ]
    states = {record["status"] for record in provider_outcomes}
    if not states or states == {"not_attempted"}:
        status = "not_attempted"
        completed_at = None
    elif "completed" in states and states == {"completed"}:
        status = "completed"
    elif "completed" in states:
        status = "partial"
    else:
        status = "failed"
    provider_records = []
    for outcome in provider_outcomes:
        provider_records.append(outcome)
    candidate_keys = [candidate["candidate_key"] for candidate in matching_candidates]
    selected_keys = [
        candidate["candidate_key"]
        for candidate in matching_candidates
        if candidate["disposition"] == "selected"
    ]
    return SearchLensExecutionV1.model_validate(
        {
            "schema_version": 1,
            "lens_id": f"L{index + 1}",
            "category": _CATEGORY_BY_FOCUS[focus],
            "purpose": rationale["purpose"],
            "focus": focus,
            "exact_query": query,
            "started_at": started_at,
            "completed_at": completed_at,
            "pagination_state": "not_attempted"
            if status == "not_attempted"
            else "single_page_bounded",
            "status": status,
            "providers": provider_records,
            "candidate_keys": candidate_keys,
            "selected_candidate_keys": selected_keys,
            "retrieval_cost_status": "unknown",
        }
    )
