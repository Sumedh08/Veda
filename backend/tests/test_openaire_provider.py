import httpx
import pytest

from app.providers.metadata import versioned_provider_metadata
from app.providers.openaire import (
    OpenAIREError,
    OpenAIREProvider,
    exact_repository_instances,
)


def _response():
    return {
        "header": {"numFound": 1, "page": 1, "pageSize": 1},
        "results": [
            {
                "id": "doi_________::example-product-1",
                "mainTitle": "Evidence on AI-assisted software development productivity",
                "subTitle": None,
                "publicationDate": "2025-07-12",
                "publisher": "Example University Repository",
                "descriptions": [
                    "<jats:p>Developers completed tasks faster in the field study.</jats:p>"
                ],
                "pids": [{"scheme": "doi", "value": "10.5555/example.1"}],
                "instances": [
                    {
                        "type": "Article",
                        "urls": ["https://repository.example/papers/example.1"],
                        "accessRight": {"code": "c_abf2", "label": "OPEN"},
                    }
                ],
                "organizations": [
                    {
                        "id": "openorgs____::institution-123",
                        "legalName": "Unseeded Software Research Institute",
                        "acronym": "USRI",
                        "websiteurl": "https://usri.example",
                        "pids": [{"scheme": "ROR", "value": "https://ror.org/03yrm5c26"}],
                        "countries": [{"code": "IN", "label": "India"}],
                    }
                ],
                "sources": ["OpenAIRE", "Example Repository"],
            }
        ],
    }


def test_openaire_search_maps_a_real_product_and_its_ror_affiliation_without_following_content():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "api.openaire.eu"
        assert request.url.path == "/graph/v4/research-products"
        assert request.url.params["search"] == "AI developer productivity"
        assert request.url.params["filter"] == "type:publication"
        assert request.url.params["page_size"] == "4"
        return httpx.Response(200, json=_response())

    provider = OpenAIREProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    works = provider.search("AI developer productivity", limit=4)
    provider.close()

    assert len(requests) == 1
    assert len(works) == 1
    work = works[0]
    assert work.external_id == "doi:10.5555/example.1"
    assert work.provider == "OpenAIRE"
    assert work.abstract_excerpt == "Developers completed tasks faster in the field study."
    metadata = versioned_provider_metadata(work.provider, work.provider_metadata)
    assert metadata["openaire_id"] == "doi_________::example-product-1"
    assert metadata["organization_records"] == [
        {
            "openaire_id": "openorgs____::institution-123",
            "ror_id": "https://ror.org/03yrm5c26",
            "display_name": "Unseeded Software Research Institute",
            "website_url": "https://usri.example",
            "country_code": "IN",
            "type": "openaire_affiliation",
        }
    ]
    assert metadata["metadata_license"] == "CC-BY"
    assert not any("pdf" in request.url.path.casefold() for request in requests)


def test_openaire_preserves_institutional_report_document_type():
    payload = _response()
    payload["results"][0]["pids"] = []
    payload["results"][0]["instances"][0]["type"] = "Technical Report"
    provider = OpenAIREProvider(
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        )
    )

    work = provider.search("institutional report topic", limit=1)[0]

    assert work.doi is None
    assert work.source_type == "institutional_report"
    assert work.provider_metadata["instance_types"] == ["Technical Report"]


