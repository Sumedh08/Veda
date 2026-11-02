import socket
from datetime import date
from io import BytesIO

import pytest

from app.research.retrieval_rights import ReviewedHostPolicy
from app.research.safe_fetch import SafeFetchError, SafeHTMLFetcher, extract_html_paragraphs


def _record(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


def _response(status: int, body: bytes = b"", headers: str = "") -> bytes:
    return f"HTTP/1.1 {status} Test\r\n{headers}Connection: close\r\n\r\n".encode() + body


class FakeSocket:
    def __init__(self, response: bytes):
        self.response = response
        self.request = b""
        self.closed = False

    def settimeout(self, timeout):
        pass

    def sendall(self, request: bytes):
        self.request = request

    def makefile(self, mode):
        return BytesIO(self.response)

    def close(self):
        self.closed = True


class FakeTLSContext:
    def __init__(self):
        self.server_names = []

    def wrap_socket(self, sock, *, server_hostname):
        self.server_names.append(server_hostname)
        return sock


class RoutedSocket:
    def __init__(
        self,
        address,
        content_sockets,
        *,
        robots_status,
        robots_body,
        robots_responses,
        source_calls,
    ):
        self.address = address
        self.content_sockets = content_sockets
        self.robots_status = robots_status
        self.robots_body = robots_body
        self.robots_responses = robots_responses
        self.source_calls = source_calls
        self.delegate = None

    def settimeout(self, timeout):
        if self.delegate:
            self.delegate.settimeout(timeout)

    def sendall(self, request: bytes):
        if b"Accept: text/plain" in request:
            if self.robots_responses:
                response = self.robots_responses.pop(0)
            else:
                response = _response(
                    self.robots_status,
                    self.robots_body,
                    "Content-Type: text/plain; charset=utf-8\r\n",
                )
            self.delegate = FakeSocket(response)
        else:
            self.source_calls.append(self.address)
            self.delegate = self.content_sockets.pop(0)
        self.delegate.sendall(request)

    def makefile(self, mode):
        return self.delegate.makefile(mode)

    def close(self):
        if self.delegate:
            self.delegate.close()


def _fetcher(
    resolver,
    sockets,
    *,
    max_bytes=1000,
    max_redirects=3,
    ssl_context=None,
    robots_status=200,
    robots_body=b"User-agent: *\nAllow: /\n",
    robots_responses=None,
    host_policy_checker=None,
    host_minimum_interval=0.0,
    origin_request_limiter=None,
    timeout_seconds=4,
):
    connector_calls = []

    def connect(address, *, timeout):
        return RoutedSocket(
            address,
            sockets,
            robots_status=robots_status,
            robots_body=robots_body,
            robots_responses=robots_responses,
            source_calls=connector_calls,
        )

    def test_host_policy(host, license_code):
        return ReviewedHostPolicy(
            host=host,
            policy_id="fixture-reviewed-host-v1",
            terms_url=f"https://{host}/terms",
            reviewed_at=date.today(),
            licenses=frozenset({license_code}),
            minimum_interval_seconds=host_minimum_interval,
        )

    if host_policy_checker is None:
        host_policy_checker = test_host_policy

    fetcher = SafeHTMLFetcher(
        resolver=resolver,
        connector=connect,
        ssl_context=ssl_context or FakeTLSContext(),
        max_bytes=max_bytes,
        max_redirects=max_redirects,
        timeout_seconds=timeout_seconds,
        host_policy_checker=host_policy_checker,
        origin_request_limiter=origin_request_limiter,
    )
    return fetcher, connector_calls


class RecordingOriginLimiter:
    def __init__(self):
        self.calls = []

    def acquire(self, origin, interval_seconds, *, deadline):
        self.calls.append((origin, interval_seconds))


class DeferringOriginLimiter:
    def acquire(self, origin, interval_seconds, *, deadline):
        if interval_seconds > 0:
            from app.research.origin_rate_limit import OriginRequestDeferred

            raise OriginRequestDeferred(12.5)


def test_fetch_pins_checked_ip_and_preserves_tls_hostname():
    body = b"<html><script>ignore this</script><main><p>Visible text.</p></main></html>"
    response = _response(
        200,
        body,
        f"Content-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\n",
    )
    sock = FakeSocket(response)
    tls = FakeTLSContext()
    resolved = []
    fetcher, calls = _fetcher(
        lambda host, port, kind: resolved.append((host, port, kind)) or [_record("93.184.216.34")],
        [sock],
        ssl_context=tls,
    )

    document = fetcher.fetch_html("https://papers.example/article?id=7", license_name="cc-by")

    assert resolved == [
        ("papers.example", 443, socket.SOCK_STREAM),
        ("papers.example", 443, socket.SOCK_STREAM),
    ]
    assert calls == [("93.184.216.34", 443)]
    assert tls.server_names == ["papers.example", "papers.example"]
    assert "Visible text." in document.text
    assert "ignore this" not in document.text
    assert len(document.sha256) == 64
    assert b"Host: papers.example" in sock.request


def test_default_resolver_uses_unspecified_family_and_stream_socket(monkeypatch):
    from app.research.safe_fetch import MAX_DOCUMENT_BYTES

    calls = []

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        calls.append((host, port, family, type))
        if family != socket.AF_UNSPEC or type != socket.SOCK_STREAM:
            raise socket.gaierror("invalid address-family/socket-type arguments")
        return [_record("93.184.216.34")]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    body = b"<html><main><p>Visible paper evidence.</p></main></html>"
    response = _response(
        200,
        body,
        f"Content-Type: text/html\r\nContent-Length: {len(body)}\r\n",
    )
    fetcher, _ = _fetcher(None, [FakeSocket(response)], max_bytes=MAX_DOCUMENT_BYTES)

    document = fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert "Visible paper evidence." in document.text
    assert calls == [
        ("papers.example", 443, socket.AF_UNSPEC, socket.SOCK_STREAM),
        ("papers.example", 443, socket.AF_UNSPEC, socket.SOCK_STREAM),
    ]


def test_private_or_mixed_dns_answers_are_rejected_before_connect():
    fetcher, calls = _fetcher(lambda host, port, kind: [_record(host)], [])
    with pytest.raises(SafeFetchError, match="non-public"):
        fetcher.fetch_html("http://127.0.0.1/admin", license_name="cc-by")
    assert not calls

    mixed, mixed_calls = _fetcher(lambda *args: [_record("93.184.216.34"), _record("10.0.0.8")], [])
    with pytest.raises(SafeFetchError, match="non-public"):
        mixed.fetch_html("https://mixed.example/paper", license_name="cc-by")
    assert not mixed_calls


def test_unlicensed_content_is_rejected_before_dns():
    fetcher, calls = _fetcher(lambda *args: pytest.fail("DNS must not run"), [])
    for license_name in (None, "public-domain", "cc-by-nc"):
        with pytest.raises(SafeFetchError, match="verified, applicable private-research decision"):
            fetcher.fetch_html("https://papers.example/paper", license_name=license_name)
    assert not calls


def _private_research_decision(*, domains=("papers.example",), robots_status="rules_checked"):
    from app.research.rights_policy import RightsContext, evaluate_rights

    return evaluate_rights(
        RightsContext(
            source_identity_verified=True,
            publicly_accessible=True,
            document_http_status=200,
            robots_status=robots_status,
            robots_allows=True if robots_status == "rules_checked" else None,
            site_terms_status="checked_no_restriction_signal",
            use_mode="private_research",
            jurisdiction="IN",
            work_type="institutional_report",
            verified_domains=domains,
            terms_url="https://papers.example/terms",
        )
    )


def test_unlicensed_private_research_fetch_requires_decision_and_stays_on_verified_domain():
    html = b"<html><main><p>Verified report evidence.</p></main></html>"
    fetcher, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, html, "Content-Type: text/html\r\n"))],
        origin_request_limiter=RecordingOriginLimiter(),
    )

    document = fetcher.fetch_html(
        "https://papers.example/reports/item",
        license_name=None,
        rights_decision=_private_research_decision(),
    )

    assert document.text == "Verified report evidence."
    assert document.host_policy_id == "private-research-v1"
    assert document.host_terms_url == "https://papers.example/terms"
    assert document.robots_status == "rules_checked"
    assert len(calls) == 1  # only the document GET consumes the fake content socket


