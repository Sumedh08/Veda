import asyncio
import hashlib
import json
import os
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.mcp_evidence_server import (
    _analysis_passage_locators,
    _passage_matches_source_provenance,
    _passage_summary,
    _source_provenance_has_passages,
    create_evidence_mcp_server,
    validate_loopback_api_url,
)
from app.models import (
    DiscoveryCandidate,
    Passage,
    Project,
    ResearchJob,
    ResearchReport,
    RetrievedDocument,
    Source,
)
from app.research.candidate_relevance import score_candidate_relevance


def _add_evidence(
    client,
    *,
    owner_id: str,
    sharing: str,
    title: str,
    passage_text: str,
    verified_license: bool = True,
):
    source_id = str(uuid4())
    project_id = str(uuid4())
    job_id = str(uuid4())
    document_id = str(uuid4())
    passage_id = str(uuid4())
    digest = hashlib.sha256(passage_text.encode()).hexdigest()
    rights = {
        "analysis": "PERMITTED" if sharing != "CITATION_ONLY" else "PERMITTED_WITH_LIMITATIONS",
        "retention": "LICENSE_SCOPED" if sharing != "CITATION_ONLY" else "LIMITED_EXCERPTS",
        "sharing": sharing,
        "basis": "verified_item_license"
        if sharing != "CITATION_ONLY"
        else "india_private_research_exception_candidate",
        "policy_version": "fixture-v1",
        "reason_codes": ["fixture_rights_evidence"],
    }
    with client.db_sessions() as db:
        project = Project(
            id=project_id,
            owner_id=owner_id,
            title="Research project",
            description="",
            domain="systems research",
        )
        job = ResearchJob(
            id=job_id,
            project_id=project_id,
            question="How does the system perform?",
            idempotency_key=str(uuid4()),
            status="completed",
            current_stage="report",
        )
        source = Source(
            id=source_id,
            job_id=job_id,
            external_id=source_id,
            title=title,
            doi="10.5555/example.1",
            url="https://publisher.example/report",
            publisher="Verified Publisher",
            source_type="institutional_report",
            retrieval_status="full_text_pdf",
            metadata_json={
                "provider": "fixture",
                "retrieval": {
                    "license": (
                        "cc-by" if sharing != "CITATION_ONLY" and verified_license else None
                    ),
                    "license_url": (
                        "https://creativecommons.org/licenses/by/4.0/"
                        if sharing != "CITATION_ONLY" and verified_license
                        else None
                    ),
                    "license_evidence": "verified item-level license"
                    if sharing != "CITATION_ONLY" and verified_license
                    else None,
                    "rights_assessment": rights,
                },
            },
        )
        document = RetrievedDocument(
            id=document_id,
            source_id=source_id,
            identity_key=hashlib.sha256(f"doc-{document_id}".encode()).hexdigest(),
            source_version="version-1",
            document_sha256=hashlib.sha256(f"file-{document_id}".encode()).hexdigest(),
            retrieved_at=datetime.now(UTC),
            locator="PDF on publisher.example",
            media_type="application/pdf",
            access_class="full_text_pdf",
            hash_scope="raw_document_bytes",
            metadata_json={"page_count": 4},
        )
        passage = Passage(
            id=passage_id,
            source_id=source_id,
            document_id=document_id,
            identity_key=hashlib.sha256(f"passage-{passage_id}".encode()).hexdigest(),
            identity_version=1,
            ordinal=0,
            locator="PDF p. 2",
            content=passage_text,
            content_hash=digest,
            access_level="full_text_pdf",
            truncated=False,
        )
        db.add_all([project, job, source, document, passage])
        db.commit()
    return source_id, passage_id


def test_loopback_api_url_rejects_remote_hosts_and_credentials():
    assert validate_loopback_api_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    assert validate_loopback_api_url("http://[::1]:8000/") == "http://[::1]:8000"
    with pytest.raises(ValueError):
        validate_loopback_api_url("https://veda.example")
    with pytest.raises(ValueError):
        validate_loopback_api_url("http://user:password@127.0.0.1:8000")


