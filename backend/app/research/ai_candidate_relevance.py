"""Bounded model-assisted relevance review over deterministic discovery records.

This module handles bibliographic relevance only. It never verifies publishers, grants
rights, appraises methods, or creates/changes publication locations.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, is_dataclass
from typing import Any

from app.research.llm_tasks import CandidateRelevanceReviewV1

MAX_REVIEW_CANDIDATES = 12
MODEL_PROMOTION_CLASS = "directly_relevant"


def _record_mapping(record: object) -> dict[str, Any] | None:
    if isinstance(record, dict):
        return record
    if is_dataclass(record) and not isinstance(record, type):
        return asdict(record)
    model_dump = getattr(record, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="python")
        return value if isinstance(value, dict) else None
    return None


def candidate_review_payload(
    question: str,
    occurrences: list[dict[str, Any]],
    *,
    maximum_candidates: int = MAX_REVIEW_CANDIDATES,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a bounded metadata-only pool that includes lexical misses.

    The payload deliberately excludes abstracts, author names, URLs, DOIs, provider
    record IDs, and stored search text. A deterministic half-pool is reserved for
    candidates that missed the lexical topic gate; the remaining slots favor the
    original lexical ordering. Duplicate works and records with hard selection blocks
    are not sent to a model.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("candidate review question is invalid or exceeds its boundary")
    if type(maximum_candidates) is not int or not 1 <= maximum_candidates <= MAX_REVIEW_CANDIDATES:
        raise ValueError("candidate review size must be between one and twelve")

    unique: dict[str, dict[str, Any]] = {}
    for item in occurrences:
        record = _record_mapping(item.get("record"))
        key = item.get("candidate_key")
        canonical_identity = item.get("canonical_identity")
        provider_metadata = record.get("provider_metadata") if record else None
        provider_metadata = provider_metadata if isinstance(provider_metadata, dict) else {}
        if (
            record is None
            or not isinstance(key, str)
            or re.fullmatch(r"[0-9a-f]{64}", key) is None
            or record.get("source_type") == "official_statistics"
            or not isinstance(canonical_identity, str)
            or canonical_identity in unique
            or provider_metadata.get("selection_block_reason")
            or not isinstance(record.get("title"), str)
            or not record["title"].strip()
        ):
            continue
        unique[canonical_identity] = item

    def baseline_key(item: dict[str, Any]) -> tuple[float, int, str]:
        relevance = item.get("relevance")
        score = (
            relevance.get("selection_score", relevance.get("score", 0.0))
            if isinstance(relevance, dict)
            else 0.0
        )
        if type(score) not in {float, int} or not math.isfinite(score):
            score = 0.0
        score = max(0.0, min(1.0, float(score)))
        original_index = item.get("original_index")
        if type(original_index) is not int:
            original_index = 0
        return (-score, original_index, str(item.get("candidate_key", "")))

    candidates = list(unique.values())
    lexical_pool = sorted(
        (item for item in candidates if item.get("topic_eligibility_basis") != "not_eligible"),
        key=baseline_key,
    )
    missed_pool = sorted(
        (item for item in candidates if item.get("topic_eligibility_basis") == "not_eligible"),
        key=lambda item: (
            item.get("original_index", 0) if type(item.get("original_index")) is int else 0,
            str(item.get("candidate_key", "")),
        ),
    )
    lexical_slots = (maximum_candidates + 1) // 2
    selected: list[dict[str, Any]] = [
        *lexical_pool[:lexical_slots],
        *missed_pool[: maximum_candidates - lexical_slots],
    ]
    selected_keys = {item["candidate_key"] for item in selected}
    for item in sorted(candidates, key=baseline_key):
        if len(selected) >= maximum_candidates:
            break
        if item["candidate_key"] not in selected_keys:
            selected.append(item)
            selected_keys.add(item["candidate_key"])

    reviewed: list[dict[str, Any]] = []
    payload_candidates: list[dict[str, Any]] = []
    for item in selected:
        record = _record_mapping(item["record"])
        if record is None:
            continue
        relevance = item.get("relevance")
        relevance = relevance if isinstance(relevance, dict) else {}
        score = relevance.get("score", 0.0) if isinstance(relevance, dict) else 0.0
        if type(score) not in {int, float} or not math.isfinite(score):
            score = 0.0
        payload_candidates.append(
            {
                "candidate_key": item["candidate_key"],
                "title": record["title"][:500],
                "publisher": record.get("publisher")[:160]
                if isinstance(record.get("publisher"), str)
                else None,
                "published_year": record.get("published_year"),
                "source_type": record.get("source_type"),
                "provider": record.get("provider"),
                "lexical_question_score": round(max(0.0, min(1.0, float(score))), 4),
                "lexical_topic_gate": "pass"
                if item.get("topic_eligibility_basis") != "not_eligible"
                else "miss",
            }
        )
        reviewed.append(item)
    return {"question": question.strip(), "candidates": payload_candidates}, reviewed


def attach_candidate_relevance_review(
    reviewed: list[dict[str, Any]],
    result: CandidateRelevanceReviewV1,
    *,
    provider: str,
    model: str,
) -> None:
    """Validate exact candidate coverage and attach provider-attributed assessments."""
    expected = [item.get("candidate_key") for item in reviewed]
    returned = [item.candidate_key for item in result.assessments]
    if (
        len(expected) != len(set(expected))
        or len(returned) != len(set(returned))
        or set(expected) != set(returned)
        or len(expected) != len(returned)
    ):
        raise ValueError("candidate relevance review must assess each submitted key exactly once")
    if provider not in {"openrouter", "openai", "sarvam"}:
        raise ValueError("candidate relevance review provider is unsupported")
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise ValueError("candidate relevance review model is invalid")

    by_key = {assessment.candidate_key: assessment for assessment in result.assessments}
    from app.schemas import CandidateAIRelevanceV1

    for occurrence in reviewed:
        relevance = occurrence.get("relevance")
        if not isinstance(relevance, dict):
            raise ValueError("candidate relevance review cannot replace missing lexical features")
        assessment = by_key[occurrence["candidate_key"]]
        relevance["ai_assessment"] = CandidateAIRelevanceV1(
            assessment=assessment.assessment,
            reason=assessment.reason,
            provider=provider,
            model=model,
        ).model_dump(mode="python")


def is_ai_direct_relevance(occurrence: dict[str, Any]) -> bool:
    """Only a direct assessment can recover a lexical miss; hard source blocks persist."""
    record = _record_mapping(occurrence.get("record"))
    if record is None:
        return False
    metadata = record.get("provider_metadata")
    if isinstance(metadata, dict) and metadata.get("selection_block_reason"):
        return False
    relevance = occurrence.get("relevance")
    assessment = relevance.get("ai_assessment") if isinstance(relevance, dict) else None
    return isinstance(assessment, dict) and assessment.get("assessment") == MODEL_PROMOTION_CLASS
