from datetime import UTC, datetime

from app.research.evidence_sufficiency import (
    evaluate_evidence_sufficiency,
    infer_evidence_requirements,
)

EVALUATED_AT = datetime(2026, 10, 31, tzinfo=UTC)


def _valid_inputs():
    return {
        "retrieval": {
            "planned_lenses": 3,
            "completed_lenses": 3,
            "failed_lenses": 0,
            "candidate_ledger_complete": True,
            "relevant_exclusions_disclosed": True,
            "counterevidence_search_completed": True,
            "citation_expansion_complete": True,
        },
        "source_access": {
            "eligible_studies": 2,
            "critical_access_assessed": True,
            "critical_studies": 1,
            "critical_studies_with_usable_methods_results": 1,
        },
        "methodology": {"critical_appraisals_expected": 1, "critical_appraisals_assessed": 1},
        "material_claims": [
            {
                "claim_id": "claim-1",
                "requirement_types": ["descriptive"],
                "provenance_valid": True,
                "support_status": "supported",
                "numerical_evidence_present": None,
                "causal_design_assessed": None,
                "explicit_absence_evidence": None,
                "unresolved_contradiction": False,
            }
        ],
        "verification": {
            "material_items_expected": 1,
            "material_items_assessed": 1,
            "deterministic_links_passed": True,
            "semantic_audit_complete": True,
            "semantic_batch_coverage_complete": True,
            "uncited_scan_complete": True,
            "audit_input_truncated": False,
        },
    }


def test_complete_automated_checks_can_pass_without_claiming_peer_review():
    decision = evaluate_evidence_sufficiency(_valid_inputs(), evaluated_at=EVALUATED_AT)

    assert decision.status == "EVIDENCE_VERIFIED"
    assert decision.human_review_status == "not_performed"
    assert decision.policy_version == "evidence-sufficiency-v1"
    assert decision.blocking_conditions == []


def test_unsupported_numerical_claim_cannot_pass_automated_sufficiency():
    inputs = _valid_inputs()
    inputs["material_claims"][0].update(
        requirement_types=["numerical"], numerical_evidence_present=False
    )

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status != "EVIDENCE_VERIFIED"
    assert any("numerical" in reason for reason in decision.blocking_conditions)


def test_unsupported_causal_claim_cannot_pass_automated_sufficiency():
    inputs = _valid_inputs()
    inputs["material_claims"][0].update(requirement_types=["causal"], causal_design_assessed=False)

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status != "EVIDENCE_VERIFIED"
    assert any("causal" in reason for reason in decision.blocking_conditions)


def test_partial_support_or_unresolved_contradiction_downgrades_decision():
    inputs = _valid_inputs()
    inputs["material_claims"][0].update(
        support_status="partially_supported", unresolved_contradiction=True
    )

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status == "PROVISIONAL"
    assert decision.blocking_conditions


def test_abstract_silence_does_not_support_a_not_measured_claim():
    inputs = _valid_inputs()
    inputs["material_claims"][0].update(
        requirement_types=["negative_or_absence"], explicit_absence_evidence=False
    )

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status != "EVIDENCE_VERIFIED"
    assert any("absence" in reason for reason in decision.blocking_conditions)


def test_incomplete_retrieval_or_truncated_audit_prevents_strong_status():
    inputs = _valid_inputs()
    inputs["retrieval"]["completed_lenses"] = 2
    inputs["verification"]["audit_input_truncated"] = True

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status == "PROVISIONAL"
    assert any("search" in reason for reason in decision.blocking_conditions)
    assert any("truncated" in reason for reason in decision.blocking_conditions)


def test_missing_semantic_batch_coverage_prevents_strong_status():
    inputs = _valid_inputs()
    inputs["verification"]["semantic_batch_coverage_complete"] = False

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status == "PROVISIONAL"
    assert "semantic_audit_batch_coverage_incomplete" in decision.blocking_conditions


def test_missing_counterevidence_search_or_citation_expansion_prevents_strong_status():
    inputs = _valid_inputs()
    inputs["retrieval"]["counterevidence_search_completed"] = False
    inputs["retrieval"]["citation_expansion_complete"] = False

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status == "PROVISIONAL"
    assert "counterevidence_search_incomplete" in decision.blocking_conditions
    assert "citation_expansion_incomplete" in decision.blocking_conditions


def test_no_eligible_studies_yields_persistable_insufficient_evidence_decision():
    inputs = _valid_inputs()
    inputs["source_access"].update(
        eligible_studies=0, critical_studies=0, critical_studies_with_usable_methods_results=0
    )
    inputs["material_claims"] = []
    inputs["verification"].update(material_items_expected=0, material_items_assessed=0)

    decision = evaluate_evidence_sufficiency(inputs, evaluated_at=EVALUATED_AT)

    assert decision.status == "INSUFFICIENT_EVIDENCE"
    assert decision.decision_timestamp is not None
    assert "no_eligible_studies" in decision.blocking_conditions


def test_assertion_routing_can_require_multiple_evidence_checks():
    requirements = infer_evidence_requirements(
        "AI improved completion time by 20% in a randomized trial."
    )

    assert requirements == ["numerical", "methodological", "causal"]
