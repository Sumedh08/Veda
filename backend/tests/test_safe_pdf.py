import json
import socket
import subprocess
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from app.research import safe_pdf
from app.research.retrieval_rights import ReviewedHostPolicy
from app.research.safe_fetch import SafeFetchError
from app.research.safe_pdf import (
    MAX_PDF_BYTES,
    MAX_PDF_PAGE_TEXT_CHARACTERS,
    MAX_PDF_PAGES,
    SafePDFFetcher,
    extract_pdf_pages,
)


def _pdf(pages: list[str]) -> bytes:
    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{3 + index} 0 R" for index in range(len(pages)))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    font_id = 3 + len(pages)
    objects[font_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for index, text in enumerate(pages):
        page_id = 3 + index
        content_id = font_id + 1 + index
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content = f"BT /F1 12 Tf 40 200 Td ({escaped}) Tj ET".encode("ascii")
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode()
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        )

    data = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (max(objects) + 1)
    for object_id, body in sorted(objects.items()):
        offsets[object_id] = len(data)
        data.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for object_id in range(1, len(offsets)):
        data.extend(f"{offsets[object_id]:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Root 1 0 R /Size {len(offsets)} >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(data)


def _response(status: int, body: bytes = b"", headers: str = "") -> bytes:
    return f"HTTP/1.1 {status} Test\r\n{headers}Connection: close\r\n\r\n".encode() + body


def _record(ip: str):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))


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
    def __init__(self, address, content_sockets, source_calls, robots_body):
        self.address = address
        self.content_sockets = content_sockets
        self.source_calls = source_calls
        self.robots_body = robots_body
        self.delegate = None

    def settimeout(self, timeout):
        if self.delegate:
            self.delegate.settimeout(timeout)

    def sendall(self, request: bytes):
        if b"Accept: text/plain" in request:
            self.delegate = FakeSocket(
                _response(
                    200,
                    self.robots_body,
                    "Content-Type: text/plain; charset=utf-8\r\n",
                )
            )
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
    max_bytes=MAX_PDF_PAGE_TEXT_CHARACTERS * 100,
    robots_body=b"User-agent: *\nAllow: /\n",
    host_policy_checker=None,
    host_minimum_interval=0.0,
    origin_request_limiter=None,
    grobid_client=None,
    timeout_seconds=45,
):
    calls = []

    def connect(address, *, timeout):
        return RoutedSocket(address, sockets, calls, robots_body)

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

    fetcher = SafePDFFetcher(
        resolver=resolver,
        connector=connect,
        ssl_context=FakeTLSContext(),
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
        host_policy_checker=host_policy_checker,
        origin_request_limiter=origin_request_limiter,
        grobid_client=grobid_client,
    )
    return fetcher, calls


class RecordingOriginLimiter:
    def __init__(self):
        self.calls = []

    def acquire(self, origin, interval_seconds, *, deadline):
        self.calls.append((origin, interval_seconds))


def test_pdf_fetch_deadline_is_separate_from_the_short_html_deadline():
    fetcher, _ = _fetcher(lambda *args: [], [])

    assert fetcher.timeout_seconds == 45

    bounded, _ = _fetcher(lambda *args: [], [], timeout_seconds=32)
    assert bounded.timeout_seconds == 32

    stage_bounded, _ = _fetcher(lambda *args: [], [], timeout_seconds=12)
    assert stage_bounded.timeout_seconds == 12

    capped, _ = _fetcher(lambda *args: [], [], timeout_seconds=60)
    assert capped.timeout_seconds == 45
    assert safe_pdf.MAX_PDF_PARSER_SECONDS == 30


