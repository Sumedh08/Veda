from app.research.candidate_relevance import (
    has_clean_bibliographic_title,
    is_repository_artifact_description,
    passes_topic_overlap_gate,
    score_candidate_relevance,
    topic_overlap_basis,
)


def test_rank_is_versioned_explainable_and_weighted_toward_title_overlap():
    relevance = score_candidate_relevance(
        "Does AI adoption improve worker productivity?",
        "AI adoption and worker productivity",
        "This experiment reports task completion outcomes.",
    )

    assert relevance["algorithm"] == "lexical_overlap_v1"
    assert relevance["schema_version"] == 1
    assert relevance["ranking_query_basis"] == "user_research_question"
    assert relevance["query_terms_truncated"] is False
    assert relevance["matched_title_terms"] == ["adoption", "ai", "productivity", "worker"]
    assert relevance["matched_abstract_terms"] == []
    assert relevance["score"] == 0.56
    assert relevance["weights"] == {"title_coverage": 0.7, "abstract_coverage": 0.3}
    assert "retrieval relevance only" in relevance["interpretation_limit"].casefold()


def test_abstract_overlap_breaks_a_title_tie_without_using_popularity_metadata():
    query = "AI adoption worker productivity"
    high_overlap = score_candidate_relevance(
        query,
        "AI adoption in firms",
        "AI adoption changed worker productivity and output per worker.",
    )
    low_overlap = score_candidate_relevance(query, "AI adoption in firms", None)

    assert high_overlap["score"] > low_overlap["score"]
    assert high_overlap["matched_abstract_terms"] == ["adoption", "ai", "productivity", "worker"]
    assert "citation" not in str(high_overlap).casefold()
    assert "venue" not in str(high_overlap).casefold()


def test_adversarial_prestige_language_cannot_create_query_relevance():
    irrelevant = score_candidate_relevance(
        "AI worker productivity",
        "Highly cited prestigious award-winning landmark study",
        "A leading journal published this influential paper.",
    )
    relevant = score_candidate_relevance(
        "AI worker productivity",
        "AI and worker productivity outcomes",
        "",
    )

    assert irrelevant["score"] == 0
    assert irrelevant["matched_title_terms"] == []
    assert relevant["score"] > irrelevant["score"]


def test_ranking_is_repeatable_and_uses_only_bounded_text_fields():
    arguments = (
        "worker productivity software adoption",
        "Software adoption and worker output",
        "Workers completed tasks more quickly after software adoption.",
    )

    assert score_candidate_relevance(*arguments) == score_candidate_relevance(*arguments)


def test_empty_or_generic_query_terms_fail_closed_to_zero():
    relevance = score_candidate_relevance("the effect of the study", "A Study", None)

    assert relevance["query_term_count"] == 0
    assert relevance["score"] == 0
    assert relevance["matched_title_terms"] == []


def test_long_question_terms_are_bounded_and_truncation_is_disclosed():
    question = " ".join(f"topic{index}" for index in range(125))
    relevance = score_candidate_relevance(question, "topic124", None)

    assert relevance["query_term_count"] == 120
    assert relevance["query_terms_truncated"] is True
    assert "topic124" not in relevance["query_terms"]


def test_topic_gate_excludes_shared_scope_words_without_intervention_or_topic_match():
    question = (
        "At a 60-engineer product company, does access to an AI coding copilot increase "
        "production accepted work without raising security defects over twelve weeks?"
    )
    irrelevant = (
        "Demonstration of Non-Orthogonal Multiple Access Scheme using Multilevel Coding "
        "without Successive Interference Cancellation with 60 GHz Radio"
    )
    relevant = "AI coding copilot use and production defects in software engineering teams"

    assert passes_topic_overlap_gate(question, relevant, None) is True
    assert passes_topic_overlap_gate(question, irrelevant, None) is False


def test_topic_gate_allows_general_research_without_ai_intervention_terms():
    assert (
        passes_topic_overlap_gate(
            "Does remote work affect employee retention?",
            "Remote work and employee retention in distributed organizations",
            None,
        )
        is True
    )