def test_unlicensed_private_research_redirect_outside_verified_domains_is_denied():
    fetcher, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(302, headers="Location: https://other.example/report\r\n"))],
        origin_request_limiter=RecordingOriginLimiter(),
    )

    with pytest.raises(SafeFetchError) as raised:
        fetcher.fetch_html(
            "https://papers.example/reports/item",
            license_name=None,
            rights_decision=_private_research_decision(),
        )

    assert raised.value.code == "verified_domain_boundary"
    assert len(calls) == 1  # only the source robots + request host DNS path


def test_unreviewed_runtime_host_is_rejected_before_dns():
    fetcher = SafeHTMLFetcher(resolver=lambda *args: pytest.fail("DNS must not run"))
    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html("https://papers.example/paper", license_name="cc-by")
    assert error.value.code == "host_policy_unknown"


def test_zero_remaining_fetch_deadline_stops_before_dns():
    fetcher, _ = _fetcher(lambda *args: pytest.fail("DNS must not run"), [], timeout_seconds=0)

    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert error.value.code == "timeout"


def test_page_timeout_retains_only_previously_verified_host_and_robots_context():
    robots = _response(
        200,
        b"User-agent: *\nAllow: /\n",
        "Content-Type: text/plain; charset=utf-8\r\n",
    )
    fetcher, _ = _fetcher(
        lambda host, port, kind: [_record("93.184.216.34")],
        [FakeSocket(robots), FakeSocket(_response(200))],
    )
    original_request = fetcher._request
    request_count = 0

    def timeout_on_article(target, deadline, **kwargs):
        nonlocal request_count
        request_count += 1
        if request_count == 2:
            raise SafeFetchError("timeout", "Source retrieval exceeded the time limit.")
        return original_request(target, deadline, **kwargs)

    fetcher._request = timeout_on_article

    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert error.value.code == "timeout"
    assert error.value.access_context is not None
    assert error.value.access_context.final_host == "papers.example"
    assert error.value.access_context.host_policy_id == "fixture-reviewed-host-v1"
    assert error.value.access_context.robots_status == "rules_checked"


