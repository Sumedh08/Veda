import gzip
from decimal import Decimal
from hashlib import sha256

import httpx
import pytest

from app.providers.openalex import (
    OpenAlexContentAuthorization,
    OpenAlexError,
    OpenAlexProvider,
)


def _work(*, doi="https://doi.org/10.5555/openalex-1"):
    return {
        "id": "https://openalex.org/W123456789",
        "ids": {"pmcid": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12345/"},
        "doi": doi,
        "title": "A bounded scholarly record",
        "publication_year": 2025,
        "authorships": [
            {"author": {"display_name": "Ada Lovelace"}},
            {"author": {"display_name": "Katherine Johnson"}},
        ],
        "primary_location": {
            "landing_page_url": "https://example.org/paper",
            "source": {"display_name": "Example Journal"},
        },
        "abstract_inverted_index": {
            "AI": [0],
            "improved": [1],
            "worker": [2],
            "output.": [3],
        },
        "open_access": {"is_oa": True, "oa_status": "green"},
        "best_oa_location": {
            "is_oa": True,
            "landing_page_url": "https://example.org/open-paper",
            "pdf_url": "https://example.org/open-paper.pdf",
            "license": "cc-by",
            "version": "publishedVersion",
        },
        "has_content": {"pdf": True, "grobid_xml": True},
        "content_urls": {
            "pdf": "https://content.openalex.org/works/W123456789.pdf",
            "grobid_xml": "https://content.openalex.org/works/W123456789.grobid-xml",
        },
        "type": "article",
    }


def test_openalex_normalizes_work_and_uses_bounded_selected_search():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openalex.org"
        assert request.url.path == "/works"
        assert request.url.params["search"] == "AI productivity"
        assert request.url.params["per_page"] == "2"
        assert "abstract_inverted_index" in request.url.params["select"]
        assert "ids" in request.url.params["select"]
        assert "has_content" in request.url.params["select"]
        assert "content_urls" not in request.url.params["select"]
        assert "api_key" not in request.url.params
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"results": [_work()]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAlexProvider(client, api_key="not-for-default-use")
    record = provider.search("  AI   productivity ", limit=2)[0]
    provider.close()

    assert record.external_id == "doi:10.5555/openalex-1"
    assert record.doi == "10.5555/openalex-1"
    assert record.provider == "OpenAlex"
    assert record.title == "A bounded scholarly record"
    assert record.abstract_excerpt == "AI improved worker output."
    assert record.authors == [{"name": "Ada Lovelace"}, {"name": "Katherine Johnson"}]
    assert record.publisher == "Example Journal"
    assert record.provider_metadata["open_access"]["is_oa"] is True
    assert record.provider_metadata["best_oa_location"]["license"] == "cc-by"
    assert record.provider_metadata["abstract_excerpt_truncated"] is False
    assert record.provider_metadata["pmcid"] == "PMC12345"
    assert record.provider_metadata["has_content"] == {"pdf": True, "grobid_xml": True}
    assert "content_urls" not in record.provider_metadata


def test_openalex_preserves_journal_issn_and_exact_author_affiliation_ids():
    data = _work()
    data["primary_location"]["source"] = {
        "display_name": "Journal of Verified Studies",
        "issn": ["1234-5679"],
        "issn_l": "1234-5679",
    }
    data["authorships"][0]["institutions"] = [
        {"id": "https://openalex.org/I123", "ror": "https://ror.org/03yrm5c26"}
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": [data]})
        )
    )
    provider = OpenAlexProvider(client)
    record = provider.search("AI productivity", limit=1)[0]
    provider.close()

    assert record.provider_metadata["journal_issns"] == ["1234-5679"]
    assert record.provider_metadata["institution_ids"] == {
        "openalex": ["I123"],
        "ror": ["https://ror.org/03yrm5c26"],
    }


