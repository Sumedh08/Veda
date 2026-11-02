import httpx
import pytest

from app.providers.govuk_search import (
    API_URL,
    MAX_RESPONSE_BYTES,
    GovUKSearchError,
    GovUKSearchProvider,
    build_govuk_search_query,
    supports_uk_geography,
)


def _result(**overrides):
    value = {
        "title": "Clean Energy Industries Sector Plan",
        "link": "https://www.gov.uk/government/publications/clean-energy-industries-sector-plan",
        "public_timestamp": "2025-06-20T09:30:00.000+01:00",
        "format": "policy_paper",
        "organisations": [
            {
                "title": "Department for Energy Security and Net Zero",
                "slug": "department-for-energy-security-and-net-zero",
                "link": "/government/organisations/department-for-energy-security-and-net-zero",
                "content_id": "11111111-1111-4111-8111-111111111111",
                "organisation_type": "ministerial_department",
                "organisation_state": "live",
            },
            {
                "title": "Department for Business and Trade",
                "slug": "department-for-business-and-trade",
                "link": "/government/organisations/department-for-business-and-trade",
                "content_id": "22222222-2222-4222-8222-222222222222",
                "organisation_type": "ministerial_department",
                "organisation_state": "live",
            },
        ],
        "description": "Must not be retained as an abstract.",
    }
    value.update(overrides)
    return value


def _provider(handler, calls):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=False)
    provider = GovUKSearchProvider(client=client)
    calls.append(client)
    return provider


def test_govuk_query_keeps_research_topic_and_drops_jurisdiction_boilerplate():
    assert (
        build_govuk_search_query(
            "How do UK government policies affect renewable energy deployment and battery storage investment?"
        )
        == "renewable energy deployment battery storage investment"
    )


def test_govuk_query_is_bounded_and_does_not_invent_terms():
    assert build_govuk_search_query("UK government renewable energy") == "renewable energy"
    assert len(build_govuk_search_query("renewable " * 200)) <= 240


def test_govuk_requires_explicit_uk_geography_before_request():
    calls = []
    provider = _provider(lambda _request: pytest.fail("unexpected request"), calls)
    try:
        with pytest.raises(GovUKSearchError, match="explicit UK geography") as error:
            provider.search("renewable energy policy", geography="India")
        assert error.value.code == "unsupported_geography"
        assert not error.value.request_dispatched
    finally:
        provider.close()
        calls[0].close()


@pytest.mark.parametrize(
    "geography", ["UK", "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland"]
)
def test_govuk_geography_requires_an_exact_supported_scope(geography):
    assert supports_uk_geography(geography)
    assert not supports_uk_geography("Ukraine")
    assert not supports_uk_geography(None)


def test_govuk_search_returns_only_verified_policy_paper_metadata():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [_result()]})

    provider = _provider(handler, [])
    try:
        records = provider.search(
            "renewable energy investment", geography="United Kingdom", limit=80
        )
    finally:
        provider.close()
    request = calls[0]
    assert str(request.url).startswith(API_URL)
    assert request.url.params["count"] == "10"
    assert request.url.params["filter_format"] == "policy_paper"
    assert request.url.params.get_list("fields") == [
        "title",
        "link",
        "public_timestamp",
        "organisations",
        "format",
        "description",
    ]
    assert len(records) == 1
    record = records[0]
    assert (
        record.external_id == "govuk:/government/publications/clean-energy-industries-sector-plan"
    )
    assert record.source_type == "institutional_report"
    assert record.published_year == 2025
    assert (
        record.publisher
        == "Department for Energy Security and Net Zero; Department for Business and Trade"
    )
    assert record.abstract_excerpt is None
    assert (
        record.provider_metadata["selection_description"] == "Must not be retained as an abstract."
    )
    assert record.provider_metadata["full_text_retrieved"] is False
    assert record.provider_metadata["api_support_status"] == "unsupported_best_effort"
    assert record.provider_metadata["publishing_organization_candidates"] == [
        {
            "slug": "department-for-energy-security-and-net-zero",
            "canonical_name": "Department for Energy Security and Net Zero",
            "content_id": "11111111-1111-4111-8111-111111111111",
            "organization_type": "ministerial_department",
            "directory_status": "live",
            "official_url": "https://www.gov.uk/government/organisations/department-for-energy-security-and-net-zero",
        },
        {
            "slug": "department-for-business-and-trade",
            "canonical_name": "Department for Business and Trade",
            "content_id": "22222222-2222-4222-8222-222222222222",
            "organization_type": "ministerial_department",
            "directory_status": "live",
            "official_url": "https://www.gov.uk/government/organisations/department-for-business-and-trade",
        },
    ]
    assert "abstract_excerpt" not in record.provider_metadata