def test_robots_rules_merge_agents_use_longest_match_and_allow_ties():
    from app.research.safe_fetch import parse_robots_txt, robots_allows, robots_crawl_delay

    groups = parse_robots_txt(
        b"""User-agent: *
Disallow: /secret
Allow: /secret/open
Disallow: /*.pdf$
User-agent: VedaResearch
Disallow: /admin
Disallow: /combine
User-agent: VedaResearch
Allow: /combine
"""
    )
    assert not robots_allows(groups, "/admin/report")
    assert robots_allows(groups, "/secret/closed")  # The exact group replaces the wildcard group.
    assert robots_allows(groups, "/combine")

    wildcard_groups = parse_robots_txt(
        b"User-agent: *\nDisallow: /secret\nAllow: /secret/open\nDisallow: /*.pdf$\n"
    )
    assert not robots_allows(wildcard_groups, "/secret/closed")
    assert robots_allows(wildcard_groups, "/secret/open/paper")
    assert not robots_allows(wildcard_groups, "/public/file.pdf")
    assert robots_allows(wildcard_groups, "/public/file.pdf?download=1")
    assert robots_crawl_delay(parse_robots_txt(b"User-agent: *\nCrawl-delay: 15\n")) == 15


def test_robots_disallow_five_xx_and_utf8_failure_are_fail_closed():
    denied, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"<p>Must not be fetched</p>", "Content-Type: text/html\r\n"))],
        robots_body=b"User-agent: *\nDisallow: /private\n",
    )
    with pytest.raises(SafeFetchError) as disallowed:
        denied.fetch_html("https://papers.example/private/article", license_name="cc-by")
    assert disallowed.value.code == "robots_disallowed"
    assert calls == []

    unavailable, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"<p>Must not be fetched</p>", "Content-Type: text/html\r\n"))],
        robots_status=404,
    )
    missing_policy = unavailable.fetch_html("https://papers.example/article", license_name="cc-by")
    assert missing_policy.text == "Must not be fetched"
    assert missing_policy.robots_status == "unavailable_4xx"
    assert calls == [("93.184.216.34", 443)]

    forbidden_robots, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"<p>Document body</p>", "Content-Type: text/html\r\n"))],
        robots_responses=[_response(403, b"robots unavailable", "Content-Type: text/plain\r\n")],
    )
    public_document = forbidden_robots.fetch_html(
        "https://papers.example/article", license_name="cc-by"
    )
    assert public_document.text == "Document body"
    assert public_document.robots_status == "unavailable_4xx"
    assert calls == [("93.184.216.34", 443)]

    document_forbidden, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(403, b"denied", "Content-Type: text/html\r\n"))],
    )
    with pytest.raises(SafeFetchError) as document_denial:
        document_forbidden.fetch_html("https://papers.example/article", license_name="cc-by")
    assert document_denial.value.code == "access_denied"
    assert calls == [("93.184.216.34", 443)]

    server_error, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"must not fetch", "Content-Type: text/html\r\n"))],
        robots_status=503,
    )
    with pytest.raises(SafeFetchError) as unreachable_policy:
        server_error.fetch_html("https://papers.example/article", license_name="cc-by")
    assert unreachable_policy.value.code == "robots_unreachable"
    assert calls == []

    delayed, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"<p>Must not be fetched</p>", "Content-Type: text/html\r\n"))],
        robots_body=b"User-agent: *\nCrawl-delay: 15\nAllow: /\n",
    )
    with pytest.raises(SafeFetchError) as crawl_delay:
        delayed.fetch_html("https://papers.example/article", license_name="cc-by")
    assert crawl_delay.value.code == "origin_rate_limit_unavailable"
    assert calls == []

    with pytest.raises(SafeFetchError) as invalid:
        from app.research.safe_fetch import parse_robots_txt

        parse_robots_txt(b"User-agent: *\nDisallow: /\xff")
    assert invalid.value.code == "robots_invalid_encoding"


