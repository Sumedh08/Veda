from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Claim, Passage, ResearchJob, RetrievedDocument, Source
from app.providers.europe_pmc import EuropePMCArticleMetadata, EuropePMCResolution
from app.research import workflow
from app.research.safe_fetch import SafeFetchError, SafeHTMLDocument
from app.research.safe_pdf import SafePDFDocument


@pytest.mark.parametrize("include_pmcid", [True, False], ids=["pmcid", "doi-fallback"])
@pytest.mark.parametrize(
    "abstract_clutters_passages", [False, True], ids=["ordinary", "abstract-heavy"]
)
def test_europe_pmc_full_text_is_rights_gated_and_persisted_with_section_provenance(
    client, monkeypatch, include_pmcid, abstract_clutters_passages
):
    project = client.post(
        "/api/v1/projects", json={"title": "Structured retrieval", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What did the trial measure?",
            "depth": "quick",
            "idempotency_key": "europe-pmc-jats-extraction",
        },
    ).json()
    abstract_text = (
        " ".join(f"Abstract context sentence {index} is recorded." for index in range(1, 20))
        if abstract_clutters_passages
        else "Forty-two adults participated."
    )
    xml = (
        "<article><front><article-meta><abstract><title>Abstract</title><p>"
        + abstract_text
        + "</p></abstract></article-meta></front><body><sec><title>Methods</title>"
        "<p>We randomized 42 adults to the intervention or control group.</p></sec>"
        "<sec><title>Results</title><p>The intervention group completed the task in less time.</p></sec>"
        "<sec><title>Limitations</title><p>The study evaluated one short task.</p></sec>"
        "</body></article>"
    ).encode()

    class FixtureEuropePMC:
        def __init__(self, *, timeout_seconds, request_admission):
            assert timeout_seconds > 0
            assert callable(request_admission)

        def resolve_full_text(self, pmcid, *, expected_doi):
            assert pmcid == ("PMC12345" if include_pmcid else None)
            assert expected_doi == "10.5555/jats-study"
            return EuropePMCResolution(
                status="retrieved",
                reason_code=None,
                metadata=EuropePMCArticleMetadata(
                    pmcid="PMC12345",
                    doi="10.5555/jats-study",
                    title="Structured trial",
                    open_access=True,
                    license_code="cc-by",
                    raw_license="CC BY",
                ),
                content=xml,
                content_type="application/xml",
            )

        def close(self):
            pass

    monkeypatch.setattr(workflow, "EuropePMCProvider", FixtureEuropePMC)
    with client.db_sessions() as db:
        persisted_job = db.get(ResearchJob, job["id"])
        persisted_job.current_stage = "extraction"
        source = Source(
            job_id=job["id"],
            external_id="doi:10.5555/jats-study",
            title="Structured trial",
            doi="10.5555/jats-study",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {"pmcid": "PMC12345"} if include_pmcid else {},
            },
        )
        db.add(source)
        db.commit()
        source_id = source.id
        stage_result = workflow.execute_stage(db, workflow.job_snapshot(persisted_job))
        workflow.persist_result(db, persisted_job, stage_result)
        db.commit()

        db.refresh(source)
        passages = list(db.scalars(select(Passage).where(Passage.source_id == source_id)))
        documents = list(
            db.scalars(select(RetrievedDocument).where(RetrievedDocument.source_id == source_id))
        )
        claims = list(db.scalars(select(Claim).where(Claim.source_id == source_id)))

    assert source.retrieval_status == "full_text_jats"
    assert source.metadata_json["retrieval"]["jats"]["lookup_key_type"] == (
        "pmcid" if include_pmcid else "doi"
    )
    assert stage_result.event_data["licensed_jats_retrieved"] == 1
    assert any("Methods" in passage.locator for passage in passages)
    assert any("Results" in passage.locator for passage in passages)
    assert any("Limitations" in passage.locator for passage in passages)
    assert any("Methods" in passage.locator for passage in passages)
    assert any("Results" in passage.locator for passage in passages)
    assert any(passage.access_level == "full_text_jats" for passage in passages)
    assert not any(passage.access_level == "abstract_only" for passage in passages)
    jats_document = next(
        document for document in documents if document.access_class == "full_text_jats"
    )
    assert not any(document.access_class == "abstract_only" for document in documents)
    assert jats_document.media_type == "application/xml"
    assert jats_document.metadata_json["rights_decision"] == "PERMITTED"
    assert jats_document.metadata_json["parser_name"] == "veda-structured-xml"
    assert jats_document.metadata_json["representation_format"] == "jats"
    assert claims

    api_source = client.get(f"/api/v1/sources/{source_id}").json()
    assert any(
        passage["access_level"] == "full_text_jats"
        and passage["document"]["metadata"]["rights_decision"] == "PERMITTED"
        for passage in api_source["passages"]
    )