def test_openaire_retains_only_explicitly_licensed_repository_instances():
    payload = _response()
    payload["results"][0]["mainTitle"] = (
        "Hybrid, Multi-Megawatt HVDC Transformer Topology Comparison for Future Offshore Wind Farms"
    )
    payload["results"][0]["pids"] = [{"scheme": "doi", "value": "10.3390/en10070851"}]
    payload["results"][0]["instances"] = [
        {
            "type": "Article",
            "urls": [
                "https://strathprints.strath.ac.uk/61241/1/article.pdf",
                "http://insecure.example/article.pdf",
            ],
            "accessRight": {"code": "OPEN", "label": "OPEN"},
            "license": {
                "code": "CC-BY-4.0",
                "url": "https://creativecommons.org/licenses/by/4.0/",
            },
            "contentVersion": "publishedVersion",
            "hostedby": {"name": "Strathprints", "url": "https://strathprints.strath.ac.uk"},
        },
        {
            "type": "Article",
            "urls": ["https://unknown.example/article.pdf"],
            "accessRight": {"code": "OPEN", "label": "OPEN"},
        },
        {
            "type": "Article",
            "urls": ["https://restricted.example/article.pdf"],
            "license": {"code": "CC-BY-NC-ND-4.0"},
        },
    ]
    provider = OpenAIREProvider(
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        )
    )
    try:
        work = provider.search("HVDC transformer topology", limit=1)[0]
    finally:
        provider.close()

    repository_instances = work.provider_metadata["repository_instances"]
    assert repository_instances == [
        {
            "url": "https://strathprints.strath.ac.uk/61241/1/article.pdf",
            "license_code": "cc-by",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "content_version": "publishedVersion",
            "instance_type": "Article",
            "access_right": "OPEN",
            "repository_name": "Strathprints",
            "repository_url": "https://strathprints.strath.ac.uk",
        }
    ]
    validated = versioned_provider_metadata("OpenAIRE", work.provider_metadata)
    assert validated["repository_instances"] == repository_instances
    assert (
        exact_repository_instances(
            [work],
            doi="10.3390/en10070851",
            title="Hybrid, Multi-Megawatt HVDC Transformer Topology Comparison for Future Offshore Wind Farms",
            license_code="cc-by",
        )
        == repository_instances
    )
    assert (
        exact_repository_instances(
            [work], doi="10.5555/wrong", title=work.title, license_code="cc-by"
        )
        == []
    )
    assert (
        exact_repository_instances(
            [work], doi=work.doi, title="A different title", license_code="cc-by"
        )
        == []
    )


def test_openaire_rejects_conflicting_license_code_and_license_url():
    payload = _response()
    payload["results"][0]["instances"] = [
        {
            "type": "Article",
            "urls": ["https://strathprints.strath.ac.uk/61241/1/article.pdf"],
            "license": {
                "code": "CC-BY-4.0",
                "url": "https://creativecommons.org/licenses/by-nc-nd/4.0/",
            },
        }
    ]
    provider = OpenAIREProvider(
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        )
    )
    try:
        work = provider.search("AI developer productivity", limit=1)[0]
    finally:
        provider.close()

    assert work.provider_metadata["repository_instances"] == []


def test_openaire_search_caps_result_count_and_rejects_unsafe_query_before_dispatch():
    requests = []
    provider = OpenAIREProvider(
        httpx.Client(transport=httpx.MockTransport(lambda request: requests.append(request)))
    )
    with pytest.raises(OpenAIREError) as error:
        provider.search(" \n " + "x" * 501, limit=100)
    provider.close()
    assert error.value.code == "invalid_query"
    assert requests == []


def test_openaire_search_caps_requested_and_returned_publication_count():
    requests = []
    payload = _response()
    template = payload["results"][0]
    payload["results"] = [
        {
            **template,
            "id": f"doi_________::example-product-{index}",
            "mainTitle": f"Evidence on software productivity, study {index}",
            "pids": [{"scheme": "doi", "value": f"10.5555/example.{index}"}],
        }
        for index in range(15)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["page_size"] == "10"
        return httpx.Response(200, json=payload)

    provider = OpenAIREProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    works = provider.search("software productivity", limit=100)
    provider.close()

    assert len(requests) == 1
    assert len(works) == 10


def test_openaire_long_abstract_is_capped_to_veda_work_schema_and_marked_truncated():
    payload = _response()
    payload["results"][0]["descriptions"] = [f"<p>{'evidence ' * 200}</p>"]
    provider = OpenAIREProvider(
        httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        )
    )
    work = provider.search("AI developer productivity", limit=1)[0]
    provider.close()

    assert len(work.abstract_excerpt or "") == 600
    assert work.provider_metadata["abstract_excerpt_truncated"] is True
    versioned_provider_metadata(work.provider, work.provider_metadata)


