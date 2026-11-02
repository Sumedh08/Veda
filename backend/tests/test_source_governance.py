from app.providers.scholarly import ScholarlyWork
from app.research.source_governance import (
    academic_preference_tier,
    build_source_governance_plan,
    classify_source,
    classify_work_record,
    default_registry,
    planned_source_classes,
    summarize_source_coverage,
    validate_registry,
)


def _provenance(url="https://registry.example/source", verified_at="2026-11-01"):
    return {"source_url": url, "verified_at": verified_at}


def _registry():
    return {
        "schema_version": 1,
        "registry_version": "test-fixture-1",
        "updated_at": "2026-11-01",
        "organizations": [
            {
                "canonical_id": "world-bank-group",
                "category": "multilateral",
                "canonical_name": "World Bank Group",
                "aliases": ["World Bank", "World Bank Data360"],
                "official_domains": ["worldbank.org", "data360.worldbank.org"],
                "identity_status": "verified",
                "identity_provenance": [_provenance("https://data360.worldbank.org/")],
                "quality_review_status": "not_assessed",
                "discovery_adapters": ["world_bank_data360"],
            },
            {
                "canonical_id": "adb",
                "category": "multilateral",
                "canonical_name": "Asian Development Bank",
                "aliases": ["ADB"],
                "official_domains": ["adb.org"],
                "identity_status": "verified",
                "identity_provenance": [_provenance("https://www.adb.org/Publications/")],
                "quality_review_status": "not_assessed",
                "discovery_adapters": ["not_integrated"],
            },
            {
                "canonical_id": "deloitte",
                "category": "consulting",
                "canonical_name": "Deloitte",
                "aliases": ["Deloitte Insights"],
                "official_domains": ["deloitte.com"],
                "identity_status": "verified",
                "identity_provenance": [
                    _provenance("https://www.deloitte.com/global/en/insights.html")
                ],
                "quality_review_status": "not_assessed",
                "discovery_adapters": ["not_integrated"],
            },
            {
                "canonical_id": "brookings",
                "category": "think_tank",
                "canonical_name": "Brookings Institution",
                "aliases": ["Brookings"],
                "official_domains": ["brookings.edu"],
                "identity_status": "verified",
                "identity_provenance": [_provenance("https://www.brookings.edu/about-us/")],
                "quality_review_status": "review_pending",
                "discovery_adapters": ["not_integrated"],
            },
        ],
        "universities": [
            {
                "canonical_id": "university-a",
                "canonical_name": "University A",
                "aliases": [],
                "identifiers": {"openalex": ["I123"], "ror": ["https://ror.org/abc"]},
                "identity_provenance": [_provenance()],
                "rankings": [
                    {
                        "system": "QS_WUR",
                        "ranking_year": 2026,
                        "rank": 73,
                        "subject_category": "overall",
                        "status": "verified",
                        "provenance": _provenance(
                            "https://www.topuniversities.com/world-university-rankings/2026"
                        ),
                    }
                ],
            },
            {
                "canonical_id": "university-b",
                "canonical_name": "University B",
                "aliases": [],
                "identifiers": {"ror": ["https://ror.org/def"]},
                "identity_provenance": [_provenance()],
                "rankings": [
                    {
                        "system": "QS_WUR",
                        "ranking_year": 2026,
                        "rank": 177,
                        "subject_category": "overall",
                        "status": "verified",
                        "provenance": _provenance(
                            "https://www.topuniversities.com/world-university-rankings/2026"
                        ),
                    }
                ],
            },
        ],
        "journals": [
            {
                "canonical_id": "journal-q1",
                "canonical_name": "Journal of Verified Studies",
                "issns": ["1234-5679"],
                "aliases": [],
                "identity_provenance": [_provenance("https://journal.example/about")],
                "quartiles": [
                    {
                        "system": "SCImago SJR",
                        "ranking_year": 2025,
                        "subject_category": "Economics",
                        "quartile": "Q1",
                        "status": "verified",
                        "provenance": _provenance(
                            "https://www.scimagojr.com/journalsearch.php?q=12345678"
                        ),
                    }
                ],
                "ft50_memberships": [],
            },
            {
                "canonical_id": "journal-ft50",
                "canonical_name": "Journal of Management Studies",
                "issns": ["8765-4326"],
                "aliases": [],
                "identity_provenance": [_provenance("https://journal.example/management")],
                "quartiles": [],
                "ft50_memberships": [
                    {
                        "list_year": 2025,
                        "status": "verified",
                        "provenance": _provenance("https://www.ft.com/ft50"),
                    }
                ],
            },
        ],
    }