def test_openalex_preserves_named_affiliations_for_dynamic_organization_discovery():
    data = _work()
    data["authorships"][0]["institutions"] = [
        {
            "id": "https://openalex.org/I123",
            "ror": "https://ror.org/03yrm5c26",
            "display_name": "Unseeded Climate Research Institute",
            "country_code": "IN",
            "type": "facility",
        }
    ]
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": [data]})
        )
    )
    provider = OpenAlexProvider(client)
    record = provider.search("renewable energy policy", limit=1)[0]
    provider.close()

    assert record.provider_metadata["institution_records"] == [
        {
            "openalex_id": "I123",
            "ror_id": "https://ror.org/03yrm5c26",
            "display_name": "Unseeded Climate Research Institute",
            "country_code": "IN",
            "type": "facility",
        }
    ]


def test_openalex_can_find_question_relevant_publications_by_discovered_institution():
    data = _work()
    data["authorships"][0]["institutions"] = [
        {
            "id": "https://openalex.org/I123",
            "ror": "https://ror.org/03yrm5c26",
            "display_name": "Unseeded Climate Research Institute",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/works"
        assert request.url.params["search"] == "renewable energy investment India"
        assert request.url.params["filter"] == "institutions.id:I123"
        assert request.url.params["per_page"] == "3"
        return httpx.Response(200, json={"results": [data]})

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    records = provider.search_for_institution("renewable energy investment India", "I123", limit=20)
    provider.close()

    assert len(records) == 1
    assert records[0].provider_metadata["institution_ids"]["openalex"] == ["I123"]


def test_openalex_resolves_an_exact_verified_ror_id_to_its_institution_id():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "api.openalex.org"
        assert request.url.path == "/institutions/ror:03yrm5c26"
        return httpx.Response(
            200,
            json={
                "id": "https://openalex.org/I123",
                "ror": "https://ror.org/03yrm5c26",
                "display_name": "Unseeded Climate Research Institute",
            },
        )

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    institution_id = provider.resolve_institution_id_by_ror("https://ror.org/03yrm5c26")
    provider.close()

    assert institution_id == "I123"
    assert len(requests) == 1


def test_openalex_ror_resolution_rejects_identity_mismatch_and_invalid_input():
    requests = []
    provider = OpenAlexProvider(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: (
                    requests.append(request)
                    or httpx.Response(
                        200,
                        json={
                            "id": "https://openalex.org/I123",
                            "ror": "https://ror.org/012345678",
                        },
                    )
                )
            )
        )
    )
    with pytest.raises(ValueError, match="ROR identifier"):
        provider.resolve_institution_id_by_ror("https://attacker.example/03yrm5c26")
    with pytest.raises(OpenAlexError, match="identity did not match"):
        provider.resolve_institution_id_by_ror("https://ror.org/03yrm5c26")
    provider.close()

    assert len(requests) == 1


def test_openalex_institution_publication_search_rejects_invalid_id_without_request():
    requests = []
    provider = OpenAlexProvider(
        httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request)))
    )
    with pytest.raises(ValueError, match="institution identifier"):
        provider.search_for_institution("renewable energy", "https://attacker.example/I123")
    provider.close()
    assert requests == []


@pytest.mark.parametrize(
    ("has_content", "expected"),
    [
        ({"pdf": True, "grobid_xml": False}, {"pdf": True, "grobid_xml": False}),
        ({"pdf": True, "grobid_xml": 1}, {"pdf": True}),
        ({"pdf": "true", "grobid_xml": 1}, None),
        ("invalid", None),
    ],
)
def test_openalex_content_availability_accepts_only_explicit_boolean_metadata(
    has_content, expected
):
    data = _work()
    data["has_content"] = has_content
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": [data]})
        )
    )
    provider = OpenAlexProvider(client)
    record = provider.search("bounded query")[0]
    provider.close()

    if expected is None:
        assert "has_content" not in record.provider_metadata
    else:
        assert record.provider_metadata["has_content"] == expected


def _permitted_content_authorization(
    *, license_code="cc-by", reservation=Decimal("0.01"), decision="PERMITTED"
):
    return OpenAlexContentAuthorization(
        rights_decision=decision,
        rights_policy_id="test-cc-by-policy",
        license_code=license_code,
        cost_reserved_usd=reservation,
    )


