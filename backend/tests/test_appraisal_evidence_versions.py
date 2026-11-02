import pytest
from pydantic import ValidationError
from sqlalchemy import select
from support import add_test_passage

from app.models import Claim, EvidenceRelationship, Hypothesis, ResearchJob, Source
from app.research.workflow import StageResult, persist_result
from app.schemas import (
    ClaimAppraisalV1,
    ClaimEconomicFacetsV1,
    ClaimMethodologyAppraisalV1,
    EvidenceHypothesisV1,
    EvidenceRelationshipV1,
    SourceMethodologicalAppraisalV1,
    claim_appraisal_for_api,
    hypothesis_record_for_api,
    relationship_record_for_api,
    source_appraisal_for_api,
    versioned_claim_appraisal,
    versioned_source_appraisal,
)

FACET_NAMES = (
    "population",
    "intervention_or_exposure",
    "comparator",
    "outcome",
    "estimate",
    "uncertainty",
    "geography",
    "time_period",
    "measure",
)


def _economic_facets():
    return {
        "schema_version": 1,
        "status": "not_assessed",
        "evidence_kind": "unknown",
        "provider": None,
        "model": None,
        "facets": {
            name: {"value": "unknown", "passage_ids": [], "status": "not_assessed"}
            for name in FACET_NAMES
        },
    }


def test_appraisal_v1_records_enforce_bounds_and_passage_links():
    source = {
        "schema_version": 1,
        "status": "model_assessed_not_independently_verified",
        "provider": "openrouter",
        "model": "fixture/free",
        "fields": {
            "design_type": {
                "value": "Randomized trial",
                "passage_ids": ["passage-1"],
                "status": "model_assessed_not_independently_verified",
            }
        },
    }
    assert versioned_source_appraisal(source, strict=True)["fields"]["design_type"]["value"] == (
        "Randomized trial"
    )

    claim = {
        "schema_version": 1,
        "extraction": "exact_source_sentence_span",
        "methodology_appraisal": {
            "schema_version": 1,
            "status": "model_assessed_not_independently_verified",
            "relationship": "supports",
            "rationale": "The quoted claim directly addresses the outcome.",
            "passage_ids": ["passage-1"],
            "provider": "openrouter",
            "model": "fixture/free",
        },
        "economic_facets": _economic_facets(),
    }
    persisted = versioned_claim_appraisal(claim, strict=True)
    assert ClaimAppraisalV1.model_validate(persisted).schema_version == 1
    assert ClaimMethodologyAppraisalV1.model_validate(
        persisted["methodology_appraisal"]
    ).status == ("model_assessed_not_independently_verified")
    assert ClaimEconomicFacetsV1.model_validate(persisted["economic_facets"]).evidence_kind == (
        "unknown"
    )

    invalid_source = {
        **source,
        "fields": {
            "design_type": {
                "value": "Randomized trial",
                "passage_ids": [],
                "status": "model_assessed_not_independently_verified",
            }
        },
    }
    with pytest.raises(ValidationError):
        SourceMethodologicalAppraisalV1.model_validate(invalid_source)

    with pytest.raises(ValidationError):
        versioned_claim_appraisal({**claim, "future_unbounded_payload": "ignored"}, strict=True)

    with pytest.raises(ValueError, match="64 KiB"):
        versioned_source_appraisal({"large_legacy_field": "x" * (65 * 1024)}, strict=True)


def test_legacy_appraisal_upcast_is_read_only_and_preserves_unknown_fields():
    legacy_source = {
        "status": "model_assessed_not_independently_verified",
        "reason": "legacy annotation",
        "fields": {
            "population": {
                "value": "urban households",
                "passage_ids": ["passage-2"],
                "status": "model_assessed_not_independently_verified",
            }
        },
        "legacy_flags": {"reviewed_by": "historical-process"},
    }
    original_source = {**legacy_source, "fields": dict(legacy_source["fields"])}
    normalized_source = source_appraisal_for_api(legacy_source)
    assert normalized_source["schema_version"] == 1
    assert normalized_source["fields"]["population"]["passage_ids"] == ["passage-2"]
    assert normalized_source["extensions"]["legacy_flags"] == {"reviewed_by": "historical-process"}
    assert legacy_source == original_source

    legacy_claim = {
        "extraction": "exact_sentence_from_abstract_excerpt",
        "economic_facets": _economic_facets(),
    }
    normalized_claim = claim_appraisal_for_api(legacy_claim)
    assert normalized_claim["schema_version"] == 1
    assert normalized_claim["extraction"] == "exact_sentence_from_abstract_excerpt"
    assert normalized_claim["methodology_appraisal"]["status"] == "not_assessed"
    assert legacy_claim == {
        "extraction": "exact_sentence_from_abstract_excerpt",
        "economic_facets": _economic_facets(),
    }


