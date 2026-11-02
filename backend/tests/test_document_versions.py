import hashlib

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from support import add_test_passage

from app.models import Passage, RetrievedDocument, Source
from app.research import workflow
from app.research.depth import PROFILES
from app.research.document_identity import document_identity, passage_identity
from app.schemas import CheckpointEnvelopeV1, RetrievedDocumentRecordV1, versioned_checkpoint


def test_document_and_passage_identity_is_stable_but_version_scoped():
    source_id = "50000000-0000-4000-8000-000000000005"
    document_args = {
        "source_id": source_id,
        "source_version": "publishedVersion",
        "document_sha256": "a" * 64,
        "media_type": "text/html",
        "access_class": "full_text_html",
    }
    first_document = document_identity(**document_args)
    assert document_identity(**document_args) == first_document
    passage_args = {
        "source_id": source_id,
        "document_id": first_document[0],
        "locator": "HTML paragraph 4, sentence 2",
        "content_sha256": hashlib.sha256(b"A reported result.").hexdigest(),
    }
    first_passage = passage_identity(**passage_args)
    assert passage_identity(**passage_args) == first_passage

    revised_document = document_identity(
        **{**document_args, "source_version": "acceptedVersion", "document_sha256": "b" * 64}
    )
    revised_passage = passage_identity(**{**passage_args, "document_id": revised_document[0]})
    assert revised_document[0] != first_document[0]
    assert revised_passage[0] != first_passage[0]


def test_retrieved_document_record_rejects_unverified_shapes():
    record = RetrievedDocumentRecordV1(
        id="50000000-0000-4000-8000-000000000005",
        source_id="50000000-0000-4000-8000-000000000006",
        identity_key="c" * 64,
        source_version="publishedVersion",
        document_sha256="a" * 64,
        retrieved_at="2026-10-29T10:00:00Z",
        locator="HTML landing page on example.org",
        media_type="text/html",
        access_class="full_text_html",
        hash_scope="raw_document_bytes",
    )
    assert record.schema_version == 1
    with pytest.raises(ValidationError):
        RetrievedDocumentRecordV1.model_validate(
            {**record.model_dump(), "document_sha256": "unknown"}
        )
    with pytest.raises(ValidationError):
        RetrievedDocumentRecordV1.model_validate({**record.model_dump(), "unreviewed_field": True})


def test_checkpoint_v1_preserves_legacy_keys_and_validates_known_fields():
    legacy = {"workflow_version": 1, "older_stage_key": {"x": 1}}
    versioned = versioned_checkpoint(legacy)
    assert versioned["schema_version"] == 1
    assert versioned["extensions"]["older_stage_key"] == {"x": 1}
    assert CheckpointEnvelopeV1.model_validate(versioned)
    with pytest.raises((ValidationError, ValueError)):
        versioned_checkpoint({"schema_version": 7, "workflow_version": 1})

    malformed_legacy = versioned_checkpoint({"workflow_version": 1, "depth_profile": "corrupt"})
    assert "depth_profile" not in malformed_legacy
    assert malformed_legacy["extensions"]["invalid_legacy_sections"]["depth_profile"] == "corrupt"
    with pytest.raises((ValidationError, ValueError)):
        versioned_checkpoint({"workflow_version": 1, "depth_profile": "corrupt"}, strict=True)


def _valid_plan_checkpoint() -> dict:
    result = workflow.execute_stage(
        None,
        {
            "id": "checkpoint-plan-contract",
            "question": "What evidence informs this bounded decision?",
            "scope": {"decision_objective": "consider a pilot"},
            "depth": "quick",
            "depth_profile": PROFILES["quick"].as_dict(),
            "attempt": 0,
            "current_stage": "planning",
            "checkpoint": {},
        },
    )
    return result.checkpoint_update.model_dump(mode="json")["plan"]


