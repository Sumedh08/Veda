import json

from sqlalchemy import select
from support import add_test_passage

from app.models import Claim, JobEvent, Source
from app.providers.llm import MAX_PROMPT_CHARS, ProviderUsage
from app.research import workflow
from app.research.depth import PROFILES
from app.research.llm_tasks import (
    DecisionImplicationDraft,
    ReportFinding,
    ResearchReportDraft,
    SemanticReportAudit,
    SemanticSupportAssessment,
    UncitedMaterialClaim,
)


def _usage():
    return ProviderUsage(
        provider="openrouter",
        model="fixture/free",
        input_tokens=400,
        output_tokens=120,
        reported_cost_usd=0,
        estimated_cost_usd=0,
        latency_ms=1,
    )


def _seed_report_records(client):
    project = client.post(
        "/api/v1/projects", json={"title": "Citation audit", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "Does the intervention improve the measured outcome?",
            "idempotency_key": "semantic-audit-job-01",
        },
    ).json()
    with client.db_sessions() as db:
        source = Source(
            job_id=job["id"],
            external_id="fixture:semantic-audit",
            title="A study about the intervention",
            retrieval_status="abstract_only",
        )
        db.add(source)
        db.flush()
        passage = add_test_passage(
            db,
            source,
            ordinal=1,
            locator="abstract excerpt",
            content="The study reports a 10 percent improvement in the measured outcome.",
        )
        db.flush()
        claim = Claim(
            job_id=job["id"],
            source_id=source.id,
            passage_id=passage.id,
            text=passage.content,
        )
        db.add(claim)
        db.commit()
        result = {
            "job": {
                "id": job["id"],
                "question": job["question"],
                "scope": {},
                "checkpoint": {
                    "citation_audit": {
                        "level": "deterministic_link_integrity_only",
                        "status": "passed",
                        "claims_checked": 1,
                        "claims_with_valid_source_and_passage": 1,
                    }
                },
                "budget_ceiling_usd": 0,
                "cost_spent_estimate_usd": 0,
                "attempt": 1,
            },
            "citation_map": {
                "S1": {
                    "source_id": source.id,
                    "title": source.title,
                    "doi": None,
                    "url": None,
                    "passages": [passage.id],
                }
            },
            "claim_id": claim.id,
            "passage_id": passage.id,
        }
    return result


