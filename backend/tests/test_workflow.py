import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest
from support import add_test_passage

from app.config import Settings
from app.models import Claim, JobEvent, ResearchJob, ResearchReport, Source, utcnow
from app.providers.crossref import CrossrefRecord
from app.providers.ilostat_sdmx import ILOSTATError
from app.providers.openalex import (
    CitationExpansionCandidate,
    CitationExpansionResult,
    OpenAlexError,
)
from app.providers.scholarly import ScholarlyWork, canonical_work_identity
from app.research import workflow
from app.research.depth import PROFILES
from app.schemas import versioned_checkpoint


@pytest.fixture(autouse=True)
def prevent_unspecified_official_statistics_requests(monkeypatch):
    class EmptyOpenAIRE:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, _query, *, limit=8):
            return []

        def search_organizations(self, _query, *, limit=8):
            return []

        def search_organization_publications(self, _organization_ids, *, query, limit=8):
            return []

        def close(self):
            pass

    monkeypatch.setattr(workflow, "OpenAIREProvider", EmptyOpenAIRE)

    class EmptyWorldBankDocuments:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, _query, *, limit=3):
            return []

        def close(self):
            pass

    monkeypatch.setattr(workflow, "WorldBankDocumentsProvider", EmptyWorldBankDocuments)

    class EmptyData360:
        provider_name = "World Bank Data360"

        def __init__(self):
            pass

        def search(self, query, *, limit=1, geography=None):
            return []

        def close(self):
            pass

    monkeypatch.setattr(workflow, "WorldBankData360Provider", EmptyData360)

    class EmptyILOSTAT:
        provider_name = "ILOSTAT"

        def __init__(self):
            pass

        def search(self, query, *, limit=1, geography=None):
            return []

        def close(self):
            pass

    monkeypatch.setattr(workflow, "ILOSTATProvider", EmptyILOSTAT)


class FakeCrossref:
    failure = False

    def __init__(self):
        self.closed = False

    def search(self, query, *, limit=5):
        if self.failure:
            raise workflow.WorkflowError(
                "provider_unavailable", "network unavailable", retryable=True
            )
        folded_query = query.casefold()
        if "population" in folded_query or "employment" in folded_query:
            topic = "population" if "population" in folded_query else "employment"
            second = "employment levels" if topic == "population" else "population levels"
            return [
                CrossrefRecord(
                    external_id=f"fixture:{topic}-trends",
                    title=f"Global {topic} trends and {second}",
                    doi=None,
                    url="https://crossref.example/global-trends",
                    authors=[],
                    published_year=2025,
                    publisher="Example Statistical Review",
                    abstract_excerpt=f"A study of global {topic} trends over time.",
                    query=query,
                )
            ]
        return [
            CrossrefRecord(
                external_id="doi:10.5555/veda-study-1",
                title="A randomized study of an AI worker productivity workflow",
                doi="10.5555/veda-study-1",
                url="https://doi.org/10.5555/veda-study-1",
                authors=[{"given": "Ada", "family": "Researcher"}],
                published_year=2025,
                publisher="Example Academic Press",
                abstract_excerpt=(
                    "In a randomized study, AI increased task completion speed by 14 percent for participating workers. "
                    "The effect varied by worker experience."
                ),
                query=query,
            ),
            CrossrefRecord(
                external_id="doi:10.5555/veda-study-2",
                title="AI implementation costs and worker productivity in small firms",
                doi="10.5555/veda-study-2",
                url="https://doi.org/10.5555/veda-study-2",
                authors=[],
                published_year=2024,
                publisher="Example Academic Press",
                abstract_excerpt=None,
                query=query,
            ),
        ]

    def close(self):
        self.closed = True


def create_project(client):
    response = client.post(
        "/api/v1/projects", json={"title": "AI adoption evidence", "domain": "AI economics"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_job(
    client,
    project_id,
    *,
    idempotency_key="research-start-key-01",
    geography="United States",
    question="What evidence shows whether AI improves worker productivity?",
    model_provider=None,
):
    request = {
        "question": question,
        "population": "customer support workers",
        "geography": geography,
        "depth": "quick",
        "budget_ceiling_usd": 0,
        "idempotency_key": idempotency_key,
    }
    if model_provider is not None:
        request["model_provider"] = model_provider
    response = client.post(f"/api/v1/projects/{project_id}/research-jobs", json=request)
    assert response.status_code == 201, response.text
    return response.json()


def checkpoint_with_queries(job: ResearchJob, queries: list[str]) -> dict:
    planned = workflow.execute_stage(
        None,
        {
            "id": job.id,
            "question": job.question,
            "scope": job.scope_json,
            "depth": job.depth,
            "depth_profile": PROFILES[job.depth].as_dict(),
            "attempt": 0,
            "current_stage": "planning",
            "checkpoint": {},
        },
    ).checkpoint_update.model_dump(mode="json")["plan"]
    plan = deepcopy(planned)
    rationales = []
    for index, query in enumerate(queries):
        focus = "counterevidence" if index == len(queries) - 1 else "direct_evidence"
        template = next(item for item in planned["query_rationales"] if item["focus"] == focus)
        rationales.append({**template, "query": query})
    plan["queries"] = queries
    plan["query_rationales"] = rationales
    return versioned_checkpoint(
        {
            "workflow_version": 1,
            "depth_profile": PROFILES[job.depth].as_dict(),
            "plan": plan,
        },
        strict=True,
    )


class FakeOpenAlexEmpty:
    def __init__(self, **_kwargs):
        pass

    def search(self, _query, *, limit=5):
        return []

    def close(self):
        pass


class FakeData360:
    provider_name = "World Bank Data360"
    failure = False
    blocked = False

    def __init__(self):
        pass

    def search(self, query, *, limit=1, geography=None):
        assert limit == 1
        assert geography == "World"
        if self.failure:
            raise workflow.WorkflowError("data360_unavailable", "sanitized failure", retryable=True)
        metadata = {
            "statistics": {
                "indicator_id": "WB_WDI_SP_POP_TOTL",
                "indicator_name": "Population, total",
                "database_id": "WB_WDI",
                "dataset_name": "World Development Indicators",
                "dataset_url": "https://datacatalog.worldbank.org/example",
                "dataset_terms_url": "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
                "license": None if self.blocked else "CC BY-4.0",
                "license_url": None
                if self.blocked
                else "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "World Bank: World Development Indicators (WDI): United Nations.",
                "definition": "Total population counts all residents.",
                "statistical_concept": None,
                "methodology": "Census and demographic estimates.",
                "limitations": "Some observations are modeled estimates.",
                "periodicity": "Annual",
                "source_update_date": None,
                "retrieved_at": "2026-10-29T00:00:00+00:00",
                "data_sources": [
                    {
                        "name": "World Population Prospects",
                        "organization": "United Nations",
                        "publisher": None,
                        "url": "https://population.un.org/wpp/",
                    }
                ],
                "observations": []
                if self.blocked
                else [
                    {
                        "value": "8215424893",
                        "period": "2025",
                        "geography_code": "WLD",
                        "geography_name": "World",
                        "unit_measure": "PS",
                        "unit_type": None,
                        "unit_multiplier": 0,
                        "observation_status": "A",
                    }
                ],
            },
            **({"selection_block_reason": "license_not_verified"} if self.blocked else {}),
        }
        return [
            ScholarlyWork(
                external_id="data360:WB_WDI:WB_WDI_SP_POP_TOTL:WLD",
                title="Population, total — World Development Indicators (World Bank)",
                doi=None,
                url="https://data360api.worldbank.org/data360/data?INDICATOR=WB_WDI_SP_POP_TOTL",
                authors=[],
                published_year=None if self.blocked else 2025,
                publisher="World Bank",
                abstract_excerpt=None,
                query=query,
                provider=self.provider_name,
                provider_metadata=metadata,
                source_type="official_statistics",
            )
        ]

    def close(self):
        pass


class FakeILOSTAT:
    provider_name = "ILOSTAT"
    failure = False

    def __init__(self):
        pass

    def search(self, query, *, limit=1, geography=None):
        assert query
        assert limit == 1
        assert geography == "World"
        if self.failure:
            raise ILOSTATError("ILOSTAT request failed; scholarly discovery can continue")
        return [
            ScholarlyWork(
                external_id="ilostat:DF_EMP_TEMP_SEX_AGE_NB:X01:2024",
                title="Employment by sex and age — ILOSTAT (World)",
                doi=None,
                url="https://sdmx.ilo.org/rest/data/ILO,DF_EMP_TEMP_SEX_AGE_NB/X01.A.EMP_TEMP_NB.SEX_T.AGE_5YRBANDS_TOTAL",
                authors=[],
                published_year=None,
                publisher="International Labour Organization",
                abstract_excerpt=None,
                query=query,
                provider="ILOSTAT",
                provider_metadata={
                    "statistics": {
                        "indicator_id": "EMP_TEMP_SEX_AGE_NB",
                        "indicator_name": "Employment by sex and age (total employment, number)",
                        "database_id": "ILOSTAT",
                        "dataset_name": "ILOSTAT labour statistics database",
                        "dataset_url": "https://ilostat.ilo.org/data/",
                        "dataset_terms_url": "https://www.ilo.org/rights-and-permissions",
                        "license": "CC BY 4.0 under ILO Open Access policy (qualified scope)",
                        "license_url": "https://creativecommons.org/licenses/by/4.0/",
                        "attribution": "International Labour Organization (ILO), ILOSTAT.",
                        "definition": "Employment total",
                        "statistical_concept": "All sexes and ages",
                        "methodology": "Labour force survey",
                        "limitations": "Descriptive observation; inspect source notes.",
                        "periodicity": "Annual",
                        "source_update_date": None,
                        "measurement_unit": "PERSONS",
                        "retrieved_at": utcnow().isoformat(),
                        "data_sources": [
                            {
                                "name": "Labour force survey",
                                "organization": "As reported in ILOSTAT",
                                "publisher": "International Labour Organization",
                                "url": None,
                            }
                        ],
                        "observations": [
                            {
                                "value": "3500000000",
                                "period": "2024",
                                "geography_code": "X01",
                                "geography_name": "World",
                                "unit_measure": "PERSONS",
                                "unit_type": None,
                                "unit_multiplier": 0,
                                "observation_status": "A",
                            }
                        ],
                    }
                },
                source_type="official_statistics",
            )
        ]

    def close(self):
        pass


def run_all_steps(client, job_id):
    job = None
    for number in range(1, 8):
        response = client.post(
            f"/api/v1/research-jobs/{job_id}/advance",
            json={"operation_key": f"operation-key-{number:04d}"},
        )
        assert response.status_code == 200, response.text
        job = response.json()
    return job


def test_html_title_shell_detection_rejects_only_title_like_page_text():
    title = "Offshore hybrid renewable energy: insights from real-world implementations"

    assert workflow._looks_like_html_title_shell(f"Frontiers | {title}", title=title)
    assert not workflow._looks_like_html_title_shell(
        "A newly retrieved licensed paragraph reports higher output per worker-hour.",
        title=title,
    )
    assert not workflow._looks_like_html_title_shell(
        "Findings are reported. " * 20,
        title=title,
    )


def test_persisted_workflow_creates_source_passage_claim_and_report(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow.settings, "openalex_api_key", "")
    monkeypatch.setattr(workflow.settings, "openalex_allow_billable_calls", False)
    project = create_project(client)
    job = create_job(client, project["id"])

    final = run_all_steps(client, job["id"])
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]

    assert final["status"] == "completed_with_limitations", (
        final.get("error_class"),
        final.get("error_message"),
        [
            {
                "stage": event["stage"],
                "error_class": event["data"].get("error_class"),
                "exception_type": event["data"].get("exception_type"),
            }
            for event in events
            if event["event_type"] == "step_failed"
        ][-2:],
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    candidates_response = client.get(f"/api/v1/research-jobs/{job['id']}/candidates").json()
    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    completed_stages = {
        event["stage"] for event in events if event["event_type"] == "step_completed"
    }
    assert completed_stages >= {
        "planning",
        "discovery",
        "extraction",
        "appraisal",
        "comparison",
        "verification",
        "synthesis",
    }
    assert all(event["data"]["data_schema_version"] == 1 for event in events)

    assert len(sources) == 2
    with client.db_sessions() as db:
        persisted_sources = db.query(Source).filter_by(job_id=job["id"]).all()
        assert persisted_sources
        assert all(
            source.metadata_json["provider_metadata"]["schema_version"] == 1
            for source in persisted_sources
        )
        persisted_report = db.query(ResearchReport).filter_by(job_id=job["id"]).one()
        assert persisted_report.citation_map_json["schema_version"] == 1
        assert set(persisted_report.citation_map_json["citations"]) == {"S1", "S2"}
        assert persisted_report.verification_json["schema_version"] == 1
        assert (
            persisted_report.verification_json["record"]["citation_link_integrity"]["status"]
            == "passed"
        )
    assert candidates_response["total"] >= len(sources)
    assert {item["disposition"] for item in candidates_response["items"]} == {
        "selected",
        "excluded",
    }
    crossref_candidates = [
        item for item in candidates_response["items"] if item["provider"] == "Crossref"
    ]
    assert crossref_candidates
    assert all(item["abstract_excerpt"] is None for item in crossref_candidates)
    assert {item["abstract_excerpt_retention_status"] for item in crossref_candidates} <= {
        "not_available",
        "not_retained_item_text_rights_unverified",
    }
    assert all(item["discovered_at"] and item["query"] for item in candidates_response["items"])
    assert any(
        item["reason_code"] == "duplicate_canonical_identity"
        for item in candidates_response["items"]
    )
    assert {source["retrieval_status"] for source in sources} == {"metadata_only"}
    crossref_sources = [source for source in sources if source["provider"] == "Crossref"]
    assert crossref_sources
    assert all(source["abstract_excerpt"] is None for source in crossref_sources)
    assert {source["abstract_text_retention_status"] for source in crossref_sources} <= {
        "not_available",
        "not_retained_item_text_rights_unverified",
    }
    assert claims == []
    assert report["status"] == "completed_with_limitations"
    assert report["version"] == 2
    assert report["citation_map_schema_version"] == 1
    assert report["verification_schema_version"] == 1
    assert report["verification"]["report_schema_version"] == 2
    assert report["verification"]["level"] == "deterministic_link_integrity_only"
    assert report["verification"]["citation_link_integrity"]["status"] == "passed"
    assert report["verification"]["semantic_assessment"]["method"] == "not_performed"
    assert report["verification"]["semantic_support_check"] == "not_performed"
    assert len(report["citation_map"]) == 2
    assert (
        "abstract text omitted because reuse rights are unverified"
        in report["body_markdown"].lower()
    )
    assert any(not item["passages"] for item in report["citation_map"].values())
    assert "No source passage is linked here" in report["body_markdown"]
    assert "## Evidence tensions and alternative explanations" in report["body_markdown"]
    assert "not evidence that the literature is unanimous" in report["body_markdown"]
    assert "## Search coverage" in report["body_markdown"]
    assert report["verification"]["search_coverage"]["providers"] == [
        "Crossref",
        "OpenAlex",
        "OpenAIRE organization discovery",
    ]
    assert report["verification"]["search_coverage"]["provider_query_counts"]["Crossref"] > 0
    routing = report["verification"]["search_coverage"]["conditional_statistics_routing"]
    assert routing["status"] == "recorded"
    assert routing["world_bank_data360"]["status"] == "not_applicable"
    assert routing["world_bank_data360"]["reason_code"] == "unsupported_topic"
    assert routing["ilostat"]["status"] == "not_applicable"
    assert "World Bank Data360 route: not applicable" in report["body_markdown"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")
    latency_samples = discovery_event["data"]["provider_query_latencies_ms"]
    assert (
        len(latency_samples["Crossref"])
        == discovery_event["data"]["provider_query_counts"]["Crossref"]
    )
    assert all(value >= 0 for timings in latency_samples.values() for value in timings)
    assert all(
        isinstance(event["data"].get("elapsed_seconds"), (int, float))
        for event in events
        if event["event_type"] == "step_completed"
    )
    assert report["verification"]["search_coverage"]["selected_sources"] == 2
    assert (
        report["verification"]["search_coverage"]["candidate_ledger_records"]
        == candidates_response["total"]
    )
    assert report["verification"]["search_coverage"]["exclusion_details_persisted"] is True
    expansion = report["verification"]["search_coverage"]["citation_expansion"]
    assert expansion["status"] == "not_attempted_operator_opt_in_required"
    assert expansion["requests_attempted"] == 0
    assert "not attempted operator opt in required" in report["body_markdown"].lower()
    history = client.get("/api/v1/reports").json()
    history_item = next(item for item in history["items"] if item["id"] == report["id"])
    assert history_item["citation_map"] == report["citation_map"]
    inspection = client.get(f"/api/v1/reports/{report['id']}/inspection").json()
    assert (
        inspection["report"]["verification"]["citation_link_integrity"]
        == report["verification"]["citation_link_integrity"]
    )
    report_export = client.get(f"/api/v1/reports/{report['id']}/export?format=json").json()
    assert report_export["citation_map_schema_version"] == 1
    assert report_export["verification_schema_version"] == 1
    assert sum(event["event_type"] == "step_completed" for event in events) == 7


def test_openalex_abstract_is_omitted_without_item_version_text_rights(client, monkeypatch):
    excerpt = "A controlled developer study reports a measured productivity outcome."

    class OpenAlexWithAbstract:
        def __init__(self, **_kwargs):
            pass

        def search(self, query, *, limit=5):
            return [
                ScholarlyWork(
                    external_id="W123456789",
                    title="Generative AI and software developer productivity study",
                    doi=None,
                    url="https://openalex.org/W123456789",
                    authors=[],
                    published_year=2025,
                    publisher="Example journal",
                    abstract_excerpt=excerpt,
                    query=query,
                    provider="OpenAlex",
                    provider_metadata={},
                )
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "OpenAlexProvider", OpenAlexWithAbstract)
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow.settings, "openalex_api_key", "")
    monkeypatch.setattr(workflow.settings, "openalex_allow_billable_calls", False)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="openalex-abstract-snapshot")
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "openalex-abstract-plan"},
    )
    discovery = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "openalex-abstract-discovery"},
    )
    assert discovery.status_code == 200, discovery.text

    candidates = client.get(f"/api/v1/research-jobs/{job['id']}/candidates").json()["items"]
    openalex_candidates = [item for item in candidates if item["provider"] == "OpenAlex"]
    assert openalex_candidates
    assert all(item["abstract_excerpt"] is None for item in openalex_candidates)
    assert all(
        item["abstract_excerpt_retention_status"] == "not_retained_item_text_rights_unverified"
        for item in openalex_candidates
    )