def test_official_search_description_can_supply_selection_overlap_without_becoming_an_abstract():
    question = "What do UK policies say about renewable energy investment for deployment?"
    title = "Clean Energy Industries Sector Plan"
    official_description = (
        "The UK's plan to create investment, growth, and jobs in clean energy industries."
    )

    assert topic_overlap_basis(question, title, None) is None
    assert (
        topic_overlap_basis(question, title, None, discovery_context=official_description)
        == "original_question"
    )


def test_topic_gate_does_not_confuse_invoice_cycle_time_with_detector_data_processing():
    question = (
        "For a 500-employee US manufacturer processing 6,000 invoices monthly, does AI-assisted "
        "invoice extraction and exception routing reduce cost and cycle time per correctly paid "
        "invoice versus the current accounts-payable process?"
    )
    unrelated_detector_paper = (
        "Intelligent experiments through real-time AI: Fast Data Processing and Autonomous "
        "Detector Control for sPHENIX and future EIC detectors"
    )

    assert passes_topic_overlap_gate(question, unrelated_detector_paper, None) is False


def test_topic_gate_recognizes_generative_ai_search_as_a_knowledge_retrieval_variant():
    question = (
        "In a professional-services firm, does a retrieval-grounded generative-AI assistant "
        "reduce employee search time and improve answer accuracy for internal knowledge queries?"
    )
    related_search_tool_paper = (
        "Designing and Evaluating Generative AI Search Tools for Human Cognitive Augmentation"
    )

    assert passes_topic_overlap_gate(question, related_search_tool_paper, None) is True


def test_topic_gate_uses_recorded_domain_expansion_to_recover_workplace_trial():
    question = "Does generative AI improve software developer productivity, and why do empirical studies report different findings?"
    planned_query = (
        "generative ai software developer productivity empirical coding assistants "
        "controlled experiments randomized trial field"
    )
    workplace_trial = (
        "Dear Diary: A Randomized Controlled Trial of Generative AI Coding Tools in the Workplace"
    )
    unrelated_detector_trial = (
        "Randomized Controlled Trial of Generative AI for Detector Calibration and Sensor Control"
    )

    assert (
        passes_topic_overlap_gate(
            question,
            workplace_trial,
            None,
            planned_query=planned_query,
        )
        is True
    )
    assert (
        passes_topic_overlap_gate(
            question,
            unrelated_detector_trial,
            None,
            planned_query=planned_query,
        )
        is False
    )


def test_heat_question_does_not_select_on_geography_or_broad_health_terms_alone():
    question = (
        "How do Indian cities reduce extreme-heat exposure, and what evidence shows effects on "
        "health and outdoor-worker productivity?"
    )
    unrelated_dam_safety = (
        "Assessing the Effects of Extreme Rainfall Patterns and their Impact on Dam Safety: "
        "A Case Study on Indian Dam Failures"
    )
    unrelated_air_pollution = (
        "Assessment of Indoor and Outdoor Exposure to Airborne Particles in Subway Metro "
        "Stations and Their Associated Health Risks"
    )
    directly_relevant_heat = (
        "Global warming amplifies outdoor extreme moist heat during the Indian Summer Monsoon"
    )

    assert topic_overlap_basis(question, unrelated_dam_safety, None) is None
    assert topic_overlap_basis(question, unrelated_air_pollution, None) is None
    assert topic_overlap_basis(question, directly_relevant_heat, None) == "original_question"


def test_bibliographic_title_check_rejects_issue_page_metadata_without_length_cutoffs():
    contaminated = (
        'Articles "Harnessing Spirituality" DOI 10.52783/jier.v6i1.4117 357 PDF: 402 PDF '
        "The Algorithmic Customer and Personalized Marketing"
    )

    assert has_clean_bibliographic_title("A randomized trial of AI assisted invoice review")
    assert not has_clean_bibliographic_title(contaminated)


def test_repository_artifact_readme_mislabelled_as_abstract_is_not_study_evidence():
    repository_description = (
        "This repository contains analyses and data related to the paper. "
        "It includes Jupyter Notebooks, raw survey data, and the original survey tool."
    )
    genuine_abstract = (
        "We conducted a mixed-methods field study of developers using a generative AI assistant. "
        "Participants reported differences in productivity and review work."
    )

    assert is_repository_artifact_description(repository_description) is True
    assert is_repository_artifact_description(genuine_abstract) is False
