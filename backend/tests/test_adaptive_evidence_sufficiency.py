from app.research.evidence_sufficiency import (
    AdaptiveSufficiencyInput,
    EvidenceIndependenceUnit,
    MaterialRequirementEvidenceV1,
    build_question_evidence_plan,
    evaluate_adaptive_sufficiency,
    publication_identity_key,
    summarize_evidence_independence,
)


def _subquestions(*items):
    return [
        {"text": text, "purpose": "Assess this material part of the question."} for text in items
    ]


def _unit(
    source_id,
    publication,
    *,
    source_type="scholarly_article",
    role="primary_empirical",
    passages=2,
    access_classes=(),
    versions=(),
    independence="unknown",
    investigation_id=None,
    datasets=(),
    basis=None,
):
    return EvidenceIndependenceUnit(
        source_id=source_id,
        publication_identity=publication,
        source_type=source_type,
        evidence_role=role,
        passage_count=passages,
        content_access_classes=list(access_classes),
        document_version_ids=list(versions),
        independence_status=independence,
        independence_reviewed=independence != "unknown",
        investigation_id=investigation_id,
        dataset_ids=list(datasets),
        assessment_basis=basis,
    )


def _complete_adaptive_input(
    plan, units, *, covered=None, independent=None, requirement_evidence=None
):
    independence = independent or summarize_evidence_independence(units)
    return AdaptiveSufficiencyInput(
        plan=plan,
        independence=independence,
        content_bearing_source_count=sum(unit.passage_count > 0 for unit in units),
        material_claims_expected=1,
        material_claims_supported=1,
        covered_requirement_ids=covered
        or [item.requirement_id for item in plan.material_requirements],
        material_requirement_evidence=requirement_evidence or [],
        counterevidence_search_completed=True,
        bounded_search_complete=True,
        source_class_coverage_complete=True,
        deterministic_citation_integrity_passed=True,
        semantic_audit_complete=True,
        unresolved_material_contradictions=0,
    )


def test_question_profile_adapts_evidence_needs_without_a_global_source_quota():
    narrow = build_question_evidence_plan(
        "What methods and outcomes does the cited study report?",
        {},
        _subquestions("Methods and outcomes reported by the study"),
    )
    broad = build_question_evidence_plan(
        "Do water-pricing reforms reduce groundwater depletion for smallholders across semi-arid regions?",
        {"geography": "multiple semi-arid regions", "population": "smallholders"},
        _subquestions("Reform design", "Groundwater outcomes", "Distributional effects"),
    )

    assert narrow.question_kind == "narrow_source_specific"
    assert not narrow.independent_corroboration_expected
    assert broad.question_kind in {"causal", "mixed"}
    assert broad.independent_corroboration_expected
    assert len(broad.material_requirements) == 3
    assert all("source_count" not in criterion for criterion in broad.minimum_criteria)


def test_questions_about_a_body_of_studies_require_independent_corroboration():
    plan = build_question_evidence_plan(
        "What randomized studies report about AI task productivity for workers?",
        {},
        _subquestions("What do randomized studies report about the outcome?"),
    )

    assert plan.scope_breadth == "broad"
    assert plan.independent_corroboration_expected


def test_source_specific_effect_question_preserves_methodological_needs_without_global_corroboration():
    plan = build_question_evidence_plan(
        "What effect did the cited evaluation report for its primary outcome?",
        {},
        _subquestions("Effect reported by the cited evaluation"),
    )

    assert plan.question_kind == "narrow_source_specific"
    assert "causal_design" in plan.evidence_dimensions
    assert not plan.independent_corroboration_expected


def test_association_language_requests_design_and_alternative_explanation_appraisal():
    plan = build_question_evidence_plan(
        "Which staffing patterns are associated with fewer medication errors across hospitals?",
        {},
        _subquestions("Outcome association", "Setting and outcome measurement"),
    )

    assert plan.question_kind in {"comparative", "mixed"}
    assert "association_design_and_alternative_explanations" in plan.evidence_dimensions
    assert plan.independent_corroboration_expected