def test_checkpoint_v1_validates_each_known_section_and_preserves_plan_generations():
    plan_v4 = _valid_plan_checkpoint()
    plan_v3 = dict(plan_v4)
    plan_v3.pop("planning_provenance")
    plan_v3["schema_version"] = 3
    plan_v3["version"] = 3
    plan_v3["planning_mode"] = "deterministic_bounded_no_model"
    legacy_plan_v2 = dict(plan_v3)
    legacy_plan_v2.pop("planning_lenses")
    legacy_plan_v2["schema_version"] = 2
    legacy_plan_v2["version"] = 2
    legacy_plan_v2["subquestions"] = legacy_plan_v2["subquestions"][:5]
    follow_up = {
        "schema_version": 1,
        "parent_job_id": "parent-job",
        "parent_question": "What was the earlier question?",
        "parent_report_id": None,
        "parent_report_status": None,
        "reused_claim_ids": ["claim-1"],
        "reuse_method": "lexical_token_overlap_top8_with_parent_evidence",
        "reuse_boundary": "Context only; retrieve and link new evidence.",
    }
    citation_map = {
        "S1": {
            "source_id": "source-1",
            "title": "A source",
            "doi": None,
            "url": "https://example.org/source",
            "passages": ["passage-1"],
        }
    }
    checkpoint = {
        "workflow_version": 1,
        "depth_profile": PROFILES["quick"].as_dict(),
        "follow_up_context": follow_up,
        "plan": plan_v3,
        "citation_audit": {
            "level": "deterministic_link_integrity_only",
            "claims_checked": 1,
            "claims_with_valid_source_and_passage": 1,
            "status": "passed",
            "semantic_support_check": "not_performed",
            "uncited_material_claim_scan": "not_performed",
        },
        "citation_map": citation_map,
        "retrieval_continuation": {
            "schema_version": 1,
            "parent_job_id": "parent-job",
            "budget_ceiling_usd": 0.0,
            "retries": [
                {"parent_source_id": "old-source", "source_id": "new-source", "kind": "html"}
            ],
            "evidence_copy_boundary": "Copy prior evidence with lineage; retry only due URLs.",
        },
        "deferred_retrieval_retry": {"sources": [{"source_id": "new-source", "kinds": ["html"]}]},
    }

    versioned = versioned_checkpoint(checkpoint, strict=True)

    assert versioned["depth_profile"] == PROFILES["quick"].as_dict()
    assert versioned["plan"]["version"] == 3
    assert versioned["citation_map"] == citation_map
    assert versioned["deferred_retrieval_retry"]["schema_version"] == 1
    assert CheckpointEnvelopeV1.model_validate(versioned)
    assert versioned_checkpoint({"plan": plan_v4}, strict=True)["plan"]["version"] == 4
    assert versioned_checkpoint({"plan": legacy_plan_v2}, strict=True)["plan"]["version"] == 2


def test_checkpoint_v1_rejects_oversized_objects_and_bounds_nested_extensions():
    with pytest.raises(ValueError, match="256 KiB"):
        versioned_checkpoint({"legacy": ["x" * 16_000 for _ in range(17)]})

    extension_checkpoint = versioned_checkpoint(
        {
            "citation_map": {
                "S1": {
                    "source_id": "source-1",
                    "title": "A source",
                    "passages": [],
                    "unexpected": "x",
                }
            }
        },
        strict=True,
    )
    assert extension_checkpoint["citation_map"]["S1"]["extensions"] == {"unexpected": "x"}
    with pytest.raises((ValidationError, ValueError)):
        versioned_checkpoint(
            {
                "citation_map": {
                    "S1": {
                        "source_id": "source-1",
                        "title": "A source",
                        "passages": "not-an-array",
                    }
                }
            },
            strict=True,
        )

    invalid_plan = _valid_plan_checkpoint()
    invalid_plan["resource_limits"]["max_queries"] = "3"
    with pytest.raises((ValidationError, ValueError)):
        versioned_checkpoint({"plan": invalid_plan}, strict=True)


def test_identical_passages_from_different_versions_are_not_conflated(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Passage versions", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How does an updated version report this outcome?",
            "idempotency_key": "passage-versioning",
        },
    ).json()
    with client.db_sessions() as db:
        source = Source(
            job_id=job["id"],
            external_id="fixture:versioned-source",
            title="Versioned source",
            retrieval_status="abstract_only",
        )
        db.add(source)
        db.flush()
        old_passage = add_test_passage(
            db,
            source,
            ordinal=0,
            locator="p. 4",
            content="The study reports a measured effect.",
            source_version="accepted-v1",
        )
        new_passage = add_test_passage(
            db,
            source,
            ordinal=0,
            locator="p. 4",
            content="The study reports a measured effect.",
            source_version="published-v2",
        )
        db.commit()
        passages = list(
            db.scalars(select(Passage).where(Passage.source_id == source.id).order_by(Passage.id))
        )
        documents = list(
            db.scalars(select(RetrievedDocument).where(RetrievedDocument.source_id == source.id))
        )
        assert len(passages) == 2
        assert len({passage.id for passage in passages}) == 2
        assert len({passage.document_id for passage in passages}) == 2
        assert {document.source_version for document in documents} == {
            "accepted-v1",
            "published-v2",
        }
        assert old_passage.id != new_passage.id
