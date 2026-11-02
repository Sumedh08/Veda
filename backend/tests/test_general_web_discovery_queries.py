import pytest

from app.research.search_queries import (
    build_general_web_discovery_queries,
    build_verified_domain_publication_query,
    rank_general_web_domain_candidates,
)


def test_general_web_queries_find_research_and_organizations_without_named_publishers():
    question = "What are the economic, regulatory, and transmission challenges affecting offshore wind development in India?"

    queries = build_general_web_discovery_queries(question, geography="India")

    assert queries == [
        "economic regulatory transmission challenges affecting offshore wind development india research institutes publications",
        "economic regulatory transmission challenges affecting offshore wind development india research report",
    ]
    assert len(queries) <= 3
    assert all(len(query) <= 512 for query in queries)
    assert not any(
        name in " ".join(queries).casefold() for name in ["mit", "stanford", "world bank"]
    )


def test_general_web_queries_are_deduplicated_and_bounded_for_short_questions():
    queries = build_general_web_discovery_queries("Solar power?", geography=None)

    assert len(queries) == len(set(queries))
    assert len(queries) <= 3
    assert all(query and len(query) <= 512 for query in queries)


def test_verified_domain_publication_query_is_topic_scoped_and_domain_bound():
    query = build_verified_domain_publication_query(
        "research.example.org.", "How does tidal energy affect grid reliability?"
    )

    assert query.startswith("site:research.example.org ")
    assert "tidal energy" in query
    assert len(query) <= 512
    for invalid_domain in ("https://example.org", "example.org/path", "localhost", "example..org"):
        with pytest.raises(ValueError):
            build_verified_domain_publication_query(invalid_domain, "tidal energy")


def test_domain_candidates_include_relevant_publications_without_generic_research_words():
    hits = [
        {
            "title": "The Toll of Extreme Heat on India's Laborers",
            "url": "https://thinkglobalhealth.org/article/toll-extreme-heat-indias-laborers",
            "domain": "thinkglobalhealth.org",
            "snippet": "Extreme heat affects outdoor laborers and health.",
            "rank": 1,
        },
        {
            "title": "Evaluating extreme heat risk among informal sector workers",
            "url": "https://preparecenter.org/uploads/2022/12/heat-risk.pdf",
            "domain": "preparecenter.org",
            "snippet": "A study of street vendors and outdoor workers in India.",
            "rank": 2,
        },
        {
            "title": "How Extreme Heat is Impacting India",
            "url": "https://ceew.in/sites/default/files/heat-and-work.pdf",
            "domain": "ceew.in",
            "snippet": "Working on a Warmer Planet: heat stress and labour productivity.",
            "rank": 3,
        },
        {
            "title": "Occupational Heat Stress Profiles in Selected Indian Industries",
            "url": "https://researchgate.net/publication/12345",
            "domain": "researchgate.net",
            "snippet": "Study results report health and productivity impacts.",
            "rank": 4,
        },
        {
            "title": "Indian tourism outlook research report",
            "url": "https://unrelated.example/research/report",
            "domain": "unrelated.example",
            "snippet": "Tourism market forecasts.",
            "rank": 5,
        },
    ]

    selected = rank_general_web_domain_candidates(
        hits,
        "How do Indian cities reduce extreme-heat exposure and what evidence shows effects on health and outdoor-worker productivity?",
        limit=4,
    )

    domains = [
        item.domain for item in selected if item.status == "eligible_for_identity_verification"
    ]
    routed_by_domain = {item.domain: item for item in selected}
    assert "thinkglobalhealth.org" in domains
    assert "preparecenter.org" in domains
    assert "ceew.in" in domains
    assert routed_by_domain["researchgate.net"].status == "excluded_aggregator_or_search_host"
    assert routed_by_domain["unrelated.example"].status == "excluded_low_topic_overlap"
    assert [item.relevance_score for item in selected] == sorted(
        (item.relevance_score for item in selected), reverse=True
    )


def test_dated_news_coverage_does_not_consume_non_ror_research_identity_budget():
    hits = [
        {
            "title": "'When I get home, my whole body aches': extreme heat and Indian workers",
            "url": "https://news.example/environment/2026/jul/20/extreme-heat-india-workers",
            "domain": "news.example",
            "snippet": "An article discusses research estimates about heat and worker productivity.",
            "rank": 1,
        },
        {
            "title": "Evaluating extreme heat risk among informal-sector workers",
            "url": "https://specialist.example/uploads/2024/heat-risk-assessment.pdf",
            "domain": "specialist.example",
            "snippet": "A study measures heat risk for outdoor workers in Indian cities.",
            "rank": 2,
        },
        {
            "title": "How Extreme Heat is Impacting India",
            "url": "https://research.example/sites/default/files/heat-and-work.pdf",
            "domain": "research.example",
            "snippet": "Institutional research on heat stress and labour productivity.",
            "rank": 3,
        },
    ]

    routed = rank_general_web_domain_candidates(
        hits,
        "How do Indian cities reduce extreme-heat exposure, and what evidence shows effects on health and outdoor-worker productivity?",
        limit=3,
    )
    by_domain = {candidate.domain: candidate for candidate in routed}
    eligible_domains = [
        candidate.domain
        for candidate in routed
        if candidate.status == "eligible_for_identity_verification"
    ]

    assert by_domain["news.example"].status == "excluded_editorial_content_lead"
    assert eligible_domains[:2] == ["specialist.example", "research.example"]
