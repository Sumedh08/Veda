import httpx
import pytest

from app.providers.ror import RORProvider, RORProviderError


def _ror_record():
    return {
        "id": "https://ror.org/03yrm5c26",
        "names": [
            {"value": "Unseeded Climate Research Institute", "types": ["ror_display", "label"]},
            {"value": "UCRI", "types": ["acronym"]},
        ],
        "types": ["education", "nonprofit"],
        "domains": ["ucri.example"],
        "links": [
            {"type": "website", "value": "https://ucri.example/about"},
            {"type": "website", "value": "http://insecure.example"},
            {"type": "wikipedia", "value": "https://en.wikipedia.org/wiki/UCRI"},
        ],
        "locations": [{"geonames_details": {"country_code": "IN"}}],
        "status": "active",
        "admin": {"last_modified": {"date": "2026-10-20"}},
    }


def test_ror_provider_verifies_exact_identity_and_returns_domains_without_quality_claim():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.ror.org"
        assert request.url.path == "/v2/organizations/03yrm5c26"
        return httpx.Response(200, json=_ror_record())

    provider = RORProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    organization = provider.verify("https://ror.org/03yrm5c26")
    provider.close()

    assert organization.canonical_name == "Unseeded Climate Research Institute"
    assert organization.aliases == ("UCRI",)
    assert organization.organization_types == ("education", "nonprofit")
    assert organization.domains == ("ucri.example",)
    assert organization.official_urls == ("https://ucri.example/about",)
    assert organization.country_code == "IN"
    assert organization.record_status == "active"
    assert organization.last_modified == "2026-10-20"
    assert organization.retrieved_at[:10] != organization.last_modified


def test_ror_provider_rejects_mismatched_identity_and_redirect():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            payload = _ror_record()
            payload["id"] = "https://ror.org/00tjv0s33"
            return httpx.Response(200, json=payload)
        return httpx.Response(302, headers={"Location": "https://attacker.example/record"})

    provider = RORProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(RORProviderError, match="did not match"):
        provider.verify("03yrm5c26")
    with pytest.raises(RORProviderError, match="redirect"):
        provider.verify("03yrm5c26")
    provider.close()
    assert calls == 2


def test_ror_provider_rejects_invalid_identifier_without_network_request():
    calls = []
    provider = RORProvider(
        httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request)))
    )
    with pytest.raises(RORProviderError) as error:
        provider.verify("https://attacker.example/03yrm5c26")
    provider.close()
    assert error.value.code == "invalid_ror_id"
    assert calls == []


def test_ror_search_returns_only_one_exact_canonical_name_match():
    requests = []
    payload = {
        "number_of_results": 2,
        "items": [
            _ror_record(),
            {
                **_ror_record(),
                "id": "https://ror.org/00tjv0s33",
                "names": [{"value": "Climate Institute", "types": ["ror_display"]}],
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/v2/organizations"
        assert request.url.params["query"] == "Unseeded Climate Research Institute"
        assert request.url.params["page"] == "1"
        assert "page_size" not in request.url.params
        return httpx.Response(200, json=payload)

    provider = RORProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    ror_id = provider.search_exact_id("Unseeded Climate Research Institute")
    provider.close()
    assert ror_id == "https://ror.org/03yrm5c26"
    assert len(requests) == 1


def test_ror_search_does_not_resolve_partial_name_or_choose_between_duplicate_exact_names():
    payloads = [
        {"items": [{**_ror_record(), "names": [{"value": "Climate Institute"}]}]},
        {
            "items": [
                _ror_record(),
                {**_ror_record(), "id": "https://ror.org/00tjv0s33"},
            ]
        },
    ]
    provider = RORProvider(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json=payloads.pop(0))
            )
        )
    )
    assert provider.search_exact_id("Unseeded Climate Research Institute") is None
    with pytest.raises(RORProviderError) as ambiguous:
        provider.search_exact_id("Unseeded Climate Research Institute")
    provider.close()
    assert ambiguous.value.code == "ambiguous_identity"


def test_ror_search_resolves_only_an_exact_verified_domain_match():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["query.advanced"] == (
            '(domains:"ucri.example" OR links.value:"ucri.example")'
        )
        payload = {
            "items": [
                _ror_record(),
                {
                    **_ror_record(),
                    "id": "https://ror.org/00tjv0s33",
                    "domains": ["other.example"],
                    "links": [{"type": "website", "value": "https://other.example/about"}],
                },
            ]
        }
        return httpx.Response(200, json=payload)

    provider = RORProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    ror_id = provider.search_exact_domain("www.ucri.example")
    provider.close()

    assert ror_id == "https://ror.org/03yrm5c26"
    assert len(requests) == 1


def test_ror_search_can_match_official_website_when_domains_field_is_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        **_ror_record(),
                        "domains": [],
                        "links": [
                            {
                                "type": "website",
                                "value": "https://www.ucri.example/",
                            }
                        ],
                    }
                ]
            },
        )

    provider = RORProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    ror_id = provider.search_exact_domain("ucri.example")
    provider.close()

    assert ror_id == "https://ror.org/03yrm5c26"


def test_ror_domain_lookup_does_not_treat_non_website_links_as_official_domains():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        **_ror_record(),
                        "domains": [],
                        "links": [
                            {
                                "type": "wikipedia",
                                "value": "https://ucri.example/",
                            }
                        ],
                    }
                ]
            },
        )

    provider = RORProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    ror_id = provider.search_exact_domain("ucri.example")
    provider.close()

    assert ror_id is None


def test_ror_domain_search_rejects_ambiguous_or_untrusted_domains():
    provider = RORProvider(
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "items": [
                            _ror_record(),
                            {**_ror_record(), "id": "https://ror.org/00tjv0s33"},
                        ]
                    },
                )
            )
        )
    )
    with pytest.raises(RORProviderError) as ambiguous:
        provider.search_exact_domain("ucri.example")
    with pytest.raises(RORProviderError) as invalid:
        provider.search_exact_domain("https://ucri.example")
    provider.close()

    assert ambiguous.value.code == "ambiguous_domain"
    assert invalid.value.code == "invalid_domain"


def test_ror_provider_classifies_missing_and_rate_limited_responses():
    statuses = iter([404, 429])
    provider = RORProvider(
        httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(next(statuses))))
    )
    with pytest.raises(RORProviderError) as missing:
        provider.verify("03yrm5c26")
    with pytest.raises(RORProviderError) as limited:
        provider.verify("03yrm5c26")
    provider.close()
    assert missing.value.code == "identity_not_found"
    assert limited.value.code == "rate_limited"
