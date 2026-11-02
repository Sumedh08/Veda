import json

import httpx
import pytest

from app.providers.official_site_search import (
    OfficialSitePublicationSearchError,
    WordPressPublicationSearchProvider,
    build_official_site_query,
)


def _organization():
    return {
        "canonical_name": "Offshore Renewable Energy Catapult",
        "organization_id": "https://ror.org/03ffv2k10",
        "identity_status": "VERIFIED_ESTABLISHED",
        "verification_source": "https://api.ror.org/v2/organizations/03ffv2k10",
        "official_domains": ["ore.catapult.org.uk"],
        "registry_match": False,
    }


@pytest.mark.parametrize(
    ("verification_method", "expected_publisher_verification"),
    [
        (
            "crawl4ai_search_result_domain_plus_ror_exact_domain",
            "official_domain_linked_from_ror_verified_site",
        ),
        (
            "crossref_publisher_doi_title_and_link_domain_match",
            "crossref_doi_title_publisher_and_link_domain_match",
        ),
    ],
)
def test_official_site_search_finds_report_from_a_linked_wordpress_catalog(
    verification_method, expected_publisher_verification
):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "ore.catapult.org.uk":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    '<html><a href="https://cms.ore.catapult.org.uk/?p=23305">'
                    "Official publication record</a>"
                    '<img src="https://cms.ore.catapult.org.uk/wp-content/image.png">'
                    "</html>"
                ),
            )
        assert request.url.host == "cms.ore.catapult.org.uk"
        assert request.url.path == "/wp-json/wp/v2/search"
        assert request.url.params["search"] == "offshore wind cable"
        assert request.url.params["per_page"] == "5"
        assert request.url.params["_fields"] == "id,title,url,type,subtype"
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(
                [
                    {
                        "id": 23305,
                        "title": {"rendered": "Can O&amp;M simulation guide cable topology?"},
                        "url": "https://cms.ore.catapult.org.uk/reports/cable-topology/",
                        "type": "post",
                        "subtype": "analysis-report",
                    },
                    {
                        "id": 23306,
                        "title": {"rendered": "Press announcement about cable"},
                        "url": "https://cms.ore.catapult.org.uk/news/cable/",
                        "type": "post",
                        "subtype": "press-release",
                    },
                ]
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )
    organization = _organization()
    organization["verification_method"] = verification_method
    if verification_method.startswith("crossref_"):
        organization.update(
            identity_status="VERIFIED_DOMAIN_SPECIALIST",
            organization_id="crossref-publisher:verified-test",
            verification_source="https://api.crossref.org/works/10.5555%2Fpublisher-report",
        )
    result = provider.search(
        organization,
        question="For UK offshore wind renewable energy projects, how should export-cable reliability and converter topology be assessed?",
        query="offshore wind cable",
        limit=5,
    )

    assert len(calls) == 2
    assert len(result.records) == 1
    report = result.records[0]
    assert report.title == "Can O&M simulation guide cable topology?"
    assert report.source_type == "institutional_report"
    assert report.abstract_excerpt is None
    assert report.provider_metadata["official_site_discovery"]["content_fetched"] is False
    assert report.provider_metadata["official_site_discovery"]["rights_status"] == "not_assessed"
    assert (
        report.provider_metadata["official_site_discovery"]["organization_id"]
        == organization["organization_id"]
    )
    assert (
        report.provider_metadata["official_site_discovery"]["publisher_verification"]
        == expected_publisher_verification
    )
    assert result.status == "completed"


def test_official_site_search_rejects_unlinked_hosts_and_nonresearch_subtypes():
    def handler(request):
        if request.url.host == "ore.catapult.org.uk":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a href="https://unrelated.example/wp-content/x.png">asset</a>',
            )
        pytest.fail("unlinked host must not be queried")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )
    result = provider.search(
        _organization(), question="offshore wind cable", query="offshore wind cable", limit=5
    )

    assert result.status == "no_catalog_discovered"
    assert result.records == []


def test_official_site_search_rejects_redirects_instead_of_following_them():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )

    with pytest.raises(OfficialSitePublicationSearchError) as raised:
        provider.search(
            _organization(), question="offshore wind cable", query="offshore wind cable", limit=5
        )

    assert raised.value.code == "redirect_rejected"
    assert len(calls) == 1