def test_report_pipeline_runs_separate_semantic_and_deterministic_checks(client, monkeypatch):
    seeded = _seed_report_records(client)
    seeded["job"]["scope"] = {"decision_objective": "Whether to pilot the intervention"}
    schemas = []

    def call_structured(_db, _job, *, schema_name, **_kwargs):
        schemas.append(schema_name)
        if schema_name == "veda_report_draft_v4":
            report_payload = json.loads(_kwargs["user"])
            assert report_payload["material_evidence_requirements"][0]["requirement_id"] == "Q1"
            assert report_payload["material_evidence_requirements"][0]["text"]
            value = ResearchReportDraft(
                schema_version=4,
                findings=[
                    ReportFinding(
                        heading="Reported outcome",
                        statement="The study reports a 10 percent improvement in the measured outcome.",
                        claim_ids=[seeded["claim_id"]],
                        requirement_ids=["Q1", "Q99"],
                    )
                ],
                qualifications=[],
                decision_implications=[
                    DecisionImplicationDraft(
                        action="collect_more_evidence",
                        condition="If effects differ across settings",
                        rationale="The stored abstract gives a limited view of the evidence.",
                        assumptions=["The abstract may omit relevant subgroup results."],
                        unknowns=["Local implementation costs are not stated."],
                        claim_ids=[seeded["claim_id"]],
                        requirement_ids=["Q1"],
                    ),
                    DecisionImplicationDraft(
                        action="scale",
                        condition="If the intervention is adopted broadly",
                        rationale="The study reports a result.",
                        assumptions=["The study is representative."],
                        unknowns=["The causal estimate is incomplete."],
                        claim_ids=[seeded["claim_id"]],
                    ),
                ],
                unanswered_questions=[],
                company_specific_inputs=[],
            )
        else:
            assert schema_name == "veda_semantic_report_audit_v1"
            value = SemanticReportAudit(
                schema_version=1,
                support_assessments=[
                    SemanticSupportAssessment(
                        item_id="F1",
                        verdict="supported",
                        rationale="The passage reports this outcome and magnitude.",
                        passage_ids=[seeded["passage_id"]],
                    ),
                    SemanticSupportAssessment(
                        item_id="D1",
                        verdict="partially_supported",
                        rationale="The cited passage reports a result, while the implication remains conditional.",
                        passage_ids=[seeded["passage_id"]],
                    ),
                ],
                uncited_material_claims=[
                    UncitedMaterialClaim(
                        text="The study reports a 10 percent improvement in the measured outcome.",
                        section="Findings",
                        recommendation="none",
                    )
                ],
            )
        return value, _usage()

    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workflow, "_call_structured", call_structured)
    with client.db_sessions() as db:
        report, _, _ = workflow._build_model_report(db, seeded["job"], seeded["citation_map"])

    body, _citation_map, verification, model_name = report
    assert schemas == ["veda_report_draft_v4", "veda_semantic_report_audit_v1"]
    assert model_name == "fixture/free"
    assert verification["finding_to_claim_links"] == "deterministic_checked"
    assert (
        verification["semantic_support_check"]
        == "performed_model_assisted_not_independently_verified"
    )
    assert verification["uncited_material_claim_scan"] == "performed_model_assisted_not_guaranteed"
    assert verification["semantic_audit_items"][0]["passage_ids"] == [seeded["passage_id"]]
    assert verification["semantic_audit_items"][0]["requirement_ids"] == ["Q1"]
    assert verification["invalid_material_requirement_mappings"] == 1
    assert [item["kind"] for item in verification["semantic_audit_items"]] == [
        "finding",
        "decision_implication",
    ]
    assert (
        verification["decision_implication_status"]
        == "accepted_with_deterministic_scope_and_evidence_gates"
    )
    assert [item["action"] for item in verification["decision_implications"]] == [
        "collect_more_evidence"
    ]
    assert verification["rejected_decision_implications"] == 1
    assert "Conditional decision implications" in body
    assert "scale" not in [item["action"] for item in verification["decision_implications"]]
    assert len(verification["uncited_material_claims"]) == 1
    assert "cannot guarantee completeness" in body


def test_semantic_audit_prompt_respects_the_saved_depth_character_limit(client, monkeypatch):
    captured: dict[str, str] = {}

    def capture(_db, _job, *, system, user, **_kwargs):
        captured["system"] = system
        captured["user"] = user
        return "fixture_prompt_capture"

    monkeypatch.setattr(workflow, "_model_call_blocker", capture)
    passage_a = "A source reports a bounded method and outcome. " * 8
    passage_b = "A second source reports a different population and measure. " * 8
    seeded = _seed_report_records(client)
    monkeypatch.setattr(workflow, "_model_call_blocker", capture)
    with client.db_sessions() as db:
        result = workflow._audit_report_semantics(
            db,
            {
                "id": seeded["job"]["id"],
                "depth": "quick",
                "depth_profile": PROFILES["quick"].as_dict(),
                "checkpoint": {},
            },
            [
                {
                    "item_id": "F1",
                    "kind": "finding",
                    "text": "Two reports describe different outcomes.",
                    "claim_ids": ["C1", "C2"],
                }
            ],
            scan_text="A material report sentence. " * 600,
            claim_passages={
                "C1": {
                    "claim_id": "C1",
                    "passage_id": "P1",
                    "passage": passage_a,
                    "source_title": "Study A",
                },
                "C2": {
                    "claim_id": "C2",
                    "passage_id": "P2",
                    "passage": passage_b,
                    "source_title": "Study B",
                },
            },
        )

    assert result["semantic_audit_skip_reason"] == "fixture_prompt_capture"
    assert (
        len(captured["system"]) + len(captured["user"])
        <= PROFILES["quick"].max_prompt_characters_per_call
    )
    payload = json.loads(captured["user"])
    assert len(payload["report_text_for_uncited_material_claim_scan"]) < len(
        "A material report sentence. " * 600
    )


