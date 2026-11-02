import pytest

from app.research.search_queries import (
    compact_bibliographic_query,
    institutional_catalog_query,
    openaire_organization_discovery_query,
)


def test_query_keeps_topic_and_measure_terms_but_drops_case_counts_and_grammar():
    query = compact_bibliographic_query(
        [
            "For a 200-employee US startup, does AI-assisted résumé screening reduce recruiter "
            "time-to-shortlist without worsening selection quality or adverse impact?",
            "Applicants and job-related selection quality",
        ]
    )

    assert "ai" in query.split()
    assert "resume" in query.split()
    assert "screening" in query.split()
    assert "recruiter" in query.split()
    assert "selection" in query.split()
    assert "quality" in query.split()
    assert "200" not in query.split()
    assert "employee" not in query.split()
    assert "without" not in query.split()
    assert "résumé" not in query


def test_query_deduplicates_and_adds_scope_terms_after_question_terms():
    query = compact_bibliographic_query(
        ["AI adoption worker productivity", "India small firms 2022 2026 worker outcomes"]
    )
    tokens = query.split()

    assert tokens[:4] == ["ai", "adoption", "worker", "productivity"]
    assert "india" in tokens
    assert "small" in tokens
    assert "firms" in tokens
    assert "2022" in tokens
    assert "2026" in tokens
    assert tokens.count("worker") == 1


def test_query_caps_terms_characters_and_rejects_invalid_bounds():
    query = compact_bibliographic_query(
        [" ".join(f"{chr(97 + index // 26)}{chr(97 + index % 26)}topic" for index in range(100))],
        max_terms=10,
        max_chars=70,
    )

    assert len(query.split()) <= 10
    assert len(query) <= 70
    with pytest.raises(ValueError):
        compact_bibliographic_query(["AI research"], max_terms=33)
    with pytest.raises(ValueError):
        compact_bibliographic_query(["AI research"], max_chars=301)


def test_generic_question_gets_a_safe_bounded_search_anchor():
    assert compact_bibliographic_query(["What is the effect of the study?"]) == (
        "What is the effect of the study?"
    )


def test_institutional_catalog_query_uses_a_short_topic_anchor_and_stays_bounded():
    query = institutional_catalog_query(
        "How do artificial intelligence investment trends in emerging economies affect "
        "productivity and business adoption?",
        ["The research will inform a long decision narrative", "India"],
    )

    assert query == "artificial intelligence investment trends emerging"
    assert len(query.split()) == 5
    assert "decision" not in query
    assert "india" not in query


def test_openaire_organization_discovery_query_uses_topic_and_research_terms():
    query = openaire_organization_discovery_query(
        "How should UK offshore wind expansion address subsea cable reliability and "
        "grid-connection delays while balancing investment costs and reliable electricity delivery?"
    )

    assert query == '"offshore" AND "wind" AND "research"'
    assert "uk" not in query.casefold()
    assert len(query) <= 300
    assert query.count('"') == 6
    assert query.count(" AND ") <= 2


def test_openaire_organization_discovery_query_has_a_bounded_short_query_fallback():
    assert openaire_organization_discovery_query("AI adoption") == (
        '"ai" AND "adoption" AND "research"'
    )