def test_mcp_derived_text_requires_matching_passage_and_document_hashes():
    source_id = str(uuid4())
    document_id = str(uuid4())
    passage_id = str(uuid4())
    provenance = {
        "source": {"id": source_id},
        "passages": [
            {
                "id": passage_id,
                "document_id": document_id,
                "content_hash": hashlib.sha256(b"passage").hexdigest(),
                "content_hash_verified": True,
            }
        ],
        "documents": [
            {"id": document_id, "document_sha256": hashlib.sha256(b"document").hexdigest()}
        ],
    }

    assert _source_provenance_has_passages(
        provenance, source_id=source_id, passage_ids={passage_id}
    )
    provenance["passages"][0]["content_hash_verified"] = False
    assert not _source_provenance_has_passages(
        provenance, source_id=source_id, passage_ids={passage_id}
    )
    provenance["passages"][0]["content_hash_verified"] = True
    provenance["passages"][0]["content_hash"] = None
    assert not _source_provenance_has_passages(
        provenance, source_id=source_id, passage_ids={passage_id}
    )
    assert not _source_provenance_has_passages(
        provenance, source_id=source_id, passage_ids={str(uuid4())}
    )


def test_mcp_passage_text_is_withheld_when_saved_hash_does_not_match():
    content = "The report measures distribution system flexibility."
    source_id = str(uuid4())
    document_id = str(uuid4())
    source = {
        "id": source_id,
        "retrieval_status": "full_text_pdf",
        "retrieval": {
            "license": "cc-by",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_evidence": "verified item license",
            "rights_assessment": {
                "analysis": "PERMITTED",
                "retention": "LICENSE_SCOPED",
                "sharing": "LICENSE_SCOPED",
                "basis": "verified_item_license",
            },
        },
    }
    passage = {
        "id": str(uuid4()),
        "source_id": source_id,
        "document_id": document_id,
        "locator": "PDF p. 4",
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "access_level": "full_text_pdf",
        "content_withheld_reason": None,
        "document": {
            "id": document_id,
            "source_id": source_id,
            "document_sha256": hashlib.sha256(b"raw PDF").hexdigest(),
        },
    }

    permitted, _ = _passage_summary(source, passage, remaining_characters=1000)
    assert permitted["content"] == content

    passage["content"] = "Changed text with stale digest."
    withheld, _ = _passage_summary(source, passage, remaining_characters=1000)
    assert withheld["content"] is None
    assert withheld["external_disclosure"] == "metadata_only"


def test_document_analysis_returns_every_referenced_locator_within_schema_bound():
    locators = {f"passage-{index}": {"passage_id": f"passage-{index}"} for index in range(33)}

    returned, truncated = _analysis_passage_locators(locators, set(locators))

    assert [item["passage_id"] for item in returned] == sorted(locators)
    assert not truncated

    returned, truncated = _analysis_passage_locators(locators, set(locators) | {"missing"})

    assert len(returned) == 33
    assert truncated


def test_mcp_passage_disclosure_requires_source_and_document_relationships():
    source_id = str(uuid4())
    document_id = str(uuid4())
    passage_id = str(uuid4())
    text = "The verified report describes a source-linked outcome."
    passage_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document_hash = hashlib.sha256(b"verified original document").hexdigest()
    source = {
        "id": source_id,
        "retrieval_status": "full_text_pdf",
        "retrieval": {
            "license": "cc-by",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_evidence": "verified item license",
            "rights_assessment": {
                "analysis": "PERMITTED",
                "retention": "LICENSE_SCOPED",
                "sharing": "LICENSE_SCOPED",
                "basis": "verified_item_license",
            },
        },
    }
    provenance = {
        "source": source,
        "passages": [
            {
                "id": passage_id,
                "document_id": document_id,
                "content_hash": passage_hash,
                "content_hash_verified": True,
            }
        ],
        "documents": [{"id": document_id, "document_sha256": document_hash}],
    }
    passage = {
        "id": passage_id,
        "source_id": source_id,
        "document_id": document_id,
        "content": text,
        "content_hash": passage_hash,
        "document": {
            "id": document_id,
            "source_id": source_id,
            "document_sha256": document_hash,
        },
    }

    assert _passage_matches_source_provenance(
        passage,
        provenance,
        source_id=source_id,
        passage_id=passage_id,
    )

    mismatched_document = {**passage, "document_id": str(uuid4())}
    assert not _passage_matches_source_provenance(
        mismatched_document,
        provenance,
        source_id=source_id,
        passage_id=passage_id,
    )
    mismatched_source = {**passage, "source_id": str(uuid4())}
    assert not _passage_matches_source_provenance(
        mismatched_source,
        provenance,
        source_id=source_id,
        passage_id=passage_id,
    )
    mismatched_id = {**passage, "id": str(uuid4())}
    assert not _passage_matches_source_provenance(
        mismatched_id,
        provenance,
        source_id=source_id,
        passage_id=passage_id,
    )
    foreign_document = {
        **passage,
        "document": {**passage["document"], "source_id": str(uuid4())},
    }
    summary, _ = _passage_summary(source, foreign_document, remaining_characters=1000)
    assert summary["content"] is None