def test_verified_qs_top_100_and_101_to_250_are_distinct_eligible_paths():
    registry = validate_registry(_registry())
    top = classify_source(
        registry=registry, institution_ids={"openalex": ["I123"]}, ranking_year=2026
    )
    eligible = classify_source(
        registry=registry, institution_ids={"ror": ["https://ror.org/def"]}, ranking_year=2026
    )

    assert top.academic_preference == "QS_TOP_100"
    assert top.quality_claim_is_truth_claim is False
    assert top.matched_institution_identifiers[0].identifier == "I123"
    assert eligible.academic_preference == "QS_101_250_ELIGIBLE"
    assert eligible.matched_institution_rankings[0].rank == 177


def test_q1_requires_exact_issn_subject_year_and_verified_provenance():
    registry = validate_registry(_registry())
    result = classify_source(
        registry=registry,
        journal_issns=["1234-5679"],
        ranking_year=2025,
        relevant_subject_categories=["Economics"],
    )
    wrong_subject = classify_source(
        registry=registry,
        journal_issns=["1234-5679"],
        ranking_year=2025,
        relevant_subject_categories=["Computer Science"],
    )

    assert result.academic_preference == "Q1"
    assert result.matched_journal_classifications[0].issn == "12345679"
    assert wrong_subject.academic_preference == "NONE"
    assert academic_preference_tier(result) == 0
    assert academic_preference_tier(wrong_subject) == 1


def test_q1_classification_without_a_question_subject_does_not_set_preference():
    result = classify_source(
        registry=validate_registry(_registry()), journal_issns=["1234-5679"], ranking_year=2025
    )

    assert result.matched_journal_classifications[0].classification == "Q1"
    assert result.academic_preference == "NONE"
    assert academic_preference_tier(result) == 1


def test_default_classification_uses_the_latest_registry_year_without_relabeling_it():
    data = _registry()
    data["journals"][0]["quartiles"].append(
        {
            "system": "SCImago SJR",
            "ranking_year": 2026,
            "subject_category": "Economics",
            "quartile": "Q2",
            "status": "verified",
            "provenance": _provenance("https://www.scimagojr.com/journalsearch.php?q=12345679"),
        }
    )
    latest = classify_source(
        registry=validate_registry(data),
        journal_issns=["1234-5679"],
        relevant_subject_categories=["Economics"],
    )
    historical = classify_source(
        registry=validate_registry(data),
        journal_issns=["1234-5679"],
        ranking_year=2025,
        relevant_subject_categories=["Economics"],
    )
    assert latest.academic_preference == "NONE"
    assert historical.academic_preference == "Q1"
    assert historical.matched_journal_classifications[0].ranking_year == 2025


def test_ft50_resolution_uses_issn_identity_and_versioned_list_provenance():
    result = classify_source(
        registry=validate_registry(_registry()), journal_issns=["8765-4326"], ranking_year=2025
    )

    assert result.academic_preference == "FT50"
    assert result.matched_journal_classifications[0].registry_id == "journal-ft50"


def test_official_multilateral_publications_are_classified_without_quality_inference():
    registry = validate_registry(_registry())
    wb = classify_source(registry=registry, publisher="World Bank Data360")
    wb_domain = classify_source(
        registry=registry, source_url="https://documents.worldbank.org/reports"
    )
    adb = classify_source(registry=registry, source_url="https://www.adb.org/Publications/paper")
    ilo_statistics = classify_source(
        source_url="https://ilostat.ilo.org/data/",
        source_type="official_statistics",
        provider="ILOSTAT",
    )

    assert wb.source_classes == ["multilateral"]
    assert wb.identity_status == "unverified"
    assert wb.matched_registry_ids == ["world-bank-group"]
    assert wb_domain.identity_status == "verified"
    assert wb_domain.source_classes == ["multilateral"]
    assert adb.source_classes == ["multilateral"]
    assert adb.identity_status == "verified"
    assert adb.methodological_quality == "not_assessed"
    assert adb.discovery_status == "not_integrated"
    assert ilo_statistics.source_classes == ["official_statistics", "multilateral"]
    assert ilo_statistics.discovery_status == "discovered_by_registered_adapter"


def test_real_crossref_world_bank_doi_prefix_resolves_institutional_identity():
    record = ScholarlyWork(
        external_id="doi:10.1596/1813-9450-10870",
        title="Who on Earth Is Using Generative AI?",
        doi="10.1596/1813-9450-10870",
        url="https://doi.org/10.1596/1813-9450-10870",
        authors=[],
        published_year=2024,
        publisher="Washington, DC: World Bank",
        abstract_excerpt=None,
        query="Who on Earth Is Using Generative AI",
        provider="Crossref",
    )

    result = classify_work_record(record)

    assert "academic" in result.source_classes
    assert "multilateral" in result.source_classes
    assert result.identity_status == "verified"
    assert "world-bank-group" in result.matched_registry_ids
    assert any(
        item.namespace == "crossref_prefix" and item.identifier == "10.1596"
        for item in result.matched_organization_identifiers
    )
    assert result.methodological_quality == "not_assessed"
    assert result.discovery_status == "registered_adapter_available"