def test_selected_source_abstract_is_not_persisted_as_evidence_without_item_version_rights(
    client, monkeypatch
):
    excerpt = "A study of software developers reported a measured productivity outcome."

    class CrossrefWithUnverifiedAbstract:
        def __init__(self):
            pass

        def search(self, query, *, limit=5):
            return [
                CrossrefRecord(
                    external_id="doi:10.5555/unverified-abstract",
                    title="Generative AI and software developer productivity experiment",
                    doi="10.5555/unverified-abstract",
                    url="https://publisher.example/unverified-abstract",
                    authors=[],
                    published_year=2025,
                    publisher="Example Academic Press",
                    abstract_excerpt=excerpt,
                    query=query,
                )
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", CrossrefWithUnverifiedAbstract)
    monkeypatch.setattr(workflow.settings, "openalex_api_key", "")
    monkeypatch.setattr(workflow.settings, "openalex_allow_billable_calls", False)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="unverified-source-abstract-01")
    for step, operation in enumerate(("plan", "discovery", "extraction"), start=1):
        response = client.post(
            f"/api/v1/research-jobs/{job['id']}/advance",
            json={"operation_key": f"unverified-source-abstract-{operation}-{step}"},
        )
        assert response.status_code == 200, response.text

    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    source = next(item for item in sources if item["doi"] == "10.5555/unverified-abstract")
    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]

    assert source["abstract_excerpt"] is None
    assert source["retrieval_status"] == "metadata_only"
    assert source["abstract_text_available_at_discovery"] is True
    assert source["abstract_text_retention_status"] == "not_retained_item_text_rights_unverified"
    assert not any(claim["source_id"] == source["id"] for claim in claims)
    with client.db_sessions() as db:
        persisted = db.get(Source, source["id"])
        assert persisted is not None
        assert persisted.abstract_excerpt is None
        assert persisted.metadata_json["abstract_text_retention_status"] == (
            "not_retained_item_text_rights_unverified"
        )


def test_versioned_truncation_flag_prevents_incomplete_abstract_claims(client, monkeypatch):
    class TruncatedCrossref(FakeCrossref):
        def search(self, query, *, limit=5):
            records = super().search(query, limit=limit)
            if not records:
                return records
            return [
                replace(
                    records[0],
                    abstract_excerpt=(
                        "The study reported a measured result. "
                        "The source excerpt ends before this sentence is complete"
                    ),
                    provider_metadata={"abstract_excerpt_truncated": True},
                ),
                *records[1:],
            ]

    monkeypatch.setattr(workflow, "CrossrefProvider", TruncatedCrossref)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="truncated-versioned-abstract-01")
    run_all_steps(client, job["id"])

    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    assert claims == []
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    source = next(item for item in sources if item["doi"] == "10.5555/veda-study-1")
    assert source["abstract_excerpt"] is None
    assert source["abstract_text_retention_status"] == ("not_retained_item_text_rights_unverified")
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    extraction = next(event for event in events if event["stage"] == "extraction")
    assert extraction["data"]["incomplete_abstract_fragments_excluded"] == 0


def test_compound_abstract_does_not_become_persisted_evidence_without_rights(client, monkeypatch):
    class CompoundCrossref(FakeCrossref):
        def search(self, query, *, limit=5):
            records = super().search(query, limit=limit)
            return [
                replace(
                    records[0],
                    abstract_excerpt=(
                        "AI increased task completion speed by 14 percent; "
                        "participating workers reported fatigue."
                    ),
                ),
                *records[1:],
            ]

    monkeypatch.setattr(workflow, "CrossrefProvider", CompoundCrossref)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="compound-claim-units-01")
    run_all_steps(client, job["id"])

    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    source = next(item for item in sources if item["doi"] == "10.5555/veda-study-1")

    assert claims == []
    assert source["abstract_excerpt"] is None
    assert source["abstract_text_retention_status"] == ("not_retained_item_text_rights_unverified")


def test_owner_scoped_report_history_is_stable_and_bounded(client):
    owner_id = client.test_user["id"]
    project = create_project(client)
    jobs = [
        create_job(client, project["id"], idempotency_key=f"report-history-{index}")
        for index in range(2)
    ]
    client.test_user["id"] = "30000000-0000-4000-8000-000000000003"
    other_project = create_project(client)
    other_job = create_job(client, other_project["id"], idempotency_key="other-user-report")
    client.test_user["id"] = owner_id

    reports = []
    legacy_payloads = {}
    with client.db_sessions() as db:
        for index, job in enumerate([*jobs, other_job]):
            report = ResearchReport(
                job_id=job["id"],
                status="completed_with_limitations",
                body_markdown=f"Report version schema 1, entry {index}",
                citation_map_json={},
                verification_json={"report_schema_version": 1},
                model_name=None,
            )
            reports.append(report)
            db.add(report)
            db.flush()
            if index == 0:
                source = Source(
                    job_id=job["id"],
                    external_id="report-history-citation",
                    title="Saved citation source",
                    doi="10.5555/saved-citation",
                    url="https://example.org/saved-citation",
                )
                db.add(source)
                db.flush()
                passage = add_test_passage(
                    db,
                    source,
                    ordinal=0,
                    locator="p. 2",
                    content="The exact saved source sentence supports a bounded claim.",
                    access_level="full_text_html",
                )
                db.flush()
                db.add(
                    Claim(
                        job_id=job["id"],
                        source_id=source.id,
                        passage_id=passage.id,
                        text="The exact saved source sentence supports a bounded claim.",
                        span_start=0,
                        span_end=58,
                        atomization_status="whole_sentence",
                        atomization_version=1,
                        claim_type="source_reported",
                        evidence_status="not_independently_verified",
                    )
                )
                report.citation_map_json = {
                    "S1": {
                        "source_id": source.id,
                        "title": source.title,
                        "doi": source.doi,
                        "url": source.url,
                        "passages": [passage.id],
                    }
                }
            legacy_payloads[report.id] = {
                "citation_map": deepcopy(report.citation_map_json),
                "verification": deepcopy(report.verification_json),
            }
        db.commit()

    first_page = client.get("/api/v1/reports?limit=1&offset=0")
    assert first_page.status_code == 200
    first = first_page.json()
    assert first["total"] == 2
    assert first["limit"] == 1
    assert first["offset"] == 0
    assert first["has_more"] is True
    assert first["items"][0]["version"] == 1
    assert first["items"][0]["citation_map_schema_version"] == 1
    assert first["items"][0]["verification_schema_version"] == 1
    assert first["items"][0]["project_id"] == project["id"]
    assert first["items"][0]["project_title"] == project["title"]
    assert first["items"][0]["question"]
    assert first["items"][0]["project_archived_at"] is None

    second = client.get("/api/v1/reports?project_id=" + project["id"] + "&limit=1&offset=1")
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["has_more"] is False
    assert second.json()["items"][0]["job_id"] != first["items"][0]["job_id"]
    assert client.get("/api/v1/reports?limit=101").status_code == 422
    assert client.get("/api/v1/reports?offset=100001").status_code == 422
    assert client.get(f"/api/v1/reports?project_id={other_project['id']}").status_code == 404
    assert client.get(f"/api/v1/reports/{reports[-1].id}").status_code == 404

    archived = client.delete(f"/api/v1/projects/{project['id']}")
    assert archived.status_code == 204
    assert client.get(f"/api/v1/reports?project_id={project['id']}").status_code == 404
    archived_history = client.get(
        f"/api/v1/reports?project_id={project['id']}&include_archived=true"
    )
    assert archived_history.status_code == 200
    assert archived_history.json()["total"] == 2
    archived_item = next(
        item for item in archived_history.json()["items"] if item["id"] == reports[0].id
    )
    assert archived_item["project_archived_at"] is not None
    inspection = client.get(f"/api/v1/reports/{archived_item['id']}/inspection")
    assert inspection.status_code == 200, inspection.text
    assert inspection.json()["report"]["id"] == archived_item["id"]
    assert inspection.json()["report"]["citation_map_schema_version"] == 1
    assert inspection.json()["report"]["verification_schema_version"] == 1
    assert inspection.json()["job"]["id"] == archived_item["job_id"]
    assert inspection.json()["project"]["archived_at"] is not None
    assert inspection.json()["sources"][0]["title"] == "Saved citation source"
    assert inspection.json()["sources"][0]["passages"][0]["locator"] == "p. 2"
    assert (
        inspection.json()["claims"][0]["source_sentence"]
        == "The exact saved source sentence supports a bounded claim."
    )
    assert (
        inspection.json()["report"]["citation_map"]["S1"]["source_id"]
        == inspection.json()["sources"][0]["id"]
    )
    with client.db_sessions() as db:
        legacy_after_reads = db.get(ResearchReport, reports[0].id)
        assert (
            legacy_after_reads.citation_map_json == legacy_payloads[reports[0].id]["citation_map"]
        )
        assert (
            legacy_after_reads.verification_json == legacy_payloads[reports[0].id]["verification"]
        )
    assert client.get(f"/api/v1/reports/{reports[-1].id}/inspection").status_code == 404


def test_discovery_candidate_ledger_marks_source_cap_exclusion(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="candidate-source-cap")
    limited_profile = replace(PROFILES["quick"], max_sources=1)
    monkeypatch.setattr(workflow, "profile_for_job", lambda *_args, **_kwargs: limited_profile)

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(persisted, ["one bounded query"])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert result.event_data["source_count"] == 1
    assert result.event_data["records_excluded_by_source_cap"] == 1
    assert [candidate.reason_code for candidate in result.candidates] == [
        "selected_by_relevance",
        "source_limit",
    ]
    assert result.candidates[0].relevance.algorithm == "lexical_overlap_v1"