def test_extraction_retrieves_only_explicitly_licensed_openalex_html(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Licensed retrieval", "domain": "testing"}
    )
    job_response = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={
            "question": "Inspect a bounded research passage",
            "depth": "quick",
            "idempotency_key": "retrieval-e2e",
        },
    )
    job_id = job_response.json()["id"]
    fetch_calls = []

    class RecordingFetcher:
        def __init__(self, *, origin_request_limiter=None):
            pass

        def fetch_html(self, url, *, license_name):
            fetch_calls.append((url, license_name))
            return SafeHTMLDocument(
                text="\n\n".join(
                    f"Finding {index} is reported with an outcome." for index in range(20)
                ),
                sha256="a" * 64,
                media_type="text/html",
                final_host="papers.example",
                retrieved_at=datetime.now(UTC),
                truncated=False,
                host_policy_id="fixture-reviewed-host-v1",
                host_terms_url="https://papers.example/terms",
                robots_status="rules_checked",
            )

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", RecordingFetcher)
    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        job.current_stage = "extraction"
        licensed = Source(
            job_id=job_id,
            external_id="doi:10.5555/allowed-html",
            title="Openly licensed study",
            doi="10.5555/allowed-html",
            url="https://doi.org/10.5555/allowed-html",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/open-study",
                        "pdf_url": "https://papers.example/open-study.pdf",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    }
                },
            },
        )
        unknown_license = Source(
            job_id=job_id,
            external_id="openalex:W-unknown-license",
            title="Unverified reuse rights",
            url="https://doi.org/10.5555/unknown-license",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/unknown",
                        "license": None,
                    }
                },
            },
        )
        db.add_all([licensed, unknown_license])
        db.commit()
        snapshot = workflow.job_snapshot(job)

        result = workflow.execute_stage(db, snapshot)
        workflow.persist_result(db, job, result)
        db.commit()

        passages = list(db.scalars(select(Passage).where(Passage.source_id == licensed.id)))
        claims = list(db.scalars(select(Claim).where(Claim.job_id == job_id)))
        db.refresh(licensed)
        db.refresh(unknown_license)

        assert result.event_data["licensed_html_attempts"] == 1
        assert result.event_data["licensed_html_retrieved"] == 1
        assert fetch_calls == [("https://papers.example/open-study", "cc-by")]
        assert licensed.retrieval_status == "full_text_html"
        assert licensed.metadata_json["retrieval"]["document_sha256"] == "a" * 64
        assert (
            licensed.metadata_json["retrieval"]["outcomes"]["by_format"]["html"]["outcome"]
            == "retrieved"
        )
        assert licensed.metadata_json["retrieval"]["version"] == "publishedVersion"
        full_text_passages = [
            passage for passage in passages if passage.access_level == "full_text_html"
        ]
        assert len(full_text_passages) == 12  # quick depth cap
        assert any(
            claim.appraisal_json["extraction"] == "exact_sentence_from_full_text_html"
            for claim in claims
        )
        document_records = list(
            db.scalars(select(RetrievedDocument).where(RetrievedDocument.source_id == licensed.id))
        )
        assert {record.access_class for record in document_records} == {
            "full_text_html",
        }
        assert all(record.schema_version == 1 for record in document_records)
        original_passage_ids = {passage.id for passage in passages}
        original_document_ids = {record.id for record in document_records}
        assert unknown_license.retrieval_status == "metadata_only"
        assert (
            unknown_license.metadata_json["retrieval"]["outcomes"]["by_format"]["html"]["outcome"]
            == "not_attempted"
        )
        assert (
            unknown_license.metadata_json["retrieval"]["reason"] == "license_not_verified_for_reuse"
        )
        # A safe stage replay may retrieve the same bytes again, but the stored version and
        # passage identities remain stable and claims stay linked to their original passages.
        replay = workflow.execute_stage(db, workflow.job_snapshot(job))
        workflow.persist_result(db, job, replay)
        db.commit()
        replay_passages = list(db.scalars(select(Passage).where(Passage.source_id == licensed.id)))
        replay_documents = list(
            db.scalars(select(RetrievedDocument).where(RetrievedDocument.source_id == licensed.id))
        )
        assert {passage.id for passage in replay_passages} == original_passage_ids
        assert {record.id for record in replay_documents} == original_document_ids
        api_source = client.get(f"/api/v1/sources/{licensed.id}")
        assert api_source.status_code == 200
        html_passage = next(
            passage
            for passage in api_source.json()["passages"]
            if passage["access_level"] == "full_text_html"
        )
        assert html_passage["identity_version"] == 1
        assert html_passage["document"]["schema_version"] == 1
        assert html_passage["document"]["source_version"] == "publishedVersion"
        assert html_passage["document"]["document_sha256"] == "a" * 64