def test_official_site_search_follows_bounded_https_redirect_within_verified_domain():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "ore.catapult.org.uk":
            return httpx.Response(
                301,
                headers={"location": "https://www.ore.catapult.org.uk/"},
            )
        if request.url.host == "www.ore.catapult.org.uk":
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text=(
                        '<link rel="https://api.w.org/" '
                        'href="https://www.ore.catapult.org.uk/wp-json/">'
                    ),
                )
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b"[]",
            )
        pytest.fail("only the verified organization domain may be requested")

    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )
    result = provider.search(
        _organization(), question="offshore wind cable", query="offshore wind cable", limit=5
    )

    assert result.status == "completed"
    assert result.request_count == 3
    assert [request.url.host for request in calls] == [
        "ore.catapult.org.uk",
        "www.ore.catapult.org.uk",
        "www.ore.catapult.org.uk",
    ]


def test_official_site_search_stops_same_url_redirect_loop_immediately():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        target = "/403" if request.url.path == "/" else "/403"
        return httpx.Response(301, headers={"location": target})

    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )

    with pytest.raises(OfficialSitePublicationSearchError) as raised:
        provider.search(
            _organization(), question="offshore wind cable", query="offshore wind cable", limit=5
        )

    assert raised.value.code == "redirect_loop"
    assert raised.value.requests_attempted == 2
    assert calls == ["/", "/403"]


def test_official_site_search_rejects_unverified_organization_domains():
    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: pytest.fail("no call"))),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )
    organization = {**_organization(), "identity_status": "PENDING_VERIFICATION"}

    with pytest.raises(OfficialSitePublicationSearchError) as raised:
        provider.search(
            organization,
            question="offshore wind cable",
            query="offshore wind cable",
            limit=5,
        )

    assert raised.value.code == "identity_not_verified"


def test_verified_publication_page_returns_only_page_metadata_and_honors_robots():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="User-agent: *\nAllow: /",
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Food security policy evidence</title>"
                '<link rel="canonical" href="https://fao.example/reports/food-security">'
                '<link rel="license" href="https://creativecommons.org/licenses/by/4.0/">'
                '<meta name="citation_title" content="Food security policy evidence">'
                '<meta name="citation_publication_date" content="2025-08-12">'
                '<a href="/reports/food-security.pdf">Download report</a>'
                "</head><body>Full text must not be returned or persisted.</body></html>"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )
    try:
        result = provider.verify_publication_page(
            _organization_for_metadata_verification(),
            "https://fao.example/reports/food-security",
            expected_title="Food security policy evidence",
        )
    finally:
        provider.close()
        client.close()

    assert [request.url.path for request in calls] == [
        "/robots.txt",
        "/reports/food-security",
    ]
    assert result.title == "Food security policy evidence"
    assert result.canonical_url == "https://fao.example/reports/food-security"
    assert result.publication_date == "2025-08-12"
    assert result.metadata_kind == "citation_metadata"
    assert result.license_code == "cc-by"
    assert result.license_url == "https://creativecommons.org/licenses/by/4.0/"
    assert result.license_evidence == "official_page_rel_license"
    assert result.linked_pdf_url == "https://fao.example/reports/food-security.pdf"
    assert not hasattr(result, "body")


def test_publication_page_records_item_rights_signals_without_retaining_notice_text():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="User-agent: *\nAllow: /",
            )
        if request.url.path in {"/terms", "/terms-of-use"}:
            return httpx.Response(404, headers={"content-type": "text/html"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>Urban climate assessment</title>"
                '<link rel="canonical" href="https://fao.example/reports/urban-climate">'
                '<meta name="citation_title" content="Urban climate assessment">'
                "</head><body><p>No part of this report may be reproduced without permission.</p>"
                "<p>Copyright 2025 Institute.</p></body></html>"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )
    try:
        result = provider.verify_publication_page(
            _organization_for_metadata_verification(),
            "https://fao.example/reports/urban-climate",
            expected_title="Urban climate assessment",
        )
    finally:
        provider.close()
        client.close()

    assert result.item_specific_restriction_codes == ("item_specific_reproduction_restriction",)
    assert result.copyright_notice_detected is True
    assert not hasattr(result, "body")


def test_unlicensed_publication_checks_linked_terms_without_retaining_terms_text():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="User-agent: *\nAllow: /",
            )
        if request.url.path == "/reports/food-security":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    "<html><head><title>Food security policy evidence</title>"
                    '<meta name="citation_title" content="Food security policy evidence">'
                    '<link rel="canonical" href="https://fao.example/reports/food-security">'
                    '</head><body><a href="/legal/terms">Terms of Use</a>'
                    "Publication body must not be retained.</body></html>"
                ),
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "Terms prohibit automated scraping and text and data mining. "
                "Terms body must not be retained."
            ),
        )

    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )
    try:
        result = provider.verify_publication_page(
            _organization_for_metadata_verification(),
            "https://fao.example/reports/food-security",
            expected_title="Food security policy evidence",
        )
    finally:
        provider.close()

    assert requests == ["/robots.txt", "/reports/food-security", "/legal/terms"]
    assert result.license_status == "not_declared"
    assert result.site_terms_status == "restriction_signal"
    assert result.site_terms_url == "https://fao.example/legal/terms"
    assert result.site_terms_restriction_codes == ("automated_access", "text_data_mining")
    assert result.site_terms_sha256 is not None
    assert result.request_count == 3
    assert not hasattr(result, "site_terms_text")


