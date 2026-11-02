import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.providers.llm import ProviderUsage
from app.research.candidate_relevance import score_candidate_relevance
from app.research.document_identity import document_identity, passage_identity
from app.research.workflow import StageResult, _extracted_claim_units, persist_result
from app.schemas import (
    CandidateOccurrenceV1,
    ConditionalStatisticsRoutingV1,
    ExtractedClaimV1,
    ExtractedPassageV1,
    JobEventDataV1,
    ReportCitationMapV1,
    RetrievedDocumentRecordV1,
    ScholarlyWorkRecordV1,
    candidate_relevance_for_api,
)


def _candidate():
    query = "AI workforce productivity"
    title = "AI adoption and workforce productivity"
    abstract = "AI tools may change measured worker productivity."
    record = {
        "external_id": "doi:10.5555/veda.1",
        "title": title,
        "doi": "10.5555/veda.1",
        "url": "https://doi.org/10.5555/veda.1",
        "authors": [{"given": "Rao", "family": "Example"}],
        "published_year": 2025,
        "publisher": "Example Press",
        "abstract_excerpt": abstract,
        "query": query,
        "provider": "Crossref",
        "provider_metadata": {"schema_version": 1, "extensions": {}},
        "source_type": "scholarly_article",
    }
    return {
        "schema_version": 1,
        "candidate_key": "a" * 64,
        "record": record,
        "canonical_identity": "doi:10.5555/veda.1",
        "relevance": score_candidate_relevance(query, title, abstract),
        "disposition": "selected",
        "reason_code": "selected_by_relevance",
        "canonical_external_id": record["external_id"],
        "discovered_at": datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
        "ranking_order": 1,
    }


def test_stage_result_builds_typed_bounded_event_candidate_and_citation_records():
    result = StageResult(
        "Discovery completed.",
        {"status": "ready", "provider_queries_attempted": 1, "future_metric": "kept"},
        "extraction",
        sources=[_candidate()["record"]],
        candidates=[_candidate()],
        citation_map={
            "S1": {
                "source_id": "source-1",
                "title": "Example source",
                "passages": ["passage-1"],
            }
        },
    )

    assert isinstance(result.event_data, JobEventDataV1)
    assert result.event_data["data_schema_version"] == 1
    assert result.event_data["future_metric"] == "kept"
    assert isinstance(result.sources[0], ScholarlyWorkRecordV1)
    assert isinstance(result.candidates[0], CandidateOccurrenceV1)
    assert isinstance(result.candidates[0].relevance.score, float)
    assert result.candidates[0].source_governance is None
    assert isinstance(result.citation_map, ReportCitationMapV1)
    assert result.citation_map.citations["S1"].passages == ["passage-1"]


def test_stage_result_rejects_malformed_or_oversized_dynamic_payloads():
    with pytest.raises(ValueError, match="64 KiB"):
        StageResult(
            "Oversized event.",
            {f"metric_{index}": "x" * 15_000 for index in range(5)},
            "extraction",
        )

    with pytest.raises((ValueError, ValidationError)):
        StageResult("Bad cite map.", {}, "synthesis", citation_map={"citation": {}})

    malformed_candidate = _candidate()
    malformed_candidate["reason_code"] = "source_limit"
    with pytest.raises(ValidationError):
        CandidateOccurrenceV1.model_validate(malformed_candidate)

    with pytest.raises(ValidationError):
        ScholarlyWorkRecordV1.model_validate(
            {**_candidate()["record"], "unexpected_field": "not accepted"}
        )


def test_conditional_statistics_routing_contract_separates_skips_and_provider_results():
    route = ConditionalStatisticsRoutingV1.model_validate(
        {
            "schema_version": 1,
            "world_bank_data360": {
                "schema_version": 1,
                "status": "not_applicable",
                "reason_code": "unsupported_topic",
            },
            "ilostat": {
                "schema_version": 1,
                "status": "searched",
                "requests": 1,
                "results": 0,
                "failures": 1,
            },
        }
    )
    assert route.world_bank_data360.status == "not_applicable"
    assert route.world_bank_data360.reason_code == "unsupported_topic"
    assert route.ilostat.status == "searched"
    assert route.ilostat.results == 0
    assert route.ilostat.failures == 1

    with pytest.raises(ValidationError, match="one request"):
        ConditionalStatisticsRoutingV1.model_validate(
            {
                "schema_version": 1,
                "world_bank_data360": {
                    "schema_version": 1,
                    "status": "searched",
                    "requests": 0,
                },
                "ilostat": {
                    "schema_version": 1,
                    "status": "not_attempted",
                    "reason_code": "deadline_elapsed",
                },
            }
        )