def test_retrieval_failure_is_persisted_without_transport_details(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Failure provenance", "domain": "testing"}
    )
    job_response = client.post(
        f"/api/v1/projects/{project.json()['id']}/research-jobs",
        json={"question": "Record safe failure", "idempotency_key": "retrieval-failure"},
    )
    job_id = job_response.json()["id"]

    class FailingFetcher:
        def __init__(self, *, origin_request_limiter=None):
            pass

        def fetch_html(self, url, *, license_name):
            raise SafeFetchError("timeout", "secret internal socket information")

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", FailingFetcher)
    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        job.current_stage = "extraction"
        source = Source(
            job_id=job_id,
            external_id="openalex:W-timeout",
            title="Slow licensed article",
            url="https://doi.org/10.5555/timeout",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://papers.example/slow",
                        "license": "cc-by",
                    }
                },
            },
        )
        db.add(source)
        db.commit()

        result = workflow.execute_stage(db, workflow.job_snapshot(job))
        workflow.persist_result(db, job, result)
        db.commit()
        db.refresh(source)

        assert result.event_data["licensed_html_failures"] == 1
        assert source.retrieval_status == "metadata_only"
        assert source.metadata_json["retrieval"]["error_code"] == "timeout"
        assert "secret" not in str(source.metadata_json)
        html_outcome = source.metadata_json["retrieval"]["outcomes"]["by_format"]["html"]
        assert html_outcome["outcome"] == "error"
        assert html_outcome["error_code"] == "timeout"
        api_source = client.get(f"/api/v1/sources/{source.id}").json()
        assert api_source["retrieval_status"] == "metadata_only"
        assert api_source["retrieval"]["outcomes"]["by_format"]["html"]["outcome"] == "error"