def test_source_cap_selects_later_candidate_with_higher_query_overlap(client, monkeypatch):
    class OrderedCrossref:
        def __init__(self):
            pass

        def search(self, query, *, limit=5):
            return [
                CrossrefRecord(
                    external_id="record:prestige-only",
                    title="Highly cited prestigious award-winning landmark study",
                    doi=None,
                    url="https://publisher.example/irrelevant",
                    authors=[],
                    published_year=2025,
                    publisher="Famous Journal",
                    abstract_excerpt="An influential paper with broad attention.",
                    query=query,
                ),
                CrossrefRecord(
                    external_id="doi:10.5555/relevant-later",
                    title="AI adoption and worker productivity",
                    doi="10.5555/relevant-later",
                    url="https://doi.org/10.5555/relevant-later",
                    authors=[],
                    published_year=2020,
                    publisher="Unranked Journal",
                    abstract_excerpt="AI adoption changed worker productivity.",
                    query=query,
                ),
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", OrderedCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="later-relevant-candidate")
    limited_profile = replace(PROFILES["quick"], max_sources=1)
    monkeypatch.setattr(workflow, "profile_for_job", lambda *_args, **_kwargs: limited_profile)

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted, ["AI adoption worker productivity"]
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert result.sources[0].title == "AI adoption and worker productivity"
    assert result.candidates[0].record.external_id == "doi:10.5555/relevant-later"
    assert result.candidates[0].reason_code == "selected_by_relevance"
    assert result.candidates[0].relevance.score > result.candidates[1].relevance.score


def test_recorded_subquery_alignment_can_promote_a_source_before_the_cap(client, monkeypatch):
    question = (
        "Does generative AI improve software developer productivity, and why do empirical "
        "studies sometimes report different findings?"
    )
    query = (
        "generative ai software developer productivity empirical coding assistants controlled "
        "experiments randomized trial field"
    )

    class QueryAlignedCrossref:
        def __init__(self):
            pass

        def search(self, actual_query, *, limit=5):
            assert actual_query == query
            return [
                CrossrefRecord(
                    external_id="record:psychological-perspective",
                    title="Developer Productivity in the Age of Generative AI: A Psychological Perspective",
                    doi=None,
                    url="https://publisher.example/psychological-perspective",
                    authors=[],
                    published_year=2026,
                    publisher="Example Publisher",
                    abstract_excerpt=None,
                    query=actual_query,
                ),
                CrossrefRecord(
                    external_id="doi:10.5555/three-field-experiments",
                    title=(
                        "The Effects of Generative AI on High Skilled Work: Evidence from Three "
                        "Field Experiments with Software Developers"
                    ),
                    doi="10.5555/three-field-experiments",
                    url="https://doi.org/10.5555/three-field-experiments",
                    authors=[],
                    published_year=2025,
                    publisher="Example Publisher",
                    abstract_excerpt=None,
                    query=actual_query,
                ),
                CrossrefRecord(
                    external_id="record:ai-call-center-experiments",
                    title="Field Experiments on Generative AI for Call Centers",
                    doi=None,
                    url="https://publisher.example/call-center-experiments",
                    authors=[],
                    published_year=2025,
                    publisher="Example Publisher",
                    abstract_excerpt=None,
                    query=actual_query,
                ),
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", QueryAlignedCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="planned-query-source-cap",
        question=question,
    )
    limited_profile = replace(PROFILES["quick"], max_sources=1)
    monkeypatch.setattr(workflow, "profile_for_job", lambda *_args, **_kwargs: limited_profile)

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(persisted, [query])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    selected = result.candidates[0]
    excluded = result.candidates[1]
    topic_excluded = next(
        candidate
        for candidate in result.candidates
        if candidate.reason_code == "insufficient_topic_overlap"
    )
    assert selected.record.title.startswith("The Effects of Generative AI")
    assert selected.reason_code == "selected_by_relevance"
    assert excluded.reason_code == "source_limit"
    assert selected.relevance.score == 0.190909
    assert excluded.relevance.score == 0.254545
    assert selected.relevance.score < excluded.relevance.score
    assert selected.relevance.planned_query_alignment.score == 0.269231
    assert (
        selected.relevance.planned_query_alignment.score
        > excluded.relevance.planned_query_alignment.score
    )
    assert selected.relevance.selection_score > excluded.relevance.selection_score
    assert topic_excluded.record.title == "Field Experiments on Generative AI for Call Centers"
    assert topic_excluded.relevance.selection_score < selected.relevance.selection_score
    assert (
        result.event_data["candidate_ranking"]["algorithm"] == "lexical_overlap_query_alignment_v1"
    )


def test_recorded_domain_expansion_recovers_a_workplace_trial_in_persisted_candidates(
    client, monkeypatch
):
    question = (
        "Does generative AI improve software developer productivity, and why do empirical "
        "studies sometimes report different findings?"
    )
    query = (
        "generative ai software developer productivity empirical coding assistants controlled "
        "experiments randomized trial field"
    )
    title = (
        "Dear Diary: A Randomized Controlled Trial of Generative AI Coding Tools in the Workplace"
    )

    class WorkplaceTrialCrossref:
        def __init__(self):
            pass

        def search(self, actual_query, *, limit=5):
            assert actual_query == query
            return [
                CrossrefRecord(
                    external_id="doi:10.5555/workplace-coding-trial",
                    title=title,
                    doi="10.5555/workplace-coding-trial",
                    url="https://doi.org/10.5555/workplace-coding-trial",
                    authors=[],
                    published_year=2025,
                    publisher="Example Journal",
                    abstract_excerpt="A randomized workplace study of generative AI coding tools.",
                    query=actual_query,
                )
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", WorkplaceTrialCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="recorded-domain-expansion-workplace-trial",
        question=question,
    )
    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(persisted, [query])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    candidate = next(item for item in result.candidates if item.record.title == title)
    assert candidate.reason_code == "selected_by_relevance"
    assert candidate.relevance.topic_eligibility_basis == "recorded_query_domain_expansion"
    assert result.sources[0].doi == "10.5555/workplace-coding-trial"


def test_discovery_keeps_low_topic_overlap_source_as_auditable_exclusion(client, monkeypatch):
    class MixedCrossref:
        def __init__(self):
            pass

        def search(self, query, *, limit=5):
            return [
                CrossrefRecord(
                    external_id="doi:10.5555/radio-coding",
                    title="Non-Orthogonal Multiple Access Scheme using Multilevel Coding",
                    doi="10.5555/radio-coding",
                    url="https://doi.org/10.5555/radio-coding",
                    authors=[],
                    published_year=2025,
                    publisher="Signal Processing Review",
                    abstract_excerpt="Radio communications coding over 60 GHz channels.",
                    query=query,
                ),
                CrossrefRecord(
                    external_id="doi:10.5555/ai-copilot",
                    title="AI coding copilot production defects and software productivity",
                    doi="10.5555/ai-copilot",
                    url="https://doi.org/10.5555/ai-copilot",
                    authors=[],
                    published_year=2025,
                    publisher="Software Engineering Review",
                    abstract_excerpt="AI coding copilots changed worker productivity and software defects.",
                    query=query,
                ),
                CrossrefRecord(
                    external_id="doi:10.5555/repository-abstract",
                    title="Empirical Study of AI Coding Copilot Productivity in Software Engineering",
                    doi="10.5555/repository-abstract",
                    url="https://doi.org/10.5555/repository-abstract",
                    authors=[],
                    published_year=2025,
                    publisher="Metadata Type Contamination Fixture",
                    abstract_excerpt=(
                        "This repository contains analyses and data related to the paper. "
                        "It includes Jupyter Notebooks, raw survey data, and the original survey tool."
                    ),
                    query=query,
                ),
                CrossrefRecord(
                    external_id="doi:10.5555/issue-page-title",
                    title=(
                        'Articles "AI coding copilot production productivity" DOI '
                        "10.1234/issue.99 357 PDF: 402 PDF"
                    ),
                    doi="10.5555/issue-page-title",
                    url="https://doi.org/10.5555/issue-page-title",
                    authors=[],
                    published_year=2025,
                    publisher="Metadata Contamination Fixture",
                    abstract_excerpt="AI coding copilot production productivity",
                    query=query,
                ),
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", MixedCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    project = create_project(client)
    question = (
        "At a 60-engineer product company, does access to an AI coding copilot increase "
        "production-accepted work without raising security defects over twelve weeks?"
    )
    job = create_job(
        client,
        project["id"],
        idempotency_key="auditable-low-overlap-candidate",
        question=question,
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted, ["AI coding copilot production productivity defects"]
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert [source.doi for source in result.sources] == ["10.5555/ai-copilot"]
    excluded = next(
        candidate
        for candidate in result.candidates
        if candidate.record.external_id == "doi:10.5555/radio-coding"
    )
    assert excluded.disposition == "excluded"
    assert excluded.reason_code == "insufficient_topic_overlap"
    assert result.event_data["records_excluded_by_topic_overlap"] == 1
    contaminated = next(
        candidate
        for candidate in result.candidates
        if candidate.record.external_id == "doi:10.5555/issue-page-title"
    )
    assert contaminated.disposition == "excluded"
    assert contaminated.reason_code == "malformed_bibliographic_title"
    assert result.event_data["records_excluded_by_malformed_bibliographic_title"] == 1
    repository_description = next(
        candidate
        for candidate in result.candidates
        if candidate.record.external_id == "doi:10.5555/repository-abstract"
    )
    assert repository_description.disposition == "excluded"
    assert repository_description.reason_code == "repository_artifact_description_not_abstract"
    assert result.event_data["records_excluded_by_repository_artifact_description"] == 1


def test_global_statistics_flow_preserves_source_type_license_and_descriptive_limits(
    client, monkeypatch
):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", FakeData360)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="global-statistics-flow",
        geography="World",
        question="What are global population trends?",
    )

    final = run_all_steps(client, job["id"])

    assert final["status"] == "completed_with_limitations", (
        final.get("error_class"),
        final.get("error_message"),
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    statistics = next(
        source for source in sources if source["source_type"] == "official_statistics"
    )
    assert statistics["retrieval_status"] == "official_statistics"
    assert statistics["statistics"]["license"] == "CC BY-4.0"
    with client.db_sessions() as db:
        persisted = (
            db.query(Source).filter_by(job_id=job["id"], source_type="official_statistics").one()
        )
        provider_metadata = persisted.metadata_json["provider_metadata"]
        assert provider_metadata["schema_version"] == 1
        assert provider_metadata["statistics"]["observations"][0]["period"] == "2025"
    assert statistics["appraisal"]["status"] == "not_applicable"
    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    statistic_claim = next(claim for claim in claims if claim["claim_type"] == "reported_statistic")
    assert statistic_claim["text"].startswith("World (WLD), 2025 — Population, total: 8215424893")
    evidence = client.get(f"/api/v1/claims/{statistic_claim['id']}/evidence").json()
    assert evidence["passage"]["access_level"] == "official_statistics"
    assert evidence["passage"]["locator"].endswith("WLD · 2025")
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    assert "official-statistics series" in report["body_markdown"].lower()
    assert (
        "descriptive observations, not study estimates or causal evidence"
        in report["body_markdown"].lower()
    )
    assert "CC BY-4.0" in report["body_markdown"]
    assert "World Bank: World Development Indicators" in report["body_markdown"]
    assert report["verification"]["search_coverage"]["providers"] == [
        "Crossref",
        "OpenAlex",
        "OpenAIRE",
        "World Bank Data360",
    ]
    candidates = client.get(f"/api/v1/research-jobs/{job['id']}/candidates").json()["items"]
    statistics_candidate = next(
        candidate for candidate in candidates if candidate["provider"] == "World Bank Data360"
    )
    assert statistics_candidate["disposition"] == "selected"
    assert statistics_candidate["reason_code"] == "selected_by_discovery_order"


def test_data360_receives_only_the_research_question_not_expanded_plan_context(client, monkeypatch):
    seen_queries = []

    class CaptureData360(FakeData360):
        def search(self, query, *, limit=1, geography=None):
            seen_queries.append(query)
            return super().search(query, limit=limit, geography=geography)

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", CaptureData360)
    project = create_project(client)
    question = "What population trends are reported for the world?"
    job = create_job(
        client,
        project["id"],
        idempotency_key="data360-minimal-query-payload",
        geography="World",
        question=question,
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted,
            ["population trends plus saved brief and decision context"],
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert seen_queries == [question]
    assert result.event_data["provider_query_counts"]["World Bank Data360"] == 1
    assert result.event_data["conditional_statistics_routing"]["world_bank_data360"] == {
        "schema_version": 1,
        "status": "searched",
        "requests": 1,
        "results": 1,
        "failures": 0,
    }


def test_data360_failure_does_not_stop_scholarly_discovery(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", FakeData360)
    monkeypatch.setattr(FakeData360, "failure", True)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="data360-independent-failure",
        geography="World",
        question="What population trends are reported worldwide?",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted, ["population trends worldwide"]
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert result.sources
    assert result.event_data["provider_failures"]["World Bank Data360"] == 1
    assert result.event_data["provider_query_counts"]["World Bank Data360"] == 1
    assert (
        result.event_data["conditional_statistics_routing"]["world_bank_data360"]["status"]
        == "searched"
    )
    assert (
        result.event_data["conditional_statistics_routing"]["world_bank_data360"]["failures"] == 1
    )
    assert result.event_data["source_count"] == len(result.sources)


def test_ilostat_statistics_flow_is_persisted_as_descriptive_evidence(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "ILOSTATProvider", FakeILOSTAT)
    monkeypatch.setattr(FakeILOSTAT, "failure", False)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="ilostat-statistics-flow",
        geography="World",
        question="How have global employment levels changed?",
    )

    final = run_all_steps(client, job["id"])

    assert final["status"] == "completed_with_limitations", (
        final.get("error_class"),
        final.get("error_message"),
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    statistics = next(source for source in sources if source["provider"] == "ILOSTAT")
    assert statistics["source_type"] == "official_statistics"
    assert statistics["statistics"]["license"].startswith("CC BY 4.0")
    with client.db_sessions() as db:
        persisted = (
            db.query(Source).filter_by(job_id=job["id"], source_type="official_statistics").one()
        )
        assert persisted.metadata_json["provider_metadata"]["schema_version"] == 1
    assert statistics["statistics"]["limitations"]
    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    claim = next(item for item in claims if item["source_id"] == statistics["id"])
    evidence = client.get(f"/api/v1/claims/{claim['id']}/evidence").json()
    assert evidence["passage"]["locator"].startswith("ILOSTAT EMP_TEMP_SEX_AGE_NB")
    assert "descriptive reported statistic" in claim["text"]
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    assert "International Labour Organization (ILO), ILOSTAT" in report["body_markdown"]
    assert "ILOSTAT" in report["verification"]["search_coverage"]["providers"]
    assert (
        report["verification"]["search_coverage"]["conditional_statistics_routing"]["ilostat"][
            "status"
        ]
        == "searched"
    )


def test_ilostat_failure_does_not_stop_scholarly_discovery(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "ILOSTATProvider", FakeILOSTAT)
    monkeypatch.setattr(FakeILOSTAT, "failure", True)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="ilostat-independent-failure",
        geography="World",
        question="Research worldwide employment levels",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(persisted, ["world employment levels"])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert result.sources
    assert result.event_data["provider_failures"]["ILOSTAT"] == 1
    assert result.event_data["provider_query_counts"]["ILOSTAT"] == 1
    assert result.event_data["conditional_statistics_routing"]["ilostat"]["status"] == "searched"
    assert result.event_data["conditional_statistics_routing"]["ilostat"]["failures"] == 1
    assert result.event_data["source_count"] == len(result.sources)


@pytest.mark.parametrize(
    ("provider_attribute", "route_key"),
    [
        ("WorldBankData360Provider", "world_bank_data360"),
        ("ILOSTATProvider", "ilostat"),
    ],
)
def test_optional_statistics_provider_initialization_failure_does_not_stop_discovery(
    client, monkeypatch, provider_attribute, route_key
):
    class UnavailableProvider:
        def __init__(self):
            raise RuntimeError("local provider setup unavailable")

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, provider_attribute, UnavailableProvider)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key=f"optional-provider-init-{route_key}",
        geography="World",
        question="How have global employment and population trends changed?",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted, ["global employment population"]
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    route = result.event_data["conditional_statistics_routing"][route_key]
    assert route["status"] == "searched"
    assert route["requests"] == 1
    assert route["failures"] == 1
    assert result.sources
    assert result.event_data["provider_query_counts"]["Crossref"] > 0


def test_unlicensed_data360_candidate_is_retained_as_excluded_without_values(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", FakeData360)
    monkeypatch.setattr(FakeData360, "blocked", True)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="data360-unlicensed-candidate",
        geography="World",
        question="What population trends are reported worldwide?",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted, ["population trends worldwide"]
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    blocked = next(
        item for item in result.candidates if item.record.provider == "World Bank Data360"
    )
    assert blocked.disposition == "excluded"
    assert blocked.reason_code == "license_not_verified"
    assert blocked.record.provider_metadata["statistics"]["observations"] == []


def test_data360_is_not_dispatched_for_generic_question_even_with_world_scope(client, monkeypatch):
    class UnexpectedData360:
        def __init__(self):
            raise AssertionError("unrelated questions must not contact official statistics")

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", UnexpectedData360)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="generic-question-no-statistics-route",
        geography="World",
        question="How does workplace AI adoption affect worker productivity outcomes?",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(
            persisted, ["AI productivity with expanded decision context"]
        )
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert result.event_data["provider_queries_attempted"] == sum(
        result.event_data["provider_query_counts"].values()
    )
    assert result.event_data["provider_query_counts"]["Crossref"] > 0
    assert result.event_data["provider_query_counts"]["OpenAlex"] > 0
    assert result.event_data["provider_query_counts"].get("World Bank Data360", 0) == 0
    assert (
        result.event_data["conditional_statistics_routing"]["world_bank_data360"]["reason_code"]
        == "unsupported_topic"
    )
    assert result.event_data["conditional_statistics_routing"]["ilostat"]["reason_code"] == (
        "unsupported_topic"
    )
    assert all(source.source_type != "official_statistics" for source in result.sources)


def test_data360_requires_explicit_geography_for_statistics_question(client, monkeypatch):
    class UnexpectedData360:
        def __init__(self):
            raise AssertionError("missing geography must not be broadened to the world")

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    monkeypatch.setattr(workflow, "WorldBankData360Provider", UnexpectedData360)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="statistics-without-geography-no-route",
        geography=None,
        question="What population trends are reported?",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(persisted, ["population trends"])
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    assert result.event_data["provider_query_counts"].get("World Bank Data360", 0) == 0
    assert (
        result.event_data["conditional_statistics_routing"]["world_bank_data360"]["reason_code"]
        == "geography_not_supplied"
    )


def test_optional_statistics_routes_record_deadline_without_sending_requests(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", FakeOpenAlexEmpty)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="statistics-deadline-not-attempted",
        geography="World",
        question="How have global employment levels changed?",
    )

    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        persisted.current_stage = "discovery"
        persisted.checkpoint_json = checkpoint_with_queries(persisted, ["global employment"])
        monkeypatch.setattr(workflow, "_stage_time_expired", lambda _snapshot: True)
        result = workflow.execute_stage(db, workflow.job_snapshot(persisted))

    routing = result.event_data["conditional_statistics_routing"]
    assert routing["world_bank_data360"]["status"] == "not_attempted"
    assert routing["world_bank_data360"]["reason_code"] == "deadline_elapsed"
    assert routing["ilostat"] == {
        "schema_version": 1,
        "status": "not_attempted",
        "reason_code": "deadline_elapsed",
        "requests": 0,
        "results": 0,
        "failures": 0,
    }
    assert result.event_data["provider_query_counts"].get("ILOSTAT", 0) == 0


def test_historical_discovery_report_does_not_infer_conditional_routes(client):
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="historical-route-coverage")

    with client.db_sessions() as db:
        db.add(
            JobEvent(
                job_id=job["id"],
                event_type="step_completed",
                stage="discovery",
                message="Legacy discovery completed.",
                data_json={
                    "provider_query_counts": {"Crossref": 1, "OpenAlex": 1},
                    "provider_result_counts": {"Crossref": 0, "OpenAlex": 0},
                    "provider_failures": {"Crossref": 0, "OpenAlex": 0},
                },
                created_at=utcnow(),
            )
        )
        db.flush()
        lines, coverage = workflow._report_search_coverage(db, job["id"], 0)

    assert coverage["conditional_statistics_routing"] == {
        "status": "not_recorded_for_historical_run"
    }
    assert "not recorded for this historical run" in "\n".join(lines)


def test_report_search_coverage_exposes_exact_lenses_and_unimplemented_expansion(client):
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="search-lens-coverage-render")
    discovery_at = utcnow()
    lens = {
        "schema_version": 1,
        "lens_id": "L1",
        "category": "CONTRARY_OR_NULL_EVIDENCE",
        "purpose": "Find negative or null empirical outcomes.",
        "focus": "counterevidence",
        "exact_query": "developer productivity null results",
        "started_at": discovery_at.isoformat(),
        "completed_at": discovery_at.isoformat(),
        "pagination_state": "single_page_bounded",
        "status": "completed",
        "providers": [],
        "candidate_keys": ["a" * 64],
        "selected_candidate_keys": [],
        "retrieval_cost_status": "unknown",
    }

    with client.db_sessions() as db:
        db.add(
            JobEvent(
                job_id=job["id"],
                event_type="step_completed",
                stage="discovery",
                message="Discovery completed.",
                data_json={
                    "queries_planned": 1,
                    "providers": ["Crossref", "OpenAlex"],
                    "provider_queries_attempted": 2,
                    "provider_query_counts": {"Crossref": 1, "OpenAlex": 1},
                    "provider_result_counts": {"Crossref": 0, "OpenAlex": 1},
                    "provider_failures": {"Crossref": 0, "OpenAlex": 0},
                    "search_lenses": [lens],
                    "search_lens_counts": {
                        "completed": 1,
                        "partial": 0,
                        "failed": 0,
                        "not_attempted": 0,
                    },
                    "citation_expansion_status": "not_implemented",
                    "retrieval_stopping_reason": "planned_single_page_queries_exhausted",
                    "source_governance_plan": {
                        "schema_version": 1,
                        "policy_version": "topic-cues-source-classes-v2",
                        "registry_version": "fixture-registry-1",
                        "planned_classes": ["academic", "consulting", "think_tank"],
                    },
                },
                created_at=discovery_at,
            )
        )
        db.flush()
        lines, coverage = workflow._report_search_coverage(db, job["id"], 0)

    rendered = "\n".join(lines)
    assert "developer productivity null results" in rendered
    assert "Contrary/null evidence search: completed" in rendered
    assert "Citation expansion: not implemented" in rendered
    assert coverage["search_lenses"][0]["exact_query"] == lens["exact_query"]
    assert coverage["counterevidence_search_status"] == "completed"
    assert coverage["citation_expansion_status"] == "not_implemented"
    source_coverage = coverage["source_governance"]
    assert source_coverage["searched_classes"] == ["academic"]
    assert source_coverage["missing_classes"] == ["consulting", "think_tank"]
    assert source_coverage["class_status"]["consulting"]["status"] == "not_integrated"
    assert "Governed source-class coverage" in rendered


def test_conditional_statistics_route_reason_codes_cover_no_plan_and_unsupported_geography():
    no_plan = workflow._conditional_statistics_route_outcome(
        supports_topic=True,
        geography="World",
        supports_geography=True,
        has_query_plan=False,
        deadline_elapsed=False,
    )
    unsupported_geography = workflow._conditional_statistics_route_outcome(
        supports_topic=True,
        geography="India",
        supports_geography=False,
        has_query_plan=True,
        deadline_elapsed=False,
    )

    assert no_plan == {
        "schema_version": 1,
        "status": "not_attempted",
        "reason_code": "no_query_plan",
    }
    assert unsupported_geography == {
        "schema_version": 1,
        "status": "not_applicable",
        "reason_code": "unsupported_geography",
    }


def test_canonical_source_identity_normalizes_doi_without_guessing_title_matches():
    common = {
        "title": "Same title",
        "url": None,
        "authors": [],
        "published_year": 2025,
        "publisher": None,
        "abstract_excerpt": None,
        "query": "test query",
    }
    crossref = ScholarlyWork(
        external_id="doi:10.5555/ABC.XYZ", doi="10.5555/ABC.XYZ", provider="Crossref", **common
    )
    openalex = ScholarlyWork(
        external_id="doi:10.5555/abc.xyz",
        doi="https://doi.org/10.5555/abc.xyz",
        provider="OpenAlex",
        **common,
    )
    no_doi_crossref = ScholarlyWork(
        external_id="record:123", doi=None, provider="Crossref", **common
    )
    no_doi_openalex = ScholarlyWork(
        external_id="record:123", doi=None, provider="OpenAlex", **common
    )

    assert canonical_work_identity(crossref) == "doi:10.5555/abc.xyz"
    assert canonical_work_identity(openalex) == canonical_work_identity(crossref)
    assert canonical_work_identity(no_doi_crossref) != canonical_work_identity(no_doi_openalex)

    crossref_url_only = ScholarlyWork(
        external_id="https://publisher.example/article/123?session=1",
        doi=None,
        provider="Crossref",
        **common,
    )
    openalex_url_only = ScholarlyWork(
        external_id="https://publisher.example/article/123?source=2",
        doi=None,
        provider="OpenAlex",
        **common,
    )
    doi_url_only = ScholarlyWork(
        external_id="https://doi.org/10.5555/ABC.XYZ",
        doi=None,
        provider="OpenAlex",
        **common,
    )
    assert canonical_work_identity(crossref_url_only) == (
        "crossref:https://publisher.example/article/123?session=1"
    )
    assert canonical_work_identity(openalex_url_only) == (
        "openalex:https://publisher.example/article/123?source=2"
    )
    assert canonical_work_identity(doi_url_only) == "doi:10.5555/abc.xyz"


def test_discovery_merges_openalex_and_crossref_with_doi_dedup_and_provenance(client, monkeypatch):
    class OverlappingOpenAlex:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, query, *, limit=5):
            return [
                ScholarlyWork(
                    external_id="doi:10.5555/veda-study-1",
                    title="Duplicate AI worker productivity research from OpenAlex",
                    doi="10.5555/veda-study-1",
                    url="https://doi.org/10.5555/veda-study-1",
                    authors=[],
                    published_year=2025,
                    publisher="OpenAlex venue",
                    abstract_excerpt=None,
                    query=query,
                    provider="OpenAlex",
                ),
                ScholarlyWork(
                    external_id="openalex:W987654321",
                    title="AI worker productivity research from OpenAlex",
                    doi=None,
                    url="https://example.org/openalex-record",
                    authors=[{"name": "Grace Hopper"}],
                    published_year=2023,
                    publisher="OpenAlex venue",
                    abstract_excerpt=None,
                    query=query,
                    provider="OpenAlex",
                    provider_metadata={"openalex_id": "https://openalex.org/W987654321"},
                ),
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", OverlappingOpenAlex)
    project = create_project(client)
    job = create_job(client, project["id"])
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "plan-openalex-01"}
    )
    discovery = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-openalex-01"},
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    candidates = client.get(f"/api/v1/research-jobs/{job['id']}/candidates").json()["items"]
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")

    assert discovery.status_code == 200
    assert discovery.json()["current_stage"] == "extraction"
    assert len(sources) == 3
    assert sum(source["doi"] == "10.5555/veda-study-1" for source in sources) == 1
    assert {source["provider"] for source in sources} == {"Crossref", "OpenAlex"}
    assert discovery_event["data"]["providers"] == [
        "Crossref",
        "OpenAlex",
        "OpenAIRE organization discovery",
    ]
    assert discovery_event["data"]["provider_result_counts"]["OpenAlex"] > 0
    assert (
        discovery_event["data"]["candidate_ranking"]["algorithm"]
        == "lexical_overlap_query_alignment_v1"
    )
    assert "citation_count" in discovery_event["data"]["candidate_ranking"]["exclusions"]
    selected_duplicate_doi = next(
        source for source in sources if source["doi"] == "10.5555/veda-study-1"
    )
    cross_provider_duplicates = [
        candidate
        for candidate in candidates
        if candidate["provider"] == "OpenAlex"
        and candidate["reason_code"] == "duplicate_canonical_identity"
        and candidate["canonical_identity"] == "doi:10.5555/veda-study-1"
    ]
    assert cross_provider_duplicates
    assert all(
        candidate["canonical_source_id"] == selected_duplicate_doi["id"]
        for candidate in cross_provider_duplicates
    )
    scholarly_candidates = [
        candidate for candidate in candidates if candidate["provider"] in {"Crossref", "OpenAlex"}
    ]
    assert [candidate["ranking_order"] for candidate in candidates] == list(
        range(1, len(candidates) + 1)
    )
    assert scholarly_candidates
    assert all(
        candidate["relevance"]["score"] == candidate["relevance_score"]
        for candidate in scholarly_candidates
    )
    assert [candidate["selection_score"] for candidate in scholarly_candidates] == sorted(
        (candidate["selection_score"] for candidate in scholarly_candidates), reverse=True
    )
    assert all(candidate["relevance"]["interpretation_limit"] for candidate in scholarly_candidates)
    assert all(
        candidate["relevance"]["ranking_query_basis"] == "user_research_question"
        for candidate in scholarly_candidates
    )
    assert all(
        candidate["relevance"]["planned_query_alignment"]["ranking_query_basis"]
        == "recorded_provider_query"
        for candidate in scholarly_candidates
    )
    assert all(
        "productivity" in candidate["relevance"]["query_terms"]
        for candidate in scholarly_candidates
    )
    assert discovery_event["data"]["source_governance_plan"]["registry_version"]
    assert "academic" in discovery_event["data"]["source_governance_plan"]["planned_classes"]
    assert all(
        candidate["source_governance"]["source_classes"] == ["academic"]
        for candidate in scholarly_candidates
    )
    assert all(source["source_governance"]["source_classes"] == ["academic"] for source in sources)


def test_discovery_finds_unseeded_organization_and_persists_its_publications(client, monkeypatch):
    from app.providers.ror import ROROrganization

    seed = ScholarlyWork(
        external_id="doi:10.5555/seed",
        title="Renewable energy investment and climate policy in India",
        doi="10.5555/seed",
        url="https://doi.org/10.5555/seed",
        authors=[],
        published_year=2025,
        publisher="Example Energy Journal",
        abstract_excerpt="A study of investment and renewable energy policy in India.",
        query="renewable energy investment India climate policy",
        provider="OpenAlex",
        provider_metadata={
            "openalex_id": "https://openalex.org/W123",
            "institution_records": [
                {
                    "openalex_id": "I987",
                    "ror_id": "https://ror.org/03yrm5c26",
                    "display_name": "Unseeded Climate Research Institute",
                    "country_code": "IN",
                    "type": "facility",
                }
            ],
        },
    )
    organization_work = replace(
        seed,
        external_id="doi:10.5555/organization-study",
        doi="10.5555/organization-study",
        title="Renewable energy financing in Indian states",
        provider_metadata={
            **seed.provider_metadata,
            "openalex_id": "https://openalex.org/W456",
        },
    )

    class EmptyCrossref:
        def __init__(self):
            pass

        def search(self, _query, *, limit=5):
            return []

        def close(self):
            pass

    class DynamicOpenAlex:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, query, *, limit=5):
            return [replace(seed, query=query), replace(organization_work, query=query)]

        def search_for_institution(self, query, institution_id, *, limit=3):
            assert query == "Does renewable energy investment improve energy access in India?"
            assert institution_id == "I987"
            return [replace(organization_work, query=query)]

        def close(self):
            pass

    class FixtureROR:
        def verify(self, ror_id):
            assert ror_id == "https://ror.org/03yrm5c26"
            return ROROrganization(
                ror_id=ror_id,
                canonical_name="Unseeded Climate Research Institute",
                aliases=("UCRI",),
                organization_types=("nonprofit",),
                domains=("ucri.example",),
                official_urls=("https://ucri.example",),
                country_code="IN",
                record_status="active",
                last_modified="2026-10-20",
                retrieved_at="2026-11-01T10:00:00+00:00",
                api_url="https://api.ror.org/v2/organizations/03yrm5c26",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", EmptyCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", DynamicOpenAlex)
    monkeypatch.setattr(workflow, "RORProvider", FixtureROR)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="dynamic-organization-discovery",
        question="Does renewable energy investment improve energy access in India?",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "plan-dynamic-org-01"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-dynamic-org-01"},
    )
    event = next(
        item
        for item in client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
        if item["stage"] == "discovery"
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    with client.db_sessions() as db:
        coverage_lines, coverage = workflow._report_search_coverage(db, job["id"], len(sources))

    assert response.status_code == 200
    assert response.json()["current_stage"] == "extraction"
    assert "organization_discovery" in event["data"], event
    org_discovery = event["data"]["organization_discovery"]
    assert org_discovery["status"] == "completed", org_discovery
    assert org_discovery["organizations"][0]["identity_status"] == "VERIFIED_ESTABLISHED"
    assert org_discovery["organizations"][0]["registry_match"] is False
    assert org_discovery["organizations"][0]["quality_assessment"] == "not_assessed"
    assert org_discovery["publication_searches"][0]["provider"] == "OpenAlex"
    assert org_discovery["publication_searches"][0]["returned_count"] == 1
    selected_organization_source = next(
        source for source in sources if source["doi"] == "10.5555/organization-study"
    )
    assert selected_organization_source["organization_provenance"]["organization_name"] == (
        "Unseeded Climate Research Institute"
    )
    assert coverage["organization_discovery"]["organizations"][0]["registry_match"] is False
    selected_publications = coverage["organization_discovery"]["selected_publications"]
    assert len(selected_publications) == 2
    assert any(
        item["source_id"] == selected_organization_source["id"] for item in selected_publications
    )
    assert all(
        item["organization_name"] == "Unseeded Climate Research Institute"
        for item in selected_publications
    )
    assert any("Dynamic organization discovery" in line for line in coverage_lines)


def test_discovery_persists_openaire_unseeded_organization_publication(client, monkeypatch):
    from app.providers.ror import ROROrganization

    publication = ScholarlyWork(
        external_id="doi:10.5555/openaire-energy",
        title="Renewable energy finance and grid reliability in India",
        doi="10.5555/openaire-energy",
        url="https://doi.org/10.5555/openaire-energy",
        authors=[{"name": "A Researcher"}],
        published_year=2024,
        publisher="Climate Research Institute",
        abstract_excerpt=(
            "This report examines renewable energy investment, financing, and energy access in India."
        ),
        query="renewable energy investment India",
        provider="OpenAIRE",
        provider_metadata={
            "openaire_id": "doi_________::energy-report",
            "metadata_license": "CC-BY-4.0",
            "metadata_attribution": "OpenAIRE Graph; attribution required under CC-BY",
            "metadata_license_url": "https://graph.openaire.eu/docs/apis/terms/",
            "organization_records": [
                {
                    "openaire_id": "openorgs____::unseeded-climate-institute",
                    "ror_id": "https://ror.org/03yrm5c26",
                    "display_name": "Unseeded Climate Research Institute",
                    "website_url": "https://ucri.example",
                    "country_code": "IN",
                    "type": "openaire_affiliation",
                }
            ],
        },
    )

    class EmptyCrossref:
        organization_queries = []

        def __init__(self):
            pass

        def search(self, _query, *, limit=5):
            return []

        def search_for_organization(self, query, *, organization_names, limit=3):
            self.organization_queries.append((query, tuple(organization_names), limit))
            return [
                replace(
                    publication,
                    provider="Crossref",
                    query=query,
                    provider_metadata={
                        "matched_author_affiliation": "Unseeded Climate Research Institute",
                        "crossref_full_text": {"retrieval_status": "not_retrieved"},
                    },
                )
            ]

        def close(self):
            pass

    class EmptyOpenAlex:
        organization_queries = []
        ror_resolution_calls = 0

        def __init__(self, *args, **kwargs):
            pass

        def search(self, _query, *, limit=5):
            return []

        def resolve_institution_id_by_ror(self, ror_id):
            type(self).ror_resolution_calls += 1
            assert ror_id == "https://ror.org/03yrm5c26"
            return "I987"

        def search_for_institution(self, query, institution_id, *, limit=3):
            self.organization_queries.append((query, institution_id, limit))
            return [
                replace(
                    publication,
                    external_id="doi:10.5555/openaire-energy-openalex",
                    doi="10.5555/openaire-energy-openalex",
                    provider="OpenAlex",
                    query=query,
                    provider_metadata={
                        "openalex_id": "https://openalex.org/W987",
                        "institution_ids": {
                            "openalex": ["I987"],
                            "ror": ["https://ror.org/03yrm5c26"],
                        },
                        "institution_records": [
                            {
                                "openalex_id": "I987",
                                "ror_id": "https://ror.org/03yrm5c26",
                                "display_name": "Unseeded Climate Research Institute",
                                "country_code": "IN",
                                "type": "nonprofit",
                            }
                        ],
                    },
                )
            ]

        def close(self):
            pass

    class DynamicOpenAIRE:
        calls = []
        organization_queries = []

        def __init__(self, *args, **kwargs):
            pass

        def search_organizations(self, query, *, limit=8):
            self.organization_queries.append((query, limit))
            return [
                {
                    "openaire_id": "openorgs____::unseeded-climate-institute",
                    "canonical_name": "Unseeded Climate Research Institute",
                    "short_name": "UCRI",
                    "website_url": "https://ucri.example",
                    "country_code": "IN",
                    "ror_id": "https://ror.org/03yrm5c26",
                    "organization_type": "research_institute",
                },
                {
                    "openaire_id": "openorgs____::unseeded-climate-institute-duplicate",
                    "canonical_name": "Unseeded Climate Research Institute",
                    "short_name": "UCRI",
                    "website_url": "https://ucri.example",
                    "country_code": "IN",
                    "ror_id": "https://ror.org/03yrm5c26",
                    "organization_type": "research_institute",
                },
            ]

        def search_organization_publications(self, organization_ids, *, query, limit=8):
            self.calls.append((organization_ids, query, limit))
            raise AssertionError("verified organizations should use the reusable Crossref route")

        def close(self):
            pass

    class FixtureOfficialSiteSearch:
        calls = []
        failure = False

        def __init__(self, *, before_request=None):
            self.before_request = before_request

        def search(self, organization, *, question, query, limit=5):
            type(self).calls.append((organization["canonical_name"], query, limit))
            assert question == "Does renewable energy investment improve energy access in India?"
            if type(self).failure:
                self.before_request("https://ucri.example")
                raise RuntimeError("private provider detail must not be persisted")
            record = ScholarlyWork(
                external_id="official-site:ucri.example:77",
                title="Renewable energy investment and energy access in India",
                doi=None,
                url="https://ucri.example/research/energy-access",
                authors=[],
                published_year=2025,
                publisher="Unseeded Climate Research Institute",
                abstract_excerpt=None,
                query=query,
                provider="Official site WordPress search",
                provider_metadata={
                    "official_site_discovery": {
                        "organization_id": organization["ror_id"],
                        "organization_name": organization["canonical_name"],
                        "identity_status": organization["identity_status"],
                        "verification_source": organization["verification_source"],
                        "official_domain": "ucri.example",
                        "homepage_url": "https://ucri.example/",
                        "api_url": "https://ucri.example/wp-json/wp/v2/search",
                        "discovery_query": query,
                        "wordpress_record_id": 77,
                        "result_type": "post",
                        "result_subtype": "report",
                        "metadata_access": "public_official_site_search_api",
                        "content_fetched": False,
                        "rights_status": "not_assessed",
                        "quality_assessment": "not_assessed",
                        "publisher_verification": "official_domain_linked_from_ror_verified_site",
                    }
                },
                source_type="institutional_report",
            )
            from app.providers.official_site_search import OfficialSitePublicationSearchResult

            return OfficialSitePublicationSearchResult(
                "completed",
                organization["ror_id"],
                organization["canonical_name"],
                "https://ucri.example/",
                "https://ucri.example/wp-json/wp/v2/search",
                query,
                [record],
                2,
                "wordpress_api_link",
            )

        def close(self):
            pass

    class FixtureROR:
        calls = 0

        def search_exact_id(self, _expected_name):
            raise AssertionError("OpenAIRE result already carries a ROR identity")

        def verify(self, ror_id):
            type(self).calls += 1
            assert ror_id == "https://ror.org/03yrm5c26"
            return ROROrganization(
                ror_id=ror_id,
                canonical_name="Unseeded Climate Research Institute",
                aliases=("UCRI",),
                organization_types=("nonprofit",),
                domains=("ucri.example",),
                official_urls=("https://ucri.example",),
                country_code="IN",
                record_status="active",
                last_modified="2026-10-20",
                retrieved_at="2026-11-01T10:00:00+00:00",
                api_url="https://api.ror.org/v2/organizations/03yrm5c26",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", EmptyCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", EmptyOpenAlex)
    monkeypatch.setattr(workflow, "OpenAIREProvider", DynamicOpenAIRE)
    monkeypatch.setattr(workflow, "RORProvider", FixtureROR)
    monkeypatch.setattr(workflow, "WordPressPublicationSearchProvider", FixtureOfficialSiteSearch)
    monkeypatch.setattr(workflow, "_stage_time_remaining", lambda _job: 100.0)

    class ImmediateOriginLimiter:
        def __init__(self, _bind):
            pass

        def acquire(self, origin, interval, *, deadline):
            assert origin in {"https://api.openaire.eu", "https://ucri.example"}
            assert interval == (61.0 if origin == "https://api.openaire.eu" else 1.0)
            assert deadline > 0

    monkeypatch.setattr(workflow, "DatabaseOriginRequestLimiter", ImmediateOriginLimiter)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="dynamic-openaire-organization-discovery",
        question="Does renewable energy investment improve energy access in India?",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "plan-openaire-org-01"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-openaire-org-01"},
    )
    event = next(
        item
        for item in client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
        if item["stage"] == "discovery"
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    with client.db_sessions() as db:
        coverage_lines, coverage = workflow._report_search_coverage(db, job["id"], len(sources))

    assert response.status_code == 200
    assert len(DynamicOpenAIRE.calls) == 0
    assert len(EmptyCrossref.organization_queries) == 1
    assert EmptyCrossref.organization_queries[0][1][0] == "Unseeded Climate Research Institute"
    assert EmptyCrossref.organization_queries[0][2] == 3
    assert DynamicOpenAIRE.organization_queries == [('"renewable" AND "energy" AND "research"', 8)]
    assert "organization_discovery" in event["data"], event
    org_discovery = event["data"]["organization_discovery"]
    assert org_discovery["openaire_search"]["status"] == "completed", org_discovery
    assert org_discovery["openaire_search"]["mode"] == "topic_organization_discovery"
    assert org_discovery["openaire_search"]["query"] == DynamicOpenAIRE.organization_queries[0][0]
    assert event["data"]["provider_query_counts"]["OpenAIRE organization discovery"] == 1
    assert (
        event["data"]["provider_query_counts"]["Crossref organization-affiliation publications"]
        == 1
    )
    assert event["data"]["provider_query_counts"]["Official site publication search"] == 2
    assert org_discovery["seed_work_count"] == 1, org_discovery
    assert org_discovery["status"] == "completed", org_discovery
    assert org_discovery["organizations"][0]["openaire_ids"] == [
        "openorgs____::unseeded-climate-institute"
    ]
    assert org_discovery["organizations"][0]["identity_status"] == "VERIFIED_ESTABLISHED"
    assert org_discovery["organizations"][0]["openalex_ids"] == ["I987"]
    assert org_discovery["institution_resolutions"][0]["status"] == "completed"
    assert org_discovery["institution_resolutions"][0]["openalex_institution_id"] == "I987"
    assert EmptyOpenAlex.organization_queries == [
        ("Does renewable energy investment improve energy access in India?", "I987", 3)
    ]
    source = next(item for item in sources if item["doi"] == "10.5555/openaire-energy")
    assert source["provider"] == "Crossref"
    assert source["organization_provenance"]["organization_name"] == (
        "Unseeded Climate Research Institute"
    )
    selected = coverage["organization_discovery"]["selected_publications"]
    assert any(item["source_id"] == source["id"] for item in selected)
    official_source = next(
        item for item in sources if item["provider"] == "Official site WordPress search"
    )
    assert official_source["organization_provenance"]["organization_name"] == (
        "Unseeded Climate Research Institute"
    )
    assert official_source["retrieval_status"] == "metadata_only"
    assert official_source["official_site_publication"]["wordpress_record_id"] == 77
    assert official_source["official_site_publication"]["content_fetched"] is False
    assert official_source["official_site_publication"]["rights_status"] == "not_assessed"
    assert any(item["source_id"] == official_source["id"] for item in selected)
    institution_publication_source = next(
        item for item in sources if item["doi"] == "10.5555/openaire-energy-openalex"
    )
    assert institution_publication_source["organization_provenance"]["organization_id"] == (
        "https://ror.org/03yrm5c26"
    )
    assert any(item["source_id"] == institution_publication_source["id"] for item in selected)
    from app.models import VerifiedOrganizationIdentity

    with client.db_sessions() as db:
        identity = db.get(VerifiedOrganizationIdentity, "https://ror.org/03yrm5c26")
        assert identity is not None
        assert identity.canonical_name == "Unseeded Climate Research Institute"
        assert identity.official_domains_json == ["ucri.example"]
        assert identity.openalex_institution_id == "I987"
        assert identity.verification_source == "https://api.ror.org/v2/organizations/03yrm5c26"
    assert FixtureROR.calls == 1
    assert EmptyOpenAlex.ror_resolution_calls == 1

    completed = run_all_steps(client, job["id"])
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    assert completed["status"] == "completed_with_limitations"
    assert report["model_name"] is None
    assert any(
        citation["source_id"] == source["id"] for citation in report["citation_map"].values()
    )
    assert any(
        citation["source_id"] == official_source["id"]
        for citation in report["citation_map"].values()
    )
    assert "Renewable energy finance and grid reliability in India" in report["body_markdown"]

    followup_job = create_job(
        client,
        project["id"],
        idempotency_key="dynamic-openaire-organization-cache-reuse",
        question="Does renewable energy investment improve energy access in India?",
    )
    client.post(
        f"/api/v1/research-jobs/{followup_job['id']}/advance",
        json={"operation_key": "plan-openaire-org-cache"},
    )
    FixtureOfficialSiteSearch.failure = True
    followup_response = client.post(
        f"/api/v1/research-jobs/{followup_job['id']}/advance",
        json={"operation_key": "discover-openaire-org-cache"},
    )
    followup_discovery = next(
        item["data"]["organization_discovery"]
        for item in client.get(f"/api/v1/research-jobs/{followup_job['id']}/events").json()["items"]
        if item["stage"] == "discovery"
    )
    assert followup_response.status_code == 200
    assert followup_discovery["identity_cache_hits"] == 1
    assert followup_discovery["identity_requests_attempted"] == 0
    assert followup_discovery["organizations"][0]["verification_method"] == (
        "ror_exact_id_cache_reuse"
    )
    assert followup_discovery["institution_resolutions"][0]["status"] == ("reused_cached_mapping")
    assert not followup_discovery["institution_resolutions"][0]["request_dispatched"]
    failed_site_search = next(
        item
        for item in followup_discovery["publication_searches"]
        if item["provider"] == "Official site publication search"
    )
    assert failed_site_search["status"] == "failed"
    assert failed_site_search["error_class"] == "RuntimeError"
    assert failed_site_search["request_count"] == 1
    assert "private provider detail" not in json.dumps(failed_site_search)
    assert FixtureROR.calls == 1
    assert EmptyOpenAlex.ror_resolution_calls == 1
    assert FixtureOfficialSiteSearch.calls == [
        ("Unseeded Climate Research Institute", "renewable energy investment", 5),
        ("Unseeded Climate Research Institute", "renewable energy investment", 5),
    ]
    assert "academic" in coverage["source_governance"]["searched_classes"]
    assert any("OpenAIRE topic organization discovery" in line for line in coverage_lines)
    assert any(
        "Crossref organization-linked publication discovery" in line for line in coverage_lines
    )
    assert not any("OpenAIRE Graph publication search" in line for line in coverage_lines)


def test_world_bank_documents_publications_enter_source_registry_and_coverage(client, monkeypatch):
    monkeypatch.setattr(
        workflow.settings,
        "world_bank_documents_noncommercial_use_confirmed",
        True,
    )
    publication = ScholarlyWork(
        external_id="worldbank:31534595",
        title="Artificial Intelligence and Productivity in Emerging Economies",
        doi=None,
        url="https://documents.worldbank.org/curated/en/617511573040599056",
        authors=[{"name": "Research Department"}],
        published_year=2019,
        publisher="World Bank Group",
        abstract_excerpt="A study of AI adoption and productivity in emerging economies.",
        query="AI adoption productivity emerging economies",
        provider="World Bank Documents & Reports",
        provider_metadata={
            "api_documentation_url": "https://documents.worldbank.org/en/publication/documents-reports/api",
            "world_bank_document_id": "31534595",
            "report_number": "143357",
            "document_type": "Policy Research Working Paper",
            "official_document_url": "https://documents.worldbank.org/curated/en/617511573040599056",
            "official_pdf_url": "https://documents1.worldbank.org/curated/en/617511573040599056/pdf/report.pdf",
            "metadata_access": "public_official_api",
            "metadata_reuse_rights_status": "not_assessed",
            "full_text_retrieved": False,
            "full_text_rights_status": "not_assessed",
            "abstract_excerpt_truncated": False,
        },
        source_type="institutional_report",
    )

    class DynamicWorldBankDocuments:
        calls = []

        def __init__(self, *args, **kwargs):
            pass

        def search(self, query, *, limit=3):
            self.calls.append((query, limit))
            return [replace(publication, query=query)]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "WorldBankDocumentsProvider", DynamicWorldBankDocuments)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="world-bank-documents-discovery",
        question="Does AI adoption improve productivity in developing economies?",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "plan-world-bank-documents"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-world-bank-documents"},
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")
    with client.db_sessions() as db:
        lines, coverage = workflow._report_search_coverage(db, job["id"], len(sources))

    assert response.status_code == 200, response.text
    assert len(DynamicWorldBankDocuments.calls) == 1
    assert DynamicWorldBankDocuments.calls[0][1] <= 3
    assert DynamicWorldBankDocuments.calls[0][0] == "ai adoption productivity developing economies"
    source = next(item for item in sources if item["provider"] == "World Bank Documents & Reports")
    assert source["source_type"] == "institutional_report"
    assert source["source_governance"]["source_classes"] == ["multilateral"]
    assert source["source_governance"]["identity_status"] == "verified"
    assert source["source_governance"]["quality_review_status"] == "not_assessed"
    assert source["institutional_publication"]["publisher_record_id"] == "31534595"
    assert source["institutional_publication"]["full_text_retrieved"] is False
    assert source["institutional_publication"]["full_text_rights_status"] == "not_assessed"
    search = discovery_event["data"]["institutional_publication_search"]
    assert search["status"] == "completed"
    assert search["request_dispatched"] is True
    assert search["publication_ids"] == ["worldbank:31534595"]
    assert coverage["source_governance"]["class_status"]["multilateral"]["status"] == "searched"
    assert any("World Bank Documents & Reports publication metadata" in line for line in lines)


