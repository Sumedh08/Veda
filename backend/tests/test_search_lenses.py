from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.research.search_lenses import build_search_lens_execution

STARTED = datetime(2026, 10, 31, tzinfo=UTC)
COMPLETED = datetime(2026, 10, 31, 0, 0, 1, tzinfo=UTC)


def _rationale(focus="counterevidence"):
    return {
        "query": "developer productivity null results",
        "purpose": "Search for null or contrary measured outcomes.",
        "focus": focus,
    }


def _provider(provider, status="completed", results=1, error_code=None):
    return {
        "provider": provider,
        "status": status,
        "results": results,
        "error_code": error_code,
        "elapsed_ms": 20,
    }


def test_lens_keeps_exact_query_provider_outcomes_and_candidate_selection():
    candidates = [
        {
            "candidate_key": "a" * 64,
            "canonical_identity": "doi:10.5555/example",
            "record": SimpleNamespace(query="developer productivity null results"),
            "disposition": "selected",
        },
        {
            "candidate_key": "b" * 64,
            "canonical_identity": "doi:10.5555/excluded",
            "record": SimpleNamespace(query="unrelated query"),
            "disposition": "excluded",
        },
    ]

    result = build_search_lens_execution(
        index=3,
        rationale=_rationale(),
        provider_outcomes=[_provider("Crossref"), _provider("OpenAlex")],
        candidates=candidates,
        started_at=STARTED,
        completed_at=COMPLETED,
    )

    assert result.lens_id == "L4"
    assert result.category == "CONTRARY_OR_NULL_EVIDENCE"
    assert result.exact_query == _rationale()["query"]
    assert result.status == "completed"
    assert result.candidate_keys == ["a" * 64]
    assert result.selected_candidate_keys == ["a" * 64]
    assert result.retrieval_cost_status == "unknown"


def test_partial_and_failed_search_lenses_are_not_reported_as_complete():
    partial = build_search_lens_execution(
        index=0,
        rationale=_rationale("direct_evidence"),
        provider_outcomes=[
            _provider("Crossref"),
            _provider("OpenAlex", status="failed", results=0, error_code="provider_query_failed"),
        ],
        candidates=[],
        started_at=STARTED,
        completed_at=COMPLETED,
    )
    failed = build_search_lens_execution(
        index=1,
        rationale=_rationale("direct_evidence"),
        provider_outcomes=[
            _provider("Crossref", status="failed", results=0, error_code="provider_query_failed"),
            _provider("OpenAlex", status="failed", results=0, error_code="provider_query_failed"),
        ],
        candidates=[],
        started_at=STARTED,
        completed_at=COMPLETED,
    )

    assert partial.status == "partial"
    assert failed.status == "failed"


def test_unattempted_lens_is_explicit_and_unrecognized_focus_fails_closed():
    unattempted = build_search_lens_execution(
        index=0,
        rationale=_rationale(),
        provider_outcomes=[
            _provider("Crossref", status="not_attempted", results=0),
            _provider("OpenAlex", status="not_attempted", results=0),
        ],
        candidates=[],
        started_at=STARTED,
        completed_at=None,
    )
    assert unattempted.status == "not_attempted"
    assert unattempted.pagination_state == "not_attempted"

    with pytest.raises(ValueError, match="no supported search-lens category"):
        build_search_lens_execution(
            index=0,
            rationale=_rationale("new_unreviewed_focus"),
            provider_outcomes=[],
            candidates=[],
            started_at=STARTED,
            completed_at=None,
        )