def test_relation_verbs_request_association_appraisal_without_matching_one_question():
    plan = build_question_evidence_plan(
        "What evidence connects treatment adherence to readmission rates across clinics?",
        {},
        _subquestions("Readmission rates and adherence measurement"),
    )

    assert plan.question_kind in {"comparative", "mixed"}
    assert "association_design_and_alternative_explanations" in plan.evidence_dimensions
    assert plan.independent_corroboration_expected


def test_tracking_language_requests_association_appraisal():
    plan = build_question_evidence_plan(
        "Do attendance changes track differences in local air-quality alerts across school districts?",
        {},
        _subquestions("Attendance and alert measurement", "Differences across districts"),
    )

    assert plan.question_kind in {"comparative", "mixed"}
    assert "association_design_and_alternative_explanations" in plan.evidence_dimensions
    assert plan.independent_corroboration_expected


def test_question_plan_identifies_numeric_and_time_series_evidence_needs():
    plan = build_question_evidence_plan(
        "What are the annual rates of informal employment by age group since 2012?",
        {},
        _subquestions("Rates, definitions, and denominators", "Age-group series over time"),
    )

    assert "quantitative_measurement_and_denominator" in plan.evidence_dimensions
    assert "time_series_comparability" in plan.evidence_dimensions
    assert any("denominator" in criterion for criterion in plan.minimum_criteria)
    assert not plan.independent_corroboration_expected


def test_single_publication_can_be_sufficient_for_a_narrow_source_specific_question():
    plan = build_question_evidence_plan(
        "What methods and outcomes does the cited study report?",
        {},
        _subquestions("Methods and outcomes reported by the study"),
    )
    units = [_unit("src-1", "doi:10.1000/example", versions=("published-v1",))]

    decision = evaluate_adaptive_sufficiency(_complete_adaptive_input(plan, units))

    assert decision.status == "SUFFICIENT_FOR_SCOPE"
    assert decision.independence.independent_investigations_confirmed == 0
    assert decision.independence.publication_groups == 1
    assert decision.independence.document_versions == 1


def test_single_cited_study_can_answer_what_it_reports_without_population_level_corroboration():
    plan = build_question_evidence_plan(
        "What effect did the cited trial report for its primary outcome?",
        {},
        _subquestions("Effect and primary outcome reported by the cited trial"),
    )

    assert plan.question_kind == "narrow_source_specific"
    assert not plan.independent_corroboration_expected
    assert "causal_design" in plan.evidence_dimensions


def test_passages_and_versions_from_one_work_do_not_count_as_independent_evidence():
    plan = build_question_evidence_plan(
        "Do water-pricing reforms reduce groundwater depletion across semi-arid regions?",
        {"geography": "multiple semi-arid regions"},
        _subquestions("Groundwater depletion outcomes"),
    )
    units = [
        _unit("src-v1", "doi:10.1000/study", versions=("accepted-v1",)),
        _unit("src-v2", "doi:10.1000/study", versions=("published-v2",)),
    ]

    decision = evaluate_adaptive_sufficiency(_complete_adaptive_input(plan, units))

    assert decision.independence.publication_groups == 1
    assert decision.independence.document_versions == 2
    assert decision.independence.independent_investigations_confirmed == 0
    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"
    assert "independent_corroboration_not_established" in decision.blocking_conditions


def test_cross_source_records_for_the_same_work_are_one_publication_group():
    summary = summarize_evidence_independence(
        [
            _unit("src-article", "doi:10.1000/shared", versions=("published-v1",)),
            _unit(
                "src-report-copy",
                "https://doi.org/10.1000/shared",
                source_type="institutional_report",
                role="institutional_analysis",
                versions=("repository-copy-v2",),
            ),
        ]
    )

    assert summary.source_records == 2
    assert summary.publication_groups == 1
    assert summary.same_publication_version_groups == 1
    assert summary.independent_investigations_confirmed == 0
    assert set(summary.groups[0].source_types) == {"scholarly_article", "institutional_report"}
    assert set(summary.groups[0].evidence_roles) == {"primary_empirical", "institutional_analysis"}


