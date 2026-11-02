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

from app.mcp_evidence_server import (
    create_evidence_mcp_server,
    validate_loopback_api_url,
)
from app.models import Passage, Project, ResearchJob, RetrievedDocument, Source


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

    foreign_source_id, _foreign_passage_id = _add_evidence(
        client,
        owner_id="20000000-0000-4000-8000-000000000002",
        sharing="CITATION_ONLY",
        title="Another user's locator-only report",
        passage_text="This other owner's source must stay isolated.",
    )
    foreign_response = client.get(f"/api/v1/sources/{foreign_source_id}/provenance")
    assert foreign_response.status_code == 404


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
            )

    (
        payload,
        source_provenance,
        passage_result,
        private_passage_result,
        private_source_id,
        unverified_passage_result,
        unverified_source_id,
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


def test_stdio_transport_works_with_official_mcp_client_protocol_only():
    mcp = pytest.importorskip("mcp", reason="install the optional backend mcp extra")
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    del mcp
    source_id, passage_id = str(uuid4()), str(uuid4())
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
        "document_id": str(uuid4()),
        "locator": "PDF p. 4",
        "content": passage_text,
        "content_hash": passage_hash,
        "access_level": "full_text_pdf",
        "content_withheld_reason": None,
        "document": {
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