def test_consulting_brand_is_identity_only_and_methodology_remains_required():
    result = classify_source(registry=validate_registry(_registry()), publisher="Deloitte Insights")

    assert result.source_classes == ["consulting"]
    assert result.identity_status == "unverified"
    assert result.quality_review_status == "not_assessed"
    assert result.methodology_review_required is True
    assert result.academic_preference == "NONE"
    assert result.selection_guidance == "do_not_promote_to_fill_coverage"
    mbb = classify_source(publisher="McKinsey Global Institute")
    big_four = classify_source(publisher="PwC")
    assert mbb.source_classes == ["consulting"]
    assert big_four.source_classes == ["consulting"]
    assert mbb.methodological_quality == big_four.methodological_quality == "not_assessed"
    official = classify_source(
        registry=validate_registry(_registry()),
        source_url="https://www.deloitte.com/global/en/insights.html",
    )
    assert official.identity_status == "verified"
    assert official.source_classes == ["consulting"]


def test_think_tank_candidate_does_not_become_vetted_from_identity_alone():
    result = classify_source(
        registry=validate_registry(_registry()), source_url="https://brookings.edu/research/example"
    )

    assert result.source_classes == ["think_tank"]
    assert result.identity_status == "verified"
    assert result.quality_review_status == "review_pending"
    assert result.methodological_quality == "not_assessed"


def test_unverified_rankings_are_not_used_even_when_names_match():
    data = _registry()
    data["universities"][0]["rankings"][0]["status"] = "unverified"
    result = classify_source(
        registry=validate_registry(data), institution_ids={"openalex": ["I123"]}, ranking_year=2026
    )

    assert result.academic_preference == "NONE"
    assert result.unverified_classification_count == 1


def test_unregistered_generic_source_is_not_promoted_to_fill_a_slot():
    result = classify_source(
        registry=validate_registry(_registry()),
        publisher="Unknown Content Farm",
        source_url="https://example.invalid/blog/post",
    )

    assert result.identity_status == "unregistered"
    assert result.selection_guidance == "do_not_promote_to_fill_coverage"


def test_material_counterevidence_exception_preserves_unregistered_source_for_review():
    result = classify_source(
        registry=validate_registry(_registry()),
        publisher="Independent Lab",
        is_material_counterevidence=True,
    )

    assert result.selection_guidance == "eligible_for_counterevidence_review"
    assert result.counterevidence_exception is True
    assert result.methodology_review_required is True


def test_report_coverage_discloses_unsearched_and_missing_source_classes():
    coverage = summarize_source_coverage(
        planned_classes=["academic", "multilateral", "consulting", "think_tank"],
        searched_classes=["academic", "multilateral"],
        candidate_class_counts={"academic": 4, "multilateral": 1},
        selected_class_counts={"academic": 2, "multilateral": 1},
        adapter_status={"consulting": "not_integrated", "think_tank": "not_integrated"},
    )

    assert coverage["searched_classes"] == ["academic", "multilateral"]
    assert coverage["missing_classes"] == ["consulting", "think_tank"]
    assert coverage["class_status"]["consulting"]["status"] == "not_integrated"


def test_productivity_questions_plan_relevant_cross_institution_classes_with_adapter_status():
    plan = build_source_governance_plan(
        "Does generative AI improve software developer productivity?"
    )

    assert plan["planned_classes"] == [
        "academic",
        "consulting",
        "think_tank",
        "multilateral",
        "official_statistics",
        "government",
    ]
    assert plan["planned_adapter_status"]["academic"] == "crossref_openalex"
    assert plan["planned_adapter_status"]["consulting"] == "not_integrated"
    assert plan["planned_adapter_status"]["think_tank"] == "not_integrated"
    assert (
        plan["planned_adapter_status"]["multilateral"]
        == "world_bank_documents_reports_api_confirmation_required"
    )


