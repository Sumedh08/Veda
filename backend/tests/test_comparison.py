from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from support import add_test_passage

from app.config import Settings
from app.models import Claim, EvidenceRelationship, Hypothesis, Passage, ResearchJob, Source
from app.providers.llm import ProviderUsage
from app.research import workflow
from app.research.llm_tasks import (
    ClaimRelationshipDraft,
    ComparisonEvidenceLink,
    CompetingHypothesesDraft,
    GroundedHypothesisDraft,
    ReportFinding,
    ReportQualification,
    ResearchComparisonBatch,
)


def test_comparison_rationale_rejects_truncated_provider_text():
    with pytest.raises(ValidationError):
        ClaimRelationshipDraft(
            claim_a_id="claim-a",
            claim_b_id="claim-b",
            relationship="qualifies",
            scope_alignment="unknown",
            scope_differences=[],
            rationale="The experiment reports a task-speed gain (passage f78029fa",
            evidence=[
                ComparisonEvidenceLink(claim_id="claim-a", passage_ids=["passage-a"]),
                ComparisonEvidenceLink(claim_id="claim-b", passage_ids=["passage-b"]),
            ],
        )


@pytest.mark.parametrize(
    "model,kwargs,field_limit",
    [
        (ReportFinding, {"heading": "Finding"}, 240),
        (ReportQualification, {}, 220),
    ],
)
def test_report_sentences_at_the_structured_field_limit_are_not_accepted(
    model, kwargs, field_limit
):
    with pytest.raises(ValidationError):
        model(statement=("x" * (field_limit - 1)) + ".", claim_ids=["claim-a"], **kwargs)


def test_report_comparison_omits_incomplete_persisted_rationale():
    relationship = SimpleNamespace(
        id="relationship-a",
        claim_a_id="claim-a",
        claim_b_id="claim-b",
        relationship_type="qualifies",
        scope_alignment="unknown",
        scope_differences_json=[],
        rationale="The experiment reports a task-speed gain (passage f78029fa",
    )

    class RelationshipRows:
        def __init__(self):
            self.calls = 0

        def scalars(self, _statement):
            self.calls += 1
            return iter([relationship] if self.calls == 1 else [])

    claim_rows = [
        (
            SimpleNamespace(id="claim-a", text="Claim A reports a measured outcome."),
            SimpleNamespace(id="source-a"),
            SimpleNamespace(id="passage-a"),
        ),
        (
            SimpleNamespace(id="claim-b", text="Claim B describes a different scope."),
            SimpleNamespace(id="source-b"),
            SimpleNamespace(id="passage-b"),
        ),
    ]
    lines, status = workflow._report_comparison_section(
        RelationshipRows(),
        "job-a",
        source_to_cite={"source-a": "S1", "source-b": "S2"},
        claim_sources={"claim-a": "source-a", "claim-b": "source-b"},
        claim_rows=claim_rows,
    )

    rendered = "\n".join(lines)
    assert status["relationships_rendered"] == 1
    assert "task-speed gain (passage f78029fa" not in rendered
    assert "stored rationale was incomplete" in rendered
    assert "The classification is provisional and model-assisted." not in rendered