def test_semantic_audit_rejects_foreign_links_and_missing_items(client, monkeypatch):
    seeded = _seed_report_records(client)
    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        workflow,
        "_call_structured",
        lambda *_args, **_kwargs: (
            SemanticReportAudit(
                schema_version=1,
                support_assessments=[
                    SemanticSupportAssessment(
                        item_id="F1",
                        verdict="supported",
                        rationale="A valid-looking answer with a foreign passage.",
                        passage_ids=["foreign-passage"],
                    )
                ],
                uncited_material_claims=[],
            ),
            _usage(),
        ),
    )
    items = [
        {"item_id": "F1", "kind": "finding", "text": "Claim one", "claim_ids": ["C1"]},
        {"item_id": "F2", "kind": "finding", "text": "Claim two", "claim_ids": ["C2"]},
    ]
    claims = {
        "C1": {
            "claim_id": "C1",
            "passage_id": "P1",
            "claim_text": "Claim one",
            "passage": "Evidence one",
            "source_title": "Study one",
        },
        "C2": {
            "claim_id": "C2",
            "passage_id": "P2",
            "claim_text": "Claim two",
            "passage": "Evidence two",
            "source_title": "Study two",
        },
    }
    with client.db_sessions() as db:
        result = workflow._audit_report_semantics(
            db,
            {"id": seeded["job"]["id"]},
            items,
            scan_text="## Findings\nClaim one [S1]\nClaim two [S2]",
            claim_passages=claims,
        )
    by_id = {item["item_id"]: item for item in result["semantic_audit_items"]}
    assert result["semantic_support_check"] == "needs_review"
    assert by_id["F1"]["status"] == "needs_review"
    assert by_id["F1"]["passage_ids"] == []
    assert by_id["F2"]["status"] == "needs_review"
    assert result["rejected_semantic_audit_records"] == 1


def test_report_suppresses_conditional_implications_without_decision_objective(client, monkeypatch):
    seeded = _seed_report_records(client)
    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)

    def call_structured(_db, _job, *, schema_name, **_kwargs):
        if schema_name == "veda_report_draft_v4":
            return (
                ResearchReportDraft(
                    schema_version=4,
                    findings=[
                        ReportFinding(
                            heading="Reported outcome",
                            statement="The passage describes an improvement.",
                            claim_ids=[seeded["claim_id"]],
                        )
                    ],
                    qualifications=[],
                    decision_implications=[
                        DecisionImplicationDraft(
                            action="collect_more_evidence",
                            condition="Before making a decision",
                            rationale="The evidence has limits.",
                            assumptions=["The retrieved abstract is incomplete."],
                            unknowns=["Implementation outcomes are unavailable."],
                            claim_ids=[seeded["claim_id"]],
                        )
                    ],
                    unanswered_questions=[],
                    company_specific_inputs=[],
                ),
                _usage(),
            )
        return (
            SemanticReportAudit(
                schema_version=1,
                support_assessments=[],
                uncited_material_claims=[],
            ),
            _usage(),
        )

    monkeypatch.setattr(workflow, "_call_structured", call_structured)
    with client.db_sessions() as db:
        report, _, _ = workflow._build_model_report(db, seeded["job"], seeded["citation_map"])
    body, _, verification, _ = report
    assert verification["decision_implication_status"] == "not_in_scope"
    assert verification["decision_implications"] == []
    assert "Conditional decision implications" not in body


