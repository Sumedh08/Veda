"""Deterministic lexical ranking for bibliographic retrieval, not evidence quality."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.schemas import CandidateRelevanceV1, PlannedQueryAlignmentV1

_TOKEN = re.compile(r"[a-z0-9]+(?:['’][a-z0-9]+)?")
_STOPWORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has have how if "
    "in into is it its may might more most of on or our should than that the their them then "
    "there these they this those through to under using was were what when where which while "
    "who why will with would evidence study studies research effect effects impact impacts "
    "whether show shows shown based assess evaluate evaluation result results".split()
)
_TOPIC_CONTEXT_TERMS = frozenset(
    "across all assigned eligible case company companies employee employees firm firms "
    "geography month months person people quarter quarters rollout startup team teams "
    "time processing twelve week weeks year years us usa united states canada english hypothetical "
    "india indian city cities health exposure "
    "current existing prior workflow process without versus compared compare improve "
    "improves increase increased increasing reduce reduced reducing effect effects impact "
    "outcome outcomes evidence decision assess evaluate estimate determine whether results "
    "study studies research question consider considering does do inform informs per monthly annual".split()
)
_STUDY_DESIGN_TERMS = frozenset(
    "empirical experiment experiments field randomized randomised controlled trial trials "
    "quasi experimental qualitative quantitative observational longitudinal cross sectional".split()
)
_CONTAMINATED_TITLE_PATTERNS = (
    re.compile(r"\bdoi\s+10\.\d{4,9}/", re.IGNORECASE),
    re.compile(r"\bpdf\s*(?::|\d)\s*\d", re.IGNORECASE),
    re.compile(r"\b(?:issn|quick\s+menu|table\s+of\s+contents)\b", re.IGNORECASE),
)
_REPOSITORY_DESCRIPTION_PREFIX = re.compile(
    r"^(?:this|the)\s+(?:(?:code|data|research)\s+)?repository\s+(?:contains|includes|provides)\b",
    re.IGNORECASE,
)
_REPOSITORY_ARTIFACT_CUES = (
    re.compile(r"\bjupyter\s+notebooks?\b", re.IGNORECASE),
    re.compile(r"\braw\b.{0,40}\bdata\b", re.IGNORECASE),
    re.compile(r"\bsurvey\s+(?:tool|instrument)\b", re.IGNORECASE),
    re.compile(r"\bsource\s+code\b", re.IGNORECASE),
    re.compile(r"\breproduction\s+(?:package|materials)\b", re.IGNORECASE),
)
_INTERVENTION_TERMS = frozenset(
    "ai artificial intelligence generative genai llm llms gpt chatgpt copilot assistant "
    "automation automated machine learning algorithm algorithms".split()
)
_INTERVENTION_EQUIVALENTS = (
    frozenset(
        {"ai", "artificial", "intelligence", "generative", "genai", "llm", "llms", "gpt", "chatgpt"}
    ),
    frozenset({"copilot", "assistant"}),
    frozenset({"automation", "automated", "algorithm", "algorithms", "machine", "learning"}),
)


def _terms(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in _TOKEN.findall(value.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _query_terms(value: str) -> tuple[set[str], bool]:
    selected: list[str] = []
    seen: set[str] = set()
    truncated = False
    for token in _TOKEN.findall(value.casefold()):
        if len(token) <= 1 or token in _STOPWORDS or token in seen:
            continue
        if len(selected) == 120:
            truncated = True
            break
        selected.append(token)
        seen.add(token)
    return set(selected), truncated


def matched_query_terms(query: str, context: str | None) -> list[str]:
    """Return exact lexical query terms present in a bounded discovery context."""
    terms, _ = _query_terms(query)
    return sorted(terms & _terms(context))


def _lexical_features(query: str, title: str, abstract_excerpt: str | None) -> dict[str, Any]:
    query_terms, query_terms_truncated = _query_terms(query)
    title_matches = sorted(query_terms & _terms(title))
    abstract_matches = sorted(query_terms & _terms(abstract_excerpt))
    denominator = len(query_terms)
    title_coverage = len(title_matches) / denominator if denominator else 0.0
    abstract_coverage = len(abstract_matches) / denominator if denominator else 0.0
    score = 0.7 * title_coverage + 0.3 * abstract_coverage
    return {
        "schema_version": 1,
        "algorithm": "lexical_overlap_v1",
        "score": round(score, 6),
        "score_scale": "0_to_1",
        "query_term_count": denominator,
        "query_terms": sorted(query_terms),
        "query_terms_truncated": query_terms_truncated,
        "matched_title_terms": title_matches,
        "matched_abstract_terms": abstract_matches,
        "title_coverage": round(title_coverage, 6),
        "abstract_coverage": round(abstract_coverage, 6),
        "weights": {"title_coverage": 0.7, "abstract_coverage": 0.3},
        "explanation": (
            f"Matched {len(title_matches)} of {denominator} query terms in the title and "
            f"{len(abstract_matches)} in the abstract excerpt."
            if denominator
            else "No indexable query terms; score is zero."
        ),
    }


def score_candidate_relevance(
    research_question: str,
    title: str,
    abstract_excerpt: str | None,
    *,
    planned_query: str | None = None,
) -> dict[str, Any]:
    """Return reproducible lexical features, never an evidence-quality judgment.

    The original-question score remains the displayed relevance score and eligibility
    checks still use the original question. When a recorded provider query is supplied,
    its independent overlap features may improve source-cap ordering only.
    """
    relevance = {
        **_lexical_features(research_question, title, abstract_excerpt),
        "ranking_query_basis": "user_research_question",
        "interpretation_limit": (
            "Retrieval relevance only; not source quality, study validity, claim support, or truth."
        ),
    }
    if planned_query is not None:
        alignment = {
            **_lexical_features(planned_query, title, abstract_excerpt),
            "ranking_query_basis": "recorded_provider_query",
            "interpretation_limit": (
                "Retrieval relevance only; not source quality, study validity, claim support, or truth."
            ),
        }
        alignment = PlannedQueryAlignmentV1.model_validate(alignment).model_dump(mode="json")
        question_score = relevance["score"]
        planned_score = alignment["score"]
        relevance["planned_query_alignment"] = alignment
        relevance["selection_score"] = max(question_score, planned_score)
        relevance["selection_basis"] = (
            "tie"
            if question_score == planned_score
            else "user_question"
            if question_score > planned_score
            else "recorded_provider_query"
        )
    return CandidateRelevanceV1.model_validate(relevance).model_dump(mode="json")


def topic_overlap_basis(
    research_question: str,
    title: str,
    abstract_excerpt: str | None,
    *,
    planned_query: str | None = None,
    discovery_context: str | None = None,
) -> str | None:
    """Return the auditable reason a candidate passes the lexical topic gate.

    This conservative gate is a retrieval filter, not a semantic relevance or evidence-quality
    judgment. A recorded query can recover a domain term omitted from a concise user question,
    but only when the title also matches the question's intervention family. Study-design words
    alone can never supply the missing topic match. Candidates it rejects remain inspectable.
    """
    query_terms, _ = _query_terms(research_question)
    query_terms = {
        term
        for term in query_terms
        if not any(character.isdigit() for character in term) and term not in _TOPIC_CONTEXT_TERMS
    }
    title_terms = {
        term
        for term in _terms(unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode())
        if term not in _TOPIC_CONTEXT_TERMS
    }
    abstract_terms = {
        term
        for term in _terms(
            unicodedata.normalize("NFKD", abstract_excerpt or "").encode("ascii", "ignore").decode()
        )
        if term not in _TOPIC_CONTEXT_TERMS
    }
    discovery_terms = {
        term
        for term in _terms(
            unicodedata.normalize("NFKD", discovery_context or "")
            .encode("ascii", "ignore")
            .decode()
        )
        if term not in _TOPIC_CONTEXT_TERMS
    }
    candidate_terms = title_terms | abstract_terms | discovery_terms
    query_interventions = query_terms & _INTERVENTION_TERMS
    if query_interventions:
        query_intervention_groups = [
            group for group in _INTERVENTION_EQUIVALENTS if query_terms & group
        ]
        if not any(candidate_terms & group for group in query_intervention_groups):
            return None
    topic_query_terms = query_terms - _INTERVENTION_TERMS
    topic_matches = topic_query_terms & candidate_terms
    direct_title_matches = topic_query_terms & title_terms
    required_matches = min(2, len(topic_query_terms))
    if query_interventions and direct_title_matches:
        # A specific title term plus a matched AI intervention can recover adjacent
        # terminology such as “generative AI search tools” for a retrieval question.
        required_matches = 1
    if len(topic_matches) < required_matches:
        direct_match = False
    else:
        direct_match = bool(direct_title_matches) or len(topic_query_terms & abstract_terms) >= 3
    if direct_match:
        return "original_question"

    if not planned_query:
        return None

    planned_terms, _ = _query_terms(planned_query)
    planned_domain_terms = planned_terms - query_terms - _TOPIC_CONTEXT_TERMS - _STUDY_DESIGN_TERMS
    planned_domain_terms -= _INTERVENTION_TERMS
    if not planned_domain_terms:
        return None

    title_domain_terms = title_terms - _STUDY_DESIGN_TERMS - _INTERVENTION_TERMS
    if not query_interventions:
        return None
    if not any(candidate_terms & group for group in query_intervention_groups):
        return None
    if planned_domain_terms & title_domain_terms:
        return "recorded_query_domain_expansion"
    return None


def passes_topic_overlap_gate(
    research_question: str,
    title: str,
    abstract_excerpt: str | None,
    *,
    planned_query: str | None = None,
) -> bool:
    """Require question-aligned topic overlap before selecting scholarly metadata."""
    return (
        topic_overlap_basis(
            research_question,
            title,
            abstract_excerpt,
            planned_query=planned_query,
        )
        is not None
    )


def has_clean_bibliographic_title(title: str) -> bool:
    """Reject provider title fields that visibly contain issue-page metadata."""
    if not isinstance(title, str) or not title.strip():
        return False
    return not any(pattern.search(title) for pattern in _CONTAMINATED_TITLE_PATTERNS)


def is_repository_artifact_description(abstract_excerpt: str | None) -> bool:
    """Detect an explicit repository/readme description mislabelled as an abstract.

    This is a narrow text-type integrity guard, not a study-quality classifier. It only
    matches excerpts that begin with a repository inventory statement and name at least
    two concrete artifacts.
    """
    normalized = " ".join((abstract_excerpt or "").split())
    if not normalized or not _REPOSITORY_DESCRIPTION_PREFIX.match(normalized):
        return False
    return sum(bool(pattern.search(normalized)) for pattern in _REPOSITORY_ARTIFACT_CUES) >= 2
