import json
from types import SimpleNamespace

from sqlalchemy import select
from support import add_test_passage

from app.config import Settings
from app.models import Claim, JobEvent, ResearchJob, Source, UsageEntry
from app.providers.llm import LLMProviderError, ProviderUsage
from app.research import workflow
from app.research.llm_tasks import (
    APPRAISAL_FIELD_NAMES,
    AppraisalField,
    ClaimAssessment,
    ClaimEconomicFacetDraft,
    ResearchAppraisalBatch,
    SourceAppraisal,
)


def test_appraisal_partition_splits_large_source_claim_set_without_duplicate_source_owner():
    source = SimpleNamespace(id="source-one")
    passages = [
        (SimpleNamespace(id=f"passage-{index}", content=f"Evidence passage {index}."), source)
        for index in range(10)
    ]
    claims = [
        SimpleNamespace(
            id=f"claim-{index}",
            source_id=source.id,
            passage_id=f"passage-{index}",
            text=f"Claim {index}",
        )
        for index in range(10)
    ]

    batches = workflow._partition_appraisal_inputs(passages, claims)

    assert [len(batch.claims) for batch in batches] == [4, 4, 2]
    assert [batch.source_ids_to_appraise for batch in batches] == [[source.id], [], []]
    assert [claim.id for batch in batches for claim in batch.claims] == [
        claim.id for claim in claims
    ]
    assert all(
        claim.passage_id in {passage.id for passage, _source in batch.passages}
        for batch in batches
        for claim in batch.claims
    )