def test_redirects_are_re_resolved_and_private_redirect_is_blocked():
    first = _response(302, headers="Location: https://repo.example/full-text\r\n")
    body = b"<p>Open licensed text.</p>"
    second = _response(
        200,
        body,
        f"Content-Type: text/html\r\nContent-Length: {len(body)}\r\n",
    )
    resolved = []
    fetcher, calls = _fetcher(
        lambda host, port, kind: resolved.append(host) or [_record("93.184.216.34")],
        [FakeSocket(first), FakeSocket(second)],
    )
    document = fetcher.fetch_html("https://publisher.example/doi", license_name="cc0")
    assert resolved == [
        "publisher.example",
        "publisher.example",
        "repo.example",
        "repo.example",
    ]
    assert len(calls) == 2
    assert "Open licensed text." in document.text

    redirect_resolved = []
    blocked, blocked_calls = _fetcher(
        lambda host, port, kind: (
            redirect_resolved.append(host)
            or [_record("93.184.216.34" if host == "publisher.example" else "169.254.169.254")]
        ),
        [FakeSocket(_response(302, headers="Location: http://internal.example/latest\r\n"))],
    )
    with pytest.raises(SafeFetchError, match="non-public"):
        blocked.fetch_html("http://publisher.example/doi", license_name="cc-by")
    assert redirect_resolved == [
        "publisher.example",
        "publisher.example",
        "internal.example",
    ]
    assert len(blocked_calls) == 1


