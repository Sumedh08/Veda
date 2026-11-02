import httpx
import pytest

from app.research.grobid import GrobidClient, GrobidError

TEI = b"""<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body>
<div><head>Methods</head><p>Participants were assigned by a random process.</p></div>
<div><head>Results</head><p>The measured completion time was lower.</p></div>
</body></text></TEI>"""


def test_grobid_requests_version_then_bounded_structured_tei_without_consolidation():
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/api/version"):
            return httpx.Response(200, text="0.9.1-abc123")
        return httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            content=TEI,
        )

    client = GrobidClient(transport=httpx.MockTransport(respond))
    parsed = client.parse_pdf(b"%PDF-1.7 bounded", timeout_seconds=2)

    assert parsed.parser_version == "0.9.1-abc123"
    assert parsed.structured_document.representation_format == "tei"
    assert [item.normalized_type for item in parsed.structured_document.sections] == [
        "methods",
        "results",
    ]
    assert [request.method for request in requests] == ["GET", "POST"]
    request = requests[1]
    assert request.url.path == "/api/processFulltextDocument"
    assert 'name="consolidateHeader"\r\n\r\n0' in request.content.decode("latin-1")
    assert 'name="consolidateCitations"\r\n\r\n0' in request.content.decode("latin-1")
    assert b"%PDF-1.7 bounded" in request.content


@pytest.mark.parametrize(
    ("status", "expected"),
    [(204, "grobid_no_content"), (400, "grobid_bad_request"), (503, "grobid_busy")],
)
def test_grobid_http_failures_are_classified_without_retry(status, expected):
    requests = []

    def respond(request):
        requests.append(request)
        return (
            httpx.Response(200, text="0.9.1") if request.method == "GET" else httpx.Response(status)
        )

    client = GrobidClient(transport=httpx.MockTransport(respond))
    with pytest.raises(GrobidError) as error:
        client.parse_pdf(b"%PDF-1.7 bounded", timeout_seconds=2)

    assert error.value.code == expected
    assert len(requests) == 2


def test_grobid_rejects_non_loopback_service_before_network_access():
    with pytest.raises(GrobidError, match="loopback"):
        GrobidClient(base_url="http://grobid.example:8070")


def test_grobid_rejects_invalid_pdf_and_oversized_or_non_xml_responses():
    client = GrobidClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(GrobidError) as invalid_pdf:
        client.parse_pdf(b"not a PDF", timeout_seconds=2)
    assert invalid_pdf.value.code == "invalid_pdf_signature"

    def invalid_xml(request):
        if request.method == "GET":
            return httpx.Response(200, text="0.9.1")
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="not TEI")

    client = GrobidClient(transport=httpx.MockTransport(invalid_xml))
    with pytest.raises(GrobidError) as bad_type:
        client.parse_pdf(b"%PDF-1.7 bounded", timeout_seconds=2)
    assert bad_type.value.code == "grobid_unexpected_media_type"

    def malformed(request):
        if request.method == "GET":
            return httpx.Response(200, text="0.9.1")
        return httpx.Response(200, headers={"content-type": "application/xml"}, content=b"<TEI>")

    client = GrobidClient(transport=httpx.MockTransport(malformed))
    with pytest.raises(GrobidError) as bad_xml:
        client.parse_pdf(b"%PDF-1.7 bounded", timeout_seconds=2)
    assert bad_xml.value.code == "grobid_invalid_tei"


def test_grobid_transport_timeout_is_sanitized_and_does_not_retry():
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, text="0.9.1")
        raise httpx.ReadTimeout("timeout detail containing untrusted data", request=request)

    client = GrobidClient(transport=httpx.MockTransport(respond))
    with pytest.raises(GrobidError) as error:
        client.parse_pdf(b"%PDF-1.7 bounded", timeout_seconds=2)
    assert error.value.code == "grobid_transport_timeout"
    assert "untrusted data" not in str(error.value)
    assert len(requests) == 2