def test_appraisal_is_versioned_and_foreign_or_missing_evidence_stays_unknown(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Appraisal validation", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does the intervention improve measured outcomes?",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "idempotency_key": "appraisal-contract",
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
        persisted_job.current_stage = "appraisal"
        first_source = Source(
            job_id=job["id"],
            external_id="source:first",
            title="First study",
            retrieval_status="abstract_only",
        )
        second_source = Source(
            job_id=job["id"],
            external_id="source:second",
            title="Second study",
            retrieval_status="abstract_only",
        )
        db.add_all([first_source, second_source])
        db.flush()
        first_passage = add_test_passage(
            db,
            first_source,
            ordinal=1,
            locator="abstract excerpt",
            content="The study randomized 120 workers.",
        )
        second_passage = add_test_passage(
            db,
            second_source,
            ordinal=1,
            locator="abstract excerpt",
            content="The study included 42 clinics.",
        )
        db.flush()
        valid_claim = Claim(
            job_id=job["id"],
            source_id=first_source.id,
            passage_id=first_passage.id,
            text=first_passage.content,
            appraisal_json={"extraction": "exact_sentence_from_abstract_excerpt"},
        )
        duplicate_claim = Claim(
            job_id=job["id"],
            source_id=second_source.id,
            passage_id=second_passage.id,
            text=second_passage.content,
        )
        db.add_all([valid_claim, duplicate_claim])
        db.commit()

        output = ResearchAppraisalBatch(
            schema_version=2,
            source_appraisals=[
                SourceAppraisal(
                    source_id=first_source.id,
                    fields=[
                        AppraisalField(
                            name="design_type",
                            value="Randomized trial",
                            passage_ids=[first_passage.id],
                        ),
                        AppraisalField(
                            name="population",
                            value="The study population is adults.",
                            passage_ids=[second_passage.id],
                        ),
                        AppraisalField(name="missingness", value="unknown", passage_ids=[]),
                    ],
                ),
                SourceAppraisal(source_id="invented-source", fields=[]),
                SourceAppraisal(source_id=second_source.id, fields=[]),
                SourceAppraisal(source_id=second_source.id, fields=[]),
            ],
            claim_assessments=[
                ClaimAssessment(
                    claim_id=valid_claim.id,
                    relationship="supports",
                    rationale="The linked sentence directly reports a measured outcome.",
                    passage_ids=[first_passage.id],
                    evidence_kind="other_study_result",
                    economic_facets=[
                        ClaimEconomicFacetDraft(
                            name="outcome",
                            value="Task completion speed",
                            passage_ids=[first_passage.id],
                        ),
                        ClaimEconomicFacetDraft(
                            name="estimate",
                            value="14 percent faster",
                            passage_ids=[second_passage.id],
                        ),
                    ],
                ),
                ClaimAssessment(
                    claim_id="invented-claim",
                    relationship="supports",
                    rationale="Not a stored claim.",
                    passage_ids=[first_passage.id],
                    evidence_kind="unknown",
                    economic_facets=[],
                ),
                ClaimAssessment(
                    claim_id=duplicate_claim.id,
                    relationship="supports",
                    rationale="Duplicate one.",
                    passage_ids=[second_passage.id],
                    evidence_kind="unknown",
                    economic_facets=[],
                ),
                ClaimAssessment(
                    claim_id=duplicate_claim.id,
                    relationship="contradicts",
                    rationale="Duplicate two.",
                    passage_ids=[second_passage.id],
                    evidence_kind="unknown",
                    economic_facets=[],
                ),
            ],
        )
        usage = ProviderUsage(
            provider="openrouter",
            model="fixture/free",
            input_tokens=50,
            output_tokens=30,
            reported_cost_usd=0.0,
            estimated_cost_usd=0.0,
            latency_ms=1,
            response_repair="markdown_json_fence_removed",
        )

    class FixtureProvider:
        def complete_json(self, **kwargs):
            assert kwargs["schema_name"] == "veda_appraisal_batch_v2"
            request = json.loads(kwargs["user"])
            submitted_claims = {item["claim_id"]: item for item in request["claims"]}
            assert submitted_claims[valid_claim.id]["passage_id"] == first_passage.id
            assert "schema_version 2" in kwargs["system"]
            assert "omit every unknown or unreported field" in kwargs["system"]
            return SimpleNamespace(value=output, usage=usage)

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", FixtureProvider)
    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted_job))
        workflow.persist_result(db, persisted_job, result)
        db.commit()

        source_result = db.get(Source, first_source.id).appraisal_json
        fields = source_result["fields"]
        assert source_result["schema_version"] == 1
        assert fields["design_type"]["value"] == "Randomized trial"
        assert fields["design_type"]["passage_ids"] == [first_passage.id]
        assert fields["population"]["value"] == "unknown"
        assert fields["population"]["passage_ids"] == []
        assert fields["missingness"]["value"] == "unknown"
        assert fields["comparator"]["value"] == "unknown"

        duplicate_source_result = db.get(Source, second_source.id).appraisal_json
        assert duplicate_source_result["status"] == "needs_review"
        assert duplicate_source_result["fields"]["design_type"]["value"] == "unknown"

        claims = {
            claim.id: claim for claim in db.scalars(select(Claim).where(Claim.job_id == job["id"]))
        }
        assert claims[valid_claim.id].appraisal_json["extraction"] == (
            "exact_sentence_from_abstract_excerpt"
        )
        claim_assessment = claims[valid_claim.id].appraisal_json["methodology_appraisal"]
        assert claim_assessment["schema_version"] == 1
        assert claim_assessment["status"] == "model_assessed_not_independently_verified"
        assert claim_assessment["passage_ids"] == [first_passage.id]
        facets = claims[valid_claim.id].appraisal_json["economic_facets"]
        assert facets["schema_version"] == 1
        assert facets["evidence_kind"] == "other_study_result"
        assert facets["facets"]["outcome"]["value"] == "Task completion speed"
        assert facets["facets"]["outcome"]["passage_ids"] == [first_passage.id]
        assert facets["facets"]["estimate"]["value"] == "unknown"
        assert facets["facets"]["estimate"]["passage_ids"] == []
        duplicate_assessment = claims[duplicate_claim.id].appraisal_json["methodology_appraisal"]
        assert duplicate_assessment["status"] == "needs_review"
        assert duplicate_assessment["relationship"] == "insufficient"
        usage_row = db.scalar(
            select(UsageEntry).where(
                UsageEntry.job_id == job["id"], UsageEntry.operation == "veda_appraisal_batch_v2"
            )
        )
        assert usage_row is not None
        assert usage_row.response_repair == "markdown_json_fence_removed"


def test_appraisal_schema_requires_explicit_version_and_rejects_unknown_fields():
    try:
        ResearchAppraisalBatch.model_validate({"source_appraisals": [], "claim_assessments": []})
    except Exception as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("schema version must be mandatory")

    try:
        ResearchAppraisalBatch.model_validate(
            {
                "schema_version": 2,
                "source_appraisals": [],
                "claim_assessments": [],
                "unexpected": "value",
            }
        )
    except Exception as exc:
        assert "unexpected" in str(exc)
    else:
        raise AssertionError("extra schema fields must be rejected")

    try:
        ResearchAppraisalBatch.model_validate(
            {"schema_version": 1, "source_appraisals": [], "claim_assessments": []}
        )
    except Exception as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("old appraisal schema versions must be rejected")