def test_redirect_destination_requires_its_own_reviewed_host_policy():
    checked_hosts = []

    def policy(host, license_code):
        checked_hosts.append(host)
        if host == "repo.example":
            raise ValueError("host_policy_unknown")
        return ReviewedHostPolicy(
            host=host,
            policy_id="fixture-reviewed-host-v1",
            terms_url=f"https://{host}/terms",
            reviewed_at=date.today(),
            licenses=frozenset({license_code}),
        )

    fetcher, source_calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(302, headers="Location: https://repo.example/paper\r\n"))],
        host_policy_checker=policy,
    )
    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html("https://publisher.example/doi", license_name="cc-by")
    assert error.value.code == "host_policy_unknown"
    assert checked_hosts == ["publisher.example", "repo.example"]
    assert len(source_calls) == 1


def test_robots_redirects_are_bounded_and_policy_applies_to_initial_origin():
    content = _response(200, b"<p>Allowed source text.</p>", "Content-Type: text/html\r\n")
    robot_responses = [
        _response(302, headers="Location: https://policy-cdn.example/rules.txt\r\n"),
        _response(
            200,
            b"User-agent: VedaResearch\nAllow: /papers/\nDisallow: /\n",
            "Content-Type: text/plain; charset=utf-8\r\n",
        ),
    ]
    resolved = []
    fetcher, source_calls = _fetcher(
        lambda host, port, kind: resolved.append(host) or [_record("93.184.216.34")],
        [FakeSocket(content)],
        robots_responses=robot_responses,
    )
    document = fetcher.fetch_html("https://papers.example/papers/article", license_name="cc-by")
    assert "Allowed source text." in document.text
    assert resolved == ["papers.example", "policy-cdn.example", "papers.example"]
    assert len(source_calls) == 1
    assert document.robots_status == "rules_checked"


def test_robots_crawl_delay_is_scheduled_for_html_request():
    limiter = RecordingOriginLimiter()
    body = b"<p>Allowed source text.</p>"
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, body, "Content-Type: text/html\r\n"))],
        robots_body=b"User-agent: *\nAllow: /\nCrawl-delay: 0.25\n",
        origin_request_limiter=limiter,
    )

    document = fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert document.text == "Allowed source text."
    assert limiter.calls == [
        ("https://papers.example", 0),
        ("https://papers.example", 0.25),
    ]


def test_crawl_delay_outside_deadline_is_reported_as_retryable_defer():
    limiter = DeferringOriginLimiter()
    body_socket = FakeSocket(
        _response(200, b"<p>Must not be fetched.</p>", "Content-Type: text/html\r\n")
    )
    fetcher, source_calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [body_socket],
        robots_body=b"User-agent: *\nAllow: /\nCrawl-delay: 15\n",
        origin_request_limiter=limiter,
    )

    with pytest.raises(SafeFetchError) as deferred:
        fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert deferred.value.code == "origin_request_deferred"
    assert deferred.value.retry_after_seconds == 12.5
    assert source_calls == []
    assert body_socket.request == b""


def test_positive_reviewed_host_interval_fails_closed_without_limiter():
    response_socket = FakeSocket(
        _response(200, b"<p>Must not be fetched.</p>", "Content-Type: text/html\r\n")
    )
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [response_socket],
        host_minimum_interval=0.2,
    )

    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert error.value.code == "origin_rate_limit_unavailable"
    assert response_socket.request == b""


def test_reviewed_host_interval_is_applied_to_robots_and_document_requests():
    limiter = RecordingOriginLimiter()
    body = b"<p>Allowed source text.</p>"
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, body, "Content-Type: text/html\r\n"))],
        host_minimum_interval=0.2,
        origin_request_limiter=limiter,
    )

    fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert limiter.calls == [
        ("https://papers.example", 0.2),
        ("https://papers.example", 0.2),
    ]