def test_doi_less_versions_with_distinct_document_urls_share_bibliographic_identity():
    first = publication_identity_key(
        doi=None,
        url="https://institute.example/reports/2021/report.html",
        title="Regional Water Security: Final Report",
        published_year=2021,
        publisher="Regional Research Institute",
        authors=["A. Researcher", "B. Analyst"],
    )
    second = publication_identity_key(
        doi=None,
        url="https://repository.example/files/water-security-final.pdf",
        title="Regional Water Security: Final Report",
        published_year=2021,
        publisher="Regional Research Institute",
        authors=["A. Researcher", "B. Analyst"],
    )

    assert first == second
    summary = summarize_evidence_independence(
        [
            _unit("src-page", first, versions=("html-v1",)),
            _unit("src-pdf", second, versions=("pdf-v1",)),
        ]
    )
    assert summary.publication_groups == 1
    assert summary.same_publication_version_groups == 1
    assert summary.independent_investigations_confirmed == 0


def test_doi_less_publications_with_distinct_report_years_remain_distinct():
    first = publication_identity_key(
        doi=None,
        url="https://institute.example/reports/2021/report.html",
        title="Annual Climate Review",
        published_year=2021,
        publisher="Regional Research Institute",
        authors=[],
    )
    second = publication_identity_key(
        doi=None,
        url="https://institute.example/reports/2022/report.html",
        title="Annual Climate Review",
        published_year=2022,
        publisher="Regional Research Institute",
        authors=[],
    )

    assert first != second


def test_separate_publications_are_not_assumed_to_be_independent_investigations():
    plan = build_question_evidence_plan(
        "Do water-pricing reforms reduce groundwater depletion across semi-arid regions?",
        {},
        _subquestions("Groundwater depletion outcomes"),
    )
    units = [_unit("src-1", "doi:10.1000/a"), _unit("src-2", "doi:10.1000/b")]

    decision = evaluate_adaptive_sufficiency(_complete_adaptive_input(plan, units))

    assert decision.independence.publication_groups == 2
    assert decision.independence.unknown_independence_publications == 2
    assert decision.independence.independent_investigations_confirmed == 0
    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"


def test_two_publications_from_the_same_investigation_count_as_one_investigation():
    summary = summarize_evidence_independence(
        [
            _unit(
                "src-paper",
                "doi:10.1000/paper",
                independence="same_investigation",
                investigation_id="investigation-1",
                basis="Reviewed methods show the same field investigation.",
            ),
            _unit(
                "src-report",
                "https://example.org/report",
                source_type="institutional_report",
                independence="same_investigation",
                investigation_id="investigation-1",
                basis="Reviewed report states it reuses the same field investigation.",
            ),
        ]
    )

    assert summary.publication_groups == 2
    assert summary.same_investigation_groups == 1
    assert summary.independent_investigations_confirmed == 0


def test_reviewed_overlapping_datasets_do_not_count_as_independent_corroboration():
    plan = build_question_evidence_plan(
        "Do water-pricing reforms reduce groundwater depletion across semi-arid regions?",
        {},
        _subquestions("Groundwater depletion outcomes"),
    )
    units = [
        _unit(
            "src-1",
            "doi:10.1000/a",
            independence="independent_investigation",
            investigation_id="investigation-a",
            datasets=("survey-x",),
            basis="Reviewed study methods and dataset declaration.",
        ),
        _unit(
            "src-2",
            "doi:10.1000/b",
            independence="independent_investigation",
            investigation_id="investigation-b",
            datasets=("survey-x",),
            basis="Reviewed study methods and dataset declaration.",
        ),
    ]

    decision = evaluate_adaptive_sufficiency(_complete_adaptive_input(plan, units))

    assert decision.independence.overlapping_dataset_pairs == 1
    assert decision.independence.independent_investigations_confirmed == 0
    assert decision.independence.corroboration_eligible_investigation_ids == []
    assert all(group.overlapping_dataset_reuse for group in decision.independence.groups)
    assert "independent_corroboration_not_established" in decision.blocking_conditions


