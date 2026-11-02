import httpx

from app.providers.europe_pmc import EuropePMCProvider

VALID_XML = b"<article><body><sec><title>Methods</title><p>We randomized 42 participants.</p></sec></body></article>"


def _response(payload, *, status_code=200, headers=None):
    return httpx.Response(status_code, json=payload, headers=headers)


def test_europe_pmc_resolves_and_fetches_only_licensed_matching_jats():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/search"):
            return _response(
                {
                    "resultList": {
                        "result": [
                            {
                                "pmcid": "PMC12345",
                                "doi": "10.5555/example",
                                "isOpenAccess": "Y",
                                "license": "CC BY",
                                "title": "Trial",
                            }
                        ]
                    }
                }
            )
        return httpx.Response(200, content=VALID_XML, headers={"content-type": "application/xml"})

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resolution = provider.resolve_full_text("PMC12345", expected_doi="10.5555/example")

    assert resolution.status == "retrieved"
    assert resolution.metadata.license_code == "cc-by"
    assert resolution.content == VALID_XML
    assert [request.url.path.rsplit("/", 1)[-1] for request in requests] == [
        "search",
        "fullTextXML",
    ]
    assert requests[0].url.params["query"] == "PMCID:PMC12345"


def test_europe_pmc_resolves_by_doi_when_pmcid_is_missing():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/search"):
            return _response(
                {
                    "resultList": {
                        "result": [
                            {
                                "pmcid": "PMC12345",
                                "doi": "10.5555/example",
                                "isOpenAccess": "Y",
                                "license": "CC BY",
                                "title": "Trial",
                            }
                        ]
                    }
                }
            )
        return httpx.Response(200, content=VALID_XML, headers={"content-type": "application/xml"})

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resolution = provider.resolve_full_text(None, expected_doi="https://doi.org/10.5555/example")

    assert resolution.status == "retrieved"
    assert resolution.metadata.pmcid == "PMC12345"
    assert resolution.requests_attempted == 2
    assert requests[0].url.params["query"] == "DOI:10.5555/example"
    assert requests[1].url.path.endswith("/PMC12345/fullTextXML")


def test_invalid_doi_lookup_is_rejected_before_network_request():
    requests = []
    provider = EuropePMCProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request)))
    )

    resolution = provider.resolve_full_text(None, expected_doi='10.5555/example" OR *:*')

    assert resolution.status == "failed"
    assert resolution.reason_code == "invalid_doi"
    assert resolution.requests_attempted == 0
    assert requests == []


def test_unknown_license_denies_content_request():
    requests = []

    def handler(request):
        requests.append(request)
        return _response(
            {
                "resultList": {
                    "result": [
                        {
                            "pmcid": "PMC12345",
                            "isOpenAccess": "Y",
                            "license": "",
                        }
                    ]
                }
            }
        )

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resolution = provider.resolve_full_text("PMC12345")

    assert resolution.status == "denied"
    assert resolution.reason_code == "license_not_permitted"
    assert len(requests) == 1


def test_doi_mismatch_denies_full_text_and_pmcid_is_validated():
    requests = []

    def handler(request):
        requests.append(request)
        return _response(
            {
                "resultList": {
                    "result": [
                        {
                            "pmcid": "PMC12345",
                            "doi": "10.5555/different",
                            "isOpenAccess": "Y",
                            "license": "CC0",
                        }
                    ]
                }
            }
        )

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    mismatch = provider.resolve_full_text("PMC12345", expected_doi="10.5555/expected")

    assert mismatch.status == "denied"
    assert mismatch.reason_code == "work_identity_mismatch"
    assert len(requests) == 1

    invalid = provider.resolve_full_text("PMC12345?redirect=https://127.0.0.1")
    assert invalid.status == "failed"
    assert invalid.reason_code == "invalid_pmcid"
    assert len(requests) == 1


def test_expected_doi_is_required_to_match_metadata_before_full_text_fetch():
    requests = []

    def handler(request):
        requests.append(request)
        return _response(
            {
                "resultList": {
                    "result": [
                        {
                            "pmcid": "PMC12345",
                            "isOpenAccess": "Y",
                            "license": "CC BY",
                        }
                    ]
                }
            }
        )

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.resolve_full_text("PMC12345", expected_doi="10.5555/expected")

    assert result.status == "denied"
    assert result.reason_code == "work_identity_mismatch"
    assert len(requests) == 1


def test_unexpected_full_text_content_type_is_rejected_without_partial_success():
    def handler(request):
        if request.url.path.endswith("/search"):
            return _response(
                {
                    "resultList": {
                        "result": [
                            {
                                "pmcid": "PMC12345",
                                "isOpenAccess": "Y",
                                "license": "CC0",
                            }
                        ]
                    }
                }
            )
        return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resolution = provider.resolve_full_text("PMC12345")

    assert resolution.status == "failed"
    assert resolution.reason_code == "unexpected_full_text_content_type"
    assert resolution.content is None


def test_http_429_is_reported_as_deferred_without_automatic_retry():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "30"})

    provider = EuropePMCProvider(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resolution = provider.resolve_full_text("PMC12345")

    assert resolution.status == "deferred"
    assert resolution.reason_code == "rate_limited"
    assert resolution.retry_after_seconds == 30
    assert len(requests) == 1