def test_mcp_evidence_search_withholds_passage_from_foreign_document_source(client):
    source_id, passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="LICENSE_SCOPED",
        title="Licensed grid report",
        passage_text="Grid frequency response stabilizes variable power systems.",
    )
    foreign_source_id, _foreign_passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="LICENSE_SCOPED",
        title="Different licensed report",
        passage_text="This unrelated document does not match the search phrase.",
    )
    with client.db_sessions() as db:
        passage = db.get(Passage, passage_id)
        foreign_document = db.scalar(
            select(RetrievedDocument).where(RetrievedDocument.source_id == foreign_source_id)
        )
        passage.document_id = foreign_document.id
        db.commit()

    server = create_evidence_mcp_server(client, api_prefix="/api/v1")
    mcp = pytest.importorskip("mcp", reason="install the optional backend mcp extra")

    async def search():
        async with mcp.Client(server) as protocol_client:
            return await protocol_client.call_tool(
                "search_research_evidence", {"query": "frequency response", "limit": 5}
            )

    result = asyncio.run(search())

    assert not result.is_error
    output = json.loads(result.content[0].text)
    matched_source = next(
        item for item in output["results"] if item["source"]["source_id"] == source_id
    )
    assert matched_source["passages"][0]["passage_id"] == passage_id
    assert matched_source["passages"][0]["content"] is None


def test_evidence_search_api_returns_owner_scoped_source_linked_passages(client):
    text = "Grid operators used frequency response to stabilize variable power generation."
    source_id, passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="LICENSE_SCOPED",
        title="Grid frequency response evidence",
        passage_text=text,
    )

    response = client.post(
        "/api/v1/evidence/search",
        json={"query": "frequency response", "limit": 5},
    )

    assert response.status_code == 200
    item = next(item for item in response.json()["items"] if item["source"]["id"] == source_id)
    assert item["passages"][0]["id"] == passage_id
    assert item["passages"][0]["content"] == text
    assert item["source"]["retrieval"]["rights_assessment"]["sharing"] == "LICENSE_SCOPED"