def test_official_statistics_facets_are_descriptive_transcriptions_only():
    source = SimpleNamespace(
        title="Employment rate",
        metadata_json={
            "provider_metadata": {
                "statistics": {
                    "indicator_name": "Employment rate",
                    "indicator_id": "EMP.RATE",
                    "observations": [
                        {
                            "value": "62.4",
                            "period": "2024",
                            "geography_name": "India",
                            "geography_code": "IND",
                            "unit_measure": "percent",
                            "unit_multiplier": 0,
                        }
                    ],
                }
            }
        },
    )
    passage_id = "stored-statistics-passage"
    statement = (
        "India (IND), 2024 — Employment rate: 62.4 (measure code percent). "
        "This is a descriptive reported statistic, not a causal estimate."
    )
    appraisal = workflow._descriptive_statistic_facets(source, statement, passage_id)
    assert appraisal["evidence_kind"] == "descriptive_statistic"
    assert appraisal["facets"]["outcome"]["value"] == "Employment rate (EMP.RATE)"
    assert appraisal["facets"]["estimate"]["value"] == "62.4 (percent)"
    assert appraisal["facets"]["uncertainty"]["value"] == "unknown"
    assert appraisal["facets"]["estimate"]["passage_ids"] == [passage_id]


def test_appraisal_batches_balance_sources_and_preserve_first_batch_on_uncertain_failure(
    client, monkeypatch
):
    project = client.post(
        "/api/v1/projects", json={"title": "Batched appraisal", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What methods and outcomes do these studies report?",
            "depth": "standard",
            "model_provider": "openrouter",
            "model_name": "openrouter/free",
            "budget_ceiling_usd": 0,
            "idempotency_key": "partial-appraisal-batch",
        },
    ).json()
    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openrouter",
            openrouter_api_key="fixture-only",
            openrouter_model="openrouter/free",
            max_daily_model_calls=20,
            max_daily_model_calls_per_user=20,
        ),
    )

    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        persisted_job.current_stage = "appraisal"
        persisted_profile = dict(workflow.profile_for_job("standard").as_dict())
        persisted_profile["max_model_calls"] = 6
        persisted_profile["max_output_token_budget_total"] = 6 * 8192
        persisted_checkpoint = dict(persisted_job.checkpoint_json)
        persisted_checkpoint["depth_profile"] = persisted_profile
        persisted_job.checkpoint_json = persisted_checkpoint
        source_ids = []
        for index in range(11):
            source = Source(
                job_id=job["id"],
                external_id=f"source:batch-{index}",
                title=f"Study {index}",
                retrieval_status="abstract_only",
            )
            db.add(source)
            db.flush()
            passage = add_test_passage(
                db,
                source,
                ordinal=1,
                locator="abstract excerpt",
                content=f"Study {index} reports its sample and measured outcome.",
            )
            db.add(
                Claim(
                    job_id=job["id"],
                    source_id=source.id,
                    passage_id=passage.id,
                    text=passage.content,
                )
            )
            source_ids.append(source.id)
        db.commit()

    accepted_source_ids = set()
    accepted_claim_ids = set()
    call_count = 0
    active_db = None

    class PartialBatchProvider:
        def complete_json(self, **kwargs):
            nonlocal call_count, active_db
            call_count += 1
            assert kwargs["schema_name"] == "veda_appraisal_batch_v2"
            if call_count == 1:
                assert active_db is not None
                plan_event = active_db.scalar(
                    select(JobEvent).where(
                        JobEvent.job_id == job["id"],
                        JobEvent.event_type == "resource_plan",
                    )
                )
                assert plan_event is not None
                assert plan_event.data_json["plan_timing"] == "before_first_appraisal_dispatch"
            if call_count == 2:
                raise LLMProviderError(
                    "fixture timeout after first batch",
                    code="provider_timeout",
                    outcome_uncertain=True,
                )
            submitted = json.loads(kwargs["user"])
            accepted_source_ids.update(item["source_id"] for item in submitted["sources"])
            accepted_claim_ids.update(item["claim_id"] for item in submitted["claims"])
            value = ResearchAppraisalBatch(
                schema_version=2,
                source_appraisals=[
                    SourceAppraisal(source_id=item["source_id"], fields=[])
                    for item in submitted["sources"]
                ],
                claim_assessments=[
                    ClaimAssessment(
                        claim_id=item["claim_id"],
                        relationship="supports",
                        rationale="The exact passage reports this claim.",
                        passage_ids=[item["passage_id"]],
                        evidence_kind="other_study_result",
                        economic_facets=[],
                    )
                    for item in submitted["claims"]
                ],
            )
            return SimpleNamespace(
                value=value,
                usage=ProviderUsage(
                    provider="openrouter",
                    model="fixture/free",
                    input_tokens=100,
                    output_tokens=60,
                    reported_cost_usd=0.0,
                    estimated_cost_usd=0.0,
                    latency_ms=1,
                ),
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "configured_provider", PartialBatchProvider)
    with client.db_sessions() as db:
        active_db = db
        persisted_job = db.get(ResearchJob, job["id"])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted_job))
        event_data = result.event_data.model_dump(mode="json")
        assert event_data["appraisal_status"] == "partial"
        assert event_data["appraisal_batches_completed"] == 1
        assert event_data["appraisal_batches_total"] == 6
        assert event_data["appraisal_batches_planned"] == 3
        assert event_data["model_execution_plan"]["required_calls"] == 9
        assert event_data["model_execution_plan"]["planned_calls"] == 6
        assert event_data["model_execution_plan"]["complete"] is False
        assert event_data["model_execution_plan"]["latency_estimate_ms"] is None
        assert event_data["model_execution_plan"]["authorized_spend_currency"] == "USD"
        assert any(
            item["deferred_reason"] == "request_quota"
            for item in event_data["model_execution_plan"]["deferred"]
        )
        workflow.persist_result(db, persisted_job, result)
        db.commit()

        saved_sources = {
            item.id: item.appraisal_json
            for item in db.scalars(select(Source).where(Source.job_id == job["id"]))
        }
        saved_claims = {
            item.id: item.appraisal_json
            for item in db.scalars(select(Claim).where(Claim.job_id == job["id"]))
        }
        usage_rows = list(
            db.scalars(
                select(UsageEntry)
                .where(UsageEntry.job_id == job["id"])
                .order_by(UsageEntry.created_at, UsageEntry.id)
            )
        )

    assert call_count == 2
    assert accepted_source_ids and accepted_claim_ids
    assert accepted_source_ids < set(source_ids)
    assert all(
        saved_sources[source_id]["status"] == "model_assessed_not_independently_verified"
        for source_id in accepted_source_ids
    )
    assert all(
        saved_sources[source_id]["status"] == "not_assessed"
        for source_id in set(source_ids) - accepted_source_ids
    )
    assert all(
        saved_claims[claim_id]["methodology_appraisal"]["status"]
        == "model_assessed_not_independently_verified"
        for claim_id in accepted_claim_ids
    )
    assert len(usage_rows) == 2
    assert usage_rows[0].succeeded is True
    assert usage_rows[1].error_class == "provider_timeout"
    assert usage_rows[1].finish_reason is None
    assert usage_rows[1].reported_cost_usd is None
    assert usage_rows[1].estimated_cost_usd is None


