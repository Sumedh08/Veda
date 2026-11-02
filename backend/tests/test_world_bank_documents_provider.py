import httpx
import pytest

from app.providers.world_bank_documents import (
    WorldBankDocumentsError,
    WorldBankDocumentsProvider,
)


def _payload():
    return {
        "rows": 1,
        "os": 0,
        "page": 1,
        "total": 1,
        "documents": {
            "D31534595": {
                "id": "31534595",
                "repnb": "WPS1234",
                "docdt": "2025-02-03T04:00:00Z",
                "docty": "Policy Research Working Paper",
                "display_title": "Artificial Intelligence and Productivity in Emerging Economies",
                "abstracts": {
                    "cdata!": "A transparent study of AI adoption and measured productivity."
                },
                "url": "http://documents.worldbank.org/curated/en/617511573040599056",
                "pdfurl": "http://documents1.worldbank.org/curated/en/617511573040599056/pdf/report.pdf",
                "authr": "Research Department",
            }
        },
    }


def test_world_bank_documents_search_maps_official_metadata_without_fetching_pdf():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "search.worldbank.org"
        assert request.url.path == "/api/v3/wds"
        assert request.url.params["format"] == "json"
        assert request.url.params["qterm"] == "AI productivity"
        assert request.url.params["rows"] == "3"
        assert "pdfurl" in request.url.params["fl"]
        return httpx.Response(200, json=_payload())

    provider = WorldBankDocumentsProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    records = provider.search("AI productivity", limit=3)
    provider.close()

    assert len(requests) == 1
    assert len(records) == 1
    record = records[0]
    assert record.external_id == "worldbank:31534595"
    assert record.provider == "World Bank Documents & Reports"
    assert record.source_type == "institutional_report"
    assert record.publisher == "World Bank Group"
    assert record.published_year == 2025
    assert (
        record.abstract_excerpt == "A transparent study of AI adoption and measured productivity."
    )
    assert record.url == "https://documents.worldbank.org/curated/en/617511573040599056"
    assert record.provider_metadata["document_type"] == "Policy Research Working Paper"
    assert record.provider_metadata["official_pdf_url"] == (
        "https://documents1.worldbank.org/curated/en/617511573040599056/pdf/report.pdf"
    )
    assert record.provider_metadata["full_text_retrieved"] is False
    assert record.provider_metadata["metadata_reuse_rights_status"] == "not_assessed"
    assert not any("/pdf/" in request.url.path for request in requests)


def test_world_bank_documents_caps_requests_and_rejects_invalid_query_before_dispatch():
    requests = []
    provider = WorldBankDocumentsProvider(
        httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request)))
    )
    with pytest.raises(WorldBankDocumentsError) as error:
        provider.search(" \n " + "x" * 501, limit=100)
    provider.close()
    assert error.value.code == "invalid_query"
    assert requests == []


def test_world_bank_documents_does_not_follow_redirects_or_retry_rate_limits():
    for response, expected in (
        (
            httpx.Response(302, headers={"Location": "https://internal.example/"}),
            "redirect_rejected",
        ),
        (httpx.Response(429, headers={"Retry-After": "20"}), "rate_limited"),
    ):
        requests = []

        def handler(request, response=response, seen=requests):
            seen.append(request)
            return response

        provider = WorldBankDocumentsProvider(httpx.Client(transport=httpx.MockTransport(handler)))
        with pytest.raises(WorldBankDocumentsError) as error:
            provider.search("AI productivity", limit=2)
        provider.close()
        assert error.value.code == expected
        assert len(requests) == 1


def test_world_bank_documents_rejects_malformed_oversized_and_wrong_origin_payloads():
    for response, expected in (
        (httpx.Response(200, content=b"not json"), "invalid_response"),
        (httpx.Response(200, content=b"{" + b" " * 600_000 + b"}"), "too_large"),
    ):
        provider = WorldBankDocumentsProvider(
            httpx.Client(
                transport=httpx.MockTransport(lambda _request, response=response: response)
            )
        )
        with pytest.raises(WorldBankDocumentsError) as error:
            provider.search("AI productivity", limit=2)
        provider.close()
        assert error.value.code == expected

    invalid = _payload()
    invalid["documents"]["D31534595"]["url"] = "https://evil.example/report"
    provider = WorldBankDocumentsProvider(
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=invalid))
        )
    )
    records = provider.search("AI productivity", limit=1)
    provider.close()
    assert records[0].url is None


def test_world_bank_documents_truncates_abstract_with_provenance_flag():
    payload = _payload()
    payload["documents"]["D31534595"]["abstracts"] = {"cdata!": "evidence " * 200}
    provider = WorldBankDocumentsProvider(
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        )
    )
    record = provider.search("AI productivity", limit=1)[0]
    provider.close()
    assert len(record.abstract_excerpt) == 600
    assert record.provider_metadata["abstract_excerpt_truncated"] is True