def test_default_pdf_fetch_limit_uses_pdf_cap_not_html_default(monkeypatch):
    body_size = 2_100_000
    body = b"%PDF-1.4\n" + b" " * (body_size - len(b"%PDF-1.4\n"))
    source = FakeSocket(
        _response(
            200,
            body,
            f"Content-Type: application/pdf\r\nContent-Length: {len(body)}\r\n",
        )
    )
    calls = []

    def connect(address, *, timeout):
        return RoutedSocket(address, [source], calls, b"User-agent: *\nAllow: /\n")

    def test_host_policy(host, license_code):
        return ReviewedHostPolicy(
            host=host,
            policy_id="fixture-reviewed-host-v1",
            terms_url=f"https://{host}/terms",
            reviewed_at=date.today(),
            licenses=frozenset({license_code}),
        )

    parsed_sizes = []

    def parse_pdf(data, *, timeout_seconds):
        parsed_sizes.append(len(data))
        return ((1, "A permitted research passage."),), 1, False

    monkeypatch.setattr(safe_pdf, "extract_pdf_pages", parse_pdf)
    fetcher = SafePDFFetcher(
        resolver=lambda *args: [_record("93.184.216.34")],
        connector=connect,
        ssl_context=FakeTLSContext(),
        host_policy_checker=test_host_policy,
    )

    document = fetcher.fetch_pdf("https://papers.example/article.pdf", license_name="cc-by")

    assert MAX_PDF_BYTES > body_size > 2_000_000
    assert document.pages == ((1, "A permitted research passage."),)
    assert parsed_sizes == [body_size]


def test_parser_extracts_text_with_page_and_total_character_caps():
    pages, page_count, truncated = extract_pdf_pages(_pdf(["A study reports a measurable effect."]))
    assert page_count == 1
    assert pages == ((1, "A study reports a measurable effect."),)
    assert not truncated

    many_pages, page_count, truncated = extract_pdf_pages(
        _pdf([f"Evidence on page {index}." for index in range(MAX_PDF_PAGES + 2)])
    )
    assert page_count == MAX_PDF_PAGES + 2
    assert len(many_pages) == MAX_PDF_PAGES
    assert truncated

    long_pages, _, truncated = extract_pdf_pages(_pdf(["A" * (MAX_PDF_PAGE_TEXT_CHARACTERS + 200)]))
    assert len(long_pages[0][1]) <= MAX_PDF_PAGE_TEXT_CHARACTERS
    assert truncated


def test_parser_rejects_encrypted_malformed_and_unextractable_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.encrypt("test-password")
    encrypted = BytesIO()
    writer.write(encrypted)
    with pytest.raises(SafeFetchError) as password_error:
        extract_pdf_pages(encrypted.getvalue())
    assert password_error.value.code == "encrypted_pdf"

    with pytest.raises(SafeFetchError) as malformed:
        extract_pdf_pages(b"%PDF-1.4\nnot a PDF object structure")
    assert malformed.value.code in {"invalid_pdf", "pdf_parser_limit"}

    with pytest.raises(SafeFetchError) as no_text:
        extract_pdf_pages(_pdf([""]))
    assert no_text.value.code == "empty_pdf_text"


def test_parser_worker_has_a_hard_deadline_and_does_not_inherit_provider_secrets(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-secret")
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "pages": [[1, "An extracted source statement."]],
                    "page_count": 1,
                    "truncated": False,
                }
            ).encode(),
        )

    monkeypatch.setattr(safe_pdf.subprocess, "run", fake_run)
    pages, page_count, truncated = extract_pdf_pages(b"%PDF-1.4 test fixture")
    assert pages == ((1, "An extracted source statement."),)
    assert page_count == 1
    assert not truncated
    assert captured["timeout"] == safe_pdf.MAX_PDF_PARSER_SECONDS
    assert "OPENROUTER_API_KEY" not in captured["env"]


def test_parser_worker_timeout_is_reported_without_exposing_process_details(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=1, output=b"untrusted parser output")

    monkeypatch.setattr(safe_pdf.subprocess, "run", timeout)
    with pytest.raises(SafeFetchError) as error:
        extract_pdf_pages(b"%PDF-1.4 test fixture")
    assert error.value.code == "pdf_parser_timeout"
    assert "untrusted parser output" not in str(error.value)