def test_evidence_search_api_does_not_return_another_users_corpus(client):
    _add_evidence(
        client,
        owner_id="20000000-0000-4000-8000-000000000002",
        sharing="LICENSE_SCOPED",
        title="Owner-private thermodynamics paper",
        passage_text="Owner-private thermodynamics results are not visible to another user.",
    )

    response = client.post(
        "/api/v1/evidence/search",
        json={"query": "thermodynamics", "limit": 5},
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_source_provenance_api_returns_bounded_locators_without_passage_text(client):
    text = "This full passage must not be loaded for a provenance-only lookup."
    source_id, passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="CITATION_ONLY",
        title="Locator-only provenance report",
        passage_text=text,
    )

    response = client.get(f"/api/v1/sources/{source_id}/provenance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["id"] == source_id
    assert len(payload["passages"]) == 1
    assert payload["passages"][0]["id"] == passage_id
    assert payload["passages"][0]["locator"] == "PDF p. 2"
    assert "content" not in payload["passages"][0]
    assert payload["passages"][0]["content_hash_verified"] is True
    assert payload["documents"][0]["document_sha256"]
    assert payload["documents"][0]["metadata"]["page_count"] == 4
    assert "content" not in payload["documents"][0]

    with client.db_sessions() as db:
        passage = db.get(Passage, passage_id)
        passage.content = "Tampered after the original digest was recorded."
        db.commit()
    mismatched_response = client.get(f"/api/v1/sources/{source_id}/provenance")
    assert mismatched_response.status_code == 200
    assert mismatched_response.json()["passages"][0]["content_hash_verified"] is False

    foreign_source_id, _foreign_passage_id = _add_evidence(
        client,
        owner_id="20000000-0000-4000-8000-000000000002",
        sharing="CITATION_ONLY",
        title="Another user's locator-only report",
        passage_text="This other owner's source must stay isolated.",
    )
    foreign_response = client.get(f"/api/v1/sources/{foreign_source_id}/provenance")
    assert foreign_response.status_code == 404


def test_mcp_document_analysis_reports_truncated_provenance_without_disclosing_analysis(client):
    source_id, initial_passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="LICENSE_SCOPED",
        title="Bounded analysis provenance report",
        passage_text="A retained passage from the verified document.",
    )
    with client.db_sessions() as db:
        initial_passage = db.get(Passage, initial_passage_id)
        document = db.get(RetrievedDocument, initial_passage.document_id)
        source = db.get(Source, source_id)
        passage_ids = [initial_passage_id]
        for ordinal in range(1, 51):
            passage_id = str(uuid4())
            content = f"Stored source passage {ordinal} includes a distinct bounded result."
            db.add(
                Passage(
                    id=passage_id,
                    source_id=source_id,
                    document_id=document.id,
                    identity_key=hashlib.sha256(f"identity-{passage_id}".encode()).hexdigest(),
                    identity_version=1,
                    ordinal=ordinal,
                    locator=f"PDF p. {ordinal + 1}",
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    access_level="full_text_pdf",
                    truncated=False,
                )
            )
            passage_ids.append(passage_id)
        source.appraisal_json = {
            "schema_version": 1,
            "status": "model_assessed_not_independently_verified",
            "fields": {},
            "extensions": {
                "document_analysis": {
                    "schema_version": 1,
                    "status": "model_assessed_not_independently_verified",
                    "scope": "persisted_passages_only",
                    "question_fit": "direct",
                    "fit_passage_ids": [passage_ids[-1]],
                    "study_focus": None,
                    "study_focus_passage_ids": [],
                    "findings": [],
                    "limitations": [],
                    "cannot_conclude": [],
                    "further_information_needed": [],
                },
            },
        }
        db.commit()

    mcp = pytest.importorskip("mcp", reason="install the optional backend mcp extra")
    server = create_evidence_mcp_server(client, api_prefix="/api/v1")

    async def inspect_analysis():
        async with mcp.Client(server) as protocol_client:
            return await protocol_client.call_tool(
                "get_document_analysis", {"source_id": source_id}
            )

    result = asyncio.run(inspect_analysis())

    assert not result.is_error
    output = json.loads(result.content[0].text)
    assert output["status"] == "provenance_incomplete"
    assert output["passage_locators_has_more"] is True
    assert "analysis" not in output