def test_pdf_fallback_persists_page_provenance_and_respects_depth_document_cap(client, monkeypatch):
    project_response = client.post(
        "/api/v1/projects", json={"title": "Licensed PDF", "domain": "testing"}
    )
    project_id = project_response.json()["id"]
    job_response = client.post(
        f"/api/v1/projects/{project_id}/research-jobs",
        json={
            "question": "Extract a licensed PDF text passage",
            "depth": "quick",
            "idempotency_key": "licensed-pdf-job-01",
        },
    )
    job_id = job_response.json()["id"]
    html_requests = []
    pdf_requests = []

    class BrokenHTMLFetcher:
        def __init__(self, *, origin_request_limiter=None):
            pass

        def fetch_html(self, url, *, license_name):
            html_requests.append((url, license_name))
            raise SafeFetchError("http_status", "The source did not return a successful response.")

    class RecordingPDFFetcher:
        def __init__(self, *, origin_request_limiter=None, timeout_seconds=None):
            pass

        def fetch_pdf(self, url, *, license_name):
            pdf_requests.append((url, license_name))
            return SafePDFDocument(
                pages=((2, "The paper reports a measured productivity effect."),),
                page_count=3,
                pages_extracted=1,
                text_truncated=False,
                sha256="b" * 64,
                media_type="application/pdf",
                final_host="repository.example",
                retrieved_at=datetime.now(UTC),
                host_policy_id="fixture-reviewed-host-v1",
                host_terms_url="https://repository.example/terms",
                robots_status="rules_checked",
            )

    monkeypatch.setattr(workflow, "SafeHTMLFetcher", BrokenHTMLFetcher)
    monkeypatch.setattr(workflow, "SafePDFFetcher", RecordingPDFFetcher)
    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        job.current_stage = "extraction"
        sources = [
            Source(
                job_id=job_id,
                external_id=f"openalex:W-pdf-{index}",
                title=f"Licensed PDF {index}",
                retrieval_status="metadata_only",
                metadata_json={
                    "provider": "OpenAlex",
                    "provider_metadata": {
                        "best_oa_location": {
                            "is_oa": True,
                            "landing_page_url": (
                                "https://publisher.example/article" if index == 0 else None
                            ),
                            "pdf_url": f"https://repository.example/paper-{index}.pdf",
                            "license": "cc-by",
                            "version": "publishedVersion",
                        }
                    },
                },
            )
            for index in range(2)
        ]
        db.add_all(sources)
        db.commit()

        result = workflow.execute_stage(db, workflow.job_snapshot(job))
        workflow.persist_result(db, job, result)
        db.commit()
        for source in sources:
            db.refresh(source)

        assert result.event_data["licensed_html_failures"] == 1
        assert result.event_data["licensed_pdf_attempts"] == 1
        assert result.event_data["licensed_pdf_retrieved"] == 1
        assert result.event_data["licensed_pdf_pages_extracted"] == 1
        assert pdf_requests == [("https://repository.example/paper-0.pdf", "cc-by")]
        assert html_requests == [("https://publisher.example/article", "cc-by")]
        assert sources[0].retrieval_status == "full_text_pdf"
        retrieval = sources[0].metadata_json["retrieval"]
        assert retrieval["format"] == "pdf"
        assert retrieval["outcomes"]["by_format"]["pdf"]["outcome"] == "partial"
        assert (
            retrieval["outcomes"]["by_format"]["pdf"]["reason_code"]
            == "some_pages_without_embedded_text"
        )
        assert retrieval["document_sha256"] == "b" * 64
        assert retrieval["version"] == "publishedVersion"
        assert retrieval["ocr_performed"] is False
        assert "data" not in retrieval
        assert sources[1].metadata_json["retrieval"]["pdf"]["reason"] == "depth_pdf_cap"

        passages = list(db.scalars(select(Passage).where(Passage.source_id == sources[0].id)))
        assert len(passages) == 1
        assert passages[0].locator == "PDF page 2, sentence 1"
        assert passages[0].access_level == "full_text_pdf"
        claim = db.scalar(select(Claim).where(Claim.job_id == job_id))
        assert claim is not None
        assert claim.appraisal_json["extraction"] == "exact_sentence_from_full_text_pdf"