def test_world_bank_publication_search_is_not_dispatched_without_terms_confirmation(
    client, monkeypatch
):
    calls = []

    class ForbiddenWorldBankDocuments:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, query, *, limit=3):
            calls.append((query, limit))
            raise AssertionError(
                "World Bank search must remain disabled without terms confirmation"
            )

        def close(self):
            pass

    monkeypatch.setattr(
        workflow.settings,
        "world_bank_documents_noncommercial_use_confirmed",
        False,
    )
    monkeypatch.setattr(workflow, "WorldBankDocumentsProvider", ForbiddenWorldBankDocuments)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="world-bank-docs-terms-confirmation-required",
        question="Does AI adoption improve productivity in developing economies?",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "plan-world-bank-docs-terms"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-world-bank-docs-terms"},
    )

    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")
    search = discovery_event["data"]["institutional_publication_search"]
    assert response.status_code == 200, response.text
    assert calls == []
    assert search["status"] == "not_attempted_terms_confirmation_required"
    assert search["request_dispatched"] is False
    assert search["content_fetched"] is False


def test_govuk_policy_publication_search_persists_real_source_and_coverage_for_uk_scope(
    client, monkeypatch
):
    from app.providers.govuk_content import GovUKPublicationBody

    record = ScholarlyWork(
        external_id="govuk:/government/publications/renewable-energy-sector-plan",
        title="Clean Energy Industries Sector Plan",
        doi=None,
        url="https://www.gov.uk/government/publications/renewable-energy-sector-plan",
        authors=[],
        published_year=2025,
        publisher="Department for Energy Security and Net Zero",
        abstract_excerpt=None,
        query="renewable energy investment grid deployment",
        provider="GOV.UK Search API",
        source_type="institutional_report",
        provider_metadata={
            "api_documentation_url": "https://docs.publishing.service.gov.uk/repos/search-api/using-the-search-api.html",
            "api_reuse_url": "https://www.gov.uk/help/reuse-govuk-content",
            "record_path": "/government/publications/renewable-energy-sector-plan",
            "document_type": "policy_paper",
            "publishing_organizations": ["Department for Energy Security and Net Zero"],
            "publishing_organization_candidates": [
                {
                    "slug": "department-for-energy-security-and-net-zero",
                    "canonical_name": "Department for Energy Security and Net Zero",
                    "content_id": "11111111-1111-4111-8111-111111111111",
                    "organization_type": "ministerial_department",
                    "directory_status": "live",
                    "official_url": "https://www.gov.uk/government/organisations/department-for-energy-security-and-net-zero",
                }
            ],
            "metadata_access": "public_official_api",
            "metadata_reuse_status": "metadata_only_content_rights_not_assessed",
            "full_text_retrieved": False,
            "full_text_rights_status": "not_assessed",
            "api_support_status": "unsupported_best_effort",
            "selection_description": (
                "The United Kingdom plan describes investment in renewable energy and grid deployment."
            ),
        },
    )
    calls = []
    organization_calls = []
    content_calls = []

    class EmptyCrossref:
        def __init__(self):
            pass

        def search(self, _query, *, limit=5):
            return []

        def close(self):
            pass

    class GovUK:
        def __init__(self, *, before_request=None):
            self.before_request = before_request
            if before_request:
                before_request()

        def search(self, query, *, geography, limit=10):
            calls.append((query, geography, limit))
            return [record]

        def verify_organization(self, slug, *, expected_name, expected_content_id):
            if self.before_request:
                self.before_request()
            organization_calls.append((slug, expected_name, expected_content_id))
            return {
                "schema_version": 1,
                "organization_id": f"govuk:{slug}",
                "canonical_name": expected_name,
                "content_id": expected_content_id,
                "organization_type": "Ministerial department",
                "directory_status": "live",
                "identity_status": "VERIFIED_ESTABLISHED",
                "verification_method": "govuk_organizations_api_exact_slug",
                "verification_source": f"https://www.gov.uk/api/organisations/{slug}",
                "verification_timestamp": "2026-11-01T12:00:00+00:00",
                "official_url": f"https://www.gov.uk/government/organisations/{slug}",
                "quality_assessment": "not_assessed",
                "limitations": ["Directory identity only; research quality not assessed."],
                "publication_ids": [],
                "discovery_result_count": 1,
            }

        def close(self):
            pass

    class GovUKContent:
        def __init__(self, *, before_request=None):
            self.before_request = before_request

        def fetch_publication_body(self, record_path, *, expected_title):
            if self.before_request:
                self.before_request("https://www.gov.uk")
            content_calls.append((record_path, expected_title))
            return GovUKPublicationBody(
                title=expected_title,
                base_path=record_path,
                body_html=(
                    "<h2>Policy context</h2>"
                    "<p>The sector plan coordinates offshore wind deployment with transmission network investment.</p>"
                    "<p>It describes policy priorities, not independently measured project outcomes.</p>"
                ),
                api_url=f"https://www.gov.uk/api/content{record_path}",
                publication_url=f"https://www.gov.uk{record_path}",
                updated_at="2025-05-01T00:00:00Z",
                retrieved_at=utcnow(),
                license_code="ogl-3.0-default",
                license_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
                rights_status="PERMITTED_WITH_RESTRICTIONS",
                rights_limit=(
                    "Default OGL basis; no item license field. Page body only; attachments not fetched."
                ),
            )

        def close(self):
            pass

    class ImmediateOriginLimiter:
        def __init__(self, _db):
            pass

        def acquire(self, origin, _interval, *, deadline):
            assert origin == "https://www.gov.uk"
            assert deadline > 0

    monkeypatch.setattr(workflow, "CrossrefProvider", EmptyCrossref)
    monkeypatch.setattr(workflow, "GovUKSearchProvider", GovUK)
    monkeypatch.setattr(workflow, "GovUKContentProvider", GovUKContent)
    monkeypatch.setattr(workflow, "DatabaseOriginRequestLimiter", ImmediateOriginLimiter)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="govuk-source-discovery-uk-scope",
        geography="United Kingdom",
        question=(
            "What evidence links renewable energy investment with grid deployment in the United Kingdom?"
        ),
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "govuk-plan"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "govuk-discovery"},
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    candidates = client.get(f"/api/v1/research-jobs/{job['id']}/candidates").json()["items"]
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")
    with client.db_sessions() as db:
        _lines, coverage = workflow._report_search_coverage(db, job["id"], len(sources))

    assert response.status_code == 200, response.text
    assert len(calls) == 1
    assert len(organization_calls) == 1
    assert organization_calls[0][0] == "department-for-energy-security-and-net-zero"
    assert calls[0][1:] == ("United Kingdom", 10)
    source = next(item for item in sources if item["provider"] == "GOV.UK Search API")
    candidate = next(item for item in candidates if item["provider"] == "GOV.UK Search API")
    assert source["source_type"] == "institutional_report"
    assert source["source_governance"]["source_classes"] == ["government"]
    assert source["source_governance"]["identity_status"] == "verified"
    assert source["source_governance"]["methodological_quality"] == "not_assessed"
    assert source["official_publication"]["publishing_organizations"] == [
        "Department for Energy Security and Net Zero"
    ]
    assert candidate["publisher"] == "Department for Energy Security and Net Zero"
    assert candidate["publisher_organizations"][0]["identity_status"] == "VERIFIED_ESTABLISHED"
    assert source["official_publication"]["publishing_organization_records"][0][
        "organization_id"
    ] == ("govuk:department-for-energy-security-and-net-zero")
    assert source["official_publication"]["full_text_retrieved"] is False
    with client.db_sessions() as db:
        persisted_source = db.get(Source, source["id"])
        persisted_metadata = persisted_source.metadata_json["provider_metadata"]["extensions"]
        relevance = next(
            item.relevance_json
            for item in db.query(workflow.DiscoveryCandidate)
            .filter_by(job_id=job["id"], provider="GOV.UK Search API")
            .all()
        )
    assert "selection_description" not in persisted_metadata
    assert persisted_metadata["selection_context"] == {
        "field": "official_search_description",
        "matched_question_terms": [
            "deployment",
            "energy",
            "grid",
            "investment",
            "kingdom",
            "renewable",
            "united",
        ],
        "raw_description_retained": False,
        "used_for_topic_eligibility": True,
    }
    assert relevance["topic_eligibility_basis"] == "original_question"
    route = discovery_event["data"]["government_publication_search"]
    assert route["status"] == "completed"
    assert route["publication_ids"] == [record.external_id]
    assert route["linked_content_fetched"] is False
    assert route["organization_discovery"]["status"] == "verified"
    assert route["organization_discovery"]["requests_attempted"] == 1
    assert route["organization_discovery"]["organizations"][0]["quality_assessment"] == (
        "not_assessed"
    )
    assert coverage["source_governance"]["class_status"]["government"]["status"] == "searched"
    assert (
        coverage["government_publication_search"]["api_support_status"] == "unsupported_best_effort"
    )

    extraction = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "govuk-extract-publication-page-body"},
    )
    assert extraction.status_code == 200, extraction.text
    assert len(content_calls) == 1
    assert content_calls[0] == (
        "/government/publications/renewable-energy-sector-plan",
        "Clean Energy Industries Sector Plan",
    )
    inspected = client.get(f"/api/v1/sources/{source['id']}").json()
    assert inspected["retrieval_status"] == "official_publication_page_body"
    govuk_retrieval = inspected["retrieval"]["govuk_content"]
    assert govuk_retrieval["status"] == "retrieved"
    assert govuk_retrieval["rights_status"] == "PERMITTED_WITH_RESTRICTIONS"
    assert govuk_retrieval["attachments_fetched"] is False
    assert inspected["official_publication"]["full_text_retrieved"] is False
    assert len(inspected["passages"]) == 2
    assert inspected["passages"][0]["access_level"] == "official_publication_page_body"
    assert inspected["passages"][0]["content"] == (
        "The sector plan coordinates offshore wind deployment with transmission network investment."
    )
    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    assert any(claim["source_id"] == source["id"] for claim in claims)
    completed = run_all_steps(client, job["id"])
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    assert completed["status"] == "completed_with_limitations"
    assert any(
        citation["source_id"] == source["id"] for citation in report["citation_map"].values()
    )