def test_numeric_support_gate_rejects_effects_absent_from_linked_claims(client):
    seeded = _seed_report_records(client)
    claim = Claim(
        job_id=seeded["job"]["id"],
        source_id=seeded["citation_map"]["S1"]["source_id"],
        passage_id=seeded["passage_id"],
        text="The study reports a change in the measured outcome.",
    )
    assert workflow._unsupported_numeric_tokens("A 25% effect was reported.", [claim]) == ["25%"]
    assert workflow._unsupported_numeric_tokens("A 10% effect was reported.", [claim]) == ["10%"]
    claim.text = "The study reports a 10 percent improvement."
    assert (
        workflow._unsupported_numeric_tokens("The study reports a 10% improvement.", [claim]) == []
    )


def test_uncited_scan_only_keeps_exact_report_quotes(client, monkeypatch):
    seeded = _seed_report_records(client)
    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        workflow,
        "_call_structured",
        lambda *_args, **_kwargs: (
            SemanticReportAudit(
                schema_version=1,
                support_assessments=[
                    SemanticSupportAssessment(
                        item_id="F1",
                        verdict="partially_supported",
                        rationale="The stated percentage is not present in the evidence.",
                        passage_ids=["P1"],
                    )
                ],
                uncited_material_claims=[
                    UncitedMaterialClaim(
                        text="Invented: 99 percent improvement",
                        section="Findings",
                        recommendation="remove_or_rewrite",
                    )
                ],
            ),
            _usage(),
        ),
    )
    with client.db_sessions() as db:
        result = workflow._audit_report_semantics(
            db,
            {"id": seeded["job"]["id"]},
            [{"item_id": "F1", "kind": "finding", "text": "A result", "claim_ids": ["C1"]}],
            scan_text="## Findings\nA result [S1]",
            claim_passages={
                "C1": {
                    "claim_id": "C1",
                    "passage_id": "P1",
                    "claim_text": "A result",
                    "passage": "Evidence",
                    "source_title": "Study",
                }
            },
        )
    assert result["uncited_material_claim_scan"] == "performed_model_assisted_not_guaranteed"
    assert result["uncited_material_claims"] == []
    assert result["rejected_semantic_audit_records"] == 1


def test_provider_or_quota_block_leaves_audit_explicitly_not_run(client, monkeypatch):
    seeded = _seed_report_records(client)
    monkeypatch.setattr(
        workflow, "_model_call_blocker", lambda *_args, **_kwargs: "daily model-call quota is full"
    )
    with client.db_sessions() as db:
        result = workflow._audit_report_semantics(
            db,
            {"id": seeded["job"]["id"]},
            [{"item_id": "F1", "kind": "finding", "text": "A result", "claim_ids": ["C1"]}],
            scan_text="A result [S1]",
            claim_passages={
                "C1": {
                    "claim_id": "C1",
                    "passage_id": "P1",
                    "claim_text": "A result",
                    "passage": "Evidence",
                    "source_title": "Study",
                }
            },
        )
    assert result["semantic_support_check"] == "not_performed"
    assert result["uncited_material_claim_scan"] == "not_performed"
    assert result["semantic_audit_skip_reason"] == "daily model-call quota is full"


