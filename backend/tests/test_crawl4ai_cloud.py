import json

import httpx
import pytest

from app.providers.crawl4ai_cloud import (
    Crawl4AICloudError,
    Crawl4AICloudSearchProvider,
)


def test_cloud_search_normalizes_ranked_hits_and_usage_without_storing_auth():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={
                "content-type": "application/json",
                "x-c4-cost": "1.000",
                "x-c4-balance": "2499.000",
                "x-c4-allowance-left": "2499.000",
            },
            json={
                "results": [
                    {
                        "title": "Energy research report",
                        "url": "https://example.org/research/report?utm_source=search",
                        "snippet": "Search excerpt is discovery metadata, not evidence.",
                        "source": "gg",
                    },
                    {
                        "title": "Unsafe redirect result",
                        "url": "http://127.0.0.1/private",
                        "snippet": "must be rejected",
                    },
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-key-never-persist", client=client)
    try:
        result = provider.search("offshore wind research institute report", limit=10)
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert requests[0].url.host == "api.crawl4ai.com"
    assert requests[0].url.path == "/search"
    assert dict(requests[0].url.params) == {
        "q": "offshore wind research institute report",
        "rich": "0",
    }
    assert requests[0].headers["authorization"] == "Bearer fake-key-never-persist"
    assert result.hits[0].rank == 1
    assert result.hits[0].normalized_domain == "example.org"
    assert result.hits[0].snippet.startswith("Search excerpt")
    assert result.hits[0].source == "gg"
    assert len(result.hits) == 1
    assert result.reported_cost_credits == 1.0
    assert result.allowance_left_credits == 2499.0
    assert "fake-key-never-persist" not in repr(result)


@pytest.mark.parametrize(
    ("status_code", "payload", "expected_code"),
    [
        (401, {"error": "unauthorized"}, "authentication_failed"),
        (403, {"error": "forbidden"}, "authentication_failed"),
        (402, {"error": "no_credit", "actions": {"topup": "do not follow"}}, "credit_exhausted"),
        (429, {"error": "rate_limit"}, "rate_limited"),
        (503, {"error": "unavailable"}, "provider_unavailable"),
    ],
)
def test_cloud_search_classifies_provider_failures_without_leaking_body(
    status_code, payload, expected_code
):
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status_code,
                headers={"retry-after": "17"},
                json=payload,
            )
        )
    )
    provider = Crawl4AICloudSearchProvider(api_key="fake-secret", client=client)
    try:
        with pytest.raises(Crawl4AICloudError) as raised:
            provider.search("energy research reports")
    finally:
        provider.close()
        client.close()

    assert raised.value.code == expected_code
    assert raised.value.request_dispatched is True
    assert raised.value.http_status == status_code
    assert raised.value.provider_charge_status == (
        "not_charged_provider_5xx" if status_code >= 500 else "unknown"
    )
    assert "fake-secret" not in str(raised.value)
    assert "do not follow" not in str(raised.value)
    assert raised.value.retry_after_seconds == (17 if status_code == 429 else None)


def test_cloud_search_rejects_malformed_json_and_missing_usage_stays_unknown():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, content=b"not-json", headers={"content-type": "application/json"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-secret", client=client)
    try:
        with pytest.raises(Crawl4AICloudError) as raised:
            provider.search("energy research reports")
    finally:
        provider.close()
        client.close()

    assert calls == 1
    assert raised.value.code == "invalid_response"
    assert raised.value.request_dispatched is True


def test_cloud_search_rejects_unknown_cost_header_without_retrying():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"results": [{"title": "Report", "url": "https://example.org/report"}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-secret", client=client)
    try:
        result = provider.search("energy research reports")
    finally:
        provider.close()
        client.close()

    assert calls == 1
    assert result.reported_cost_credits is None
    assert result.usage_status == "cost_unknown"


def test_balance_is_read_only_and_reserves_only_reported_free_allowance():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/billing/balance"
        return httpx.Response(
            200,
            json={
                "tier": "community",
                "plan": "",
                "plan_name": "",
                "allowance_mc": 2_500_000,
                "free_mc": 1_000_000,
                "free": 1_000.0,
                "credit": 0.0,
                "topups": 0,
                "has_card": False,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        balance = provider.balance()
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    assert balance.plan == "community"
    assert balance.balance_credits == 1000.0
    assert balance.allowance_left_credits == 2500.0
    assert balance.raw_status == "reported"


def test_balance_reserves_against_free_pool_not_larger_plan_allowance():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "tier": "community",
                    "allowance_mc": 2_500_000,
                    "free_mc": 1_000_000,
                    # No current free balance: the plan cap is not sufficient to authorize calls.
                },
            )
        )
    )
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        balance = provider.balance()
    finally:
        provider.close()
        client.close()

    assert balance.balance_credits == 1000.0
    assert balance.allowance_left_credits == 2500.0
    assert balance.raw_status == "reported"


