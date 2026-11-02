"""Optional, loopback-only adapter for the GROBID full-text PDF endpoint.

The caller must already have made a source-specific rights decision and safely
retrieved the PDF. This module sends that bounded PDF to a local GROBID service,
validates its TEI output with Veda's parser, and never persists raw documents.
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.research.safe_fetch import SafeFetchError
from app.research.structured_documents import (
    MAX_STRUCTURED_DOCUMENT_BYTES,
    StructuredDocument,
    StructuredDocumentError,
    parse_structured_document,
)

MAX_GROBID_RESPONSE_BYTES = MAX_STRUCTURED_DOCUMENT_BYTES
MAX_GROBID_VERSION_BYTES = 256
MAX_GROBID_PDF_BYTES = 8_000_000
MAX_GROBID_REQUEST_SECONDS = 8.0
GROBID_PARSER_NAME = "grobid"


class GrobidError(SafeFetchError):
    """Sanitized local parser failure with a stable, safe error code."""


@dataclass(frozen=True)
class GrobidParseResult:
    structured_document: StructuredDocument
    parser_name: str
    parser_version: str


class GrobidClient:
    """Parse a licensed PDF through an explicitly enabled local GROBID service.

    Only literal IPv4/IPv6 loopback URLs are accepted, redirects are disabled,
    and uncertain POSTs are never retried. The service-version lookup is
    best-effort; parsing remains possible with an explicit `unreported` version.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8070",
        transport: httpx.BaseTransport | None = None,
        max_response_bytes: int = MAX_GROBID_RESPONSE_BYTES,
        request_seconds: float = MAX_GROBID_REQUEST_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.max_response_bytes = min(max(1, max_response_bytes), MAX_GROBID_RESPONSE_BYTES)
        self.request_seconds = min(max(request_seconds, 0.1), MAX_GROBID_REQUEST_SECONDS)
        self._validate_base_url()

    def parse_pdf(self, pdf_bytes: bytes, *, timeout_seconds: float) -> GrobidParseResult:
        if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
            raise GrobidError(
                "invalid_pdf_signature", "The source does not contain a valid PDF header."
            )
        if len(pdf_bytes) > MAX_GROBID_PDF_BYTES:
            raise GrobidError("response_too_large", "The PDF exceeds the byte limit.")

        deadline = time.monotonic() + min(max(0.0, timeout_seconds), self.request_seconds)
        with httpx.Client(
            transport=self.transport,
            timeout=self._timeout(deadline),
            follow_redirects=False,
            trust_env=False,
            headers={"Accept-Encoding": "identity"},
        ) as client:
            version = self._service_version(client, deadline)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GrobidError(
                    "grobid_transport_timeout", "GROBID parsing exceeded its time limit."
                )
            try:
                with client.stream(
                    "POST",
                    f"{self.base_url}/api/processFulltextDocument",
                    files={"input": ("source.pdf", pdf_bytes, "application/pdf")},
                    data={"consolidateHeader": "0", "consolidateCitations": "0"},
                    headers={"Accept": "application/xml"},
                    timeout=self._timeout(deadline),
                ) as response:
                    self._check_status(response.status_code)
                    media_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if media_type.casefold().strip() not in {
                        "application/xml",
                        "text/xml",
                    }:
                        raise GrobidError(
                            "grobid_unexpected_media_type",
                            "GROBID did not return an XML document.",
                        )
                    tei_bytes = self._read_bounded(response, deadline)
            except httpx.TimeoutException:
                raise GrobidError(
                    "grobid_transport_timeout", "GROBID parsing exceeded its time limit."
                ) from None
            except httpx.RequestError:
                raise GrobidError(
                    "grobid_transport_error", "The local GROBID service could not be reached."
                ) from None

        try:
            structured_document = parse_structured_document(tei_bytes, format_hint="tei")
        except StructuredDocumentError as exc:
            raise GrobidError(
                "grobid_invalid_tei", "GROBID returned TEI that Veda could not validate."
            ) from exc
        return GrobidParseResult(
            structured_document=structured_document,
            parser_name=GROBID_PARSER_NAME,
            parser_version=version,
        )

    def _service_version(self, client: httpx.Client, deadline: float) -> str:
        if deadline - time.monotonic() <= 0:
            return "unreported"
        try:
            with client.stream(
                "GET",
                f"{self.base_url}/api/version",
                headers={"Accept": "text/plain"},
                timeout=self._timeout(deadline),
            ) as response:
                if response.status_code != 200:
                    return "unreported"
                body = self._read_bounded(response, deadline, limit=MAX_GROBID_VERSION_BYTES)
                version = body.decode("utf-8", errors="strict").strip()
                if not version or len(version) > MAX_GROBID_VERSION_BYTES:
                    return "unreported"
                if any(ord(character) < 32 for character in version):
                    return "unreported"
                return version
        except (httpx.RequestError, UnicodeDecodeError, GrobidError):
            return "unreported"

    @staticmethod
    def _check_status(status_code: int) -> None:
        errors = {
            204: ("grobid_no_content", "GROBID could not extract structured content."),
            400: ("grobid_bad_request", "GROBID rejected the PDF request."),
            429: ("grobid_rate_limited", "GROBID is rate limited."),
            500: ("grobid_processing_error", "GROBID could not process this PDF."),
            503: ("grobid_busy", "GROBID is temporarily unavailable or busy."),
        }
        if status_code == 200:
            return
        code, message = errors.get(
            status_code,
            ("grobid_unexpected_status", "GROBID returned an unexpected status."),
        )
        raise GrobidError(code, message)

    def _read_bounded(
        self, response: httpx.Response, deadline: float, *, limit: int | None = None
    ) -> bytes:
        maximum = min(limit or self.max_response_bytes, self.max_response_bytes)
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > maximum:
                    raise GrobidError(
                        "grobid_response_too_large", "GROBID output exceeds the byte limit."
                    )
            except ValueError:
                raise GrobidError(
                    "grobid_invalid_response", "GROBID returned an invalid response."
                ) from None
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                if time.monotonic() >= deadline:
                    raise GrobidError(
                        "grobid_transport_timeout", "GROBID parsing exceeded its time limit."
                    )
                total += len(chunk)
                if total > maximum:
                    raise GrobidError(
                        "grobid_response_too_large", "GROBID output exceeds the byte limit."
                    )
                chunks.append(chunk)
        except httpx.TimeoutException:
            raise
        return b"".join(chunks)

    @staticmethod
    def _timeout(deadline: float) -> httpx.Timeout:
        remaining = max(0.001, deadline - time.monotonic())
        return httpx.Timeout(
            connect=min(2.0, remaining),
            read=remaining,
            write=remaining,
            pool=min(1.0, remaining),
        )

    def _validate_base_url(self) -> None:
        parsed = urlsplit(self.base_url)
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            address = None
        if (
            parsed.scheme != "http"
            or address is None
            or not address.is_loopback
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.port is None
        ):
            raise GrobidError(
                "grobid_service_url_rejected",
                "GROBID must use an HTTP URL with a literal loopback address and port.",
            )


def grobid_fallback_error(exc: Exception) -> str:
    """Return only a stable parser failure class for persisted diagnostics."""
    if isinstance(exc, GrobidError):
        return exc.code
    return "grobid_unexpected_error"