def test_openaire_rate_limit_is_not_retried():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "30"})

    provider = OpenAIREProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OpenAIREError) as error:
        provider.search("software productivity", limit=2)
    provider.close()
    assert error.value.code == "rate_limited"
    assert error.value.retry_after_seconds == 30
    assert error.value.http_status == 429
    assert len(requests) == 1


def test_openaire_rejected_request_preserves_http_status_without_response_body():
    provider = OpenAIREProvider(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(400, content=b"private provider details")
            )
        )
    )
    with pytest.raises(OpenAIREError) as error:
        provider.search("a bounded publication title", limit=2)
    provider.close()

    assert error.value.code == "provider_rejected_request"
    assert error.value.http_status == 400
    assert "private provider details" not in str(error.value)


def test_openaire_redirect_is_rejected_without_following_it():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://internal.example/"})

    provider = OpenAIREProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(OpenAIREError) as error:
        provider.search("software productivity", limit=2)
    provider.close()
    assert error.value.code == "redirect_rejected"
    assert len(requests) == 1


def test_openaire_malformed_or_oversized_responses_fail_closed():
    for response, expected in (
        (httpx.Response(200, content=b"not json"), "invalid_response"),
        (httpx.Response(200, content=b"{" + b" " * 2_100_000 + b"}"), "too_large"),
    ):
        provider = OpenAIREProvider(
            httpx.Client(
                transport=httpx.MockTransport(lambda _request, response=response: response)
            )
        )
        with pytest.raises(OpenAIREError) as error:
            provider.search("software productivity", limit=2)
        provider.close()
        assert error.value.code == expected


def test_openaire_can_discover_organizations_and_their_publications_from_topic_content():
    requests = []
    organization_payload = {
        "header": {"numFound": 1, "page": 1, "pageSize": 1},
        "results": [
            {
                "id": "pending_org_::specialist-123",
                "legalName": "Unseeded Offshore Energy Institute",
                "legalShortName": "UOEI",
                "websiteurl": "https://uoei.example.org",
                "pids": [],
                "countries": [{"code": "GB", "label": "United Kingdom"}],
                "type": "nonprofit",
            }
        ],
    }
    publication_payload = _response()
    publication_payload["results"][0]["organizations"] = [
        {
            "id": "pending_org_::specialist-123",
            "legalName": "Unseeded Offshore Energy Institute",
            "pids": [],
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/graph/v3/organizations":
            assert request.url.params["search"] == ('"offshore" AND "wind" AND "research"')
            assert request.url.params["pageSize"] == "4"
            return httpx.Response(200, json=organization_payload)
        assert request.url.path == "/graph/v3/research-products"
        assert request.url.params["relOrganizationId"] == "pending_org_::specialist-123"
        assert request.url.params["type"] == "publication"
        assert request.url.params["pageSize"] == "3"
        return httpx.Response(200, json=publication_payload)

    provider = OpenAIREProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    organizations = provider.search_organizations('"offshore" AND "wind" AND "research"', limit=4)
    works = provider.search_organization_publications(
        ["pending_org_::specialist-123"],
        query="offshore wind grid reliability",
        limit=3,
    )
    provider.close()

    assert [item["canonical_name"] for item in organizations] == [
        "Unseeded Offshore Energy Institute"
    ]
    assert organizations[0]["openaire_id"] == "pending_org_::specialist-123"
    assert organizations[0]["ror_id"] is None
    assert len(works) == 1
    assert works[0].doi == "10.5555/example.1"
    assert len(requests) == 2