def test_openalex_tei_download_requires_separate_metered_opt_in_before_request():
    requests = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (requests.append(request), httpx.Response(200))[1]
        )
    )
    provider = OpenAlexProvider(client, api_key="fixture-openalex-key", allow_billable_calls=True)

    with pytest.raises(OpenAlexError) as error:
        provider.download_grobid_tei("W123456789", authorization=_permitted_content_authorization())

    assert error.value.code == "content_download_not_authorized"
    assert requests == []
    provider.close()


@pytest.mark.parametrize(
    ("authorization", "error_code"),
    [
        (
            _permitted_content_authorization(decision="REQUIRES_REVIEW"),
            "content_rights_not_permitted",
        ),
        (_permitted_content_authorization(license_code="unknown"), "content_rights_not_permitted"),
        (
            _permitted_content_authorization(reservation=Decimal("0.009")),
            "content_budget_not_reserved",
        ),
    ],
)
def test_openalex_tei_download_fails_closed_on_rights_or_cost_gate(authorization, error_code):
    requests = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (requests.append(request), httpx.Response(200))[1]
        )
    )
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    with pytest.raises(OpenAlexError) as error:
        provider.download_grobid_tei("W123456789", authorization=authorization)

    assert error.value.code == error_code
    assert requests == []
    provider.close()


def test_openalex_tei_download_uses_fixed_host_validates_xml_and_reports_unknown_cost():
    content = b"<TEI><text><body><div><head>Methods</head></div></body></text></TEI>"
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.host == "content.openalex.org"
        assert request.url.path == "/works/W123456789.grobid-xml"
        assert not request.url.query
        assert request.headers.get("Authorization") == "Bearer fixture-openalex-key"
        return httpx.Response(200, headers={"Content-Type": "application/xml"}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    result = provider.download_grobid_tei(
        "https://openalex.org/W123456789",
        authorization=_permitted_content_authorization(),
    )

    assert result.work_id == "W123456789"
    assert result.content == content
    assert result.content_sha256 == sha256(content).hexdigest()
    assert result.cost_reserved_usd == Decimal("0.01")
    assert result.reported_cost_usd is None
    assert result.reported_cost_status == "unknown"
    assert len(seen) == 1
    provider.close()


@pytest.mark.parametrize(
    ("status", "headers", "body", "error_code"),
    [
        (302, {"Location": "https://127.0.0.1/internal"}, b"", "content_redirect_rejected"),
        (200, {"Content-Type": "text/html"}, b"<html></html>", "content_type_rejected"),
    ],
)
def test_openalex_tei_download_rejects_redirects_and_wrong_mime(status, headers, body, error_code):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, headers=headers, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    with pytest.raises(OpenAlexError) as error:
        provider.download_grobid_tei("W123456789", authorization=_permitted_content_authorization())

    assert error.value.code == error_code
    assert len(calls) == 1
    provider.close()


def test_openalex_tei_download_rejects_oversized_response_without_retry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/xml"},
            content=b"<TEI>" + b"x" * 2_000_001 + b"</TEI>",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    with pytest.raises(OpenAlexError) as error:
        provider.download_grobid_tei("W123456789", authorization=_permitted_content_authorization())

    assert error.value.code == "content_response_too_large"
    assert error.value.request_dispatched is True
    assert error.value.reported_cost_usd is None
    assert error.value.reported_cost_status == "unknown"
    assert len(calls) == 1
    provider.close()


def test_openalex_tei_download_rate_limit_is_recorded_without_retry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "12"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    with pytest.raises(OpenAlexError) as error:
        provider.download_grobid_tei("W123456789", authorization=_permitted_content_authorization())

    assert error.value.code == "provider_rate_limited"
    assert error.value.retry_after_seconds == 12
    assert error.value.request_dispatched is True
    assert error.value.reserved_cost_usd == Decimal("0.01")
    assert error.value.reported_cost_status == "unknown"
    assert len(calls) == 1
    provider.close()


def test_openalex_tei_download_timeout_keeps_cost_unknown_and_error_sanitized():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("fixture transport detail with secret-like marker")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    with pytest.raises(OpenAlexError) as error:
        provider.download_grobid_tei("W123456789", authorization=_permitted_content_authorization())

    assert error.value.code == "content_timeout"
    assert error.value.request_dispatched is True
    assert error.value.reserved_cost_usd == Decimal("0.01")
    assert error.value.reported_cost_usd is None
    assert "fixture transport detail" not in str(error.value)
    assert "fixture-openalex-key" not in str(error.value)
    assert len(calls) == 1
    provider.close()


def test_openalex_tei_result_is_consumable_by_veda_structured_parser():
    from app.research.structured_documents import parse_structured_document

    content = (
        b"<TEI><text><body><div><head>Methods</head>"
        b"<p>Participants were randomly assigned.</p></div></body></text></TEI>"
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, headers={"Content-Type": "application/xml"}, content=content
            )
        )
    )
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    downloaded = provider.download_grobid_tei(
        "W123456789", authorization=_permitted_content_authorization()
    )
    parsed = parse_structured_document(downloaded.content, format_hint="tei")

    assert parsed.content_sha256 == downloaded.content_sha256
    assert parsed.representation_format == "tei"
    assert parsed.sections[0].normalized_type == "methods"
    assert parsed.paragraphs[0].text == "Participants were randomly assigned."
    provider.close()