def test_html_redirect_reserves_slots_for_each_exact_origin():
    limiter = RecordingOriginLimiter()
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [
            FakeSocket(_response(302, headers="Location: https://repo.example/article\r\n")),
            FakeSocket(_response(200, b"<p>Redirected text.</p>", "Content-Type: text/html\r\n")),
        ],
        origin_request_limiter=limiter,
    )

    fetcher.fetch_html("https://papers.example/article", license_name="cc-by")

    assert limiter.calls == [
        ("https://papers.example", 0),
        ("https://papers.example", 0),
        ("https://repo.example", 0),
        ("https://repo.example", 0),
    ]


def test_https_redirect_cannot_downgrade():
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(302, headers="Location: http://plain.example/page\r\n"))],
    )
    with pytest.raises(SafeFetchError, match="downgrade"):
        fetcher.fetch_html("https://publisher.example/doi", license_name="cc-by")


def test_redirect_loop_and_redirect_limit_are_bounded():
    loop_fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [
            FakeSocket(_response(302, headers="Location: /same\r\n")),
            FakeSocket(_response(302, headers="Location: /same\r\n")),
        ],
    )
    with pytest.raises(SafeFetchError, match="redirected repeatedly"):
        loop_fetcher.fetch_html("http://papers.example/same", license_name="cc-by")

    limited, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [
            FakeSocket(_response(302, headers="Location: /one\r\n")),
            FakeSocket(_response(302, headers="Location: /two\r\n")),
        ],
        max_redirects=1,
    )
    with pytest.raises(SafeFetchError, match="redirect limit"):
        limited.fetch_html("http://papers.example/start", license_name="cc-by")


def test_byte_and_media_type_caps_are_enforced():
    large, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [
            FakeSocket(
                _response(
                    200,
                    headers="Content-Type: text/html\r\nContent-Length: 100\r\n",
                )
            )
        ],
        max_bytes=8,
    )
    with pytest.raises(SafeFetchError, match="byte limit"):
        large.fetch_html("http://papers.example/paper", license_name="cc-by")

    for content_length in ("-1", "not-a-number"):
        malformed, _ = _fetcher(
            lambda *args: [_record("93.184.216.34")],
            [
                FakeSocket(
                    _response(
                        200,
                        headers=f"Content-Type: text/html\r\nContent-Length: {content_length}\r\n",
                    )
                )
            ],
        )
        with pytest.raises(SafeFetchError, match="malformed"):
            malformed.fetch_html("http://papers.example/paper", license_name="cc-by")

    not_html, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"%PDF", "Content-Type: application/pdf\r\n"))],
    )
    with pytest.raises(SafeFetchError, match="Only HTML"):
        not_html.fetch_html("http://papers.example/paper", license_name="cc-by")


def test_html_parser_skips_active_content_and_caps_text():
    paragraphs, truncated = extract_html_paragraphs(
        "<script>steal()</script><style>.x{}</style><p>Visible text</p><p>Second paragraph</p>",
        max_characters=18,
    )
    text = " ".join(paragraphs)
    assert "steal" not in text
    assert "Visible" in text
    assert truncated


def test_html_parser_prefers_article_body_over_navigation_that_fills_the_text_cap():
    navigation = " ".join(f"Section {index} navigation item." for index in range(80))
    html = (
        f"<nav><p>{navigation}</p></nav>"
        "<main><article><h1>Offshore energy study</h1>"
        "<section><h2>Methods</h2><p>Researchers compared three operating projects.</p></section>"
        "<section><h2>Results</h2><p>Grid connection constraints delayed deployment.</p></section>"
        "</article></main><footer><p>Cookie settings and site links.</p></footer>"
    )

    paragraphs, truncated = extract_html_paragraphs(html, max_characters=160)

    text = "\n".join(paragraphs)
    assert "Researchers compared three operating projects." in text
    assert "Grid connection constraints delayed deployment." in text
    assert "navigation item" not in text
    assert "Cookie settings" not in text
    assert not truncated