def test_review_synthesis_is_not_counted_as_an_independent_primary_investigation():
    summary = summarize_evidence_independence(
        [
            _unit(
                "src-review",
                "doi:10.1000/review",
                role="synthesis",
                independence="review_synthesis",
                basis="Review methods identify a synthesis of prior studies.",
            )
        ]
    )

    assert summary.review_synthesis_groups == 1
    assert summary.independent_investigations_confirmed == 0


def test_confirmed_independent_investigations_can_satisfy_broad_corroboration_rule():
    plan = build_question_evidence_plan(
        "Do water-pricing reforms reduce groundwater depletion across semi-arid regions?",
        {},
        _subquestions("Groundwater depletion outcomes"),
    )
    units = [
        _unit(
            "src-1",
            "doi:10.1000/a",
            independence="independent_investigation",
            investigation_id="investigation-a",
            datasets=("survey-a",),
            basis="Reviewed source methods, sample, and data provenance.",
        ),
        _unit(
            "src-2",
            "doi:10.1000/b",
            independence="independent_investigation",
            investigation_id="investigation-b",
            datasets=("survey-b",),
            basis="Reviewed source methods, sample, and data provenance.",
        ),
    ]

    decision = evaluate_adaptive_sufficiency(
        _complete_adaptive_input(
            plan,
            units,
            requirement_evidence=[
                MaterialRequirementEvidenceV1(
                    requirement_id="Q1",
                    linked_publication_identities=["doi:10.1000/a", "doi:10.1000/b"],
                    supporting_publication_identities=["doi:10.1000/a", "doi:10.1000/b"],
                    confirmed_independent_investigation_ids=["investigation-a", "investigation-b"],
                    independence_unknown_publication_identities=[],
                    known_non_independent_publication_identities=[],
                )
            ],
        )
    )

    assert decision.independence.independent_investigations_confirmed == 2
    assert decision.status == "SUFFICIENT_FOR_SCOPE"


def test_independent_investigations_must_support_the_same_material_requirement():
    plan = build_question_evidence_plan(
        "Do water-pricing reforms reduce groundwater depletion across semi-arid regions?",
        {},
        _subquestions("Groundwater depletion outcomes"),
    )
    units = [
        _unit(
            "src-a",
            "doi:10.1000/a",
            independence="independent_investigation",
            investigation_id="investigation-a",
            datasets=("dataset-a",),
            basis="Reviewed study methods and dataset declaration.",
        ),
        _unit(
            "src-b",
            "doi:10.1000/b",
            independence="independent_investigation",
            investigation_id="investigation-b",
            datasets=("dataset-b",),
            basis="Reviewed study methods and dataset declaration.",
        ),
    ]

    decision = evaluate_adaptive_sufficiency(
        _complete_adaptive_input(
            plan,
            units,
            requirement_evidence=[
                MaterialRequirementEvidenceV1(
                    requirement_id="Q1",
                    linked_publication_identities=["doi:10.1000/a"],
                    supporting_publication_identities=["doi:10.1000/a"],
                    confirmed_independent_investigation_ids=["investigation-a"],
                    independence_unknown_publication_identities=[],
                    known_non_independent_publication_identities=[],
                )
            ],
        )
    )

    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"
    assert (
        "independent_corroboration_not_established_for_requirement:Q1"
        in decision.blocking_conditions
    )


def test_metadata_only_record_cannot_count_as_an_independent_investigation():
    metadata_only = _unit(
        "src-metadata",
        "doi:10.1000/metadata",
        passages=0,
        independence="independent_investigation",
        investigation_id="investigation-metadata",
        datasets=("dataset-metadata",),
        basis="Reviewed publication methods and dataset provenance.",
    )

    summary = summarize_evidence_independence([metadata_only])

    assert summary.independent_investigations_confirmed == 0
    assert summary.content_bearing_publication_groups == 0