def test_grobid_pdf_sections_and_exact_methods_results_passages_persist(client, monkeypatch):
    from app.research.structured_documents import parse_structured_document

    project = client.post(
        "/api/v1/projects", json={"title": "GROBID extraction", "domain": "testing"}
    ).json()
    job = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "What did the licensed study measure?",
            "depth": "quick",
            "idempotency_key": "grobid-pdf-section-provenance",
        },
    ).json()
    tei = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div><head>Methods</head><p>Researchers randomized 80 developers to two conditions.</p></div>
      <div><head>Results</head><p>The measured task-completion time was lower in the treatment group.</p></div>
    </body></text></TEI>"""
    structured = parse_structured_document(tei, format_hint="tei")
    monkeypatch.setattr(workflow.settings, "grobid_enabled", True)
    grobid_options = []

    class FixtureGrobid:
        def __init__(self, *, base_url):
            grobid_options.append(base_url)

    class BrokenHTMLFetcher:
        def __init__(self, *, origin_request_limiter=None):
            pass

        def fetch_html(self, url, *, license_name):
            raise SafeFetchError("http_status", "The source did not return a successful response.")

    class StructuredPDFFetcher:
        def __init__(
            self, *, origin_request_limiter=None, timeout_seconds=None, grobid_client=None
        ):
            assert grobid_client is not None

        def fetch_pdf(self, url, *, license_name):
            return SafePDFDocument(
                pages=(),
                page_count=None,
                pages_extracted=0,
                text_truncated=False,
                sha256="c" * 64,
                media_type="application/pdf",
                final_host="repository.example",
                retrieved_at=datetime.now(UTC),
                host_policy_id="fixture-reviewed-host-v1",
                host_terms_url="https://repository.example/terms",
                robots_status="rules_checked",
                structured_document=structured,
                parser_name="grobid",
                parser_version="0.9.1-fixture",
            )

    monkeypatch.setattr(workflow, "GrobidClient", FixtureGrobid)
    monkeypatch.setattr(workflow, "SafeHTMLFetcher", BrokenHTMLFetcher)
    monkeypatch.setattr(workflow, "SafePDFFetcher", StructuredPDFFetcher)
    with client.db_sessions() as db:
        research_job = db.get(ResearchJob, job["id"])
        assert research_job is not None
        research_job.current_stage = "extraction"
        source = Source(
            job_id=job["id"],
            external_id="openalex:W-grobid-study",
            title="Licensed study with structured methods",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "OpenAlex",
                "provider_metadata": {
                    "best_oa_location": {
                        "is_oa": True,
                        "landing_page_url": "https://repository.example/article",
                        "pdf_url": "https://repository.example/article.pdf",
                        "license": "cc-by",
                        "version": "publishedVersion",
                    }
                },
            },
        )
        db.add(source)
        db.commit()
        source_id = source.id
        result = workflow.execute_stage(db, workflow.job_snapshot(research_job))
        workflow.persist_result(db, research_job, result)
        db.commit()

        passages = list(db.scalars(select(Passage).where(Passage.source_id == source_id)))
        document = db.scalar(
            select(RetrievedDocument).where(RetrievedDocument.source_id == source_id)
        )

    assert grobid_options == ["http://127.0.0.1:8070"]
    assert {"methods", "results"} <= {item.locator.split(" ", 2)[1].casefold() for item in passages}
    assert any(
        item.content == "Researchers randomized 80 developers to two conditions."
        for item in passages
    )
    assert any(
        item.content == "The measured task-completion time was lower in the treatment group."
        for item in passages
    )
    assert all(item.document_id == document.id for item in passages)
    assert document.metadata_json["parser_name"] == "grobid"
    assert document.metadata_json["parser_version"] == "0.9.1-fixture"
    assert [section["original_heading"] for section in document.metadata_json["sections"]] == [
        "Methods",
        "Results",
    ]
    api_source = client.get(f"/api/v1/sources/{source_id}").json()
    assert api_source["retrieval"]["grobid"]["status"] == "parsed"
    assert api_source["retrieval"]["structured_document"]["methods_results_usable"] is True
    assert api_source["retrieval"]["structured_document"]["parser_version"] == "0.9.1-fixture"


def test_crossref_ore_affiliated_work_uses_exact_openair_strathprints_pdf(client, monkeypatch):
    from app.providers.scholarly import ScholarlyWork
    from app.research.structured_documents import parse_structured_document

    title = (
        "Hybrid, Multi-Megawatt HVDC Transformer Topology Comparison for Future Offshore Wind Farms"
    )
    doi = "10.3390/en10070851"
    repository_url = (
        "https://strathprints.strath.ac.uk/61241/1/"
        "Smailes_etal_Energies_2017_hybrid_multi_megawatt_HVDC_transformer_topology_comparison.pdf"
    )
    project = client.post(
        "/api/v1/projects", json={"title": "Repository evidence", "domain": "energy"}
    ).json()
    job_response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How do HVDC transformer topologies compare for offshore wind?",
            "depth": "quick",
            "idempotency_key": "crossref-openaire-ore-full-text",
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]
    admitted_origins = []
    requested_urls = []
    tei = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
      <div><head>Methods</head><p>The comparison models three multi-megawatt transformer topologies for offshore wind transmission.</p></div>
      <div><head>Results</head><p>The study compares losses, mass, and cost across the three HVDC transformer topologies.</p></div>
      <div><head>Limitations</head><p>The findings depend on the modeled system boundary and assumptions.</p></div>
    </body></text></TEI>"""
    structured = parse_structured_document(tei, format_hint="tei")

    class FixtureOriginLimiter:
        def __init__(self, _db):
            pass

        def acquire(self, origin, _interval_seconds, *, deadline):
            admitted_origins.append(origin)
            assert deadline > 0

    class FixtureEuropePMC:
        def __init__(self, *, timeout_seconds, request_admission):
            assert timeout_seconds > 0
            self.request_admission = request_admission

        def resolve_full_text(self, _pmcid, *, expected_doi):
            self.request_admission()
            assert expected_doi == doi
            from app.providers.europe_pmc import EuropePMCArticleMetadata, EuropePMCResolution

            return EuropePMCResolution(
                status="unavailable",
                reason_code="not_covered",
                metadata=EuropePMCArticleMetadata(
                    pmcid=None,
                    doi=doi,
                    title=title,
                    open_access=False,
                    license_code=None,
                    raw_license=None,
                ),
                content=None,
                content_type=None,
            )

        def close(self):
            pass

    class FixtureOpenAIRE:
        def __init__(self, *, before_request):
            self.before_request = before_request

        def search(self, query, *, limit):
            self.before_request()
            assert query == title
            assert limit == 4
            return [
                ScholarlyWork(
                    external_id=f"doi:{doi}",
                    title=title,
                    doi=doi,
                    url=f"https://doi.org/{doi}",
                    authors=[],
                    published_year=2017,
                    publisher="MDPI AG",
                    abstract_excerpt=None,
                    query=query,
                    provider="OpenAIRE",
                    provider_metadata={
                        "openaire_id": "doi_________::61241",
                        "repository_instances": [
                            {
                                "url": "https://www.mdpi.com/1996-1073/10/7/851/pdf",
                                "license_code": "cc-by",
                                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                                "content_version": "publishedVersion",
                                "instance_type": "Article",
                                "access_right": "OPEN",
                                "repository_name": "Publisher landing",
                                "repository_url": "https://www.mdpi.com/",
                            },
                            {
                                "url": repository_url,
                                "license_code": "cc-by",
                                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                                "content_version": "publishedVersion",
                                "instance_type": "Article",
                                "access_right": "OPEN",
                                "repository_name": "Strathprints",
                                "repository_url": "https://strathprints.strath.ac.uk/",
                            },
                        ],
                    },
                )
            ]

        def close(self):
            pass

    class FixturePDFFetcher:
        def __init__(self, *, origin_request_limiter, timeout_seconds):
            assert origin_request_limiter is not None
            assert timeout_seconds > 0

        def fetch_pdf(self, url, *, license_name):
            requested_urls.append((url, license_name))
            return SafePDFDocument(
                pages=(),
                page_count=None,
                pages_extracted=0,
                text_truncated=False,
                sha256="d" * 64,
                media_type="application/pdf",
                final_host="strathprints.strath.ac.uk",
                retrieved_at=datetime.now(UTC),
                host_policy_id="strathprints-research-copy-2026-11-01",
                host_terms_url="https://strathprints.strath.ac.uk/policies.html",
                robots_status="rules_checked",
                structured_document=structured,
                parser_name="veda-structured-xml-fixture",
                parser_version="1",
            )

    monkeypatch.setattr(workflow, "DatabaseOriginRequestLimiter", FixtureOriginLimiter)
    monkeypatch.setattr(workflow, "EuropePMCProvider", FixtureEuropePMC)
    monkeypatch.setattr(workflow, "OpenAIREProvider", FixtureOpenAIRE)
    monkeypatch.setattr(workflow, "SafePDFFetcher", FixturePDFFetcher)
    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        job.current_stage = "extraction"
        source = Source(
            job_id=job_id,
            external_id=f"doi:{doi}",
            title=title,
            doi=doi,
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "Crossref",
                "provider_metadata": {
                    "schema_version": 1,
                    "extensions": {
                        "crossref_full_text": {
                            "rights_evidence_source": "crossref_deposited_work_metadata",
                            "license_code": "cc-by",
                            "license_url": "https://creativecommons.org/licenses/by/4.0/",
                            "content_version": "vor",
                        },
                        "organization_discovery": {
                            "organization_id": "https://ror.org/03ffv2k10",
                            "organization_name": "Offshore Renewable Energy Catapult",
                            "identity_status": "VERIFIED_ESTABLISHED",
                            "verification_method": "ror_exact_identity",
                        },
                    },
                },
            },
        )
        db.add(source)
        db.commit()
        source_id = source.id
        result = workflow.execute_stage(db, workflow.job_snapshot(job))
        workflow.persist_result(db, job, result)
        db.commit()
        db.refresh(source)
        passages = list(db.scalars(select(Passage).where(Passage.source_id == source_id)))
        document = db.scalar(
            select(RetrievedDocument).where(RetrievedDocument.source_id == source_id)
        )
        claims = list(db.scalars(select(Claim).where(Claim.source_id == source_id)))

    assert requested_urls == [(repository_url, "cc-by")]
    assert admitted_origins.count("https://api.openaire.eu") == 1
    assert source.retrieval_status == "full_text_pdf"
    assert document is not None
    assert document.access_class == "full_text_pdf"
    assert document.document_sha256 == "d" * 64
    assert document.metadata_json["host_policy_id"] == "strathprints-research-copy-2026-11-01"
    assert (
        document.metadata_json["host_terms_url"]
        == "https://strathprints.strath.ac.uk/policies.html"
    )
    assert {passage.locator.split(" ", 2)[1].casefold() for passage in passages} >= {
        "methods",
        "results",
        "limitations",
    }
    assert any("three multi-megawatt transformer topologies" in p.content for p in passages)
    assert len(claims) >= 3
    retrieval = source.metadata_json["retrieval"]
    assert retrieval["scope"] == "openaire_exact_licensed_repository_instance"
    assert retrieval["openaire_resolution"]["status"] == "exact_match"
    assert retrieval["openaire_resolution"]["matched_doi"] == doi
    assert retrieval["openaire_resolution"]["license_code"] == "cc-by"
    assert retrieval["format"] == "pdf"
    assert retrieval["status"] == "retrieved"
    provider_metadata = source.metadata_json["provider_metadata"]
    repository_evidence = provider_metadata["extensions"]["openaire_repository_evidence"]
    assert repository_evidence["doi"] == doi
    assert repository_evidence["title"] == title
    assert repository_evidence["metadata_license"] == "CC-BY-4.0"
    assert result.event_data["openaire_repository_lookup_attempts"] == 1
    assert result.event_data["openaire_repository_instances_found"] == 1