def test_openalex_tei_download_decodes_provider_gzip_content():
    content = (
        b"<TEI><text><body><div><head>Results</head><p>One result.</p></div></body></text></TEI>"
    )
    compressed = gzip.compress(content)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={
                    "Content-Type": "application/xml",
                    "Content-Encoding": "gzip",
                },
                content=compressed,
            )
        )
    )
    provider = OpenAlexProvider(
        client,
        api_key="fixture-openalex-key",
        allow_billable_calls=True,
        allow_metered_content_downloads=True,
    )

    downloaded = provider.download_grobid_tei(
        "W123456789", authorization=_permitted_content_authorization()
    )

    assert downloaded.content == content
    assert downloaded.content_sha256 == sha256(content).hexdigest()
    provider.close()


def test_openalex_marks_an_abstract_excerpt_truncated_at_provider_limit():
    record_data = _work()
    record_data["abstract_inverted_index"] = {"word": list(range(140))}
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": [record_data]})
        )
    )
    provider = OpenAlexProvider(client)
    record = provider.search("bounded query")[0]
    provider.close()

    # The bounded 560-character slice ends with a separator that is stripped
    # from the stored excerpt, so the persisted text is one character shorter.
    assert len(record.abstract_excerpt or "") == 559
    assert record.provider_metadata["abstract_excerpt_truncated"] is True


def test_openalex_key_requires_explicit_billable_call_opt_in():
    # Use separate transports so the assertion is explicit for each configuration.
    keyless_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, json={"results": []})
                if "Authorization" not in request.headers
                else httpx.Response(400)
            )
        )
    )
    keyless = OpenAlexProvider(keyless_client, api_key="free-key", allow_billable_calls=False)
    assert keyless.search("bounded query") == []
    keyless.close()

    keyed_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, json={"results": []})
                if request.headers.get("Authorization") == "Bearer free-key"
                else httpx.Response(400)
            )
        )
    )
    keyed = OpenAlexProvider(keyed_client, api_key="free-key", allow_billable_calls=True)
    assert keyed.search("bounded query") == []
    keyed.close()


def test_openalex_retries_rate_limit_once(monkeypatch):
    calls = 0
    from app.providers import retry

    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.1"})
        return httpx.Response(200, json={"results": [_work()]})

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(provider.search("bounded query")) == 1
    provider.close()
    assert calls == 2


def test_openalex_retries_one_transient_gateway_failure(monkeypatch):
    calls = 0
    from app.providers import retry

    monkeypatch.setattr(retry.time, "sleep", lambda _: None)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, headers={"Retry-After": "invalid"})
        return httpx.Response(200, json={"results": [_work()]})

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(provider.search("bounded query")) == 1
    provider.close()
    assert calls == 2