def test_govuk_publication_route_is_not_dispatched_for_non_uk_scope(client, monkeypatch):
    calls = []

    class ForbiddenGovUK:
        def __init__(self, *args, **kwargs):
            calls.append("constructed")

    monkeypatch.setattr(workflow, "GovUKSearchProvider", ForbiddenGovUK)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="govuk-source-discovery-india-scope",
        geography="India",
        question="What do government policy papers say about renewable energy investment?",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "govuk-india-plan"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "govuk-india-discovery"},
    )
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")

    assert response.status_code == 200, response.text
    assert calls == []
    assert discovery_event["data"]["government_publication_search"]["status"] == (
        "not_applicable_explicit_uk_geography_required"
    )


def test_discovery_persists_bounded_openalex_citation_lineage_when_operator_enabled(
    client, monkeypatch
):
    seed = ScholarlyWork(
        external_id="openalex:W123456789",
        title="Generative AI and software developer productivity field experiment",
        doi="10.5555/seed-work",
        url="https://doi.org/10.5555/seed-work",
        authors=[],
        published_year=2024,
        publisher="Example Journal",
        abstract_excerpt="A workplace field experiment measures software developer productivity.",
        query="generative AI software developer productivity",
        provider="OpenAlex",
        provider_metadata={"openalex_id": "https://openalex.org/W123456789"},
    )
    citing = ScholarlyWork(
        external_id="doi:10.5555/citing-work",
        title="Generative AI software developer productivity in a workplace study",
        doi="10.5555/citing-work",
        url="https://doi.org/10.5555/citing-work",
        authors=[],
        published_year=2025,
        publisher="Example Journal",
        abstract_excerpt="A field study compares software developer productivity outcomes.",
        query="citation_forward from W123456789",
        provider="OpenAlex",
        provider_metadata={"openalex_id": "https://openalex.org/W987654321"},
    )

    class EmptyCrossref:
        def __init__(self):
            pass

        def search(self, _query, *, limit=5):
            return []

        def close(self):
            pass

    class CitationOpenAlex:
        def __init__(self, **_kwargs):
            pass

        def search(self, query, *, limit=5):
            return [replace(seed, query=query)]

        def expand_citation_neighborhood(self, seed_ids, *, limit_per_direction, max_seeds):
            assert seed_ids == ["W123456789"]
            assert limit_per_direction == 3
            assert max_seeds == 2
            return CitationExpansionResult(
                status="completed",
                seed_openalex_ids=seed_ids,
                candidates=[CitationExpansionCandidate("forward", "W123456789", citing)],
                requests_attempted=3,
                reported_cost_usd=0.0006,
                reported_cost_status="provider_reported_complete",
                omitted_backward_count=4,
                backward_available_counts={"W123456789": 7},
                forward_result_counts={"W123456789": 12},
                forward_returned_counts={"W123456789": 1},
                errors=[],
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", EmptyCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", CitationOpenAlex)
    monkeypatch.setattr(workflow.settings, "openalex_api_key", "fixture-key")
    monkeypatch.setattr(workflow.settings, "openalex_allow_billable_calls", True)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="citation-expansion-lineage",
        question="Does generative AI improve software developer productivity?",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "plan-citation-01"}
    )
    discovery = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-citation-01"},
    )
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    candidates = client.get(f"/api/v1/research-jobs/{job['id']}/candidates").json()["items"]
    event = next(item for item in events if item["stage"] == "discovery")
    expansion = event["data"]["citation_expansion"]

    assert discovery.status_code == 200
    assert discovery.json()["current_stage"] == "extraction"
    assert expansion["status"] == "completed"
    assert expansion["requests_attempted"] == 3
    assert expansion["reported_cost_usd"] == pytest.approx(0.0006)
    assert expansion["omitted_backward_count"] == 4
    assert expansion["seeds"][0]["references_available"] == 7
    assert expansion["seeds"][0]["forward_result_count"] == 12
    assert expansion["candidate_keys"]
    assert any(candidate["provider"] == "OpenAlex" for candidate in candidates)
    assert "not a complete citation review" in expansion["sampling_note"]
    with client.db_sessions() as db:
        coverage_lines, coverage = workflow._report_search_coverage(db, job["id"], 1)
    assert coverage["citation_expansion"]["candidate_keys"] == expansion["candidate_keys"]
    assert "provider-reported cost: $0.000600 USD" in "\n".join(coverage_lines)


def test_openalex_failure_degrades_without_discarding_crossref_results(client, monkeypatch):
    class BrokenOpenAlex:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, query, *, limit=5):
            raise OpenAlexError("OpenAlex rate limit reached; retry this step later")

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", BrokenOpenAlex)
    project = create_project(client)
    job = create_job(client, project["id"])
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "plan-partial-01"}
    )
    discovery = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-partial-01"},
    ).json()
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")

    assert discovery["current_stage"] == "extraction"
    assert len(sources) == 2
    assert discovery_event["data"]["provider_failures"]["OpenAlex"] > 0