def test_audit_input_chunks_complete_report_text_without_losing_accepted_batches(
    client, monkeypatch
):
    seeded = _seed_report_records(client)
    captured = []
    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)

    def call_structured(_db, _job, *, system, user, **_kwargs):
        payload = json.loads(user)
        captured.append((len(system) + len(user), system, payload))
        return (
            SemanticReportAudit(
                schema_version=1,
                support_assessments=[
                    SemanticSupportAssessment(
                        item_id=item["item_id"],
                        verdict="supported",
                        rationale="The supplied passage supports this wording.",
                        passage_ids=["P1"],
                    )
                    for item in payload["items_for_passage_support_review"]
                ],
                uncited_material_claims=[],
            ),
            _usage(),
        )

    monkeypatch.setattr(workflow, "_call_structured", call_structured)
    with client.db_sessions() as db:
        scan_text = "A result [S1]\n" + ("Additional text. " * 2000)
        job = {
            "id": seeded["job"]["id"],
            "depth": "quick",
            "depth_profile": PROFILES["quick"].as_dict(),
        }
        result = workflow._audit_report_semantics(
            db,
            job,
            [{"item_id": "F1", "kind": "finding", "text": "A result", "claim_ids": ["C1"]}],
            scan_text=scan_text,
            claim_passages={
                "C1": {
                    "claim_id": "C1",
                    "passage_id": "P1",
                    "claim_text": "A result",
                    "passage": "Evidence",
                    "source_title": "Study",
                }
            },
        )
        coverage = result["semantic_audit_batch_coverage"]
        assert (
            workflow._audit_report_semantics(
                db,
                job,
                [{"item_id": "F1", "kind": "finding", "text": "A result", "claim_ids": ["C1"]}],
                scan_text=scan_text,
                claim_passages={
                    "C1": {
                        "claim_id": "C1",
                        "passage_id": "P1",
                        "claim_text": "A result",
                        "passage": "Evidence",
                        "source_title": "Study",
                    }
                },
            )
            == result
        )

    assert len(captured) == coverage["expected_batches"] > 1
    assert all(
        characters <= min(MAX_PROMPT_CHARS, PROFILES["quick"].max_prompt_characters_per_call)
        for characters, _system, _payload in captured
    )
    ranges = sorted(
        (batch["scan_start"], batch["scan_end"])
        for _characters, _system, payload in captured
        for batch in [payload]
        if batch["scan_end"] > batch["scan_start"]
    )
    assert coverage["uncovered_scan_start"] is None, coverage
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(scan_text)
    assert all(left[1] >= right[0] for left, right in zip(ranges, ranges[1:], strict=False))
    assert coverage["complete"] is True
    assert coverage["completed_batches"] == coverage["expected_batches"]
    assert result["uncited_material_claim_scan"] == "performed_model_assisted_not_guaranteed"
    assert result["uncited_scan_input_truncated"] is False
    assert (
        result["semantic_audit_items"][0]["status"] == "model_assessed_not_independently_verified"
    )
    assert (
        len(
            [
                event
                for event in db.scalars(
                    select(JobEvent).where(
                        JobEvent.job_id == seeded["job"]["id"],
                        JobEvent.event_type == "semantic_audit_batch",
                    )
                )
            ]
        )
        == coverage["expected_batches"]
    )