def test_openalex_rejects_oversized_response_without_unbounded_buffering():
    provider = OpenAlexProvider(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"x" * (2_000_001))
            )
        )
    )
    with pytest.raises(OpenAlexError, match="2 MB safety limit"):
        provider.search("bounded query")
    provider.close()


def test_openalex_failure_message_does_not_include_provider_body_or_key():
    provider = OpenAlexProvider(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(403, text="private diagnostic payload")
            )
        ),
        api_key="secret-token",
        allow_billable_calls=True,
    )
    with pytest.raises(OpenAlexError) as error:
        provider.search("bounded query")
    provider.close()
    assert "private diagnostic payload" not in str(error.value)
    assert "secret-token" not in str(error.value)


def test_openalex_one_hop_expansion_is_bounded_and_records_both_directions():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "api.openalex.org"
        if request.url.params.get("select") == "id,referenced_works":
            return httpx.Response(
                200,
                json={
                    "meta": {"cost_usd": 0.0001},
                    "results": [
                        {
                            "id": "https://openalex.org/W123456789",
                            "referenced_works": [
                                "https://openalex.org/W200000001",
                                "https://openalex.org/W200000002",
                            ],
                        }
                    ],
                },
            )
        if request.url.params.get("filter", "").startswith("openalex:"):
            ids = request.url.params["filter"].removeprefix("openalex:").split("|")
            return httpx.Response(
                200,
                json={
                    "meta": {"cost_usd": 0.0002},
                    "results": [
                        {**_work(doi=f"https://doi.org/10.5555/ref-{index}"), "id": work_id}
                        for index, work_id in enumerate(ids, start=1)
                    ],
                },
            )
        assert request.url.params["filter"] == "cites:W123456789"
        assert request.url.params["per_page"] == "2"
        return httpx.Response(
            200,
            json={
                "meta": {"count": 3, "cost_usd": 0.0003},
                "results": [
                    {
                        **_work(doi="https://doi.org/10.5555/citing-1"),
                        "id": "https://openalex.org/W300000001",
                    }
                ],
            },
        )

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.expand_citation_neighborhood(
        ["https://openalex.org/W123456789"], limit_per_direction=2
    )
    provider.close()

    assert result.status == "completed"
    assert result.requests_attempted == 3
    assert result.reported_cost_usd == pytest.approx(0.0006)
    assert [candidate.direction for candidate in result.candidates] == [
        "backward",
        "backward",
        "forward",
    ]
    assert result.forward_result_counts["W123456789"] == 3
    assert result.omitted_backward_count == 0
    assert len(calls) == 3
    assert "secret" not in str(result)


def test_openalex_citation_expansion_fails_closed_on_rate_limit_without_retry():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "30"}, text="private response")

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.expand_citation_neighborhood(["W123456789"])
    provider.close()

    assert result.status == "failed"
    assert result.requests_attempted == calls == 1
    assert result.errors == [
        {
            "stage": "work_details",
            "error_code": "provider_rate_limited",
            "retry_after_seconds": 30.0,
        }
    ]
    assert "private response" not in str(result)


def test_openalex_citation_expansion_records_cooldown_and_stops_after_later_rate_limit():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "meta": {"cost_usd": 0.0001},
                    "results": [
                        {
                            "id": "https://openalex.org/W123456789",
                            "referenced_works": ["https://openalex.org/W222222222"],
                        }
                    ],
                },
            )
        return httpx.Response(429, headers={"Retry-After": "45"}, text="private response")

    provider = OpenAlexProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.expand_citation_neighborhood(["W123456789"])
    provider.close()

    assert result.status == "failed"
    assert result.requests_attempted == len(calls) == 2
    assert result.errors == [
        {
            "stage": "backward_references",
            "error_code": "provider_rate_limited",
            "retry_after_seconds": 45.0,
        }
    ]
    assert "private response" not in str(result)