def test_invalid_provider_metadata_degrades_only_that_provider_query(client, monkeypatch):
    class MalformedOpenAlex:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, query, *, limit=5):
            return [
                ScholarlyWork(
                    external_id="openalex:W111",
                    title="Malformed OpenAlex metadata fixture",
                    doi=None,
                    url="https://openalex.org/W111",
                    authors=[],
                    published_year=2024,
                    publisher=None,
                    abstract_excerpt=None,
                    query=query,
                    provider="OpenAlex",
                    provider_metadata={"open_access": {"is_oa": "yes"}},
                )
            ]

        def close(self):
            pass

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    monkeypatch.setattr(workflow, "OpenAlexProvider", MalformedOpenAlex)
    project = create_project(client)
    job = create_job(client, project["id"])
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "plan-metadata-01"}
    )
    discovery = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-metadata-01"},
    ).json()
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    discovery_event = next(event for event in events if event["stage"] == "discovery")

    assert discovery["current_stage"] == "extraction"
    assert sources and {source["provider"] for source in sources} == {"Crossref"}
    assert discovery_event["data"]["provider_failures"]["OpenAlex"] > 0


def test_duplicate_advance_operation_is_idempotent(client, monkeypatch):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    project = create_project(client)
    job = create_job(client, project["id"])
    payload = {"operation_key": "same-operation-key-01"}

    first = client.post(f"/api/v1/research-jobs/{job['id']}/advance", json=payload).json()
    second = client.post(f"/api/v1/research-jobs/{job['id']}/advance", json=payload).json()

    assert first["version"] == second["version"]
    assert first["current_stage"] == second["current_stage"] == "discovery"
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
    assert len([event for event in events if event["event_type"] == "step_completed"]) == 1


def test_project_and_nested_resources_are_owner_scoped(client, monkeypatch, test_user):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    project = create_project(client)
    job = create_job(client, project["id"])
    run_all_steps(client, job["id"])
    source = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"][0]
    with client.db_sessions() as db:
        stored_source = db.get(Source, source["id"])
        passage_record = add_test_passage(
            db,
            stored_source,
            ordinal=0,
            locator="fixture full-text passage",
            content="Fixture sentence for owner-scoped passage lookup.",
            access_level="full_text_html",
        )
        db.flush()
        db.add(
            Claim(
                job_id=job["id"],
                source_id=stored_source.id,
                passage_id=passage_record.id,
                text=passage_record.content,
                span_start=0,
                span_end=len(passage_record.content),
                atomization_status="whole_sentence",
                atomization_version=1,
            )
        )
        db.commit()
    passage = client.get(f"/api/v1/sources/{source['id']}").json()["passages"][0]
    claim = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"][0]
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    conversation = client.post(f"/api/v1/projects/{project['id']}/conversations").json()
    message = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "Compare this evidence with a shorter time horizon."},
    ).json()
    test_user["id"] = "20000000-0000-4000-8000-000000000002"

    requests = [
        ("GET", f"/api/v1/projects/{project['id']}", None),
        ("PATCH", f"/api/v1/projects/{project['id']}", {"title": "stolen edit"}),
        ("DELETE", f"/api/v1/projects/{project['id']}", None),
        ("GET", f"/api/v1/projects/{project['id']}/conversations", None),
        ("POST", f"/api/v1/projects/{project['id']}/conversations", None),
        ("GET", f"/api/v1/conversations/{conversation['id']}/messages", None),
        (
            "POST",
            f"/api/v1/conversations/{conversation['id']}/messages",
            {"content": "cross-owner write attempt"},
        ),
        ("GET", f"/api/v1/conversations/{conversation['id']}/messages?limit=10", None),
        ("GET", f"/api/v1/projects/{project['id']}/research-jobs", None),
        (
            "POST",
            f"/api/v1/projects/{project['id']}/research-jobs",
            {
                "question": "An unauthorized cross-user research question",
                "idempotency_key": "cross-user-job-key-01",
            },
        ),
        ("GET", f"/api/v1/projects/{project['id']}/usage", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/plan", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/events", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/sources", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/candidates", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/claims", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/hypotheses", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/relationships", None),
        ("GET", f"/api/v1/research-jobs/{job['id']}/report", None),
        (
            "POST",
            f"/api/v1/research-jobs/{job['id']}/advance",
            {"operation_key": "other-user-operation-01"},
        ),
        ("POST", f"/api/v1/research-jobs/{job['id']}/pause", None),
        ("POST", f"/api/v1/research-jobs/{job['id']}/resume", None),
        ("POST", f"/api/v1/research-jobs/{job['id']}/cancel", None),
        ("GET", f"/api/v1/sources/{source['id']}", None),
        ("GET", f"/api/v1/passages/{passage['id']}", None),
        ("GET", f"/api/v1/claims/{claim['id']}/evidence", None),
        ("GET", f"/api/v1/reports/{report['id']}", None),
        ("GET", f"/api/v1/reports/{report['id']}/export?format=json", None),
    ]
    for method, path, payload in requests:
        response = client.request(method, path, json=payload)
        assert response.status_code == 404, (
            f"{method} {path}: {response.status_code} {response.text}"
        )
    assert project["id"] not in [
        item["id"] for item in client.get("/api/v1/projects").json()["items"]
    ]
    assert message["content"] == "Compare this evidence with a shorter time horizon."


def test_failed_provider_step_is_durable_and_resumable(client, monkeypatch):
    class BrokenCrossref(FakeCrossref):
        def search(self, query, *, limit=5):
            raise workflow.WorkflowError(
                "provider_unavailable", "temporarily unreachable", retryable=True
            )

    monkeypatch.setattr(workflow, "CrossrefProvider", BrokenCrossref)
    project = create_project(client)
    job = create_job(client, project["id"])
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "plan-operation-01"}
    )

    failed = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "failed-operation-01"}
    ).json()
    assert failed["status"] == "retryable_failure"
    assert failed["error_class"] == "providers_unavailable"
    assert client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"] == []

    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    resumed = client.post(f"/api/v1/research-jobs/{job['id']}/resume").json()
    assert resumed["status"] == "queued"
    advanced = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance", json={"operation_key": "retry-operation-01"}
    ).json()
    assert advanced["status"] == "active"
    assert advanced["current_stage"] == "extraction"
    assert len(client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]) == 2


def test_resume_reclaims_expired_worker_lease_from_persisted_state(client):
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="expired-worker-job-01")
    with client.db_sessions() as db:
        persisted = db.get(ResearchJob, job["id"])
        assert persisted is not None
        persisted.status = "active"
        persisted.lease_owner = "worker-lost-with-process"
        persisted.lease_expires_at = utcnow().replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()

    resumed = client.post(f"/api/v1/research-jobs/{job['id']}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"
    assert resumed.json()["error_class"] is None


def test_project_idempotency_and_archive(client):
    project = create_project(client)
    first = create_job(client, project["id"])
    duplicate = create_job(client, project["id"])
    assert first["id"] == duplicate["id"]
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 404
    archived = client.get("/api/v1/projects?include_archived=true").json()["items"]
    assert any(item["id"] == project["id"] and item["archived_at"] for item in archived)
    archived_only = client.get("/api/v1/projects?archived_only=true").json()["items"]
    assert [item["id"] for item in archived_only] == [project["id"]]
    assert client.post(f"/api/v1/projects/{project['id']}/restore").status_code == 200
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200


def test_archived_project_reports_remain_exportable_and_restore_is_owner_scoped(
    client, monkeypatch
):
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    project = create_project(client)
    job = create_job(client, project["id"])
    run_all_steps(client, job["id"])
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()

    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/v1/reports/{report['id']}").status_code == 200
    markdown = client.get(f"/api/v1/reports/{report['id']}/export?format=markdown")
    json_export = client.get(f"/api/v1/reports/{report['id']}/export?format=json")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert json_export.status_code == 200
    assert json_export.json()["id"] == report["id"]

    owner_a = client.test_user["id"]
    client.test_user["id"] = "30000000-0000-4000-8000-000000000003"
    assert client.post(f"/api/v1/projects/{project['id']}/restore").status_code == 404
    client.test_user["id"] = owner_a
    restored = client.post(f"/api/v1/projects/{project['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None


def test_project_edit_updates_fields_and_rejects_blank_names(client):
    project = create_project(client)

    updated = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={
            "title": "Updated research",
            "domain": "SME productivity",
            "description": "Decision context",
        },
    )
    blank = client.patch(f"/api/v1/projects/{project['id']}", json={"title": "   "})

    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated research"
    assert updated.json()["domain"] == "SME productivity"
    assert updated.json()["description"] == "Decision context"
    assert blank.status_code == 422


def test_project_brief_context_is_snapshotted_independently_per_research_run(client):
    project = create_project(client)
    project_brief = "Compare productivity gains with implementation costs for small firms."
    first = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What evidence compares productivity and implementation costs?",
            "context": project_brief,
            "depth": "quick",
            "budget_ceiling_usd": 0,
            "idempotency_key": "project-brief-run-01",
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["scope"]["context"] == project_brief

    updated_brief = "Assess rural firms separately from urban firms."
    update = client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"description": updated_brief},
    )
    assert update.status_code == 200, update.text

    second = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What evidence compares productivity and implementation costs?",
            "context": updated_brief,
            "depth": "quick",
            "budget_ceiling_usd": 0,
            "idempotency_key": "project-brief-run-02",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["scope"]["context"] == updated_brief

    owner_id = client.test_user["id"]
    client.test_user["id"] = "30000000-0000-4000-8000-000000000003"
    assert client.get(f"/api/v1/research-jobs/{first.json()['id']}").status_code == 404
    client.test_user["id"] = owner_id

    reread_first = client.get(f"/api/v1/research-jobs/{first.json()['id']}")
    assert reread_first.status_code == 200
    assert reread_first.json()["scope"]["context"] == project_brief


def test_zero_paid_budget_completes_with_limited_report_without_model_calls(client, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(
        workflow,
        "settings",
        Settings(
            llm_provider="openai",
            openai_api_key="test-key",
            openai_model_fast="gpt-6-luna",
            allow_paid_llm_calls=True,
            openai_input_price_per_million=0.1,
            openai_output_price_per_million=0.5,
        ),
    )
    monkeypatch.setattr(workflow, "CrossrefProvider", FakeCrossref)
    project = create_project(client)
    job = create_job(client, project["id"], idempotency_key="zero-budget-run-01")

    final = run_all_steps(client, job["id"])
    report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
    usage = client.get(f"/api/v1/projects/{project['id']}/usage").json()

    assert final["status"] == "completed_with_limitations"
    assert usage["model_calls"] == 0
    assert report["model_name"] is None
    assert (
        "model-generated synthesis and semantic citation checks did not run"
        in report["body_markdown"].lower()
    )


def test_model_synthesis_deduplicates_shared_passage_text_before_prompt_budget_check(
    client, monkeypatch
):
    project = create_project(client)
    job_payload = create_job(
        client,
        project["id"],
        idempotency_key="synthesis-passage-dedup",
        question="How do studies measure productivity and what explains different results?",
    )
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
    captured = {}

    def capture_blocker(_db, _job, *, system, user, **_kwargs):
        captured["system"] = system
        captured["user"] = user
        return "fixture_prompt_capture_only"

    monkeypatch.setattr(workflow, "_model_call_blocker", capture_blocker)
    long_passages = []
    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job_payload["id"])
        source_records = []
        claim_number = 0
        for source_index in range(12):
            source = Source(
                job_id=job_payload["id"],
                external_id=f"source:compact-{source_index}",
                title=f"Study {source_index} on productivity measurement",
                retrieval_status="abstract_only",
                appraisal_json={
                    "status": "model_assessed_not_independently_verified",
                    "fields": {
                        "design_type": {
                            "value": "bounded design description " * 8,
                            "passage_ids": [],
                        },
                        "sample": {
                            "value": "bounded sample description " * 8,
                            "passage_ids": [],
                        },
                    },
                },
            )
            db.add(source)
            db.flush()
            passage_text = (
                f"PASSAGE-{source_index}-" + ("reported study methods and outcomes " * 30)
            )[:600]
            passage = add_test_passage(
                db,
                source,
                ordinal=1,
                locator="abstract excerpt",
                content=passage_text,
            )
            source_records.append((source, passage))
            long_passages.append(passage_text)
            claims_for_source = 3 if source_index < 2 else 2
            for _local_index in range(claims_for_source):
                claim_number += 1
                db.add(
                    Claim(
                        job_id=job_payload["id"],
                        source_id=source.id,
                        passage_id=passage.id,
                        text=f"Reported finding {claim_number}: {passage_text[20:110]}",
                        appraisal_json={
                            "methodology_appraisal": {
                                "status": "model_assessed_not_independently_verified",
                                "relationship": "qualifies",
                                "rationale": "methodological qualification " * 8,
                                "passage_ids": [passage.id],
                            },
                            "economic_facets": {
                                "status": "model_assessed_not_independently_verified",
                                "evidence_kind": "association",
                                "facets": {
                                    name: {
                                        "value": f"{name} value " * 12,
                                        "passage_ids": [passage.id],
                                    }
                                    for name in (
                                        "population",
                                        "intervention_or_exposure",
                                        "comparator",
                                        "outcome",
                                    )
                                },
                            },
                        },
                    )
                )
        assert claim_number == 26
        db.commit()
        citation_map = {
            f"S{index + 1}": {"source_id": source.id, "passages": [passage.id]}
            for index, (source, passage) in enumerate(source_records)
        }
        report, usage, skip_reason = workflow._build_model_report(
            db, workflow.job_snapshot(persisted_job), citation_map
        )

    payload = json.loads(captured["user"])
    assert report[0].startswith("# Preliminary evidence map")
    assert usage is None
    assert skip_reason == "fixture_prompt_capture_only"
    assert len(payload["evidence"]["sources"]) == 12
    assert len(payload["evidence"]["claims"]) == 26
    assert sum(len(item["passages"]) for item in payload["evidence"]["sources"]) == 12
    assert all(captured["user"].count(text) == 1 for text in long_passages)
    assert all(
        set(claim)
        <= {
            "claim_id",
            "source_id",
            "passage_id",
            "claim_text",
            "claim_text_truncated",
        }
        for claim in payload["evidence"]["claims"]
    )
    assert all(source["methodological_appraisal"] for source in payload["evidence"]["sources"])
    assert all(
        field.get("value_truncated") is True
        for source in payload["evidence"]["sources"]
        for field in source["methodological_appraisal"].values()
    )
    assert all(claim.get("claim_text_truncated") is True for claim in payload["evidence"]["claims"])
    assert len(captured["system"]) + len(captured["user"]) < 24_000