def test_candidate_api_omits_corrupt_optional_relevance_instead_of_echoing_it():
    valid = candidate_relevance_for_api(_candidate()["relevance"])
    assert valid["algorithm"] == "lexical_overlap_v1"
    assert candidate_relevance_for_api({"score": 9_999, "api_key": "should not echo"}) is None


def _passage_and_document():
    source_id = "11111111-1111-4111-8111-111111111111"
    content = "AI adoption improved worker productivity in this sample."
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    document_id, document_key = document_identity(
        source_id=source_id,
        source_version="provider-v1",
        document_sha256="a" * 64,
        media_type="text/plain",
        access_class="abstract_only",
    )
    document = RetrievedDocumentRecordV1(
        id=document_id,
        source_id=source_id,
        identity_key=document_key,
        source_version="provider-v1",
        document_sha256="a" * 64,
        retrieved_at=datetime(2026, 10, 29, tzinfo=UTC),
        locator="provider abstract excerpt",
        media_type="text/plain",
        access_class="abstract_only",
        hash_scope="bounded_provider_excerpt",
    )
    passage_id, passage_key = passage_identity(
        source_id=source_id,
        document_id=document_id,
        locator="abstract excerpt",
        content_sha256=content_hash,
    )
    passage = ExtractedPassageV1(
        id=passage_id,
        source_id=source_id,
        document_id=document_id,
        identity_key=passage_key,
        identity_version=1,
        ordinal=0,
        locator="abstract excerpt",
        content=content,
        content_hash=content_hash,
        truncated=False,
        access_level="abstract_only",
    )
    return document, passage


def test_stage_result_validates_document_passage_identity_and_exact_claim_spans():
    document, passage = _passage_and_document()
    claims = _extracted_claim_units(passage)
    result = StageResult(
        "Extracted source evidence.",
        {},
        "appraisal",
        documents=[document],
        passages=[passage],
        claims=claims,
    )

    assert result.documents[0].id == document.id
    assert isinstance(result.passages[0], ExtractedPassageV1)
    assert isinstance(result.claims[0], ExtractedClaimV1)
    assert (
        result.claims[0].unit.text
        == passage.content[result.claims[0].unit.start : result.claims[0].unit.end]
    )


def test_stage_result_rejects_tampered_passage_hash_and_foreign_claim_source():
    document, passage = _passage_and_document()
    tampered = passage.model_copy(update={"content": "tampered text"})
    with pytest.raises(ValidationError, match="content hash"):
        StageResult(
            "Malformed passage.",
            {},
            "appraisal",
            documents=[document],
            passages=[tampered],
        )

    claim = _extracted_claim_units(passage)[0].model_copy(
        update={"source_id": "22222222-2222-4222-8222-222222222222"}
    )
    with pytest.raises(ValueError, match="same-source passage"):
        StageResult(
            "Malformed claim.",
            {},
            "appraisal",
            documents=[document],
            passages=[passage],
            claims=[claim],
        )


def test_stage_result_revalidates_mutable_records_at_the_persistence_boundary():
    document, passage = _passage_and_document()
    result = StageResult(
        "Extracted source evidence.",
        {},
        "appraisal",
        documents=[document],
        passages=[passage],
        claims=_extracted_claim_units(passage),
    )
    result.passages[0].content = "changed after construction"

    with pytest.raises(ValidationError, match="content hash"):
        persist_result(None, None, result)


def test_retrieved_document_metadata_has_the_same_bounded_json_contract():
    document, _passage = _passage_and_document()
    with pytest.raises(ValidationError, match="64 KiB"):
        RetrievedDocumentRecordV1.model_validate(
            {
                **document.model_dump(mode="python"),
                "metadata": {f"part_{index}": "x" * 15_000 for index in range(5)},
            }
        )


def test_stage_result_requires_bounded_provider_usage_records():
    with pytest.raises(TypeError, match="ProviderUsage"):
        StageResult("Invalid usage record.", {}, "comparison", usage={"provider": "openrouter"})

    with pytest.raises(ValueError, match="finite"):
        ProviderUsage(
            provider="openrouter",
            model="fixture/free",
            input_tokens=1,
            output_tokens=1,
            reported_cost_usd=float("nan"),
            estimated_cost_usd=0.0,
            latency_ms=1,
        )