def test_comparison_persists_grounded_relations_and_rejects_fake_or_mis_scoped_links(
    client, monkeypatch
):
    project = client.post(
        "/api/v1/projects", json={"title": "Evidence comparison", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How does adoption affect productivity?",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "idempotency_key": "comparison-contract",
        },
    ).json()
    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openrouter",
            openrouter_api_key="fixture-only",
            openrouter_model="openrouter/free",
            max_daily_model_calls=10,
            max_daily_model_calls_per_user=10,
        ),
    )

    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        persisted_job.current_stage = "comparison"
        sources = [
            Source(
                job_id=job["id"],
                external_id=f"source:{index}",
                title=f"Study {index}",
                published_year=2024 + index,
                retrieval_status="abstract_only",
            )
            for index in range(5)
        ]
        db.add_all(sources)
        db.flush()
        passages = [
            add_test_passage(
                db,
                source,
                ordinal=1,
                locator="abstract excerpt",
                content=f"Study {index} reports a productivity result.",
            )
            for index, source in enumerate(sources)
        ]
        db.flush()
        for index, (source, passage) in enumerate(zip(sources, passages, strict=True)):
            if index == 4:
                source.appraisal_json = {}
                continue
            scope_values = {
                "population": "warehouse workers" if index < 2 else "operations managers",
                "geography": "United States",
                "time_period": "2022 to 2024",
                "intervention_or_exposure": "AI assistant adoption",
                "comparator": "no AI assistant",
                "outcomes": "worker productivity",
                "measure": "tasks completed per hour",
            }
            source.appraisal_json = {
                "schema_version": 1,
                "status": "model_assessed_not_independently_verified",
                "fields": {
                    name: {
                        "value": value,
                        "passage_ids": [passage.id],
                        "status": "model_assessed_not_independently_verified",
                    }
                    for name, value in scope_values.items()
                },
            }
        claims = [
            Claim(
                job_id=job["id"],
                source_id=source.id,
                passage_id=passage.id,
                text=passage.content,
            )
            for source, passage in zip(sources, passages, strict=True)
        ]
        db.add_all(claims)
        db.commit()

        claim_ids = [claim.id for claim in claims]
        passage_ids = [passage.id for passage in passages]
        output = ResearchComparisonBatch(
            schema_version=1,
            relationships=[
                ClaimRelationshipDraft(
                    claim_a_id=claim_ids[0],
                    claim_b_id=claim_ids[1],
                    relationship="contradicts",
                    scope_alignment="same",
                    scope_differences=[],
                    rationale="The passages report opposite results for the same outcome.",
                    evidence=[
                        ComparisonEvidenceLink(claim_id=claim_ids[0], passage_ids=[passage_ids[0]]),
                        ComparisonEvidenceLink(claim_id=claim_ids[1], passage_ids=[passage_ids[1]]),
                    ],
                ),
                ClaimRelationshipDraft(
                    claim_a_id=claim_ids[2],
                    claim_b_id=claim_ids[3],
                    relationship="contradicts",
                    scope_alignment="different",
                    scope_differences=["population"],
                    rationale="The studies address different populations.",
                    evidence=[
                        ComparisonEvidenceLink(claim_id=claim_ids[2], passage_ids=[passage_ids[2]]),
                        ComparisonEvidenceLink(claim_id=claim_ids[3], passage_ids=[passage_ids[3]]),
                    ],
                ),
                ClaimRelationshipDraft(
                    claim_a_id=claim_ids[0],
                    claim_b_id=claim_ids[2],
                    relationship="contradicts",
                    scope_alignment="same",
                    scope_differences=[],
                    rationale="Stored population fields show a scope difference.",
                    evidence=[
                        ComparisonEvidenceLink(claim_id=claim_ids[0], passage_ids=[passage_ids[0]]),
                        ComparisonEvidenceLink(claim_id=claim_ids[2], passage_ids=[passage_ids[2]]),
                    ],
                ),
                ClaimRelationshipDraft(
                    claim_a_id=claim_ids[0],
                    claim_b_id=claim_ids[3],
                    relationship="contradicts",
                    scope_alignment="same",
                    scope_differences=[],
                    rationale="This includes an unrelated passage link.",
                    evidence=[
                        ComparisonEvidenceLink(claim_id=claim_ids[0], passage_ids=[passage_ids[1]]),
                        ComparisonEvidenceLink(claim_id=claim_ids[3], passage_ids=[passage_ids[3]]),
                    ],
                ),
                ClaimRelationshipDraft(
                    claim_a_id=claim_ids[0],
                    claim_b_id=claim_ids[4],
                    relationship="contradicts",
                    scope_alignment="same",
                    scope_differences=[],
                    rationale="The model cannot establish missing source scope details.",
                    evidence=[
                        ComparisonEvidenceLink(claim_id=claim_ids[0], passage_ids=[passage_ids[0]]),
                        ComparisonEvidenceLink(claim_id=claim_ids[4], passage_ids=[passage_ids[4]]),
                    ],
                ),
                ClaimRelationshipDraft(
                    claim_a_id="invented-claim-a",
                    claim_b_id=claim_ids[1],
                    relationship="contradicts",
                    scope_alignment="same",
                    scope_differences=[],
                    rationale="An arbitrary ID must not be stored.",
                    evidence=[
                        ComparisonEvidenceLink(
                            claim_id="invented-claim-a", passage_ids=[passage_ids[0]]
                        ),
                        ComparisonEvidenceLink(claim_id=claim_ids[1], passage_ids=[passage_ids[1]]),
                    ],
                ),
            ],
            competing_hypotheses=[
                CompetingHypothesesDraft(
                    hypothesis_a=GroundedHypothesisDraft(
                        statement="Productivity gains occur when training enables workers to use the tool.",
                        evidence=[
                            ComparisonEvidenceLink(
                                claim_id=claim_ids[0], passage_ids=[passage_ids[0]]
                            )
                        ],
                        uncertainty="The abstract does not identify the training mechanism.",
                    ),
                    hypothesis_b=GroundedHypothesisDraft(
                        statement="Productivity gains depend mainly on task standardization.",
                        evidence=[
                            ComparisonEvidenceLink(
                                claim_id=claim_ids[1], passage_ids=[passage_ids[1]]
                            )
                        ],
                        uncertainty="The underlying study details were not retrieved.",
                    ),
                    why_competing="Both propose different explanations for observed productivity gains.",
                ),
                CompetingHypothesesDraft(
                    hypothesis_a=GroundedHypothesisDraft(
                        statement="Same evidence one.",
                        evidence=[
                            ComparisonEvidenceLink(
                                claim_id=claim_ids[2], passage_ids=[passage_ids[2]]
                            )
                        ],
                        uncertainty="Not established.",
                    ),
                    hypothesis_b=GroundedHypothesisDraft(
                        statement="Same evidence two.",
                        evidence=[
                            ComparisonEvidenceLink(
                                claim_id=claim_ids[2], passage_ids=[passage_ids[2]]
                            )
                        ],
                        uncertainty="Not established.",
                    ),
                    why_competing="Overlapping evidence must not create a competing pair.",
                ),
            ],
        )
        usage = ProviderUsage(
            provider="openrouter",
            model="fixture/free",
            input_tokens=80,
            output_tokens=50,
            reported_cost_usd=0.0,
            estimated_cost_usd=0.0,
            latency_ms=1,
        )

    class FixtureProvider:
        def complete_json(self, **kwargs):
            assert kwargs["schema_name"] == "veda_comparison_batch_v1"
            return SimpleNamespace(value=output, usage=usage)

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", FixtureProvider)
    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted_job))
        workflow.persist_result(db, persisted_job, result)
        db.commit()

        relationships = list(
            db.query(EvidenceRelationship)
            .filter(EvidenceRelationship.job_id == job["id"])
            .order_by(EvidenceRelationship.claim_a_id)
        )
        assert len(relationships) == 4
        by_pair = {(item.claim_a_id, item.claim_b_id): item for item in relationships}
        assert by_pair[tuple(sorted(claim_ids[:2]))].relationship_type == "contradicts"
        heterogeneity = by_pair[tuple(sorted(claim_ids[2:4]))]
        assert heterogeneity.relationship_type == "heterogeneous"
        assert heterogeneity.scope_differences_json == ["population"]
        assert heterogeneity.status == "model_assessed_not_independently_verified"
        assert all(item["passage_ids"] for item in heterogeneity.evidence_json)
        stored_heterogeneity = by_pair[tuple(sorted((claim_ids[0], claim_ids[2])))]
        assert stored_heterogeneity.relationship_type == "heterogeneous"
        assert stored_heterogeneity.scope_alignment == "different"
        unknown_scope = by_pair[tuple(sorted((claim_ids[0], claim_ids[4])))]
        assert unknown_scope.relationship_type == "incomparable"
        assert unknown_scope.scope_alignment == "unknown"

        hypotheses = list(db.query(Hypothesis).filter(Hypothesis.job_id == job["id"]).all())
        assert len(hypotheses) == 2
        assert {item.side for item in hypotheses} == {"A", "B"}
        assert len({item.comparison_group_id for item in hypotheses}) == 1
        assert all(
            item.status == "model_assessed_not_independently_verified" for item in hypotheses
        )

        claim_rows = list(
            db.execute(
                select(Claim, Source, Passage)
                .join(Source, Claim.source_id == Source.id)
                .join(Passage, Claim.passage_id == Passage.id)
                .where(Claim.job_id == job["id"])
                .order_by(Claim.id)
            )
        )
        claim_sources = {claim.id: source.id for claim, source, _ in claim_rows}
        source_to_cite = {source.id: f"S{index + 1}" for index, source in enumerate(sources)}
        comparison_lines, comparison_status = workflow._report_comparison_section(
            db,
            job["id"],
            source_to_cite=source_to_cite,
            claim_sources=claim_sources,
            claim_rows=claim_rows,
        )
        comparison_text = "\n".join(comparison_lines)
        assert comparison_status["relationships_rendered"] == 4
        assert comparison_status["hypothesis_pairs_rendered"] == 1
        assert "Recorded relationship — contradicts" in comparison_text
        assert "Recorded relationship — heterogeneous" in comparison_text
        assert "Competing explanation pair" in comparison_text
        assert "model-assessed; not independently verified" in comparison_text

        hypotheses[0].evidence_json = [
            {"claim_id": claim_ids[0], "passage_ids": ["foreign-passage"]}
        ]
        db.flush()
        unsafe_lines, unsafe_status = workflow._report_comparison_section(
            db,
            job["id"],
            source_to_cite=source_to_cite,
            claim_sources=claim_sources,
            claim_rows=claim_rows,
        )
        assert unsafe_status["hypothesis_pairs_rendered"] == 0
        assert "Competing explanation pair" not in "\n".join(unsafe_lines)

    relation_response = client.get(f"/api/v1/research-jobs/{job['id']}/relationships")
    hypotheses_response = client.get(f"/api/v1/research-jobs/{job['id']}/hypotheses")
    assert relation_response.status_code == 200
    assert relation_response.json()["status"] == "model_assessed_not_independently_verified"
    assert hypotheses_response.status_code == 200
    assert len(hypotheses_response.json()["items"]) == 2

    relationship_page = client.get(
        f"/api/v1/research-jobs/{job['id']}/relationships?limit=1&offset=0"
    )
    relationship_next_page = client.get(
        f"/api/v1/research-jobs/{job['id']}/relationships?limit=1&offset=1"
    )
    hypothesis_page = client.get(f"/api/v1/research-jobs/{job['id']}/hypotheses?limit=1&offset=0")
    assert relationship_page.status_code == 200
    assert relationship_page.json()["total"] == 4
    assert relationship_page.json()["has_more"] is True
    assert relationship_next_page.json()["has_more"] is True
    assert (
        relationship_next_page.json()["items"][0]["id"]
        != relationship_page.json()["items"][0]["id"]
    )
    assert hypothesis_page.status_code == 200
    assert hypothesis_page.json()["total"] == 2
    assert hypothesis_page.json()["has_more"] is True
    assert hypothesis_page.json()["status"] == hypotheses_response.json()["status"]


def test_comparison_without_model_is_explicitly_unassessed(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "No model comparison", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={"question": "Compare evidence", "idempotency_key": "no-model-comparison"},
    ).json()
    monkeypatch.setattr(workflow, "settings", Settings(llm_provider="disabled"))

    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        persisted_job.current_stage = "comparison"
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted_job))
        assert result.next_stage == "verification"
        assert result.event_data["status"] == "not_assessed"
        assert result.relationships is None
        assert result.hypotheses is None

    assert client.get(f"/api/v1/research-jobs/{job['id']}/hypotheses").json()["items"] == []
    assert client.get(f"/api/v1/research-jobs/{job['id']}/relationships").json()["items"] == []