def test_comparison_v1_requires_claim_pair_links_and_advisory_status():
    record = {
        "claim_a_id": "claim-a",
        "claim_b_id": "claim-b",
        "relationship_type": "contradicts",
        "scope_alignment": "same",
        "scope_differences": [],
        "rationale": "The passage-linked claims report different results.",
        "evidence": [
            {"claim_id": "claim-a", "passage_ids": ["passage-a"]},
            {"claim_id": "claim-b", "passage_ids": ["passage-b"]},
        ],
        "status": "model_assessed_not_independently_verified",
        "schema_version": 1,
        "provider": "openrouter",
        "model_name": "fixture/free",
    }
    validated = EvidenceRelationshipV1.model_validate(record)
    assert validated.status == "model_assessed_not_independently_verified"

    with pytest.raises(ValidationError):
        EvidenceRelationshipV1.model_validate({**record, "evidence": record["evidence"][:1]})
    with pytest.raises(ValidationError):
        EvidenceRelationshipV1.model_validate({**record, "status": "verified_true"})

    hypothesis = EvidenceHypothesisV1.model_validate(
        {
            "comparison_group_id": "group-1",
            "side": "A",
            "statement": "The effect depends on implementation support.",
            "evidence": [{"claim_id": "claim-a", "passage_ids": ["passage-a"]}],
            "uncertainty": "The report does not isolate that mechanism.",
            "why_competing": "A different explanation has support in another source.",
            "status": "model_assessed_not_independently_verified",
            "schema_version": 1,
            "provider": None,
            "model_name": None,
        }
    )
    assert hypothesis.side == "A"


def test_malformed_legacy_appraisals_and_comparisons_degrade_without_hiding_evidence():
    source = source_appraisal_for_api({"schema_version": 1, "fields": ["not-an-object"]})
    assert source["status"] == "legacy_unvalidated"

    claim = claim_appraisal_for_api({"schema_version": 99, "economic_facets": "corrupt"})
    assert claim["extensions"]["legacy_unvalidated"] is True
    assert claim["economic_facets"]["evidence_kind"] == "unknown"

    relationship = relationship_record_for_api(
        {
            "claim_a_id": "claim-a",
            "claim_b_id": "claim-b",
            "relationship_type": "contradicts",
            "scope_alignment": "same",
            "scope_differences": [],
            "rationale": "malformed link",
            "evidence": [{"claim_id": "claim-a", "passage_ids": []}],
            "status": "model_assessed_not_independently_verified",
            "schema_version": 1,
            "provider": None,
            "model_name": None,
        }
    )
    assert relationship["relationship_type"] == "legacy_unvalidated"
    assert relationship["evidence"] == []

    hypothesis = hypothesis_record_for_api({"comparison_group_id": "group", "evidence": "bad"})
    assert hypothesis["status"] == "legacy_unvalidated"
    assert hypothesis["evidence"] == []