def test_crossref_repository_lookup_requires_verified_organization_identity(client, monkeypatch):
    project = client.post(
        "/api/v1/projects", json={"title": "Unverified publisher", "domain": "energy"}
    ).json()
    job_response = client.post(
        f"/api/v1/projects/{project['id']}/research-jobs",
        json={
            "question": "How does this offshore wind engineering study compare designs?",
            "depth": "quick",
            "idempotency_key": "unverified-repository-affiliation-no-request",
        },
    )
    assert job_response.status_code == 201
    job_id = job_response.json()["id"]

    class FixtureEuropePMC:
        def __init__(self, *, timeout_seconds, request_admission):
            pass

        def resolve_full_text(self, _pmcid, *, expected_doi):
            from app.providers.europe_pmc import EuropePMCArticleMetadata, EuropePMCResolution

            return EuropePMCResolution(
                status="unavailable",
                reason_code="not_covered",
                metadata=EuropePMCArticleMetadata(
                    pmcid=None,
                    doi=expected_doi,
                    title="Unverified offshore wind work",
                    open_access=False,
                    license_code=None,
                    raw_license=None,
                ),
                content=None,
                content_type=None,
            )

        def close(self):
            pass

    class ForbiddenOpenAIRECall:
        def __init__(self, **_kwargs):
            raise AssertionError(
                "Unverified organization identity must not trigger repository lookup"
            )

    monkeypatch.setattr(workflow, "EuropePMCProvider", FixtureEuropePMC)
    monkeypatch.setattr(workflow, "OpenAIREProvider", ForbiddenOpenAIRECall)
    with client.db_sessions() as db:
        job = db.get(ResearchJob, job_id)
        assert job is not None
        job.current_stage = "extraction"
        source = Source(
            job_id=job_id,
            external_id="doi:10.5555/unverified-affiliation",
            title="Unverified offshore wind work",
            doi="10.5555/unverified-affiliation",
            retrieval_status="metadata_only",
            metadata_json={
                "provider": "Crossref",
                "provider_metadata": {
                    "schema_version": 1,
                    "extensions": {
                        "crossref_full_text": {
                            "license_code": "cc-by",
                            "license_url": "https://creativecommons.org/licenses/by/4.0/",
                            "content_version": "vor",
                        },
                        "organization_discovery": {
                            "organization_id": "unknown:publisher",
                            "identity_status": "PENDING_VERIFICATION",
                        },
                    },
                },
            },
        )
        db.add(source)
        db.commit()
        result = workflow.execute_stage(db, workflow.job_snapshot(job))
        assert result.event_data["openaire_repository_lookup_attempts"] == 0
        assert result.event_data["openaire_repository_instances_found"] == 0
        assert source.retrieval_status == "metadata_only"