def test_robots_403_is_unavailable_but_document_403_remains_denied():
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text="not available")
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "<html><head><title>Food security policy evidence</title>"
                '<meta name="citation_title" content="Food security policy evidence">'
                '<link rel="canonical" href="https://fao.example/reports/food-security">'
                "</head></html>"
            ),
        )

    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )
    try:
        result = provider.verify_publication_page(
            _organization_for_metadata_verification(),
            "https://fao.example/reports/food-security",
            expected_title="Food security policy evidence",
        )
    finally:
        provider.close()
    assert result.robots_status == "unavailable_4xx"
    assert result.robots_http_status == 403
    assert requests[:2] == ["/robots.txt", "/reports/food-security"]


def test_publication_page_license_parser_fails_closed_for_unknown_or_conflicting_rights():
    from app.providers.official_site_search import _PublicationMetadata

    unknown = _PublicationMetadata()
    unknown.feed(
        '<html><head><link rel="license" '
        'href="https://creativecommons.org/licenses/by-nc/4.0/"></head></html>'
    )
    unknown.close()
    assert unknown.reuse_license() == (
        None,
        None,
        None,
        "unrecognized_or_restricted",
    )

    conflicting = _PublicationMetadata()
    conflicting.feed(
        '<html><head><link rel="license" '
        'href="https://creativecommons.org/licenses/by/4.0/">'
        '<meta name="citation_license" '
        'content="https://creativecommons.org/publicdomain/zero/1.0/">'
        "</head></html>"
    )
    conflicting.close()
    assert conflicting.reuse_license() == (
        None,
        None,
        None,
        "unrecognized_or_conflicting",
    )


def _organization_for_metadata_verification():
    return {
        "canonical_name": "Food and Agriculture Organization",
        "organization_id": "https://ror.org/00pe0tf51",
        "identity_status": "VERIFIED_ESTABLISHED",
        "verification_source": "https://api.ror.org/v2/organizations/00pe0tf51",
        "official_domains": ["fao.example"],
        "registry_match": False,
    }


def test_verified_publication_page_fails_closed_when_robots_disallows_fetch():
    requested_paths = []

    def handler(request):
        requested_paths.append(request.url.path)
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            text="User-agent: *\nDisallow: /reports/",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )
    try:
        with pytest.raises(OfficialSitePublicationSearchError) as raised:
            provider.verify_publication_page(
                _organization_for_metadata_verification(),
                "https://fao.example/reports/food-security",
                expected_title="Food security policy evidence",
            )
    finally:
        provider.close()
        client.close()

    assert raised.value.code == "robots_disallowed"
    assert requested_paths == ["/robots.txt"]


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, "authentication_required"),
        (403, "access_denied"),
        (429, "rate_limited"),
        (503, "upstream_server_error"),
    ],
)
def test_verified_publication_page_preserves_terminal_http_failure_class(
    status_code, expected_code
):
    requested_paths = []

    def handler(request):
        requested_paths.append(request.url.path)
        return httpx.Response(status_code)

    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )
    try:
        with pytest.raises(OfficialSitePublicationSearchError) as raised:
            provider.verify_publication_page(
                _organization_for_metadata_verification(),
                "https://fao.example/reports/food-security",
                expected_title="Food security policy evidence",
            )
    finally:
        provider.close()

    assert raised.value.code == expected_code
    assert raised.value.request_dispatched is True
    expected_paths = (
        ["/robots.txt", "/reports/food-security"] if status_code in {401, 403} else ["/robots.txt"]
    )
    assert raised.value.requests_attempted == len(expected_paths)
    assert requested_paths == expected_paths


