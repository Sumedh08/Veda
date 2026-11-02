from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.research.ai_candidate_relevance import (
    attach_candidate_relevance_review,
    candidate_review_payload,
    is_ai_direct_relevance,
)
from app.research.llm_tasks import CandidateRelevanceReviewV1


def _occurrence(key: str, title: str, *, eligible: bool, abstract: str = "private abstract"):
    return {
        "candidate_key": key * 64,
        "canonical_identity": f"work:{key}",
        "record": {
            "title": title,
            "publisher": "Example Publisher",
            "published_year": 2025,
            "source_type": "scholarly_article",
            "provider": "Crossref",
            "external_id": f"record:{key}",
            "url": f"https://example.test/{key}",
            "doi": f"10.5555/{key}",
            "abstract_excerpt": abstract,
            "authors": [{"given": "Private", "family": "Author"}],
        },
        "relevance": {
            "score": 0.6 if eligible else 0.0,
            "selection_score": 0.6 if eligible else 0.0,
        },
        "topic_eligibility_basis": "original_question" if eligible else "not_eligible",
        "selection_context": None,
        "original_index": ord(key) - ord("a"),
    }


def test_review_payload_is_metadata_only_bounded_and_includes_lexical_misses():
    rows = [_occurrence(key, "Direct lexical match", eligible=True) for key in "12345678"] + [
        _occurrence("a", "Different terminology about the same outcome", eligible=False)
    ]

    payload, reviewed = candidate_review_payload(
        "What evidence links care continuity to hospitalization?", rows, maximum_candidates=8
    )

    assert len(reviewed) == 8
    assert "a" * 64 in {row["candidate_key"] for row in payload["candidates"]}
    serialized = str(payload)
    assert "private abstract" not in serialized
    assert "example.test" not in serialized
    assert "10.5555" not in serialized
    assert "Private" not in serialized
    assert payload["question"] == "What evidence links care continuity to hospitalization?"


def test_ai_direct_relevance_can_recover_a_lexical_miss_without_changing_other_gates():
    rows = [_occurrence("a", "Continuity and avoidable admissions", eligible=False)]
    review = CandidateRelevanceReviewV1.model_validate(
        {
            "schema_version": 1,
            "assessments": [
                {
                    "candidate_key": "a" * 64,
                    "assessment": "directly_relevant",
                    "reason": "The title describes the requested relationship using different wording.",
                }
            ],
        }
    )

    attach_candidate_relevance_review(rows, review, provider="openrouter", model="test-model")

    assert is_ai_direct_relevance(rows[0]) is True
    assert rows[0]["topic_eligibility_basis"] == "not_eligible"
    assert rows[0]["relevance"]["ai_assessment"]["provider"] == "openrouter"

    blocked = deepcopy(rows[0])
    blocked["record"]["provider_metadata"] = {"selection_block_reason": "license_not_verified"}
    assert is_ai_direct_relevance(blocked) is False


@pytest.mark.parametrize(
    "assessments",
    [
        [],
        [
            {
                "candidate_key": "a" * 64,
                "assessment": "directly_relevant",
                "reason": "ok",
            },
            {
                "candidate_key": "a" * 64,
                "assessment": "unrelated",
                "reason": "duplicate key",
            },
        ],
        [
            {
                "candidate_key": "f" * 64,
                "assessment": "directly_relevant",
                "reason": "unknown key",
            }
        ],
    ],
)
def test_review_requires_exactly_one_assessment_for_every_reviewed_candidate(assessments):
    rows = [_occurrence("a", "One candidate", eligible=False)]
    review = CandidateRelevanceReviewV1.model_validate(
        {"schema_version": 1, "assessments": assessments}
    )

    with pytest.raises(ValueError, match="exactly once"):
        attach_candidate_relevance_review(rows, review, provider="openrouter", model="test-model")


def test_review_schema_rejects_untrusted_fields_and_unbounded_rationale():
    with pytest.raises(ValidationError):
        CandidateRelevanceReviewV1.model_validate(
            {
                "schema_version": 1,
                "assessments": [
                    {
                        "candidate_key": "a" * 64,
                        "assessment": "directly_relevant",
                        "reason": "ok",
                        "url": "https://attacker.invalid",
                    }
                ],
            }
        )


def test_review_payload_tolerates_legacy_optional_metadata_and_nonfinite_scores():
    item = _occurrence("a", "A bounded candidate title", eligible=True)
    item["record"]["provider_metadata"] = None
    item["relevance"] = {"score": float("nan"), "selection_score": float("inf")}

    payload, reviewed = candidate_review_payload("A question about research", [item])

    assert reviewed == [item]
    assert payload["candidates"][0]["lexical_question_score"] == 0.0