@pytest.mark.parametrize(
    "verification_path",
    [
        "ror",
        "crossref_publisher_link",
        "official_page_metadata",
        "crossref_and_official_page_metadata",
    ],
)
def test_general_web_discovery_verifies_unknown_domain_and_selects_official_publication(
    client, monkeypatch, verification_path
):
    from app.providers.crawl4ai_cloud import (
        Crawl4AIBalance,
        Crawl4AIWebHit,
        Crawl4AIWebSearchResult,
    )
    from app.providers.official_site_search import OfficialSitePublicationSearchResult
    from app.providers.ror import ROROrganization

    publication = ScholarlyWork(
        external_id="official-site:windlab.example:710",
        title="Offshore wind transmission planning in India: engineering research report",
        doi=None,
        url="https://windlab.example/reports/offshore-wind-transmission",
        authors=[],
        published_year=2025,
        publisher="Unseeded Wind Systems Laboratory",
        abstract_excerpt=None,
        query="offshore wind transmission India",
        provider="Official site publication search",
        provider_metadata={"official_site_discovery": {"content_fetched": False}},
        source_type="institutional_report",
    )

    class FakeCrawl4AI:
        queries = []

        def __init__(self, *, api_key):
            assert api_key == "test-only-crawl-key"

        def balance(self):
            return Crawl4AIBalance(
                plan="free",
                balance_credits=100.0,
                allowance_left_credits=90.0,
                raw_status="reported",
            )

        def search(self, query, *, limit=10):
            self.queries.append(query)
            site_search = query.startswith("site:windlab.example ")
            if site_search and verification_path == "crossref_and_official_page_metadata":
                hits = (
                    Crawl4AIWebHit(
                        title="Offshore wind transmission system dynamics in India",
                        url="https://windlab.example/research/offshore-wind-dynamics",
                        snippet="Untrusted search snippet; not stored as evidence.",
                        source="gg",
                        rank=1,
                        normalized_domain="windlab.example",
                    ),
                    Crawl4AIWebHit(
                        title="Offshore wind transmission policy response evidence report",
                        url="https://windlab.example/reports/offshore-wind-transmission.html",
                        snippet="Untrusted search snippet; not stored as evidence.",
                        source="gg",
                        rank=2,
                        normalized_domain="windlab.example",
                    ),
                )
            else:
                hits = (
                    Crawl4AIWebHit(
                        title=(
                            "Offshore wind transmission system dynamics in India"
                            if verification_path
                            in {"crossref_publisher_link", "crossref_and_official_page_metadata"}
                            and not site_search
                            else "Offshore wind transmission policy response evidence report"
                            if site_search
                            and verification_path == "crossref_and_official_page_metadata"
                            else "Offshore wind transmission planning in India engineering report"
                            if site_search
                            else "Unseeded Wind Systems Laboratory research report"
                        ),
                        url=(
                            "https://windlab.example/reports/offshore-wind-transmission.html"
                            if site_search
                            and verification_path
                            in {"official_page_metadata", "crossref_and_official_page_metadata"}
                            else "https://windlab.example/reports/offshore-wind-transmission-study"
                            if site_search
                            else "https://windlab.example/research/offshore-wind-transmission"
                            if verification_path
                            in {"crossref_publisher_link", "crossref_and_official_page_metadata"}
                            else "https://windlab.example/reports/offshore-wind-transmission.html"
                            if verification_path == "official_page_metadata"
                            else "https://windlab.example/reports/offshore-wind-transmission"
                        ),
                        snippet="Untrusted search snippet; not stored as evidence.",
                        source="gg",
                        rank=1,
                        normalized_domain="windlab.example",
                    ),
                )
            return Crawl4AIWebSearchResult(
                query=query,
                provider="Crawl4AI Cloud",
                searched_at="2026-11-01T12:00:00+00:00",
                hits=hits,
                reported_cost_credits=1.0,
                balance_credits=99.0,
                allowance_left_credits=89.0,
                usage_status="reported",
            )

        def close(self):
            pass

    class FixtureROR:
        def search_exact_domain(self, domain):
            assert domain == "windlab.example"
            return (
                "https://ror.org/03yrm5c26"
                if verification_path
                in {"ror", "official_page_metadata", "crossref_and_official_page_metadata"}
                else None
            )

        def verify(self, ror_id):
            assert verification_path in {
                "ror",
                "official_page_metadata",
                "crossref_and_official_page_metadata",
            }
            return ROROrganization(
                ror_id=ror_id,
                canonical_name="Unseeded Wind Systems Laboratory",
                aliases=("UWSL",),
                organization_types=("nonprofit",),
                domains=(
                    ()
                    if verification_path
                    in {"official_page_metadata", "crossref_and_official_page_metadata"}
                    else ("windlab.example",)
                ),
                official_urls=("https://www.windlab.example/about",),
                country_code="IN",
                record_status="active",
                last_modified="2026-10-20",
                retrieved_at="2026-11-01T12:00:00+00:00",
                api_url="https://api.ror.org/v2/organizations/03yrm5c26",
            )

        def close(self):
            pass

    class FixtureOfficialSite:
        search_calls = 0

        def __init__(self, *args, **kwargs):
            self.before_request = kwargs.get("before_request")

        def search(self, organization, *, question, query=None, limit=5):
            type(self).search_calls += 1
            assert organization["canonical_name"] == "Unseeded Wind Systems Laboratory"
            assert organization["identity_status"] == (
                "VERIFIED_ESTABLISHED"
                if verification_path in {"ror", "crossref_and_official_page_metadata"}
                else "VERIFIED_DOMAIN_SPECIALIST"
            )
            return OfficialSitePublicationSearchResult(
                status="completed",
                organization_id=organization["organization_id"],
                organization_name=organization["canonical_name"],
                homepage_url="https://windlab.example/",
                api_url="https://windlab.example/wp-json/wp/v2/search",
                query=query or "offshore wind transmission india",
                records=[publication],
                request_count=2,
                discovery_link_source="wordpress_api_link",
            )

        def verify_publication_page(self, organization, publication_url, *, expected_title):
            assert verification_path in {
                "official_page_metadata",
                "crossref_and_official_page_metadata",
            }
            assert organization["canonical_name"] == "Unseeded Wind Systems Laboratory"
            assert publication_url.endswith(".html")
            assert "Offshore wind transmission" in expected_title
            from app.providers.official_site_search import OfficialPublicationPageMetadata

            return OfficialPublicationPageMetadata(
                requested_url=publication_url,
                canonical_url=publication_url,
                title="Offshore wind transmission planning in India engineering report",
                publication_date="2025-04-12",
                metadata_kind="citation_metadata",
                retrieved_at="2026-11-01T12:00:00+00:00",
                request_count=2,
            )

        def close(self):
            pass

    class EmptyCrossref:
        queries = []

        def __init__(self, *args, **kwargs):
            type(self).queries = []

        def search(self, query, *, limit=5):
            type(self).queries.append(query)
            if (
                query == "Offshore wind transmission system dynamics in India"
                and verification_path
                in {"crossref_publisher_link", "crossref_and_official_page_metadata"}
            ):
                return [
                    ScholarlyWork(
                        external_id="doi:10.5555/offshore-wind-dynamics",
                        title=query,
                        doi="10.5555/offshore-wind-dynamics",
                        url="https://doi.org/10.5555/offshore-wind-dynamics",
                        authors=[],
                        published_year=2025,
                        publisher="Unseeded Wind Systems Laboratory",
                        abstract_excerpt="The paper models offshore wind transmission system dynamics.",
                        query=query,
                        provider="Crossref",
                        provider_metadata={
                            "crossref_full_text": {
                                "links": [{"url": "https://windlab.example/reports/dynamics.pdf"}]
                            }
                        },
                    )
                ][:limit]
            if (
                query == "Offshore wind transmission planning in India engineering report"
                and verification_path != "official_page_metadata"
            ):
                return [
                    ScholarlyWork(
                        external_id="doi:10.5555/offshore-wind-transmission",
                        title="Offshore wind transmission planning in India engineering report",
                        doi="10.5555/offshore-wind-transmission",
                        url="https://doi.org/10.5555/offshore-wind-transmission",
                        authors=[],
                        published_year=2025,
                        publisher="Unseeded Wind Systems Laboratory",
                        abstract_excerpt="The report assesses transmission engineering options.",
                        query=query,
                        provider="Crossref",
                        provider_metadata={
                            "crossref_full_text": {
                                "license_code": None,
                                "links": [
                                    {
                                        "url": "https://windlab.example/reports/offshore-wind-transmission.pdf"
                                    }
                                ],
                            }
                        },
                        source_type="scholarly_article",
                    )
                ][:limit]
            return []

        def resolve_doi(self, doi):
            assert doi == "10.5555/offshore-wind-transmission"
            return ScholarlyWork(
                external_id="doi:10.5555/offshore-wind-transmission",
                title="Offshore wind transmission planning in India engineering report",
                doi=doi,
                url="https://doi.org/10.5555/offshore-wind-transmission",
                authors=[],
                published_year=2025,
                publisher="Unseeded Wind Systems Laboratory",
                abstract_excerpt="The report assesses transmission engineering options.",
                query=f"doi:{doi}",
                provider="Crossref",
                provider_metadata={
                    "crossref_full_text": {
                        "license_code": None,
                        "links": [
                            {
                                "url": "https://windlab.example/reports/offshore-wind-transmission.pdf"
                            }
                        ],
                    }
                },
                source_type="scholarly_article",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow.settings, "crawl4ai_enabled", True)
    monkeypatch.setattr(workflow.settings, "crawl4ai_key", "test-only-crawl-key")
    monkeypatch.setattr(workflow, "Crawl4AICloudSearchProvider", FakeCrawl4AI)
    monkeypatch.setattr(workflow, "RORProvider", FixtureROR)
    monkeypatch.setattr(workflow, "WordPressPublicationSearchProvider", FixtureOfficialSite)
    monkeypatch.setattr(workflow, "CrossrefProvider", EmptyCrossref)

    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="general-web-unseeded-organization",
        question="What are the offshore wind transmission challenges affecting development in India?",
        model_provider="disabled",
    )
    client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "plan-general-web-01"},
    )
    response = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "discover-general-web-01"},
    )
    event = next(
        item
        for item in client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]
        if item["stage"] == "discovery"
    )
    sources = client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]

    assert response.status_code == 200
    assert response.json()["current_stage"] == "extraction"
    assert event["data"]["general_web_discovery"]["status"] == "completed"
    routing = event["data"]["general_web_discovery"]["domain_candidate_routing"]
    assert any(
        item["domain"] == "windlab.example"
        and item["status"] == "eligible_for_identity_verification"
        and "wind" in item["matched_topic_terms"]
        and "transmission" in item["matched_topic_terms"]
        for item in routing
    )
    assert event["data"]["general_web_discovery"]["request_count"] == 2, json.dumps(
        event["data"]["general_web_discovery"], indent=2
    )
    assert len(FakeCrawl4AI.queries) == 2
    assert FakeCrawl4AI.queries[1].startswith("site:windlab.example ")
    assert event["data"]["general_web_discovery"]["searches"][1]["purpose"] == (
        "verified_official_domain_publication_discovery"
    )
    verified_publications = event["data"]["general_web_discovery"]["verified_official_publications"]
    if verification_path == "official_page_metadata":
        assert len(verified_publications) == 1
        assert verified_publications[0]["doi"] is None
        assert verified_publications[0]["publisher_verification"] == (
            "official_page_metadata_verified"
        )
        assert verified_publications[0]["page_body_retained"] is False
    elif verification_path == "crossref_and_official_page_metadata":
        assert any(
            item.get("doi") == "10.5555/offshore-wind-dynamics" for item in verified_publications
        ), json.dumps(
            event["data"]["general_web_discovery"].get("publication_verification_attempts"),
            indent=2,
        )
        assert any(
            item.get("publisher_verification") == "official_page_metadata_verified"
            and item.get("doi") is None
            for item in verified_publications
        )
        page_attempt = next(
            item
            for item in event["data"]["general_web_discovery"]["publication_verification_attempts"]
            if item.get("verification_method")
            == "verified_domain_robots_and_page_metadata_title_match"
        )
        assert page_attempt["search_title"] == (
            "Offshore wind transmission policy response evidence report"
        )
    else:
        assert any(
            item["doi"] == "10.5555/offshore-wind-transmission" for item in verified_publications
        )
        assert verified_publications[0]["lookup_method"] == (
            "crossref_title_search"
            if verification_path == "ror"
            else "crossref_publisher_link_domain_match"
        )
    expected_crossref_query = (
        "Offshore wind transmission system dynamics in India"
        if verification_path in {"crossref_publisher_link", "crossref_and_official_page_metadata"}
        else "Offshore wind transmission planning in India engineering report"
    )
    assert expected_crossref_query in EmptyCrossref.queries
    dynamic_org = next(
        item
        for item in event["data"]["organization_discovery"]["organizations"]
        if item["canonical_name"] == "Unseeded Wind Systems Laboratory"
    )
    assert dynamic_org["identity_status"] == (
        "VERIFIED_ESTABLISHED"
        if verification_path
        in {"ror", "official_page_metadata", "crossref_and_official_page_metadata"}
        else "VERIFIED_DOMAIN_SPECIALIST"
    )
    assert dynamic_org["registry_match"] is False
    assert FixtureOfficialSite.search_calls == 0
    assert any(
        item["provider"] == "Official site publication search"
        and item["status"] == "not_attempted_verified_publication_already_discovered"
        and item["request_count"] == 0
        for item in event["data"]["organization_discovery"]["publication_searches"]
    )
    assert all(source["title"] != publication.title for source in sources)
    if verification_path in {"official_page_metadata", "crossref_and_official_page_metadata"}:
        verified_source = next(
            source
            for source in sources
            if source["provider"] == "Official publication page metadata"
        )
        assert verified_source["source_type"] == "institutional_report"
        assert verified_source["doi"] is None
        assert verified_source["retrieval_status"] == "metadata_only"
        assert verified_source["organization_provenance"]["publisher_verification"] == (
            "official_page_metadata_verified"
        )
        assert verified_source["organization_provenance"]["publication_rights_status"] == (
            "not_assessed_metadata_only"
        )
        assert verified_source["organization_provenance"]["publication_content_access"] == (
            "not_retrieved"
        )
        assert verified_source["abstract_excerpt"] is None
        assert client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"] == []

        # Continue through the real persisted workflow with inference disabled.
        # Metadata identity must remain inspectable without becoming evidence.
        final = run_all_steps(client, job["id"])
        assert final["status"] == "completed_with_limitations"
        report = client.get(f"/api/v1/research-jobs/{job['id']}/report").json()
        assert report["id"]
        inspection = client.get(f"/api/v1/reports/{report['id']}/inspection").json()
        report_source = next(
            item for item in inspection["sources"] if item["id"] == verified_source["id"]
        )
        assert inspection["claims"] == []
        assert report_source["retrieval_status"] == "metadata_only"
        assert report_source["passages"] == []
        assert report_source["organization_provenance"]["publication_rights_status"] == (
            "not_assessed_metadata_only"
        )
        assert (
            "Offshore wind transmission planning in India engineering report"
            in report["body_markdown"]
        )
        assert (
            "https://windlab.example/reports/offshore-wind-transmission.html"
            in report["body_markdown"]
        )
        assert any(
            citation.get("source_id") == verified_source["id"]
            for citation in report["citation_map"].values()
        )
        search_coverage = report["verification"]["search_coverage"]
        reconciled = next(
            item
            for item in search_coverage["general_web_discovery"]["verified_official_publications"]
            if item.get("publisher_verification") == "official_page_metadata_verified"
        )
        assert reconciled["selected"] is True
        assert reconciled["source_id"] == verified_source["id"]
        assert reconciled["retrieval_status"] == "metadata_only"
        assert reconciled["passage_count"] == 0
        assert reconciled["rights_status"] == "not_assessed_metadata_only"
    else:
        verified_source = next(
            source for source in sources if source["doi"] == "10.5555/offshore-wind-transmission"
        )
        assert verified_source["url"] == (
            "https://windlab.example/reports/offshore-wind-transmission-study"
        )
        assert verified_source["organization_provenance"]["publisher_verification"] == (
            "verified_organization_domain_and_crossref_publisher_identity"
            if verification_path == "ror"
            else "crossref_doi_title_publisher_and_link_domain_match"
        )


def test_official_domain_publication_verification_requires_publisher_and_title_match():
    from app.research.workflow import (
        _doi_from_official_publication_url,
        _publication_title_matches_search_lead,
        _publisher_matches_verified_organization,
    )

    organization = {
        "canonical_name": "Frontiers Media SA (Switzerland)",
        "aliases": ["Frontiers"],
    }
    assert _publisher_matches_verified_organization("Frontiers Media SA", organization)
    assert not _publisher_matches_verified_organization("Unrelated Publisher Ltd", organization)
    assert _publication_title_matches_search_lead(
        "A grid integration planning approach for partitioned wind energy systems",
        "A grid integration planning approach for partitioned super grid regions",
    )
    assert not _publication_title_matches_search_lead(
        "A grid integration planning approach for partitioned wind energy systems",
        "Unrelated pediatric medicine review article",
    )
    assert (
        _doi_from_official_publication_url(
            "https://www.frontiersin.org/journals/energy/articles/10.3389/fenrg.2025.1689106/full"
        )
        == "10.3389/fenrg.2025.1689106"
    )
    assert _doi_from_official_publication_url("https://example.org/reports/annual-report") is None


def test_crossref_can_independently_link_an_unregistered_publisher_to_its_domain():
    from app.research.workflow import _crossref_record_matches_publisher_domain

    record = ScholarlyWork(
        external_id="doi:10.5555/energy-report",
        title="Grid integration evidence for offshore wind",
        doi="10.5555/energy-report",
        url="https://doi.org/10.5555/energy-report",
        authors=[],
        published_year=2026,
        publisher="Specialist Energy Institute",
        abstract_excerpt=None,
        query="grid integration offshore wind",
        provider="Crossref",
        provider_metadata={
            "crossref_full_text": {
                "links": [{"url": "https://research.specialist-energy.example/reports/energy.pdf"}]
            }
        },
    )

    assert _crossref_record_matches_publisher_domain(record, "specialist-energy.example")
    assert not _crossref_record_matches_publisher_domain(record, "energy.example")
    assert not _crossref_record_matches_publisher_domain(record, "not-specialist-energy.example")
    assert not _crossref_record_matches_publisher_domain(
        replace(record, publisher=None), "specialist-energy.example"
    )
    unrelated_host_record = replace(
        record,
        publisher="Elsevier BV",
        provider_metadata={
            "crossref_full_text": {
                "links": [{"url": "https://researchgate.net/publication/12345/article.pdf"}]
            }
        },
    )
    assert not _crossref_record_matches_publisher_domain(unrelated_host_record, "researchgate.net")


def test_recent_same_job_openaire_search_is_respected_by_repository_lookup_budget():
    now = utcnow()
    event = SimpleNamespace(
        data_json={"organization_discovery": {"openaire_search": {"request_dispatched": True}}},
        created_at=now - timedelta(seconds=4),
    )

    assert workflow._recent_openaire_request_cooldown_seconds(event, now=now) == 57.0
    event.created_at = now - timedelta(seconds=62)
    assert workflow._recent_openaire_request_cooldown_seconds(event, now=now) == 0.0
    event.data_json["organization_discovery"]["openaire_search"]["request_dispatched"] = False
    assert workflow._recent_openaire_request_cooldown_seconds(event, now=now) == 0.0


def test_verified_crossref_publication_uses_only_reviewed_official_html_hosts():
    from app.research.workflow import _crossref_verified_official_html_location

    rights = {
        "license_code": "cc-by",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "content_version": "vor",
    }
    publisher = {
        "organization_id": "https://ror.org/00xhkbc10",
        "identity_status": "VERIFIED_ESTABLISHED",
        "official_domain": "frontiersin.org",
        "official_publication_url": (
            "https://www.frontiersin.org/journals/energy-research/articles/"
            "10.3389/fenrg.2026.1779158/full"
        ),
        "publisher_verification": "verified_organization_domain_and_crossref_publisher_identity",
    }

    location = _crossref_verified_official_html_location(
        source_url=publisher["official_publication_url"],
        full_text_evidence=rights,
        organization_evidence=publisher,
    )

    assert location is not None
    best_location, host_policy = location
    assert best_location == {
        "is_oa": True,
        "landing_page_url": publisher["official_publication_url"],
        "pdf_url": None,
        "license": "cc-by",
        "version": "vor",
    }
    assert host_policy.host == "www.frontiersin.org"
    assert host_policy.terms_url == "https://www.frontiersin.org/about/open-access"

    assert (
        _crossref_verified_official_html_location(
            source_url="https://unreviewed.example/paper",
            full_text_evidence=rights,
            organization_evidence={
                **publisher,
                "official_domain": "unreviewed.example",
                "official_publication_url": "https://unreviewed.example/paper",
            },
        )
        is None
    )
    assert (
        _crossref_verified_official_html_location(
            source_url=publisher["official_publication_url"],
            full_text_evidence={
                **rights,
                "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
            },
            organization_evidence=publisher,
        )
        is None
    )