def test_abstract_passage_is_content_bearing_but_not_full_text():
    summary = summarize_evidence_independence(
        [
            _unit(
                "src-abstract",
                "doi:10.1000/abstract",
                access_classes=("abstract_only",),
            )
        ]
    )

    assert summary.content_bearing_publication_groups == 1
    assert summary.abstract_only_publication_groups == 1
    assert summary.full_text_publication_groups == 0


def test_metadata_only_sources_cannot_satisfy_a_content_evidence_requirement():
    plan = build_question_evidence_plan(
        "What methods and outcomes does the cited study report?",
        {},
        _subquestions("Methods and outcomes"),
    )
    units = [_unit("src-1", "doi:10.1000/example", passages=0)]
    inputs = _complete_adaptive_input(plan, units)
    inputs.content_bearing_source_count = 0
    inputs.material_claims_supported = 0

    decision = evaluate_adaptive_sufficiency(inputs)

    assert decision.status == "INSUFFICIENT_EVIDENCE"
    assert "no_content_bearing_evidence" in decision.blocking_conditions


def test_content_with_only_partial_or_unsupported_claims_is_preliminary_not_empty():
    plan = build_question_evidence_plan(
        "How do urban heat adaptation strategies affect health outcomes across Indian cities?",
        {"geography": "multiple Indian cities"},
        _subquestions("Health outcomes in cities"),
    )
    inputs = _complete_adaptive_input(
        plan,
        [_unit("src-1", "doi:10.1000/partial")],
    )
    inputs.material_claims_supported = 0

    decision = evaluate_adaptive_sufficiency(inputs)

    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"
    assert "no_supported_material_claims" in decision.blocking_conditions


def test_uncovered_material_subquestions_keep_report_as_preliminary():
    plan = build_question_evidence_plan(
        "How can cities assess heat risk and which strategies reduce harm?",
        {"geography": "cities"},
        _subquestions("Assess differential heat risk", "Evaluate adaptation outcomes"),
    )
    units = [_unit("src-1", "doi:10.1000/example")]
    first_requirement = plan.material_requirements[0].requirement_id

    decision = evaluate_adaptive_sufficiency(
        _complete_adaptive_input(plan, units, covered=[first_requirement])
    )

    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"
    assert decision.uncovered_requirement_ids == [plan.material_requirements[1].requirement_id]


def test_planned_but_unsearched_source_class_prevents_strong_status():
    plan = build_question_evidence_plan(
        "What methods and outcomes does the cited study report?",
        {},
        _subquestions("Methods and outcomes"),
    )
    inputs = _complete_adaptive_input(
        plan,
        [_unit("src-1", "doi:10.1000/example")],
    )
    inputs.source_class_coverage_complete = False

    decision = evaluate_adaptive_sufficiency(inputs)

    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"
    assert "planned_source_class_coverage_incomplete" in decision.blocking_conditions


def test_unmet_question_specific_methodological_criterion_prevents_strong_status():
    plan = build_question_evidence_plan(
        "Do irrigation reforms reduce groundwater depletion across semi-arid regions?",
        {"geography": "multiple semi-arid regions"},
        _subquestions("Groundwater outcomes under the reform"),
    )
    inputs = _complete_adaptive_input(
        plan,
        [
            _unit(
                "src-a",
                "doi:10.1000/a",
                independence="independent_investigation",
                investigation_id="investigation-a",
                datasets=("dataset-a",),
                basis="Reviewed study methods and dataset declaration.",
            ),
            _unit(
                "src-b",
                "doi:10.1000/b",
                independence="independent_investigation",
                investigation_id="investigation-b",
                datasets=("dataset-b",),
                basis="Reviewed study methods and dataset declaration.",
            ),
        ],
    )
    inputs.unmet_evidence_criteria = ["causal_design_not_assessed:C1"]

    decision = evaluate_adaptive_sufficiency(inputs)

    assert decision.status == "PRELIMINARY_EVIDENCE_MAP"
    assert "evidence_criterion_unmet:causal_design_not_assessed:C1" in decision.blocking_conditions