def test_mcp_protocol_exposes_licensed_passage_and_withholds_private_research_text(client):
    permitted_text = (
        "Grid operators used frequency response to stabilize variable power generation."
    )
    private_text = "Private-only evidence says frequency response improved reliability."
    permitted_source_id, permitted_passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="LICENSE_SCOPED",
        title="Licensed grid frequency response report",
        passage_text=permitted_text,
    )
    private_source_id, private_passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="CITATION_ONLY",
        title="Private grid frequency response report",
        passage_text=private_text,
    )
    unverified_license_text = "Frequency response source has an unverified license assertion."
    unverified_source_id, unverified_passage_id = _add_evidence(
        client,
        owner_id=client.test_user["id"],
        sharing="LICENSE_SCOPED",
        title="Unverified grid frequency response report",
        passage_text=unverified_license_text,
        verified_license=False,
    )
    with client.db_sessions() as db:
        permitted_source = db.get(Source, permitted_source_id)
        permitted_job_id = permitted_source.job_id
        permitted_source.appraisal_json = {
            "schema_version": 1,
            "status": "model_assessed_not_independently_verified",
            "fields": {},
            "extensions": {
                "document_analysis": {
                    "schema_version": 1,
                    "status": "model_assessed_not_independently_verified",
                    "scope": "persisted_passages_only",
                    "question_fit": "direct",
                    "fit_passage_ids": [permitted_passage_id],
                    "study_focus": "Grid frequency response.",
                    "study_focus_passage_ids": [permitted_passage_id],
                    "findings": [
                        {
                            "statement": "The report describes grid frequency response.",
                            "passage_ids": [permitted_passage_id],
                        }
                    ],
                    "limitations": [],
                    "cannot_conclude": [],
                    "further_information_needed": [],
                    "provider": "fixture",
                    "model": "fixture-model",
                }
            },
        }
        private_source = db.get(Source, private_source_id)
        private_document = db.scalar(
            select(RetrievedDocument).where(RetrievedDocument.source_id == private_source_id)
        )
        private_document.metadata_json = {
            **private_document.metadata_json,
            "sections": [
                {
                    "section_id": "result",
                    "original_heading": "PRIVATE REPORT FINDING MUST NOT LEAK",
                    "normalized_type": "results",
                    "section_path": ["Results"],
                    "ordinal": 1,
                    "source_locator": "PDF p. 3",
                }
            ],
        }
        private_source.appraisal_json = {
            "schema_version": 1,
            "status": "model_assessed_not_independently_verified",
            "fields": {},
            "extensions": {
                "document_analysis": {
                    "schema_version": 1,
                    "status": "model_assessed_not_independently_verified",
                    "scope": "persisted_passages_only",
                    "question_fit": "direct",
                    "fit_passage_ids": [private_passage_id],
                    "study_focus": "Private findings.",
                    "study_focus_passage_ids": [private_passage_id],
                    "findings": [
                        {
                            "statement": "PRIVATE DERIVED ANALYSIS MUST NOT LEAK.",
                            "passage_ids": [private_passage_id],
                        }
                    ],
                    "limitations": [],
                    "cannot_conclude": [],
                    "further_information_needed": [],
                    "provider": "fixture",
                    "model": "fixture-model",
                }
            },
        }
        db.add(
            ResearchReport(
                job_id=permitted_job_id,
                status="completed_with_limitations",
                body_markdown="# Evidence map\n\nThe report describes grid response. [S1]",
                citation_map_json={
                    "schema_version": 1,
                    "citations": {
                        "S1": {
                            "source_id": permitted_source_id,
                            "title": permitted_source.title,
                            "doi": permitted_source.doi,
                            "url": permitted_source.url,
                            "passages": [permitted_passage_id],
                        }
                    },
                },
                verification_json={"schema_version": 1, "record": {"schema_version": 1}},
            )
        )
        db.commit()
    server = create_evidence_mcp_server(client, api_prefix="/api/v1")
    protocol_client = pytest.importorskip(
        "mcp", reason="install the optional backend mcp extra"
    ).Client

    async def call_server():
        async with protocol_client(server) as mcp_client:
            listed = await mcp_client.list_tools()
            assert {tool.name for tool in listed.tools} >= {
                "search_research_evidence",
                "get_evidence_passage",
                "get_source_provenance",
                "get_document_structure",
                "get_research_job_status",
                "get_document_analysis",
                "get_evidence_comparison",
                "get_evidence_coverage",
                "get_research_report",
            }
            result = await mcp_client.call_tool(
                "search_research_evidence", {"query": "frequency response", "limit": 5}
            )
            assert not result.is_error
            search_result = json.loads(result.content[0].text)
            source_tool = await mcp_client.call_tool(
                "get_source_provenance", {"source_id": permitted_source_id}
            )
            passage_tool = await mcp_client.call_tool(
                "get_evidence_passage", {"passage_id": permitted_passage_id}
            )
            private_passage_tool = await mcp_client.call_tool(
                "get_evidence_passage", {"passage_id": private_passage_id}
            )
            analysis_tool = await mcp_client.call_tool(
                "get_document_analysis", {"source_id": permitted_source_id}
            )
            structure_tool = await mcp_client.call_tool(
                "get_document_structure", {"source_id": permitted_source_id}
            )
            private_analysis_tool = await mcp_client.call_tool(
                "get_document_analysis", {"source_id": private_source_id}
            )
            private_structure_tool = await mcp_client.call_tool(
                "get_document_structure", {"source_id": private_source_id}
            )
            status_tool = await mcp_client.call_tool(
                "get_research_job_status", {"job_id": permitted_job_id}
            )
            report_tool = await mcp_client.call_tool(
                "get_research_report", {"job_id": permitted_job_id}
            )
            coverage_tool = await mcp_client.call_tool(
                "get_evidence_coverage", {"job_id": permitted_job_id}
            )
            comparison_tool = await mcp_client.call_tool(
                "get_evidence_comparison", {"job_id": permitted_job_id}
            )
            unverified_passage_tool = await mcp_client.call_tool(
                "get_evidence_passage", {"passage_id": unverified_passage_id}
            )
            assert not source_tool.is_error and not passage_tool.is_error
            assert not private_passage_tool.is_error
            assert not unverified_passage_tool.is_error
            return (
                search_result,
                json.loads(source_tool.content[0].text),
                json.loads(passage_tool.content[0].text),
                json.loads(private_passage_tool.content[0].text),
                private_source_id,
                json.loads(unverified_passage_tool.content[0].text),
                unverified_source_id,
                json.loads(analysis_tool.content[0].text),
                json.loads(structure_tool.content[0].text),
                json.loads(private_analysis_tool.content[0].text),
                json.loads(private_structure_tool.content[0].text),
                json.loads(status_tool.content[0].text),
                json.loads(report_tool.content[0].text),
                json.loads(coverage_tool.content[0].text),
                json.loads(comparison_tool.content[0].text),
            )

    (
        payload,
        source_provenance,
        passage_result,
        private_passage_result,
        private_source_id,
        unverified_passage_result,
        unverified_source_id,
        analysis_result,
        structure_result,
        private_analysis_result,
        private_structure_result,
        status_result,
        report_result,
        coverage_result,
        comparison_result,
    ) = asyncio.run(call_server())
    returned_text = [
        passage["content"]
        for item in payload["results"]
        for passage in item["passages"]
        if isinstance(passage.get("content"), str)
    ]
    assert permitted_text in returned_text
    assert private_text not in returned_text
    assert unverified_license_text not in returned_text
    private_results = [
        passage
        for item in payload["results"]
        if item["source"]["title"] == "Private grid frequency response report"
        for passage in item["passages"]
    ]
    assert private_results
    assert private_results[0]["content"] is None
    assert private_results[0]["external_disclosure"] == "metadata_only"
    assert source_provenance["source_id"] == permitted_source_id
    assert "passage_locators" in source_provenance
    assert passage_result["passage"]["content"] == permitted_text
    assert passage_result["passage"]["locator"] == "PDF p. 2"
    assert private_passage_result["source"]["source_id"] == private_source_id
    assert private_passage_result["passage"]["content"] is None
    assert unverified_passage_result["source"]["source_id"] == unverified_source_id
    assert unverified_passage_result["passage"]["content"] is None
    assert analysis_result["external_disclosure"] == "license_scoped_derived_analysis"
    assert analysis_result["analysis"]["findings"][0]["passage_ids"] == [permitted_passage_id]
    assert structure_result["documents"][0]["parser"]["page_count"] == 4
    assert structure_result["documents"][0]["document_sha256"]
    assert permitted_text not in json.dumps(structure_result)
    assert private_analysis_result["external_disclosure"] == "metadata_only"
    assert "PRIVATE DERIVED ANALYSIS MUST NOT LEAK" not in json.dumps(private_analysis_result)
    assert "PRIVATE REPORT FINDING MUST NOT LEAK" not in json.dumps(private_structure_result)
    assert status_result["id"] == permitted_job_id
    assert report_result["external_disclosure"] == "license_scoped_report"
    assert report_result["body_markdown"].startswith("# Evidence map")
    assert coverage_result["job_id"] == permitted_job_id
    assert coverage_result["interpretation_limit"].startswith("Operational evidence coverage")
    assert comparison_result["external_disclosure"] == "metadata_only"