def test_crossref_verified_official_html_enters_persisted_passage_pipeline(client, monkeypatch):
    from datetime import UTC, datetime
    from hashlib import sha256

    from app.providers.europe_pmc import EuropePMCResolution
    from app.research.safe_fetch import SafeHTMLDocument

    url = "https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2026.1779158/full"
    article_text = (
        "We conducted a structured review of peer-reviewed studies and online industry reports.\n\n"
        "The review searched Scopus, Web of Science, and Google Scholar between January and March 2024.\n\n"
        "The analysis identified transmission planning and grid-integration constraints as challenges for offshore renewable systems."
    )
    fetched: list[tuple[str, str]] = []

    class NoEuropePMC:
        def __init__(self, **_kwargs):
            self.requests_attempted = 0

        def resolve_full_text(self, _pmcid, *, expected_doi):
            assert expected_doi == "10.3389/fenrg.2026.1779158"
            self.requests_attempted = 1
            return EuropePMCResolution(
                status="unavailable",
                reason_code="not_in_test_fixture",
                metadata=None,
                requests_attempted=1,
            )

        def close(self):
            pass

    class FixtureHTMLFetcher:
        document_byte_limit = 2_000_000

        def __init__(self, **_kwargs):
            self.timeout_seconds = 8

        def fetch_html(self, page_url, *, license_name):
            fetched.append((page_url, license_name))
            raw = article_text.encode()
            return SafeHTMLDocument(
                text=article_text,
                sha256=sha256(raw).hexdigest(),
                media_type="text/html",
                final_host="www.frontiersin.org",
                retrieved_at=datetime.now(UTC),
                truncated=False,
                host_policy_id="frontiers-open-access-2026-11-01",
                host_terms_url="https://www.frontiersin.org/about/open-access",
                robots_status="rules_checked",
            )

    monkeypatch.setattr(workflow, "EuropePMCProvider", NoEuropePMC)
    monkeypatch.setattr(workflow, "SafeHTMLFetcher", FixtureHTMLFetcher)
    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="crossref-official-html-source-01",
        question="What engineering challenges affect offshore wind grid integration?",
    )
    planned = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "crossref-official-html-plan-01"},
    )
    assert planned.status_code == 200, planned.text
    with client.db_sessions() as db:
        research_job = db.get(ResearchJob, job["id"])
        assert research_job is not None
        research_job.current_stage = "extraction"
        db.add(
            Source(
                job_id=job["id"],
                external_id="doi:10.3389/fenrg.2026.1779158",
                title="Offshore hybrid renewable energy: insights from real-world implementations",
                doi="10.3389/fenrg.2026.1779158",
                url="https://doi.org/10.3389/fenrg.2026.1779158",
                publisher="Frontiers Media SA",
                source_type="scholarly_article",
                retrieval_status="metadata_only",
                metadata_json={
                    "provider": "Crossref",
                    "provider_metadata": workflow.versioned_provider_metadata(
                        "Crossref",
                        {
                            "crossref_full_text": {
                                "rights_evidence_source": "crossref_deposited_work_metadata",
                                "license_code": "cc-by",
                                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                                "content_version": "vor",
                            },
                            "organization_discovery": {
                                "organization_id": "https://ror.org/00xhkbc10",
                                "organization_name": "Frontiers Media SA (Switzerland)",
                                "identity_status": "VERIFIED_ESTABLISHED",
                                "verification_method": "crawl4ai_search_result_domain_plus_ror_exact_domain",
                                "verification_source": "https://api.ror.org/v2/organizations/00xhkbc10",
                                "official_domain": "frontiersin.org",
                                "publisher_verification": "verified_organization_domain_and_crossref_publisher_identity",
                                "official_publication_url": url,
                                "publication_discovery_provider": "Crawl4AI Cloud site search plus Crossref DOI resolution",
                            },
                        },
                    ),
                },
            )
        )
        db.commit()

    extracted = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "crossref-official-html-extract-01"},
    )
    assert extracted.status_code == 200, extracted.text
    source = next(
        item
        for item in client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
        if item["doi"] == "10.3389/fenrg.2026.1779158"
    )
    inspected = client.get(f"/api/v1/sources/{source['id']}").json()

    assert extracted.json()["current_stage"] == "appraisal"
    assert fetched == [(url, "cc-by")]
    assert source["retrieval_status"] == "full_text_html"
    assert source["retrieval"]["scope"] == "crossref_licensed_verified_official_publisher_page"
    assert source["retrieval"]["site_policy_status"] == "allowed"
    assert len(inspected["passages"]) == 3
    assert any("Scopus, Web of Science" in passage["content"] for passage in inspected["passages"])
    claims = client.get(f"/api/v1/research-jobs/{job['id']}/claims").json()["items"]
    assert any(claim["source_id"] == source["id"] for claim in claims)

    with client.db_sessions() as db:
        db.add(
            JobEvent(
                job_id=job["id"],
                event_type="step_completed",
                stage="discovery",
                message="Fixture discovery completed.",
                data_json={
                    "provider_query_counts": {"Crawl4AI Cloud Search": 2},
                    "provider_result_counts": {"Crawl4AI Cloud Search": 1},
                    "provider_failures": {},
                    "general_web_discovery": {
                        "schema_version": 1,
                        "status": "completed",
                        "verified_official_publications": [
                            {
                                "organization_id": "https://ror.org/00xhkbc10",
                                "title": "Offshore hybrid renewable energy: insights from real-world implementations",
                                "doi": "10.3389/fenrg.2026.1779158",
                                "publisher": "Frontiers Media SA",
                                "publisher_verification": "verified",
                                "official_url": url,
                                "content_fetched": False,
                                "rights_status": "metadata_only_not_assessed",
                            }
                        ],
                    },
                    "organization_discovery": {
                        "schema_version": 1,
                        "status": "completed",
                        "seed_work_count": 0,
                        "organizations": [],
                        "publication_searches": [
                            {
                                "organization_id": "https://ror.org/00xhkbc10",
                                "organization_name": "Frontiers Media SA (Switzerland)",
                                "provider": "Official website search plus Crossref DOI resolution",
                                "status": "completed",
                                "query": "site:frontiersin.org offshore wind",
                                "returned_count": 1,
                                "request_count": 2,
                                "content_fetched": False,
                                "rights_status": "metadata_only_not_assessed",
                                "publications": [
                                    {
                                        "doi": "10.3389/fenrg.2026.1779158",
                                        "title": "Offshore hybrid renewable energy: insights from real-world implementations",
                                        "content_fetched": False,
                                        "rights_status": "metadata_only_not_assessed",
                                    }
                                ],
                            }
                        ],
                    },
                },
                created_at=utcnow(),
            )
        )
        db.flush()
        _lines, coverage = workflow._report_search_coverage(db, job["id"], 1)

    report_publication = coverage["general_web_discovery"]["verified_official_publications"][0]
    assert report_publication["selected"] is True
    assert report_publication["content_fetched"] is True
    assert report_publication["rights_status"] == "permitted"
    assert report_publication["passage_count"] == 3
    linked_search_publication = coverage["organization_discovery"]["publication_searches"][0][
        "publications"
    ][0]
    assert linked_search_publication["source_id"] == source["id"]
    assert linked_search_publication["content_fetched"] is True


@pytest.mark.parametrize(
    ("publisher_response", "estimate_failure"),
    [
        ("page_shell", None),
        ("timeout_after_robots", None),
        ("page_shell", "http_503"),
        ("page_shell", "timeout"),
    ],
)
def test_verified_crossref_page_shell_uses_bounded_crawl4ai_content_and_persists_passages(
    client, monkeypatch, publisher_response, estimate_failure
):
    from datetime import UTC, datetime
    from hashlib import sha256

    from app.providers.crawl4ai_cloud import (
        Crawl4AIBalance,
        Crawl4AICloudError,
        Crawl4AICloudScrapeResult,
        Crawl4AIScrapeEstimate,
    )
    from app.providers.europe_pmc import EuropePMCResolution
    from app.research.safe_fetch import SafeFetchError, SafeHTMLAccessContext, SafeHTMLDocument

    url = "https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2026.1779158/full"
    markdown = """# Frontiers | Offshore hybrid renewable energy: insights from real-world implementations

Front.

Energy Res., 19 May 2026

Sec. Sustainable Energy Systems

Volume 14 - 2026 | https://doi.org/10.3389/fenrg.2026.1779158

Nisha Kaur 1,2

K. Sudhakar 2,3,4

Faculty of Electrical and Electronics Engineering Technology, Universiti Malaysia Pahang Al Sultan Abdullah.

School of Electrical and Electronics Engineering, SASTRA Deemed University, Thanjavur, India.

## Abstract

This review examines offshore hybrid renewable energy systems and their grid integration.

The authors searched peer-reviewed literature and industry data using a documented review method.

The review reports that transmission planning and system integration remain material constraints.

The reported capacity factors of up to 45 percent are context dependent and are not a causal estimate.

## Methodology

The authors compared selected offshore hybrid energy case studies using reported project characteristics.

## Results and discussion

The review identifies transmission planning and system integration as material implementation challenges.
"""
    dispatched = []

    class NoEuropePMC:
        def __init__(self, **_kwargs):
            self.requests_attempted = 0

        def resolve_full_text(self, _pmcid, *, expected_doi):
            assert expected_doi == "10.3389/fenrg.2026.1779158"
            self.requests_attempted = 1
            return EuropePMCResolution(
                status="unavailable",
                reason_code="not_in_test_fixture",
                metadata=None,
                requests_attempted=1,
            )

        def close(self):
            pass

    class PageShellFetcher:
        document_byte_limit = 2_000_000

        def __init__(self, **_kwargs):
            self.timeout_seconds = 8

        def fetch_html(self, page_url, *, license_name):
            assert page_url == url
            assert license_name == "cc-by"
            if publisher_response == "timeout_after_robots":
                error = SafeFetchError("timeout", "Source retrieval exceeded the time limit.")
                error.access_context = SafeHTMLAccessContext(
                    final_host="www.frontiersin.org",
                    host_policy_id="frontiers-open-access-2026-11-01",
                    host_terms_url="https://www.frontiersin.org/about/open-access",
                    robots_status="rules_checked",
                )
                raise error
            text = "Frontiers | Offshore hybrid renewable energy: insights from real-world implementations"
            return SafeHTMLDocument(
                text=text,
                sha256=sha256(text.encode()).hexdigest(),
                media_type="text/html",
                final_host="www.frontiersin.org",
                retrieved_at=datetime.now(UTC),
                truncated=False,
                host_policy_id="frontiers-open-access-2026-11-01",
                host_terms_url="https://www.frontiersin.org/about/open-access",
                robots_status="rules_checked",
            )

    class BoundedCloudProvider:
        def __init__(self, *, api_key):
            assert api_key == "test-only-crawl-key"

        def balance(self):
            dispatched.append("balance")
            return Crawl4AIBalance(
                plan="community",
                balance_credits=990.0,
                allowance_left_credits=990.0,
                raw_status="reported",
            )

        def estimate_scrape(self, page_url, *, expected_domain):
            dispatched.append(("estimate", page_url, expected_domain))
            if estimate_failure == "http_503":
                raise Crawl4AICloudError(
                    "provider_unavailable",
                    request_dispatched=True,
                    http_status=503,
                    provider_charge_status="not_charged_provider_5xx",
                )
            if estimate_failure == "timeout":
                raise Crawl4AICloudError(
                    "request_timeout", request_dispatched=True, provider_charge_status="unknown"
                )
            return Crawl4AIScrapeEstimate(
                minimum_credits=0.5,
                maximum_credits=1.0,
                reported_cost_credits=None,
                usage_status="cost_unknown",
            )

        def scrape_markdown(self, page_url, *, expected_domain):
            dispatched.append(("scrape", page_url, expected_domain))
            return Crawl4AICloudScrapeResult(
                requested_url=page_url,
                markdown=markdown,
                reported_cost_credits=0.75,
                balance_credits=989.25,
                allowance_left_credits=989.25,
                usage_status="reported",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "EuropePMCProvider", NoEuropePMC)
    monkeypatch.setattr(workflow, "SafeHTMLFetcher", PageShellFetcher)
    monkeypatch.setattr(workflow, "Crawl4AICloudSearchProvider", BoundedCloudProvider)
    monkeypatch.setattr(workflow.settings, "crawl4ai_enabled", True)
    monkeypatch.setattr(workflow.settings, "crawl4ai_key", "test-only-crawl-key")
    monkeypatch.setattr(workflow.settings, "crawl4ai_max_scrape_requests_per_job", 1)
    monkeypatch.setattr(workflow.settings, "crawl4ai_max_scrape_credits_per_job", 1.0)
    monkeypatch.setattr(workflow.settings, "crawl4ai_estimate_reservation_credits", 1.0)
    monkeypatch.setattr(workflow.settings, "crawl4ai_max_total_requests_per_job", 5)
    monkeypatch.setattr(workflow.settings, "crawl4ai_max_total_credits_per_job", 5.0)

    project = create_project(client)
    job = create_job(
        client,
        project["id"],
        idempotency_key="crossref-crawl4ai-page-shell-01",
        question="What technical and grid-integration challenges affect offshore hybrid renewable energy systems?",
    )
    planned = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "crossref-crawl4ai-page-shell-plan-01"},
    )
    assert planned.status_code == 200, planned.text
    with client.db_sessions() as db:
        research_job = db.get(ResearchJob, job["id"])
        assert research_job is not None
        research_job.current_stage = "extraction"
        db.add(
            Source(
                job_id=job["id"],
                external_id="doi:10.3389/fenrg.2026.1779158",
                title="Offshore hybrid renewable energy: insights from real-world implementations",
                doi="10.3389/fenrg.2026.1779158",
                url="https://doi.org/10.3389/fenrg.2026.1779158",
                publisher="Frontiers Media SA",
                source_type="scholarly_article",
                retrieval_status="metadata_only",
                metadata_json={
                    "provider": "Crossref",
                    "provider_metadata": workflow.versioned_provider_metadata(
                        "Crossref",
                        {
                            "crossref_full_text": {
                                "rights_evidence_source": "crossref_deposited_work_metadata",
                                "license_code": "cc-by",
                                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                                "content_version": "vor",
                            },
                            "organization_discovery": {
                                "organization_id": "https://ror.org/00xhkbc10",
                                "organization_name": "Frontiers Media SA (Switzerland)",
                                "identity_status": "VERIFIED_ESTABLISHED",
                                "verification_method": "crawl4ai_search_result_domain_plus_ror_exact_domain",
                                "verification_source": "https://api.ror.org/v2/organizations/00xhkbc10",
                                "official_domain": "frontiersin.org",
                                "publisher_verification": "verified_organization_domain_and_crossref_publisher_identity",
                                "official_publication_url": url,
                                "publication_discovery_provider": "Crawl4AI Cloud site search plus Crossref DOI resolution",
                            },
                        },
                    ),
                },
            )
        )
        db.commit()

    extracted = client.post(
        f"/api/v1/research-jobs/{job['id']}/advance",
        json={"operation_key": "crossref-crawl4ai-page-shell-extract-01"},
    )
    assert extracted.status_code == 200, extracted.text
    matching_sources = [
        item
        for item in client.get(f"/api/v1/research-jobs/{job['id']}/sources").json()["items"]
        if item["doi"] == "10.3389/fenrg.2026.1779158"
    ]
    source = matching_sources[0]
    inspected = client.get(f"/api/v1/sources/{source['id']}").json()
    events = client.get(f"/api/v1/research-jobs/{job['id']}/events").json()["items"]

    if estimate_failure:
        assert dispatched == ["balance", ("estimate", url, "frontiersin.org")]
        assert source["retrieval_status"] == "metadata_only"
        crawl_state = source["retrieval"]["crawl4ai_page"]
        expected_failure_status = "failed" if estimate_failure == "http_503" else "uncertain"
        assert crawl_state["status"] == expected_failure_status
        assert crawl_state["estimate_status"] == expected_failure_status
        assert crawl_state["error_code"] == (
            "provider_unavailable" if estimate_failure == "http_503" else "request_timeout"
        )
        assert "scrape_status" not in crawl_state
        assert crawl_state["reported_cost_credits"] is None
        assert crawl_state["reported_cost_status"] == "unknown"
        expected_unresolved = 0.0 if estimate_failure == "http_503" else 1.0
        assert crawl_state["unresolved_reserved_credits"] == expected_unresolved
        assert crawl_state["provider_charge_status"] == (
            "not_charged_provider_5xx" if estimate_failure == "http_503" else "unknown"
        )
        assert events[-1]["data"]["crawl4ai_page_estimate_requests"] == 1
        assert events[-1]["data"]["crawl4ai_page_scrape_requests"] == 0
        assert "crawl4ai_page_reported_cost_credits" not in events[-1]["data"]
        assert events[-1]["data"]["crawl4ai_page_reported_cost_status"] == "unknown"
        assert events[-1]["data"]["crawl4ai_page_unresolved_reserved_credits"] == (
            expected_unresolved
        )
        return

    assert dispatched == [
        "balance",
        ("estimate", url, "frontiersin.org"),
        ("scrape", url, "frontiersin.org"),
    ], json.dumps(source["retrieval"], indent=2)
    assert extracted.json()["current_stage"] == "appraisal", (
        events[-1]["data"].get("exception_type") if events else extracted.json()
    )
    assert source["retrieval_status"] == "full_text_html"
    assert source["retrieval"]["crawl4ai_page"]["status"] == "completed", json.dumps(
        {
            "crawl4ai_page": source["retrieval"]["crawl4ai_page"],
            "terminal_status": events[-1]["data"].get("crawl4ai_page_terminal_status"),
            "request_counts": {
                key: events[-1]["data"].get(key)
                for key in (
                    "crawl4ai_page_estimate_requests",
                    "crawl4ai_page_scrape_requests",
                    "crawl4ai_page_reported_cost_credits",
                )
            },
        },
        indent=2,
    )
    assert source["retrieval"]["crawl4ai_page"]["reported_cost_credits"] == 0.75
    with client.db_sessions() as db:
        workflow.append_event(
            db,
            job["id"],
            event_type="step_completed",
            stage="discovery",
            message="Fixture discovery provenance for report-coverage integration.",
            operation_key="crossref-crawl4ai-page-shell-discovery-01",
            data={
                "providers": ["Crawl4AI Cloud", "Crossref"],
                "organization_discovery": {
                    "schema_version": 1,
                    "seed_work_count": 1,
                    "organizations": [],
                    "publication_searches": [],
                },
                "general_web_discovery": {
                    "schema_version": 1,
                    "status": "completed",
                    "queries_planned": ["topic-aligned official publication search"],
                    "request_count": 1,
                    "preflight_request_count": 1,
                    "hits": [],
                    "newly_discovered_organizations": [],
                    "verified_official_publications": [
                        {
                            "title": source["title"],
                            "doi": source["doi"],
                            "publisher": source["publisher"],
                            "organization_id": "https://ror.org/00xhkbc10",
                            "organization_name": "Frontiers Media SA",
                            "rights_status": "permitted",
                        }
                    ],
                },
            },
        )
        db.flush()
        _lines, coverage = workflow._report_search_coverage(db, job["id"], 1)
    covered_publication = next(
        item
        for item in coverage["organization_discovery"]["selected_publications"]
        if item["doi"] == "10.3389/fenrg.2026.1779158"
    )
    assert covered_publication["content_provider"] == "Crawl4AI Cloud"
    assert covered_publication["content_request_count"] == 2
    assert covered_publication["content_preflight_request_count"] == 1
    assert covered_publication["content_reported_cost_credits"] == 0.75
    assert covered_publication["content_unresolved_reserved_credits"] == 1.0
    assert events[-1]["data"]["crawl4ai_page_reported_cost_status"] == "partial"
    assert any("provider-reported credits: 0.75" in line for line in _lines)
    assert inspected["passages"]
    assert any("transmission planning" in item["content"] for item in inspected["passages"])
    assert any("documented review method" in item["content"] for item in inspected["passages"])
    assert all(
        not any(marker in item["content"] for marker in ("Front.", "Nisha Kaur", "Volume 14"))
        for item in inspected["passages"]
    )
    assert all(
        item["locator"].startswith("Crawl4AI Cloud Markdown") for item in inspected["passages"]
    )


def test_crawl4ai_markdown_passage_selection_balances_sections_and_excludes_references():
    markdown = """# Offshore wind and transmission planning

## Abstract

Offshore wind transmission planning affects grid reliability and investment decisions.

Transmission planning needs coordinated offshore wind grid integration and reliability.

The offshore wind transmission planning question is central to grid reliability.

Offshore wind transmission planning and grid reliability require careful policy choices.

Transmission planning for offshore wind affects grid reliability and project delivery.

## Methods

Project documents and engineering studies were reviewed using a predefined selection protocol.

## Results

The reviewed projects reported long connection queues and changing transmission costs.

## Limitations

The evidence is limited by inconsistent project reporting and short observation periods.

Kaur N, Sudhakar K, Mohamed MR, B R and Barbulescu D (2026) Offshore hybrid renewable energy: insights from real-world implementations.
"""

    selected, audit = workflow._select_html_evidence_sentences(
        markdown,
        question="How does offshore wind transmission planning affect grid reliability?",
        source_title="Offshore wind transmission planning and grid reliability",
        limit=4,
    )

    selected_sections = {section for _paragraph, _sentence, _text, section in selected}
    selected_text = " ".join(text for _paragraph, _sentence, text, _section in selected)
    assert {"methods", "results", "limitations"}.issubset(selected_sections)
    assert "predefined selection protocol" in selected_text
    assert "long connection queues" in selected_text
    assert "Kaur N, Sudhakar K" not in selected_text
    assert audit["selected_sentences"] == 4
    assert audit["interpretation"].startswith("Passage retrieval relevance only")