def test_semantic_audit_failure_keeps_completed_batch_and_never_resends_uncertain_batch(
    client, monkeypatch
):
    seeded = _seed_report_records(client)
    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)
    calls = 0

    def call_structured(_db, _job, *, user, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise workflow.WorkflowError("model_call_uncertain", "sanitized fixture failure")
        payload = json.loads(user)
        return (
            SemanticReportAudit(
                schema_version=1,
                support_assessments=[
                    SemanticSupportAssessment(
                        item_id=item["item_id"],
                        verdict="supported",
                        rationale="The supplied passage supports this wording.",
                        passage_ids=["P1"],
                    )
                    for item in payload["items_for_passage_support_review"]
                ],
                uncited_material_claims=[],
            ),
            _usage(),
        )

    monkeypatch.setattr(workflow, "_call_structured", call_structured)
    scan_text = "A result [S1]\n" + ("Additional text. " * 2000)
    job = {
        "id": seeded["job"]["id"],
        "depth": "quick",
        "depth_profile": PROFILES["quick"].as_dict(),
    }
    items = [{"item_id": "F1", "kind": "finding", "text": "A result", "claim_ids": ["C1"]}]
    passages = {
        "C1": {
            "claim_id": "C1",
            "passage_id": "P1",
            "claim_text": "A result",
            "passage": "Evidence",
            "source_title": "Study",
        }
    }
    with client.db_sessions() as db:
        result = workflow._audit_report_semantics(
            db, job, items, scan_text=scan_text, claim_passages=passages
        )
        repeated = workflow._audit_report_semantics(
            db, job, items, scan_text=scan_text, claim_passages=passages
        )
        events = list(
            db.scalars(
                select(JobEvent).where(
                    JobEvent.job_id == seeded["job"]["id"],
                    JobEvent.event_type == "semantic_audit_batch",
                )
            )
        )

    assert calls == 2
    assert repeated == result
    assert (
        result["semantic_audit_items"][0]["status"] == "model_assessed_not_independently_verified"
    )
    assert result["semantic_support_check"] == "performed_model_assisted_not_independently_verified"
    assert (
        result["uncited_material_claim_scan"] == "performed_partial_model_assisted_not_guaranteed"
    )
    assert result["semantic_audit_batch_coverage"]["complete"] is False
    assert result["semantic_audit_batch_coverage"]["completed_batches"] == 1
    assert result["semantic_audit_batch_coverage"]["unresolved_batch_ids"]
    assert sorted(event.data_json["semantic_audit_batch_v1"]["status"] for event in events) == [
        "completed",
        "uncertain",
    ]


def test_semantic_audit_stops_when_resolved_model_changes_between_batches(client, monkeypatch):
    seeded = _seed_report_records(client)
    monkeypatch.setattr(workflow, "_model_call_blocker", lambda *_args, **_kwargs: None)
    calls = 0

    def call_structured(_db, _job, *, user, **_kwargs):
        nonlocal calls
        calls += 1
        payload = json.loads(user)
        usage = _usage()
        if calls == 2:
            usage = ProviderUsage(
                provider="openrouter",
                model="a-different-resolved-route:free",
                input_tokens=425,
                output_tokens=96,
                reported_cost_usd=0.0,
                estimated_cost_usd=0.0,
                latency_ms=2,
            )
        return (
            SemanticReportAudit(
                schema_version=1,
                support_assessments=[
                    SemanticSupportAssessment(
                        item_id=item["item_id"],
                        verdict="supported",
                        rationale="The supplied passage supports this wording.",
                        passage_ids=["P1"],
                    )
                    for item in payload["items_for_passage_support_review"]
                ],
                uncited_material_claims=[],
            ),
            usage,
        )

    monkeypatch.setattr(workflow, "_call_structured", call_structured)
    job = {
        "id": seeded["job"]["id"],
        "depth": "quick",
        "depth_profile": PROFILES["quick"].as_dict(),
        "model_provider": "openrouter",
        "model_name": "openrouter/free",
    }
    scan_text = "A result [S1]\n" + ("Additional text. " * 2000)
    with client.db_sessions() as db:
        result = workflow._audit_report_semantics(
            db,
            job,
            [{"item_id": "F1", "kind": "finding", "text": "A result", "claim_ids": ["C1"]}],
            scan_text=scan_text,
            claim_passages={
                "C1": {
                    "claim_id": "C1",
                    "passage_id": "P1",
                    "claim_text": "A result",
                    "passage": "Evidence",
                    "source_title": "Study",
                }
            },
        )
        events = list(
            db.scalars(
                select(JobEvent).where(
                    JobEvent.job_id == seeded["job"]["id"],
                    JobEvent.event_type == "semantic_audit_batch",
                )
            )
        )

    assert calls == 2
    assert (
        result["semantic_audit_items"][0]["status"] == "model_assessed_not_independently_verified"
    )
    assert result["semantic_audit_batch_coverage"]["complete"] is False
    assert result["semantic_audit_batch_coverage"]["unresolved_batch_ids"]
    mismatched = next(
        event.data_json["semantic_audit_batch_v1"]
        for event in events
        if event.data_json["semantic_audit_batch_v1"]["error_class"]
        == "provider_model_identity_changed"
    )
    assert mismatched["model"] == "a-different-resolved-route:free"
    assert mismatched["usage"]["input_tokens"] == 425
    assert mismatched["output"] is None


def test_semantic_audit_schema_rejects_unrecognized_fields():
    try:
        SemanticReportAudit.model_validate(
            {
                "schema_version": 1,
                "support_assessments": [],
                "uncited_material_claims": [],
                "independent_verification": True,
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Unexpected schema fields must be rejected")