@pytest.mark.parametrize(
    ("page_response", "expected_code"),
    [
        (
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    "<html><head><title>Food security policy evidence</title>"
                    '<meta name="citation_title" content="Food security policy evidence">'
                    '<link rel="canonical" href="https://other.example/report">'
                    "</head></html>"
                ),
            ),
            "canonical_domain_mismatch",
        ),
        (
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=(
                    "<html><head><title>Unrelated health policy report</title>"
                    '<meta name="citation_title" content="Unrelated health policy report">'
                    "</head></html>"
                ),
            ),
            "search_page_title_mismatch",
        ),
        (
            httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.7 must not be parsed or retained here",
            ),
            "unexpected_content_type",
        ),
    ],
)
def test_verified_publication_page_rejects_untrusted_canonical_wrong_title_and_pdf(
    page_response, expected_code
):
    requested_paths = []

    def handler(request):
        requested_paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="User-agent: *\nAllow: /",
            )
        return page_response

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    provider = WordPressPublicationSearchProvider(
        client=client, public_resolver=lambda *_args: ["8.8.8.8"]
    )
    try:
        with pytest.raises(OfficialSitePublicationSearchError) as raised:
            provider.verify_publication_page(
                _organization_for_metadata_verification(),
                "https://fao.example/reports/food-security",
                expected_title="Food security policy evidence",
            )
    finally:
        provider.close()
        client.close()

    assert raised.value.code == expected_code
    assert requested_paths == ["/robots.txt", "/reports/food-security"]


def test_verified_ror_official_url_is_usable_when_ror_has_no_domain_field():
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.host == "ore.catapult.org.uk":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a href="https://cms.ore.catapult.org.uk/wp-content/report.pdf">report</a>',
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"[]",
        )

    organization = {
        **_organization(),
        "official_domains": [],
        "official_urls": ["https://ore.catapult.org.uk/"],
    }
    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )

    result = provider.search(
        organization,
        question="offshore wind cable",
        query="offshore wind cable",
        limit=5,
    )

    assert result.status == "completed"
    assert len(calls) == 2
    assert calls[1].url.host == "cms.ore.catapult.org.uk"


def test_official_site_records_use_ror_id_when_candidate_has_no_organization_id():
    def handler(request):
        if request.url.host == "ore.catapult.org.uk":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<a href="https://cms.ore.catapult.org.uk/wp-content/report.pdf">report</a>',
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=json.dumps(
                [
                    {
                        "id": 501,
                        "title": {"rendered": "Offshore cable reliability report"},
                        "url": "https://cms.ore.catapult.org.uk/analysis-report/cable-reliability/",
                        "type": "post",
                        "subtype": "analysis-report",
                    }
                ]
            ),
        )

    organization = {
        **_organization(),
        "ror_id": "https://ror.org/03ffv2k10",
        "official_domains": [],
        "official_urls": ["https://ore.catapult.org.uk/"],
    }
    organization.pop("organization_id")
    provider = WordPressPublicationSearchProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
        public_resolver=lambda *_args: ["8.8.8.8"],
    )

    result = provider.search(
        organization,
        question="offshore wind cable reliability",
        query="offshore wind cable",
        limit=5,
    )

    assert len(result.records) == 1
    assert (
        result.records[0].provider_metadata["official_site_discovery"]["organization_id"]
        == "https://ror.org/03ffv2k10"
    )


def test_official_site_search_rejects_private_dns_results_before_http_request():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: pytest.fail("private host must not be requested")
        )
    )
    provider = WordPressPublicationSearchProvider(
        client=client,
        public_resolver=lambda *_args: ["127.0.0.1"],
    )

    with pytest.raises(OfficialSitePublicationSearchError) as raised:
        provider.search(
            _organization(),
            question="offshore wind cable",
            query="offshore wind cable",
            limit=5,
        )

    assert raised.value.code == "non_public_address"


def test_official_site_query_is_short_and_derived_from_question_terms():
    question = "For UK offshore wind renewable energy projects, how should export-cable reliability and converter topology be assessed?"
    assert build_official_site_query(question) == "offshore wind cable"


def test_food_price_official_catalog_query_keeps_topic_terms_not_question_grammar():
    question = (
        "Which policies have reduced food price volatility and improved food security "
        "for smallholder agriculture in South Asia, and what evidence explains "
        "differences in outcomes?"
    )

    assert build_official_site_query(question) == "food price volatility"