def test_fetch_pins_ip_checks_license_mime_and_file_signature():
    body = _pdf(["The source reports a treatment effect."])
    sock = FakeSocket(
        _response(
            200,
            body,
            f"Content-Type: application/pdf\r\nContent-Length: {len(body)}\r\n",
        )
    )
    resolved = []
    fetcher, calls = _fetcher(
        lambda host, port, kind: resolved.append((host, port, kind)) or [_record("93.184.216.34")],
        [sock],
    )
    document = fetcher.fetch_pdf("https://papers.example/article.pdf", license_name="cc-by")
    assert resolved == [
        ("papers.example", 443, socket.SOCK_STREAM),
        ("papers.example", 443, socket.SOCK_STREAM),
    ]
    assert calls == [("93.184.216.34", 443)]
    assert b"Host: papers.example" in sock.request
    assert b"Accept: application/pdf" in sock.request
    assert document.pages[0][1] == "The source reports a treatment effect."
    assert len(document.sha256) == 64
    assert not hasattr(document, "data")
    assert document.host_policy_id == "fixture-reviewed-host-v1"
    assert document.robots_status == "rules_checked"

    unlicensed, unlicensed_calls = _fetcher(lambda *args: pytest.fail("DNS must not run"), [])
    with pytest.raises(SafeFetchError, match="verified, applicable private-research decision"):
        unlicensed.fetch_pdf("https://papers.example/article.pdf", license_name=None)
    assert not unlicensed_calls


def test_unlicensed_pdf_requires_private_research_decision_and_stays_on_verified_domain(
    monkeypatch,
):
    from app.research.rights_policy import RightsContext, evaluate_rights

    body = _pdf(["The report describes a measured policy outcome."])
    source = FakeSocket(
        _response(
            200,
            body,
            f"Content-Type: application/pdf\r\nContent-Length: {len(body)}\r\n",
        )
    )
    decision = evaluate_rights(
        RightsContext(
            source_identity_verified=True,
            publicly_accessible=True,
            document_http_status=200,
            robots_status="rules_checked",
            robots_allows=True,
            site_terms_status="checked_no_restriction_signal",
            use_mode="private_research",
            jurisdiction="IN",
            work_type="institutional_report",
            verified_domains=("papers.example",),
            terms_url="https://papers.example/terms",
        )
    )
    monkeypatch.setattr(
        safe_pdf,
        "extract_pdf_pages",
        lambda *_args, **_kwargs: (
            ((1, "The report describes a measured policy outcome."),),
            1,
            False,
        ),
    )
    fetcher, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [source],
        origin_request_limiter=RecordingOriginLimiter(),
    )

    document = fetcher.fetch_pdf(
        "https://papers.example/report.pdf",
        license_name=None,
        rights_decision=decision,
    )

    assert document.pages == ((1, "The report describes a measured policy outcome."),)
    assert document.host_policy_id == "private-research-v1"
    assert calls == [("93.184.216.34", 443)]

    html, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, body, "Content-Type: text/html\r\n"))],
    )
    with pytest.raises(SafeFetchError) as bad_mime:
        html.fetch_pdf("https://papers.example/article.pdf", license_name="cc0")
    assert bad_mime.value.code == "unsupported_media_type"

    bad_signature, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, b"not-pdf", "Content-Type: application/pdf\r\n"))],
    )
    with pytest.raises(SafeFetchError) as bad_header:
        bad_signature.fetch_pdf("https://papers.example/article.pdf", license_name="cc0")
    assert bad_header.value.code == "invalid_pdf_signature"


def test_pdf_fetcher_uses_grobid_tei_for_sections_and_records_parser_version():
    import httpx

    from app.research.grobid import GrobidClient

    pdf = _pdf(["PDF text is a fallback, not this parser's output."])
    grobid_transport = httpx.MockTransport(
        lambda request: (
            httpx.Response(200, text="0.9.1")
            if request.method == "GET"
            else httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                content=(
                    b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>'
                    b"<div><head>Methods</head><p>Participants completed a randomized task.</p></div>"
                    b"<div><head>Results</head><p>Completion time decreased in the treatment group.</p></div>"
                    b"</body></text></TEI>"
                ),
            )
        )
    )
    grobid = GrobidClient(transport=grobid_transport)
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, pdf, "Content-Type: application/pdf\r\n"))],
        grobid_client=grobid,
    )

    document = fetcher.fetch_pdf("https://papers.example/article.pdf", license_name="cc-by")

    assert document.parser_name == "grobid"
    assert document.parser_version == "0.9.1"
    assert document.page_count is None
    assert document.pages == ()
    assert [item.normalized_type for item in document.structured_document.sections] == [
        "methods",
        "results",
    ]
    assert document.grobid_fallback_error is None