def test_govuk_organization_is_verified_against_exact_official_slug_and_identity():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "title": "Department for Energy Security and Net Zero",
                "format": "Ministerial department",
                "details": {
                    "slug": "department-for-energy-security-and-net-zero",
                    "govuk_status": "live",
                    "content_id": "11111111-1111-4111-8111-111111111111",
                    "closed_at": None,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = GovUKSearchProvider(client=client)
    try:
        identity = provider.verify_organization(
            "department-for-energy-security-and-net-zero",
            expected_name="Department for Energy Security and Net Zero",
            expected_content_id="11111111-1111-4111-8111-111111111111",
        )
    finally:
        provider.close()
        client.close()

    assert len(calls) == 1
    assert calls[0].url.path == ("/api/organisations/department-for-energy-security-and-net-zero")
    assert identity["organization_id"] == "govuk:department-for-energy-security-and-net-zero"
    assert identity["identity_status"] == "VERIFIED_ESTABLISHED"
    assert identity["verification_method"] == "govuk_organizations_api_exact_slug"
    assert identity["official_url"] == (
        "https://www.gov.uk/government/organisations/department-for-energy-security-and-net-zero"
    )
    assert identity["quality_assessment"] == "not_assessed"


def test_govuk_organization_name_or_content_id_mismatch_is_not_verified():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "title": "A different department",
                    "format": "Ministerial department",
                    "details": {
                        "slug": "department-for-energy-security-and-net-zero",
                        "govuk_status": "live",
                        "content_id": "11111111-1111-4111-8111-111111111111",
                        "closed_at": None,
                    },
                },
            )
        ),
        follow_redirects=False,
    )
    provider = GovUKSearchProvider(client=client)
    try:
        identity = provider.verify_organization(
            "department-for-energy-security-and-net-zero",
            expected_name="Department for Energy Security and Net Zero",
            expected_content_id="33333333-3333-4333-8333-333333333333",
        )
    finally:
        provider.close()
        client.close()

    assert identity["identity_status"] == "PENDING_VERIFICATION"
    assert identity["limitations"]


@pytest.mark.parametrize(
    ("directory_status", "closed_at"),
    [("closed", "2024-01-01T00:00:00Z"), ("live", "2024-01-01T00:00:00Z")],
)
def test_govuk_closed_organization_is_not_verified(directory_status, closed_at):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "title": "Department for Energy Security and Net Zero",
                    "format": "Ministerial department",
                    "details": {
                        "slug": "department-for-energy-security-and-net-zero",
                        "govuk_status": directory_status,
                        "content_id": "11111111-1111-4111-8111-111111111111",
                        "closed_at": closed_at,
                    },
                },
            )
        ),
        follow_redirects=False,
    )
    provider = GovUKSearchProvider(client=client)
    try:
        identity = provider.verify_organization(
            "department-for-energy-security-and-net-zero",
            expected_name="Department for Energy Security and Net Zero",
            expected_content_id="11111111-1111-4111-8111-111111111111",
        )
    finally:
        provider.close()
        client.close()

    assert identity["identity_status"] == "PENDING_VERIFICATION"
    assert identity["directory_status"] == directory_status
    assert any("not live" in limitation for limitation in identity["limitations"])


def test_govuk_directory_response_for_a_different_slug_is_rejected():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "title": "Department for Energy Security and Net Zero",
                    "format": "Ministerial department",
                    "details": {
                        "slug": "department-for-business-and-trade",
                        "govuk_status": "live",
                        "content_id": "11111111-1111-4111-8111-111111111111",
                        "closed_at": None,
                    },
                },
            )
        ),
        follow_redirects=False,
    )
    provider = GovUKSearchProvider(client=client)
    try:
        with pytest.raises(GovUKSearchError) as error:
            provider.verify_organization(
                "department-for-energy-security-and-net-zero",
                expected_name="Department for Energy Security and Net Zero",
                expected_content_id="11111111-1111-4111-8111-111111111111",
            )
    finally:
        provider.close()
        client.close()

    assert error.value.code == "invalid_response"
    assert error.value.request_dispatched


def test_govuk_search_resolves_relative_publication_paths_against_fixed_origin():
    item = _result(link="/government/publications/clean-energy-industries-sector-plan")
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": [item]})
        )
    )
    provider = GovUKSearchProvider(client=client)
    try:
        record = provider.search("clean energy industries", geography="UK")[0]
    finally:
        provider.close()
        client.close()

    assert (
        record.url
        == "https://www.gov.uk/government/publications/clean-energy-industries-sector-plan"
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"format": "news_story"},
        {"link": "https://not-gov.uk/government/publications/wrong-host"},
        {"link": "//attacker.example/government/publications/wrong-host"},
        {"link": "https://www.gov.uk/government/publications/../internal"},
        {"link": "https://www.gov.uk/government/policy/example"},
    ],
)
def test_govuk_rejects_unexpected_format_or_nonpublication_url(overrides):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"results": [_result(**overrides)]})
        )
    )
    provider = GovUKSearchProvider(client=client)
    try:
        assert provider.search("renewable energy policy", geography="UK") == []
    finally:
        provider.close()
        client.close()


def test_govuk_rate_limit_is_sanitized_and_not_retried():
    calls = []

    def handler(_request):
        calls.append(1)
        return httpx.Response(429, headers={"Retry-After": "30"}, text="secret upstream body")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GovUKSearchProvider(client=client)
    try:
        with pytest.raises(GovUKSearchError) as error:
            provider.search("renewable energy", geography="UK")
        assert error.value.code == "rate_limited"
        assert error.value.request_dispatched
        assert error.value.retry_after_seconds == 30
        assert "secret upstream body" not in str(error.value)
        assert len(calls) == 1
    finally:
        provider.close()
        client.close()


def test_govuk_rejects_redirects_without_following_them():
    calls = []

    def handler(_request):
        calls.append(1)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = GovUKSearchProvider(client=client)
    try:
        with pytest.raises(GovUKSearchError) as error:
            provider.search("renewable energy", geography="UK")
        assert error.value.code == "redirect_rejected"
        assert len(calls) == 1
    finally:
        provider.close()
        client.close()


def test_govuk_response_size_is_bounded():
    body = b"{" + b" " * MAX_RESPONSE_BYTES + b"}"
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=body))
    )
    provider = GovUKSearchProvider(client=client)
    try:
        with pytest.raises(GovUKSearchError) as error:
            provider.search("renewable energy", geography="UK")
        assert error.value.code == "response_too_large"
    finally:
        provider.close()
        client.close()