def test_mcp_candidate_ledger_is_bounded_owner_scoped_and_metadata_only(client):
    project_id, job_id, candidate_id = str(uuid4()), str(uuid4()), str(uuid4())
    with client.db_sessions() as db:
        project = Project(
            id=project_id,
            owner_id=client.test_user["id"],
            title="Candidate review project",
            description="",
            domain="health policy",
        )
        job = ResearchJob(
            id=job_id,
            project_id=project_id,
            question="What evidence links primary care continuity to admissions?",
            idempotency_key=str(uuid4()),
            status="completed",
            current_stage="complete",
        )
        candidate = DiscoveryCandidate(
            id=candidate_id,
            job_id=job_id,
            candidate_key="a" * 64,
            provider="Crossref",
            provider_record_id="fixture:record-1",
            canonical_identity="doi:10.5555/example.1",
            title="Continuity of primary care and avoidable hospital admissions",
            publisher="Example Health Journal",
            abstract_excerpt="PRIVATE ABSTRACT MUST NOT BE DISCLOSED",
            abstract_excerpt_retention_status="not_retained_rights_unclear",
            doi="10.5555/example.1",
            url="https://doi.org/10.5555/example.1",
            published_year=2025,
            query_text="primary care continuity admissions",
            ranking_order=1,
            relevance_score=0.0,
            relevance_json={
                **score_candidate_relevance(
                    "primary care continuity and admissions",
                    "Continuity of primary care and avoidable hospital admissions",
                    None,
                ),
                "topic_eligibility_basis": "not_eligible",
                "ai_assessment": {
                    "schema_version": 1,
                    "assessment": "directly_relevant",
                    "reason": "Title is relevant to the question's stated relationship.",
                    "provider": "openrouter",
                    "model": "fixture-model",
                    "interpretation_limit": "Model-assisted bibliographic relevance only; not source quality, study validity, evidence, or truth.",
                },
            },
            disposition="excluded",
            reason_code="insufficient_topic_overlap",
            discovered_at=datetime.now(UTC),
        )
        db.add_all([project, job, candidate])
        db.commit()

    server = create_evidence_mcp_server(client)
    from app.api.routes import _candidate_out

    with client.db_sessions() as db:
        direct_candidate = _candidate_out(db.get(DiscoveryCandidate, candidate_id))
        assert direct_candidate["relevance"]["ai_assessment"]["assessment"] == "directly_relevant"
    protocol_client = pytest.importorskip(
        "mcp", reason="install the optional backend mcp extra"
    ).Client

    async def call_server():
        async with protocol_client(server) as mcp_client:
            listed = await mcp_client.list_tools()
            assert "list_research_candidates" in {tool.name for tool in listed.tools}
            result = await mcp_client.call_tool(
                "list_research_candidates", {"job_id": job_id, "limit": 5}
            )
            return result

    result = asyncio.run(call_server())
    assert not result.is_error
    payload = json.loads(result.content[0].text)
    assert payload["candidates"][0]["title"] == candidate.title
    assert payload["candidates"][0]["ai_relevance"]["assessment"] == "directly_relevant"
    assert payload["candidates"][0]["external_disclosure"] == "metadata_only"
    assert "PRIVATE ABSTRACT MUST NOT BE DISCLOSED" not in result.content[0].text
    assert "abstract_excerpt" not in result.content[0].text