def test_persistence_rejects_cross_source_and_non_exact_passage_links(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Exact appraisal links", "domain": "testing"}
    ).json()
    job_json = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How does the program change measured outcomes?",
            "idempotency_key": "typed-appraisal-persistence",
        },
    ).json()

    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_json["id"])
        source_a = Source(job_id=job.id, external_id="source:a", title="A")
        source_b = Source(job_id=job.id, external_id="source:b", title="B")
        db.add_all([source_a, source_b])
        db.flush()
        passage_a = add_test_passage(
            db, source_a, ordinal=1, locator="abstract", content="Source A reports an outcome."
        )
        passage_b = add_test_passage(
            db, source_b, ordinal=1, locator="abstract", content="Source B reports an outcome."
        )
        db.flush()
        claim_a = Claim(
            job_id=job.id,
            source_id=source_a.id,
            passage_id=passage_a.id,
            text=passage_a.content,
        )
        claim_b = Claim(
            job_id=job.id,
            source_id=source_b.id,
            passage_id=passage_b.id,
            text=passage_b.content,
        )
        db.add_all([claim_a, claim_b])
        db.commit()

        wrong_source_appraisal = SourceMethodologicalAppraisalV1.model_validate(
            {
                "schema_version": 1,
                "status": "model_assessed_not_independently_verified",
                "fields": {
                    "design_type": {
                        "value": "Randomized trial",
                        "passage_ids": [passage_b.id],
                        "status": "model_assessed_not_independently_verified",
                    }
                },
            }
        )
        with pytest.raises(ValueError, match="passage outside its source"):
            persist_result(
                db,
                job,
                StageResult(
                    "bad source link",
                    {},
                    "comparison",
                    appraisal_updates={source_a.id: wrong_source_appraisal},
                ),
            )
        db.rollback()

        wrong_claim_appraisal = ClaimAppraisalV1.model_validate(
            {
                "schema_version": 1,
                "methodology_appraisal": {
                    "schema_version": 1,
                    "status": "model_assessed_not_independently_verified",
                    "relationship": "supports",
                    "rationale": "The claim is linked to the wrong source passage.",
                    "passage_ids": [passage_b.id],
                },
                "economic_facets": _economic_facets(),
            }
        )
        with pytest.raises(ValueError, match="exact claim passage"):
            persist_result(
                db,
                job,
                StageResult(
                    "bad claim link",
                    {},
                    "comparison",
                    claim_appraisal_updates={claim_a.id: wrong_claim_appraisal},
                ),
            )
        db.rollback()

        relationship = EvidenceRelationshipV1.model_validate(
            {
                "claim_a_id": claim_a.id,
                "claim_b_id": claim_b.id,
                "relationship_type": "contradicts",
                "scope_alignment": "same",
                "scope_differences": [],
                "rationale": "The claim pair appears inconsistent.",
                "evidence": [
                    {"claim_id": claim_a.id, "passage_ids": [passage_b.id]},
                    {"claim_id": claim_b.id, "passage_ids": [passage_b.id]},
                ],
                "status": "model_assessed_not_independently_verified",
                "schema_version": 1,
                "provider": "fixture",
                "model_name": "fixture/free",
            }
        )
        with pytest.raises(ValueError, match="non-exact claim passage"):
            persist_result(
                db,
                job,
                StageResult(
                    "bad comparison link", {}, "verification", relationships=[relationship]
                ),
            )
        db.rollback()
        assert (
            db.scalar(select(EvidenceRelationship).where(EvidenceRelationship.job_id == job.id))
            is None
        )

        hypotheses = [
            EvidenceHypothesisV1.model_validate(
                {
                    "comparison_group_id": "pair-group",
                    "side": side,
                    "statement": statement,
                    "evidence": [{"claim_id": claim.id, "passage_ids": [passage.id]}],
                    "uncertainty": "The underlying design remains uncertain.",
                    "why_competing": "The explanations differ.",
                    "status": "model_assessed_not_independently_verified",
                    "schema_version": 1,
                    "provider": "fixture",
                    "model_name": "fixture/free",
                }
            )
            for side, statement, claim, passage in (
                ("A", "Training changes use", claim_a, passage_b),
                ("B", "Workflow design changes use", claim_b, passage_b),
            )
        ]
        with pytest.raises(ValueError, match="non-exact claim passage"):
            persist_result(
                db,
                job,
                StageResult("bad hypothesis link", {}, "verification", hypotheses=hypotheses),
            )
        db.rollback()
        assert db.scalar(select(Hypothesis).where(Hypothesis.job_id == job.id)) is None