def test_balance_with_unknown_free_pool_does_not_claim_reported_balance():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"tier": "community", "allowance_mc": 2_500_000},
            )
        )
    )
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        balance = provider.balance()
    finally:
        provider.close()
        client.close()

    assert balance.balance_credits is None
    assert balance.raw_status == "unknown"


def test_missing_credential_fails_before_network_dispatch():
    with pytest.raises(Crawl4AICloudError) as raised:
        Crawl4AICloudSearchProvider(api_key=" ")

    assert raised.value.code == "credential_missing"
    assert raised.value.request_dispatched is False


def test_estimate_scrape_uses_fixed_endpoint_and_validates_credit_range():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"min": "0.5", "max": "1.0", "text": "about 1"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        estimate = provider.estimate_scrape(
            "https://www.example.org/reports/energy", expected_domain="example.org"
        )
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.host == "api.crawl4ai.com"
    assert request.url.path == "/v1/estimate"
    assert request.read() == b'{"endpoint":"scrape","url":"https://www.example.org/reports/energy"}'
    assert estimate.minimum_credits == 0.5
    assert estimate.maximum_credits == 1.0
    assert estimate.reported_cost_credits is None
    assert estimate.usage_status == "cost_unknown"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/report",
        "https://127.0.0.1/private",
        "https://user:pass@example.org/report",
        "https://other.example/report",
    ],
)
def test_estimate_scrape_rejects_unsafe_or_unverified_domain_before_dispatch(url):
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: pytest.fail("must not dispatch"))
    )
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        with pytest.raises(Crawl4AICloudError) as raised:
            provider.estimate_scrape(url, expected_domain="example.org")
    finally:
        provider.close()
        client.close()
    assert raised.value.code == "invalid_url"
    assert raised.value.request_dispatched is False


def test_scrape_uses_public_publisher_url_markdown_no_proxy_and_actual_usage():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            headers={"x-c4-cost": "0.75", "x-c4-balance": "998.25"},
            json={
                "url": "https://www.example.org/reports/energy",
                "markdown": "# Report\n\nMethods describe a field survey.\n\nResults report a measured outcome.",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        result = provider.scrape_markdown(
            "https://www.example.org/reports/energy", expected_domain="example.org"
        )
    finally:
        provider.close()
        client.close()

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/scrape"
    assert json.loads(request.content) == {
        "url": "https://www.example.org/reports/energy",
        "format": "md",
        "proxy": "none",
        "engine": "auto",
    }
    assert result.markdown.startswith("# Report")
    assert result.reported_cost_credits == 0.75
    assert result.balance_credits == 998.25
    assert result.usage_status == "reported"


def test_scrape_rejects_cross_domain_result_and_does_not_retry():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"url": "https://attacker.example/report", "markdown": "untrusted content"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-key", client=client)
    try:
        with pytest.raises(Crawl4AICloudError) as raised:
            provider.scrape_markdown(
                "https://www.example.org/reports/energy", expected_domain="example.org"
            )
    finally:
        provider.close()
        client.close()
    assert calls == 1
    assert raised.value.code == "publisher_domain_mismatch"
    assert raised.value.request_dispatched is True


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, "authentication_failed"),
        (402, "credit_exhausted"),
        (403, "provider_rejected_request"),
        (429, "rate_limited"),
        (503, "provider_unavailable"),
    ],
)
def test_scrape_provider_failures_are_sanitized_and_never_retried(status_code, expected_code):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"error": "private provider detail"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = Crawl4AICloudSearchProvider(api_key="fake-secret", client=client)
    try:
        with pytest.raises(Crawl4AICloudError) as raised:
            provider.scrape_markdown(
                "https://www.example.org/reports/energy", expected_domain="example.org"
            )
    finally:
        provider.close()
        client.close()
    assert calls == 1
    assert raised.value.code == expected_code
    assert raised.value.request_dispatched is True
    assert "fake-secret" not in str(raised.value)
    assert "private provider detail" not in str(raised.value)