def test_rejects_other_schemes_credentials_and_compressed_content():
    fetcher, _ = _fetcher(lambda *args: [], [])
    for url in (
        "file:///etc/passwd",
        "ftp://papers.example/paper",
        "https://user:pass@papers.example/",
    ):
        with pytest.raises(SafeFetchError):
            fetcher.fetch_html(url, license_name="cc-by")

    compressed, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [
            FakeSocket(
                _response(
                    200,
                    b"gzip",
                    "Content-Type: text/html\r\nContent-Encoding: gzip\r\n",
                )
            )
        ],
    )
    with pytest.raises(SafeFetchError, match="Compressed"):
        compressed.fetch_html("http://papers.example/paper", license_name="cc-by")


@pytest.mark.parametrize(
    "url",
    [
        "http://papers.example:8080/paper",
        "https://papers.example:8443/paper",
    ],
)
def test_unreviewed_nonstandard_ports_are_rejected_before_dns(url):
    resolved = []
    fetcher, source_calls = _fetcher(
        lambda host, port, kind: resolved.append((host, port)) or [_record("93.184.216.34")],
        [],
    )

    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html(url, license_name="cc-by")

    assert error.value.code == "unreviewed_port"
    assert resolved == []
    assert source_calls == []


def test_explicit_default_port_remains_accepted():
    body = b"<p>Standard service port.</p>"
    resolved = []
    fetcher, _ = _fetcher(
        lambda host, port, kind: resolved.append((host, port)) or [_record("93.184.216.34")],
        [FakeSocket(_response(200, body, "Content-Type: text/html\r\n"))],
    )

    document = fetcher.fetch_html("http://papers.example:80/paper", license_name="cc-by")

    assert document.text == "Standard service port."
    assert resolved == [("papers.example", 80), ("papers.example", 80)]


def test_content_redirect_to_unreviewed_port_is_rejected_before_target_dns():
    resolved = []
    fetcher, source_calls = _fetcher(
        lambda host, port, kind: resolved.append((host, port)) or [_record("93.184.216.34")],
        [FakeSocket(_response(302, headers="Location: https://papers.example:8443/paper\r\n"))],
    )

    with pytest.raises(SafeFetchError) as error:
        fetcher.fetch_html("https://papers.example/doi", license_name="cc-by")

    assert error.value.code == "unreviewed_port"
    assert resolved == [("papers.example", 443), ("papers.example", 443)]
    assert len(source_calls) == 1


def test_robots_redirect_to_unreviewed_port_is_rejected_before_target_dns():
    resolved = []
    fetcher, source_calls = _fetcher(
        lambda host, port, kind: resolved.append((host, port)) or [_record("93.184.216.34")],
        [],
        robots_responses=[
            _response(302, headers="Location: https://policy-cdn.example:8443/robots.txt\r\n")
        ],
    )

    with pytest.raises(SafeFetchError):
        fetcher.fetch_html("https://papers.example/paper", license_name="cc-by")

    assert resolved == [("papers.example", 443)]
    assert source_calls == []


def test_body_socket_timeout_is_reported_as_a_sanitized_fetch_error():
    class TimeoutBody(BytesIO):
        def read(self, size=-1):
            raise TimeoutError("secret internal socket detail")

    class TimeoutSocket(FakeSocket):
        def makefile(self, mode):
            return TimeoutBody(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")

    fetcher, _ = _fetcher(lambda *args: [_record("93.184.216.34")], [TimeoutSocket(b"")])
    with pytest.raises(SafeFetchError) as caught:
        fetcher.fetch_html("http://papers.example/paper", license_name="cc-by")
    assert caught.value.code == "timeout"
    assert "secret internal" not in str(caught.value)