@pytest.mark.parametrize(
    ("candidate_url", "expected"),
    [
        ("https://publisher.example/research.pdf", "https://publisher.example/research.pdf"),
        ("http://127.0.0.1/private", None),
        ("https://metadata.internal/report", None),
        ("javascript:alert(1)", None),
        ("https://example.test:99999/report", None),
        ("https://user:secret@example.test/report", None),
        ("https://[invalid/report", None),
        (f"https://example.test/{'a' * 800}", None),
    ],
)
def test_mcp_candidate_url_projection_rejects_nonpublic_or_malformed_urls(candidate_url, expected):
    from app.mcp_evidence_server import _safe_candidate_url

    assert _safe_candidate_url(candidate_url) == expected


def test_stdio_transport_works_with_official_mcp_client_protocol_only():
    mcp = pytest.importorskip("mcp", reason="install the optional backend mcp extra")
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    del mcp
    source_id, passage_id, document_id = str(uuid4()), str(uuid4()), str(uuid4())
    passage_text = "A verified publication reports a bounded measurable outcome."
    passage_hash = hashlib.sha256(passage_text.encode()).hexdigest()
    source = {
        "id": source_id,
        "title": "Protocol test research report",
        "doi": None,
        "url": "https://publisher.example/report.pdf",
        "publisher": "Verified Publisher",
        "source_type": "institutional_report",
        "retrieval_status": "full_text_pdf",
        "organization_provenance": None,
        "official_publication": None,
        "official_site_publication": None,
        "retrieval": {
            "license": "cc-by",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_evidence": "item-level license metadata",
            "rights_assessment": {
                "analysis": "PERMITTED",
                "retention": "LICENSE_SCOPED",
                "sharing": "LICENSE_SCOPED",
                "basis": "verified_item_license",
                "reason_codes": ["test_only"],
            },
        },
    }
    passage = {
        "id": passage_id,
        "source_id": source_id,
        "document_id": document_id,
        "locator": "PDF p. 4",
        "content": passage_text,
        "content_hash": passage_hash,
        "access_level": "full_text_pdf",
        "content_withheld_reason": None,
        "document": {
            "id": document_id,
            "source_id": source_id,
            "source_version": "v1",
            "document_sha256": hashlib.sha256(b"protocol-test-document").hexdigest(),
            "media_type": "application/pdf",
        },
    }

    class APIHandler(BaseHTTPRequestHandler):
        def log_message(self, _format, *args):
            return

        def _json(self, status: int, body: dict):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _authorized(self) -> bool:
            if self.headers.get("Authorization") == "Bearer test-only-mcp-token":
                return True
            self._json(401, {"detail": "unauthorized"})
            return False

        def do_POST(self):
            if not self._authorized():
                return
            size = int(self.headers.get("Content-Length", "0"))
            json.loads(self.rfile.read(size))
            self._json(200, {"items": [{"source": source, "passages": [passage]}]})

        def do_GET(self):
            if not self._authorized():
                return
            if self.path == f"/api/v1/sources/{source_id}/provenance":
                locator = {
                    key: passage[key]
                    for key in (
                        "id",
                        "document_id",
                        "locator",
                        "content_hash",
                        "access_level",
                        "truncated",
                    )
                }
                self._json(
                    200,
                    {
                        "source": source,
                        "passages": [locator],
                        "total_passages": 1,
                        "has_more": False,
                    },
                )
            elif self.path == f"/api/v1/passages/{passage_id}":
                self._json(200, passage)
            else:
                self._json(404, {"detail": "not found"})

    api = ThreadingHTTPServer(("127.0.0.1", 0), APIHandler)
    api_thread = threading.Thread(target=api.serve_forever, daemon=True)
    api_thread.start()
    backend_root = Path(__file__).resolve().parents[1]
    environment = {
        **{
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            if os.environ.get(key)
        },
        "VEDA_MCP_API_BASE_URL": f"http://127.0.0.1:{api.server_port}",
        "VEDA_MCP_BEARER_TOKEN": "test-only-mcp-token",
        "PYTHONPATH": str(backend_root),
        "PYTHONUTF8": "1",
    }
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_evidence_server"],
        cwd=str(backend_root),
        env=environment,
    )

    async def inspect():
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert "search_research_evidence" in {tool.name for tool in tools.tools}
                result = await session.call_tool(
                    "search_research_evidence", {"query": "measurable outcome", "limit": 1}
                )
                assert not result.is_error
                return json.loads(result.content[0].text)

    try:
        result = asyncio.run(inspect())
    finally:
        api.shutdown()
        api.server_close()
        api_thread.join(timeout=2)

    returned_passage = result["results"][0]["passages"][0]
    assert returned_passage["content"] == passage_text
    assert returned_passage["locator"] == "PDF p. 4"
    assert returned_passage["content_hash"] == passage_hash