def test_disabled_appraisal_persists_every_missing_field_as_unknown(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Unknown appraisal", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={"question": "What is not reported?", "idempotency_key": "unknown-appraisal"},
    ).json()
    monkeypatch.setattr(workflow, "settings", Settings(llm_provider="disabled"))

    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        persisted_job.current_stage = "appraisal"
        source = Source(
            job_id=job["id"],
            external_id="source:unassessed",
            title="Abstract-only evidence",
            retrieval_status="abstract_only",
        )
        db.add(source)
        db.flush()
        passage = add_test_passage(
            db,
            source,
            ordinal=1,
            locator="abstract excerpt",
            content="The study reports an outcome.",
        )
        db.flush()
        claim = Claim(
            job_id=job["id"],
            source_id=source.id,
            passage_id=passage.id,
            text=passage.content,
            appraisal_json={"extraction": "exact_sentence_from_abstract_excerpt"},
        )
        db.add(claim)
        db.commit()

        result = workflow.execute_stage(db, workflow.job_snapshot(persisted_job))
        workflow.persist_result(db, persisted_job, result)
        db.commit()

        appraisal = db.get(Source, source.id).appraisal_json
        assert appraisal["schema_version"] == 1
        assert appraisal["status"] == "not_performed"
        assert set(appraisal["fields"]) == set(APPRAISAL_FIELD_NAMES)
        assert all(field["value"] == "unknown" for field in appraisal["fields"].values())
        assert (
            db.get(Claim, claim.id).appraisal_json["methodology_appraisal"]["status"]
            == "not_performed"
        )