def test_grobid_failure_falls_back_to_bounded_pdf_text_extraction():
    import httpx

    from app.research.grobid import GrobidClient

    pdf = _pdf(["The bounded local PDF parser remains available."])
    grobid = GrobidClient(
        transport=httpx.MockTransport(
            lambda request: (
                httpx.Response(200, text="0.9.1")
                if request.method == "GET"
                else httpx.Response(503)
            )
        )
    )
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, pdf, "Content-Type: application/pdf\r\n"))],
        grobid_client=grobid,
    )

    document = fetcher.fetch_pdf("https://papers.example/article.pdf", license_name="cc-by")

    assert document.parser_name == "pypdf"
    assert document.pages[0][1] == "The bounded local PDF parser remains available."
    assert document.grobid_fallback_error == "grobid_busy"


def test_pdf_redirects_are_revalidated_and_download_is_size_bounded():
    body = _pdf(["Licensed redirected text."])
    first = _response(302, headers="Location: https://repo.example/paper.pdf\r\n")
    second = _response(
        200,
        body,
        f"Content-Type: application/pdf\r\nContent-Length: {len(body)}\r\n",
    )
    resolved = []
    fetcher, calls = _fetcher(
        lambda host, port, kind: resolved.append(host) or [_record("93.184.216.34")],
        [FakeSocket(first), FakeSocket(second)],
    )
    assert fetcher.fetch_pdf("https://publisher.example/file", license_name="cc0").pages
    assert resolved == [
        "publisher.example",
        "publisher.example",
        "repo.example",
        "repo.example",
    ]
    assert len(calls) == 2

    oversized, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [
            FakeSocket(
                _response(200, headers="Content-Type: application/pdf\r\nContent-Length: 99\r\n")
            )
        ],
        max_bytes=16,
    )
    with pytest.raises(SafeFetchError) as too_large:
        oversized.fetch_pdf("https://papers.example/file.pdf", license_name="cc-by")
    assert too_large.value.code == "response_too_large"
    assert len(calls) == 1

    private_redirect, private_calls = _fetcher(
        lambda host, port, kind: [
            _record("93.184.216.34" if host == "publisher.example" else "10.0.0.7")
        ],
        [FakeSocket(_response(302, headers="Location: https://inside.example/file.pdf\r\n"))],
    )
    with pytest.raises(SafeFetchError, match="non-public"):
        private_redirect.fetch_pdf("https://publisher.example/file.pdf", license_name="cc-by")
    assert len(private_calls) == 1


def test_pdf_path_honors_robots_and_requires_each_redirect_host_review():
    pdf_bytes = _pdf(["The PDF must not be retrieved."])
    denied, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, pdf_bytes, "Content-Type: application/pdf\r\n"))],
        robots_body=b"User-agent: *\nDisallow: /private\n",
    )
    with pytest.raises(SafeFetchError) as disallowed:
        denied.fetch_pdf("https://papers.example/private/paper.pdf", license_name="cc-by")
    assert disallowed.value.code == "robots_disallowed"
    assert calls == []

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

    redirected, calls = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(302, headers="Location: https://repo.example/paper.pdf\r\n"))],
        host_policy_checker=policy,
    )
    with pytest.raises(SafeFetchError) as unreviewed:
        redirected.fetch_pdf("https://publisher.example/paper.pdf", license_name="cc-by")
    assert unreviewed.value.code == "host_policy_unknown"
    assert checked_hosts == ["publisher.example", "repo.example"]
    assert len(calls) == 1


def test_robots_crawl_delay_is_scheduled_for_pdf_request():
    from app.research.safe_fetch import SafeHTMLFetcher

    body = _pdf(["The source reports a treatment effect."])
    limiter = RecordingOriginLimiter()
    fetcher, _ = _fetcher(
        lambda *args: [_record("93.184.216.34")],
        [FakeSocket(_response(200, body, "Content-Type: application/pdf\r\n"))],
        robots_body=b"User-agent: *\nAllow: /\nCrawl-delay: 0.2\n",
        origin_request_limiter=limiter,
    )
    assert isinstance(fetcher, SafeHTMLFetcher)

    document = fetcher.fetch_pdf("https://papers.example/article.pdf", license_name="cc-by")

    assert document.pages
    assert limiter.calls == [
        ("https://papers.example", 0),
        ("https://papers.example", 0.2),
    ]
