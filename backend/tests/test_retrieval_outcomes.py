from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Source
from app.research import workflow
from app.research.retrieval_outcomes import (
    record_attempt_outcome,
    record_status_outcome,
    retrieval_metadata_for_api,
)
from app.schemas import RetrievalAttemptOutcomeV1


@pytest.mark.parametrize(
    ("status", "truncated", "expected"),
    [
        ("not_attempted", False, "not_attempted"),
        ("retrieved", False, "retrieved"),
        ("retrieved", True, "partial"),
        ("unsupported", False, "unavailable"),
        ("failed", False, "error"),
        ("deferred", False, "deferred"),
    ],
)
def test_status_mapping_has_a_strict_versioned_contract(status, truncated, expected):
    retrieval = {}
    record_status_outcome(
        retrieval,
        format="html",
        status=status,
        observed_at=datetime(2026, 10, 29, tzinfo=UTC),
        error_code="timeout" if status == "failed" else None,
        retry_after_seconds=17 if status == "deferred" else None,
        truncated=truncated,
    )

    row = retrieval["outcomes"]["by_format"]["html"]
    assert row["schema_version"] == 1
    assert row["format"] == "html"
    assert row["outcome"] == expected
    parsed = RetrievalAttemptOutcomeV1.model_validate(row)
    assert parsed.observed_at == datetime(2026, 10, 29, tzinfo=UTC)


def test_outcome_contract_rejects_raw_error_details_and_invalid_retry_bounds():
    with pytest.raises(ValidationError):
        RetrievalAttemptOutcomeV1(
            format="pdf",
            outcome="error",
            error_code="socket failure: C:/Users/private/token.txt",
        )
    with pytest.raises(ValidationError):
        RetrievalAttemptOutcomeV1(format="pdf", outcome="deferred", retry_after_seconds=86_401)


def test_legacy_api_normalization_preserves_access_class_and_drops_unsafe_error_text():
    secret_detail = "socket failure at C:/Users/private/token.txt"
    retrieval = retrieval_metadata_for_api(
        {
            "status": "failed",
            "error_code": secret_detail,
            "retry_after_seconds": 999_999,
            "pdf": {"status": "failed", "error_code": secret_detail},
            "retrieved_at": "2026-10-29T12:00:00Z",
        },
        "abstract_only",
    )

    assert retrieval["outcomes"]["schema_version"] == 1
    assert retrieval["outcomes"]["by_format"]["html"]["outcome"] == "error"
    assert "error_code" not in retrieval["outcomes"]["by_format"]["html"]
    assert "retry_after_seconds" not in retrieval
    assert "error_code" not in retrieval["pdf"]
    assert secret_detail not in str(retrieval)


def test_source_access_summary_counts_attempt_outcomes_separately(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Outcome summary", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Summarize retrieval attempt states",
            "idempotency_key": "outcome-summary",
        },
    ).json()
    sources = []
    for index, outcome in enumerate(
        ["not_attempted", "retrieved", "partial", "unavailable", "error", "deferred"]
    ):
        retrieval = {}
        record_attempt_outcome(
            retrieval,
            format="html",
            outcome=outcome,
            error_code="timeout" if outcome == "error" else None,
            retry_after_seconds=13 if outcome == "deferred" else None,
        )
        sources.append(
            Source(
                job_id=job["id"],
                external_id=f"outcome:{index}",
                title=f"Record {index}",
                retrieval_status="metadata_only",
                metadata_json={"retrieval": retrieval},
            )
        )

    with client.db_sessions() as db:
        db.add_all(sources)
        db.commit()
        summary = workflow._source_access_summary(db, job["id"], sources)

    assert "6 metadata-only" in summary
    assert (
        "retrieval attempts: 1 retrieved, 1 partial, 1 unavailable, 1 errors, "
        "1 deferred; 1 format(s) not attempted"
    ) in summary