def test_domain_planner_covers_energy_trade_and_regulatory_source_classes():
    energy = build_source_governance_plan(
        "How do battery storage and grid constraints affect renewable electricity investment in India?"
    )
    trade = build_source_governance_plan(
        "How does industrial policy affect international trade competitiveness?"
    )
    regulatory = build_source_governance_plan(
        "What regulatory requirements affect international market entry and compliance?"
    )
    holdout = build_source_governance_plan(
        "How does wildfire smoke exposure affect cardiovascular hospital admissions?"
    )

    assert energy["planned_classes"] == [
        "academic",
        "consulting",
        "think_tank",
        "multilateral",
        "official_statistics",
        "government",
    ]
    assert trade["planned_classes"] == [
        "academic",
        "consulting",
        "think_tank",
        "multilateral",
        "official_statistics",
        "government",
    ]
    assert regulatory["planned_classes"] == [
        "academic",
        "consulting",
        "think_tank",
        "multilateral",
        "government",
    ]
    assert holdout["planned_classes"] == [
        "academic",
        "multilateral",
        "official_statistics",
        "government",
    ]
    assert all(
        plan["planned_adapter_status"][source_class] == "not_integrated"
        for plan in (energy, trade, regulatory)
        for source_class in ("consulting", "think_tank")
    )
    assert all(
        plan["planned_adapter_status"]["government"]
        == "not_applicable_explicit_uk_geography_required"
        for plan in (energy, trade, regulatory)
    )
    assert "investment" in energy["class_selection_reasons"]["consulting"]
    assert "trade" in trade["class_selection_reasons"]["multilateral"]
    assert "regulatory" in regulatory["class_selection_reasons"]["government"]


def test_food_price_policy_plans_multilateral_and_primary_statistics_coverage():
    plan = build_source_governance_plan(
        "Which policies have reduced food price volatility and improved food security "
        "for smallholder agriculture in South Asia, and what evidence explains "
        "differences in outcomes?"
    )

    assert plan["planned_classes"] == [
        "academic",
        "think_tank",
        "multilateral",
        "official_statistics",
        "government",
    ]
    assert "consulting" not in plan["planned_classes"]
    assert "policies" in plan["class_selection_reasons"]["think_tank"]
    assert "policies" in plan["class_selection_reasons"]["multilateral"]
    assert "food price volatility" in plan["class_selection_reasons"]["official_statistics"]


def test_food_security_conceptual_question_does_not_alone_trigger_public_authorities():
    assert planned_source_classes(
        "How do soil microbial communities affect food security in smallholder systems?"
    ) == ["academic"]


def test_policy_only_food_security_plans_public_authorities_but_not_statistics():
    assert planned_source_classes(
        "Which policies shape food security among smallholder systems?"
    ) == ["academic", "think_tank", "multilateral", "government"]


def test_source_governance_plan_enables_best_effort_uk_official_metadata_only_for_uk_scope():
    question = "What government policy reports describe renewable energy deployment?"
    uk = build_source_governance_plan(question, geography="United Kingdom")
    india = build_source_governance_plan(question, geography="India")

    assert uk["planned_adapter_status"]["government"] == (
        "govuk_search_api_unsupported_best_effort"
    )
    assert india["planned_adapter_status"]["government"] == (
        "not_applicable_explicit_uk_geography_required"
    )
    assert uk["policy_version"] == "topic-cues-source-classes-v5"


def test_registry_rejects_unverifiable_q1_records():
    data = _registry()
    data["journals"][0]["quartiles"][0]["provenance"] = {}

    try:
        validate_registry(data)
    except ValueError as exc:
        assert "provenance" in str(exc).casefold()
    else:
        raise AssertionError("unverifiable ranking data must be rejected")


def test_shipped_registry_contains_verified_identities_but_no_unverified_rank_claims():
    registry = default_registry()
    assert registry.registry_version == "veda-source-governance-2026-11-01-v4"
    assert registry.universities == []
    assert registry.journals == []
    assert classify_source(publisher="Asian Development Bank").source_classes == ["multilateral"]
    govuk = classify_source(source_url="https://www.gov.uk/government/publications/example-report")
    assert govuk.source_classes == ["government"]
    assert govuk.identity_status == "verified"
    assert govuk.methodological_quality == "not_assessed"
    consulting = classify_source(publisher="Deloitte Insights")
    assert consulting.source_classes == ["consulting"]
    assert consulting.identity_status == "unverified"
    assert consulting.methodological_quality == "not_assessed"


def test_official_domain_match_rejects_hostname_suffix_confusion():
    registry = validate_registry(_registry())
    assert classify_source(
        registry=registry, source_url="https://www.adb.org/publications/report"
    ).matched_registry_ids == ["adb"]
    impostor = classify_source(
        registry=registry, source_url="https://adb.org.attacker.example/report"
    )
    assert impostor.identity_status == "unregistered"
    assert impostor.source_classes == []


def test_journal_identity_requires_a_valid_issn_checksum():
    result = classify_source(
        registry=validate_registry(_registry()),
        journal_issns=["1234-5678"],
        ranking_year=2025,
        relevant_subject_categories=["Economics"],
    )
    assert result.academic_preference == "NONE"
    assert result.matched_journal_classifications == []
