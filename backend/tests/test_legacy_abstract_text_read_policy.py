import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    Claim,
    EvidenceRelationship,
    Hypothesis,
    Passage,
    ResearchReport,
    RetrievedDocument,
    Source,
)
from app.research.abstract_text_rights import abstract_text_reuse_permitted


@pytest.mark.parametrize("access_level", ["abstract_only", "abstract_excerpt"])
def test_unverified_legacy_abstract_text_is_withheld_from_api_and_exports(client, access_level):
    project = client.post(
        "/api/v1/projects", json={"title": "Historical abstract", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What did the historical abstract report?",
            "idempotency_key": "legacy-abstract-read-policy",
        },
    ).json()
    original_text = "Legacy source wording reports a measured productivity increase."
    text_hash = hashlib.sha256(original_text.encode()).hexdigest()

    with client.db_sessions() as db:
        source = Source(
            job_id=job["id"],
            external_id="doi:10.5555/legacy-abstract",
            title="Historical abstract record",
            doi="10.5555/legacy-abstract",
            retrieval_status="abstract_only",
            abstract_excerpt=original_text,
            metadata_json={"provider": "Crossref"},
            appraisal_json={
                "status": "model_assessed_not_independently_verified",
                "reason": original_text,
            },
        )
        db.add(source)
        db.flush()
        document = RetrievedDocument(
            id=str(uuid4()),
            source_id=source.id,
            identity_key=hashlib.sha256(b"legacy-abstract-document").hexdigest(),
            source_version="abstract-v1",
            document_sha256=text_hash,
            retrieved_at=datetime.now(UTC),
            locator="Crossref abstract metadata",
            media_type="text/plain",
            access_class="abstract_only",
            hash_scope="normalized_text",
        )
        db.add(document)
        db.flush()
        passage = Passage(
            id=str(uuid4()),
            source_id=source.id,
            document_id=document.id,
            identity_key=text_hash,
            ordinal=0,
            locator="Abstract sentence 1",
            content=original_text,
            content_hash=text_hash,
            access_level=access_level,
        )
        db.add(passage)
        db.flush()
        claim = Claim(
            job_id=job["id"],
            source_id=source.id,
            passage_id=passage.id,
            text=original_text,
            span_start=0,
            span_end=len(original_text),
        )
        db.add(claim)
        db.flush()
        comparison_claim = Claim(
            job_id=job["id"],
            source_id=source.id,
            passage_id=passage.id,
            text="A separately worded source-reported claim.",
        )
        db.add(comparison_claim)
        db.flush()
        relationship = EvidenceRelationship(
            job_id=job["id"],
            claim_a_id=claim.id,
            claim_b_id=comparison_claim.id,
            relationship_type="qualifies",
            scope_alignment="same",
            scope_differences_json=[],
            rationale=original_text,
            evidence_json=[
                {"claim_id": claim.id, "passage_ids": [passage.id]},
                {"claim_id": comparison_claim.id, "passage_ids": [passage.id]},
            ],
            status="model_assessed_not_independently_verified",
            schema_version=1,
        )
        hypothesis = Hypothesis(
            job_id=job["id"],
            comparison_group_id=str(uuid4()),
            side="A",
            statement=original_text,
            evidence_json=[{"claim_id": claim.id, "passage_ids": [passage.id]}],
            uncertainty=original_text,
            why_competing=original_text,
            status="model_assessed_not_independently_verified",
            schema_version=1,
        )
        report = ResearchReport(
            job_id=job["id"],
            status="completed",
            body_markdown=f"# Historical finding\n\n{original_text} [S1]",
            citation_map_json={
                "S1": {
                    "source_id": source.id,
                    "title": source.title,
                    "doi": source.doi,
                    "url": None,
                    "passages": [passage.id],
                }
            },
            verification_json={"report_schema_version": 1},
        )
        db.add_all([relationship, hypothesis, report])
        db.commit()
        source_id, passage_id, claim_id, report_id = (
            source.id,
            passage.id,
            claim.id,
            report.id,
        )
        stored_job_id = job["id"]

    source_response = client.get(f"/api/v1/sources/{source_id}")
    assert source_response.status_code == 200
    assert source_response.json()["abstract_excerpt"] is None
    assert source_response.json()["abstract_text_retention_status"] == "legacy_not_recorded"
    assert source_response.json()["appraisal"]["status"] == "legacy_unassessed"
    assert original_text not in source_response.text

    passage_response = client.get(f"/api/v1/passages/{passage_id}")
    assert passage_response.status_code == 200
    assert original_text not in passage_response.text
    claim_response = client.get(f"/api/v1/claims/{claim_id}/evidence")
    assert claim_response.status_code == 200
    assert original_text not in claim_response.text
    relationship_response = client.get(f"/api/v1/research-jobs/{stored_job_id}/relationships")
    assert relationship_response.status_code == 200
    assert original_text not in relationship_response.text
    hypothesis_response = client.get(f"/api/v1/research-jobs/{stored_job_id}/hypotheses")
    assert hypothesis_response.status_code == 200
    assert original_text not in hypothesis_response.text

    report_response = client.get(f"/api/v1/reports/{report_id}")
    assert report_response.status_code == 200
    assert original_text not in report_response.text
    assert report_response.json()["evidence_content_withheld"] is True
    assert report_response.json()["citation_map"]["S1"]["passages"] == [passage_id]
    markdown_export = client.get(f"/api/v1/reports/{report_id}/export?format=markdown")
    assert markdown_export.status_code == 200
    assert original_text not in markdown_export.text
    account_export = client.get("/api/v1/me/export")
    assert account_export.status_code == 200
    assert original_text not in account_export.text

    with client.db_sessions() as db:
        persisted_source = db.scalar(select(Source).where(Source.id == source_id))
        persisted_passage = db.scalar(select(Passage).where(Passage.id == passage_id))
        persisted_claim = db.scalar(select(Claim).where(Claim.id == claim_id))
        persisted_report = db.scalar(select(ResearchReport).where(ResearchReport.id == report_id))
        assert persisted_source is not None and persisted_source.abstract_excerpt == original_text
        assert persisted_passage is not None and persisted_passage.content == original_text
        assert persisted_claim is not None and persisted_claim.text == original_text
        assert persisted_report is not None and original_text in persisted_report.body_markdown
        persisted_source.metadata_json = {
            "provider": "Crossref",
            "abstract_text_version_id": "abstract-v1",
            "abstract_text_rights_decision_v1": {
                "schema_version": 1,
                "decision": "PERMITTED",
                "scope": "item_version_text_retention_and_display",
                "source_id": source_id,
                "source_identity": "doi:10.5555/legacy-abstract",
                "source_version_id": "abstract-v1",
                "text_sha256": text_hash,
                "license_id": "cc-by-4.0",
                "evidence_url": "https://repository.example/license-record",
                "decided_at": "2026-10-31T12:00:00Z",
            },
        }
        db.commit()

    permitted_source = client.get(f"/api/v1/sources/{source_id}").json()
    assert permitted_source["abstract_excerpt"] == original_text
    assert client.get(f"/api/v1/passages/{passage_id}").json()["content"] == original_text
    permitted_report = client.get(f"/api/v1/reports/{report_id}").json()
    assert permitted_report["evidence_content_withheld"] is False
    assert original_text in permitted_report["body_markdown"]
    permitted_relationship = client.get(
        f"/api/v1/research-jobs/{stored_job_id}/relationships"
    ).json()["items"][0]
    assert permitted_relationship["rationale"] == original_text
    permitted_hypothesis = client.get(f"/api/v1/research-jobs/{stored_job_id}/hypotheses").json()[
        "items"
    ][0]
    assert permitted_hypothesis["statement"] == original_text


def test_abstract_text_display_requires_a_grant_bound_to_source_version_and_text():
    text = "A rights-verified abstract excerpt."
    source = SimpleNamespace(
        id="source-1",
        external_id="doi:10.5555/rights-test",
        abstract_excerpt=text,
        metadata_json={
            "abstract_text_version_id": "accepted-manuscript-v2",
            "abstract_text_rights_decision_v1": {
                "schema_version": 1,
                "decision": "PERMITTED",
                "scope": "item_version_text_retention_and_display",
                "source_id": "source-1",
                "source_identity": "doi:10.5555/rights-test",
                "source_version_id": "accepted-manuscript-v2",
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "license_id": "cc-by-4.0",
                "evidence_url": "https://repository.example/license-record",
                "decided_at": "2026-10-31T12:00:00Z",
            },
        },
    )
    assert abstract_text_reuse_permitted(source, text)
    assert not abstract_text_reuse_permitted(source, text + " changed")
    source.metadata_json["abstract_text_rights_decision_v1"]["source_id"] = "another-source"
    assert not abstract_text_reuse_permitted(source, text)
