import httpx
import pytest

from app.providers.govuk_content import (
    CONTENT_API_BASE,
    MAX_RESPONSE_BYTES,
    GovUKContentError,
    GovUKContentProvider,
)


def _payload(**overrides):
    value = {
        "base_path": "/government/publications/offshore-wind-net-zero-investment-roadmap",
        "document_type": "policy_paper",
        "schema_name": "publication",
        "title": "Offshore wind net zero investment roadmap",
        "public_updated_at": "2025-04-15T12:00:00Z",
        "details": {
            "body": "<h2>Purpose</h2><p>Plan offshore wind investment and grid infrastructure.</p>",
            "attachments": [{"url": "https://assets.publishing.service.gov.uk/ignored.pdf"}],
        },
    }
    value.update(overrides)
    return value


def test_govuk_content_fetches_only_the_exact_publication_body_and_records_default_ogl_basis():
    calls = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: (
                calls.append(request)
                or httpx.Response(
                    200, json=_payload(), headers={"content-type": "application/json"}
                )
            )
        ),
        follow_redirects=False,
    )
    provider = GovUKContentProvider(client=client)
    try:
        result = provider.fetch_publication_body(
            "/government/publications/offshore-wind-net-zero-investment-roadmap",
            expected_title="Offshore wind net zero investment roadmap",
        )
    finally:
        provider.close()
        client.close()

    assert len(calls) == 1
    assert str(calls[0].url) == (
        CONTENT_API_BASE + "/government/publications/offshore-wind-net-zero-investment-roadmap"
    )
    assert result.body_html == _payload()["details"]["body"]
    assert "attachments" not in result.body_html
    assert result.license_code == "ogl-3.0-default"
    assert result.rights_status == "PERMITTED_WITH_RESTRICTIONS"
    assert result.license_url.endswith("open-government-licence/version/3/")
    assert "no per-item licence field" in result.rights_limit


def test_govuk_content_rejects_content_api_identity_drift():
    payload = _payload(
        base_path="/government/publications/a-different-publication",
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload)),
        follow_redirects=False,
    )
    provider = GovUKContentProvider(client=client)
    try:
        with pytest.raises(GovUKContentError) as error:
            provider.fetch_publication_body(
                "/government/publications/offshore-wind-net-zero-investment-roadmap",
                expected_title="Offshore wind net zero investment roadmap",
            )
    finally:
        provider.close()
        client.close()
    assert error.value.code == "publication_identity_or_body_mismatch"


def test_govuk_content_rejects_unsupported_content_type_and_redirects_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = GovUKContentProvider(client=client)
    try:
        with pytest.raises(GovUKContentError) as error:
            provider.fetch_publication_body(
                "/government/publications/offshore-wind-net-zero-investment-roadmap",
                expected_title="Offshore wind net zero investment roadmap",
            )
    finally:
        provider.close()
        client.close()
    assert error.value.code == "redirect_rejected"
    assert len(calls) == 1


def test_govuk_content_is_bounded_and_rejects_unsafe_paths():
    body = b"{" + b" " * MAX_RESPONSE_BYTES + b"}"
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200, content=body, headers={"content-type": "application/json"}
            )
        ),
        follow_redirects=False,
    )
    provider = GovUKContentProvider(client=client)
    try:
        with pytest.raises(GovUKContentError) as too_large:
            provider.fetch_publication_body(
                "/government/publications/offshore-wind-net-zero-investment-roadmap",
                expected_title="Offshore wind net zero investment roadmap",
            )
        with pytest.raises(GovUKContentError) as unsafe_path:
            provider.fetch_publication_body(
                "/government/publications/../admin", expected_title="anything"
            )
    finally:
        provider.close()
        client.close()
    assert too_large.value.code == "response_too_large"
    assert unsafe_path.value.code == "invalid_publication_identity"


def test_govuk_content_records_an_unreported_api_failure_without_exposing_response_body():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, text="upstream-private-details")
        ),
        follow_redirects=False,
    )
    provider = GovUKContentProvider(client=client)
    try:
        with pytest.raises(GovUKContentError) as error:
            provider.fetch_publication_body(
                "/government/publications/offshore-wind-net-zero-investment-roadmap",
                expected_title="Offshore wind net zero investment roadmap",
            )
    finally:
        provider.close()
        client.close()
    assert error.value.code == "rate_limited"
    assert "upstream-private-details" not in str(error.value)