def test_source_and_claim_api_upcast_legacy_appraisal_without_database_rewrite(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Legacy appraisal API", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What does the stored evidence report?",
            "idempotency_key": "legacy-appraisal-api",
        },
    ).json()
    with client.db_sessions() as db:
        source = Source(
            job_id=job["id"],
            external_id="legacy-source",
            title="Historical study",
            retrieval_status="abstract_only",
        )
        db.add(source)
        db.flush()
        passage = add_test_passage(
            db,
            source,
            ordinal=1,
            locator="abstract",
            content="A historical study reports a result.",
        )
        source.appraisal_json = {
            "status": "model_assessed_not_independently_verified",
            "fields": {
                "design_type": {
                    "value": "Cohort study",
                    "passage_ids": [passage.id],
                    "status": "model_assessed_not_independently_verified",
                }
            },
            "old_annotation_id": "kept-as-extension",
        }
        claim = Claim(
            job_id=job["id"],
            source_id=source.id,
            passage_id=passage.id,
            text=passage.content,
            appraisal_json={
                "extraction": "exact_sentence_from_abstract_excerpt",
                "economic_facets": _economic_facets(),
            },
        )
        db.add(claim)
        db.commit()
        source_id, claim_id = source.id, claim.id

    source_response = client.get(f"/api/v1/sources/{source_id}")
    claim_response = client.get(f"/api/v1/claims/{claim_id}/evidence")
    assert source_response.status_code == 200
    assert source_response.json()["appraisal"]["schema_version"] == 1
    assert source_response.json()["appraisal"]["extensions"]["old_annotation_id"] == (
        "kept-as-extension"
    )
    assert claim_response.status_code == 200
    claim_out = claim_response.json()["claim"]["appraisal"]
    assert claim_out["schema_version"] == 1
    assert claim_out["methodology_appraisal"]["status"] == "not_assessed"

    with client.db_sessions() as db:
        stored_source = db.get(Source, source_id).appraisal_json
        stored_claim = db.get(Claim, claim_id).appraisal_json
        assert "schema_version" not in stored_source
        assert "schema_version" not in stored_claim


def test_claim_evidence_returns_only_methodology_passages_from_the_claim_source(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Method appraisal links", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={"question": "How was the result assessed?", "idempotency_key": "method-links"},
    ).json()
    with client.db_sessions() as db:
        source = Source(job_id=job["id"], external_id="appraised-source", title="Appraised study")
        other_source = Source(job_id=job["id"], external_id="other-source", title="Other study")
        db.add_all([source, other_source])
        db.flush()
        passage = add_test_passage(
            db,
            source,
            ordinal=1,
            locator="page 4, paragraph 2",
            content="The study used a panel design.",
            access_level="full_text_html",
        )
        foreign_passage = add_test_passage(
            db,
            other_source,
            ordinal=1,
            locator="page 8",
            content="Unrelated source passage.",
            access_level="full_text_html",
        )
        claim = Claim(
            job_id=job["id"],
            source_id=source.id,
            passage_id=passage.id,
            text=passage.content,
            appraisal_json={
                "schema_version": 1,
                "extraction": "exact_source_sentence_span",
                "methodology_appraisal": {
                    "schema_version": 1,
                    "status": "model_assessed_not_independently_verified",
                    "relationship": "qualifies",
                    "rationale": "The cited passage describes the study design.",
                    "passage_ids": [passage.id, foreign_passage.id],
                    "provider": "openrouter",
                    "model": "fixture/free",
                },
                "economic_facets": _economic_facets(),
            },
        )
        db.add(claim)
        db.commit()
        claim_id, expected_passage_id, foreign_passage_id = claim.id, passage.id, foreign_passage.id

    response = client.get(f"/api/v1/claims/{claim_id}/evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["claim"]["appraisal"]["methodology_appraisal"]["relationship"] == "qualifies"
    assert [item["id"] for item in body["methodology_passages"]] == [expected_passage_id]
    assert body["methodology_passages"][0]["source_id"] == body["claim"]["source_id"]
    assert body["methodology_passages"][0]["locator"] == "page 4, paragraph 2"
    assert all(item["id"] != foreign_passage_id for item in body["methodology_passages"])
