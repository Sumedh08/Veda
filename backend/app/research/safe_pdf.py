"""Rights- and host-policy-gated bounded PDF download and text extraction.

Downloads reuse the pinned-IP transport from ``safe_fetch``. The in-memory PDF
parser does not execute document actions, attachments, scripts, or embedded files.
"""

import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

from pypdf import PdfReader, apply_configuration
from pypdf.errors import LimitReachedError, PdfReadError

from app.research.grobid import MAX_GROBID_PDF_BYTES, GrobidClient, grobid_fallback_error
from app.research.rights_policy import RightsDecision
from app.research.safe_fetch import (
    MAX_REDIRECTS,
    PERMITTED_LICENSES,
    REDIRECT_STATUSES,
    SafeFetchError,
    SafeHTMLFetcher,
    _is_private_research_decision,
)
from app.research.structured_documents import StructuredDocument

# The prior 8 MB ceiling excluded a preserved institutional PDF lead estimated
# at ~25.7 MB. This remains a hard per-document bound; parsing limits below are
# unchanged, and large bodies are streamed to short-lived storage.
MAX_PDF_BYTES = 32_000_000
MAX_PDF_PAGE_TREE_ENTRIES = 500
MAX_PDF_PAGES = 40
MAX_PDF_PAGE_TEXT_CHARACTERS = 4_000
MAX_PDF_TEXT_CHARACTERS = 60_000
MAX_PDF_STREAM_BYTES = 1_000_000
MAX_PDF_DECODE_WORK = 12_000_000
# PDF retrieval and parsing need more time than the HTML path, but remain
# bounded by a per-document ceiling and the caller's persisted job-step budget.
MAX_PDF_TOTAL_SECONDS = 45.0
MAX_PDF_PARSER_SECONDS = 30.0

try:
    PYPDF_VERSION = package_version("pypdf")
except PackageNotFoundError:
    PYPDF_VERSION = "unreported"


@dataclass(frozen=True)
class SafePDFDocument:
    pages: tuple[tuple[int, str], ...]
    page_count: int | None
    pages_extracted: int
    text_truncated: bool
    sha256: str
    media_type: str
    final_host: str
    retrieved_at: datetime
    host_policy_id: str
    host_terms_url: str
    robots_status: str
    robots_http_status: int | None = None
    structured_document: StructuredDocument | None = None
    parser_name: str = "pypdf"
    parser_version: str | None = None
    grobid_fallback_error: str | None = None


class SafePDFFetcher(SafeHTMLFetcher):
    """Fetch and extract a licensed or rights-policy-approved PDF without retaining bytes."""

    document_byte_limit = MAX_PDF_BYTES

    def __init__(self, *, grobid_client: GrobidClient | None = None, **kwargs) -> None:
        # The inherited HTML fetcher defaults to a smaller HTML ceiling. Keep
        # the PDF path bounded by its own declared cap unless a caller supplies
        # a stricter per-request limit.
        kwargs.setdefault("max_bytes", self.document_byte_limit)
        requested_timeout = kwargs.pop("timeout_seconds", MAX_PDF_TOTAL_SECONDS)
        super().__init__(**kwargs)
        self.timeout_seconds = min(max(0.0, requested_timeout), MAX_PDF_TOTAL_SECONDS)
        self.grobid_client = grobid_client

    def fetch_pdf(
        self,
        url: str,
        *,
        license_name: str | None,
        rights_decision: RightsDecision | None = None,
    ) -> SafePDFDocument:
        license_code = (license_name or "").strip().casefold()
        private_research = license_code not in PERMITTED_LICENSES
        if private_research and not _is_private_research_decision(rights_decision):
            raise SafeFetchError(
                "rights_basis_unresolved",
                "Unlicensed PDF retrieval requires a verified, applicable private-research decision.",
            )
        if not isinstance(url, str) or not url or len(url) > 2000:
            raise SafeFetchError("invalid_url", "The source URL is invalid.")

        deadline = time.monotonic() + self.timeout_seconds
        current_url = url
        original_scheme = ""
        visited: set[str] = set()
        host_policy = None
        robots_status = ""
        for redirect_count in range(min(self.max_redirects, MAX_REDIRECTS) + 1):
            target = self._target(current_url)
            host_policy = self._check_host_policy(
                target, license_code, rights_decision=rights_decision if private_research else None
            )
            robots_policy = self._check_robots(
                target,
                deadline,
                license_code,
                host_policy,
                rights_decision=rights_decision if private_research else None,
            )
            robots_status = robots_policy.status
            if not original_scheme:
                original_scheme = target.scheme
            canonical = f"{target.scheme}://{target.netloc}{target.path}"
            if target.query:
                canonical += f"?{target.query}"
            if canonical in visited:
                raise SafeFetchError("redirect_loop", "The source redirected repeatedly.")
            visited.add(canonical)

            response, sock = self._request(
                target,
                deadline,
                accept_header="application/pdf",
                minimum_interval_seconds=max(
                    host_policy.minimum_interval_seconds,
                    robots_policy.crawl_delay_seconds,
                ),
            )
            try:
                if response.status in REDIRECT_STATUSES:
                    location = response.getheader("Location")
                    if not location or redirect_count >= self.max_redirects:
                        raise SafeFetchError(
                            "redirect_limit", "The source exceeded the redirect limit."
                        )
                    next_url = urljoin(canonical, location)
                    next_target = self._target(next_url)
                    if original_scheme == "https" and next_target.scheme != "https":
                        raise SafeFetchError(
                            "redirect_downgrade", "HTTPS redirects cannot downgrade to HTTP."
                        )
                    current_url = next_url
                    continue
                if response.status != 200:
                    raise SafeFetchError(
                        "http_status", "The source did not return a successful response."
                    )

                media_type = response.headers.get_content_type().lower()
                if media_type != "application/pdf":
                    raise SafeFetchError(
                        "unsupported_media_type", "The source did not return a PDF document."
                    )
                content_encoding = (
                    response.getheader("Content-Encoding", "identity") or "identity"
                ).lower()
                if content_encoding not in {"", "identity"}:
                    raise SafeFetchError(
                        "unsupported_content_encoding",
                        "Compressed source responses are not accepted.",
                    )
                content_length = response.getheader("Content-Length")
                if content_length:
                    try:
                        parsed_length = int(content_length)
                        if parsed_length < 0:
                            raise ValueError
                        if parsed_length > self.max_bytes:
                            raise SafeFetchError(
                                "response_too_large", "The PDF exceeds the byte limit."
                            )
                    except ValueError:
                        raise SafeFetchError(
                            "invalid_response", "The source response is malformed."
                        ) from None

                try:
                    temp_directory = tempfile.TemporaryDirectory(prefix="veda-pdf-")
                except OSError:
                    raise SafeFetchError(
                        "temporary_storage_unavailable",
                        "Temporary storage for safe PDF processing is unavailable.",
                    ) from None
                try:
                    with temp_directory as temp_dir:
                        pdf_path = Path(temp_dir) / "source.pdf"
                        document_sha256, document_size = self._stream_pdf_to_file(
                            response, sock, deadline, pdf_path
                        )
                        parser_timeout = min(
                            MAX_PDF_PARSER_SECONDS,
                            max(0.0, deadline - time.monotonic()),
                        )
                        if parser_timeout <= 0:
                            raise SafeFetchError(
                                "timeout", "Source retrieval exceeded the time limit."
                            )
                        grobid_error = None
                        if self.grobid_client is not None:
                            if document_size > MAX_GROBID_PDF_BYTES:
                                grobid_error = "grobid_input_size_limit"
                            else:
                                try:
                                    grobid_result = self.grobid_client.parse_pdf(
                                        pdf_path.read_bytes(), timeout_seconds=parser_timeout
                                    )
                                except Exception as exc:
                                    grobid_error = grobid_fallback_error(exc)
                                else:
                                    return SafePDFDocument(
                                        pages=(),
                                        page_count=None,
                                        pages_extracted=0,
                                        text_truncated=bool(
                                            grobid_result.structured_document.extraction_warnings
                                        ),
                                        sha256=document_sha256,
                                        media_type=media_type,
                                        final_host=target.host,
                                        retrieved_at=datetime.now(UTC),
                                        host_policy_id=host_policy.policy_id,
                                        host_terms_url=host_policy.terms_url,
                                        robots_status=robots_status,
                                        robots_http_status=robots_policy.http_status_code,
                                        structured_document=grobid_result.structured_document,
                                        parser_name=grobid_result.parser_name,
                                        parser_version=grobid_result.parser_version,
                                    )
                                parser_timeout = max(0.0, deadline - time.monotonic())
                                if parser_timeout <= 0:
                                    raise SafeFetchError(
                                        "pdf_parser_timeout",
                                        "PDF text extraction exceeded its time limit.",
                                    )
                        pages, page_count, text_truncated = extract_pdf_pages_from_file(
                            pdf_path, timeout_seconds=parser_timeout
                        )
                        return SafePDFDocument(
                            pages=pages,
                            page_count=page_count,
                            pages_extracted=len(pages),
                            text_truncated=text_truncated,
                            sha256=document_sha256,
                            media_type=media_type,
                            final_host=target.host,
                            retrieved_at=datetime.now(UTC),
                            host_policy_id=host_policy.policy_id,
                            host_terms_url=host_policy.terms_url,
                            robots_status=robots_status,
                            robots_http_status=robots_policy.http_status_code,
                            parser_name="pypdf",
                            parser_version=PYPDF_VERSION,
                            grobid_fallback_error=grobid_error,
                        )
                except TimeoutError:
                    raise SafeFetchError(
                        "timeout", "Source retrieval exceeded the time limit."
                    ) from None
                except OSError:
                    raise SafeFetchError(
                        "network_error", "The public source could not be retrieved safely."
                    ) from None
                except http.client.HTTPException:
                    raise SafeFetchError(
                        "network_error", "The public source returned a malformed response."
                    ) from None
            finally:
                response.close()
                sock.close()
        raise SafeFetchError("redirect_limit", "The source exceeded the redirect limit.")

    def _stream_pdf_to_file(
        self,
        response: http.client.HTTPResponse,
        sock,
        deadline: float,
        path: Path,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        signature = bytearray()
        total = 0
        try:
            output = path.open("xb")
        except OSError:
            raise SafeFetchError(
                "temporary_storage_unavailable",
                "Temporary storage for safe PDF processing is unavailable.",
            ) from None
        try:
            with output:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        sock.settimeout(remaining)
                        chunk = response.read(min(64_000, self.max_bytes - total + 1))
                    except TimeoutError:
                        raise
                    except (OSError, http.client.HTTPException):
                        raise SafeFetchError(
                            "network_error", "The public source could not be retrieved safely."
                        ) from None
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise SafeFetchError(
                            "response_too_large", "The PDF exceeds the byte limit."
                        )
                    if len(signature) < 1024:
                        signature.extend(chunk[: 1024 - len(signature)])
                    digest.update(chunk)
                    try:
                        output.write(chunk)
                    except OSError:
                        raise SafeFetchError(
                            "temporary_storage_unavailable",
                            "Temporary storage for safe PDF processing is unavailable.",
                        ) from None
        except SafeFetchError:
            raise
        except OSError:
            # This catches buffered flush/close errors after successful writes.
            raise SafeFetchError(
                "temporary_storage_unavailable",
                "Temporary storage for safe PDF processing is unavailable.",
            ) from None
        if b"%PDF-" not in signature:
            raise SafeFetchError(
                "invalid_pdf_signature", "The source does not contain a valid PDF header."
            )
        return digest.hexdigest(), total


def extract_pdf_pages(
    data: bytes, *, timeout_seconds: float = MAX_PDF_PARSER_SECONDS
) -> tuple[tuple[tuple[int, str], ...], int, bool]:
    """Extract text in a short-lived worker with parser and wall-clock limits."""
    if len(data) > MAX_PDF_BYTES:
        raise SafeFetchError("response_too_large", "The PDF exceeds the byte limit.")
    process = _run_pdf_worker(input_data=data, timeout_seconds=timeout_seconds)
    return _validated_pdf_worker_result(process)


def extract_pdf_pages_from_file(
    path: str | Path, *, timeout_seconds: float = MAX_PDF_PARSER_SECONDS
) -> tuple[tuple[tuple[int, str], ...], int, bool]:
    """Parse a bounded temporary PDF by path without duplicating it in the parent process."""
    pdf_path = Path(path)
    try:
        size = pdf_path.stat().st_size
        if not pdf_path.is_file() or size <= 0 or size > MAX_PDF_BYTES:
            raise SafeFetchError("response_too_large", "The PDF exceeds the byte limit.")
        with pdf_path.open("rb") as pdf_file:
            signature = pdf_file.read(1024)
        if b"%PDF-" not in signature:
            raise SafeFetchError(
                "invalid_pdf_signature", "The source does not contain a valid PDF header."
            )
    except SafeFetchError:
        raise
    except OSError:
        raise SafeFetchError(
            "pdf_input_unavailable", "The temporary PDF could not be read safely."
        ) from None
    process = _run_pdf_worker(input_path=pdf_path, timeout_seconds=timeout_seconds)
    return _validated_pdf_worker_result(process)


def _run_pdf_worker(
    *,
    timeout_seconds: float,
    input_data: bytes | None = None,
    input_path: Path | None = None,
) -> subprocess.CompletedProcess:
    if (input_data is None) == (input_path is None):
        raise ValueError("exactly one PDF worker input is required")
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
        if os.environ.get(name)
    }
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(entry for entry in sys.path if entry)
    command = [sys.executable, "-m", "app.research.pdf_worker"]
    if input_path is not None:
        command.extend(("--input-file", str(input_path.resolve())))
    try:
        process = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            timeout=min(MAX_PDF_PARSER_SECONDS, max(0.0, timeout_seconds)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SafeFetchError(
            "pdf_parser_timeout", "PDF text extraction exceeded its time limit."
        ) from None
    except OSError:
        raise SafeFetchError(
            "pdf_parser_unavailable", "PDF text extraction could not be started."
        ) from None
    return process


def _validated_pdf_worker_result(
    process: subprocess.CompletedProcess,
) -> tuple[tuple[tuple[int, str], ...], int, bool]:
    try:
        result = json.loads(process.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeFetchError(
            "pdf_parser_error", "The PDF parser returned no valid result."
        ) from None
    if not isinstance(result, dict):
        raise SafeFetchError("pdf_parser_error", "The PDF parser returned no valid result.")
    if process.returncode != 0 or result.get("ok") is not True:
        error_code = result.get("error_code")
        messages = {
            "encrypted_pdf": "Password-protected PDFs are not processed.",
            "empty_pdf_text": "No extractable text was found; scanned pages are not OCR-processed.",
            "invalid_pdf": "The PDF could not be safely parsed.",
            "pdf_parser_error": "The PDF parser rejected the document safely.",
            "pdf_parser_limit": "The PDF exceeded a safe parser resource limit.",
            "response_too_large": "The PDF exceeds the byte limit.",
        }
        if error_code not in messages:
            error_code = "pdf_parser_error"
        raise SafeFetchError(error_code, messages[error_code])

    raw_pages = result.get("pages")
    page_count = result.get("page_count")
    truncated = result.get("truncated")
    if (
        not isinstance(raw_pages, list)
        or not 0 < len(raw_pages) <= MAX_PDF_PAGES
        or not isinstance(page_count, int)
        or isinstance(page_count, bool)
        or not 1 <= page_count <= MAX_PDF_PAGE_TREE_ENTRIES
        or not isinstance(truncated, bool)
    ):
        raise SafeFetchError("pdf_parser_error", "The PDF parser returned an invalid result.")
    pages: list[tuple[int, str]] = []
    total_characters = 0
    previous_page = 0
    for item in raw_pages:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], int)
            or isinstance(item[0], bool)
            or not previous_page < item[0] <= page_count
            or not isinstance(item[1], str)
            or len(item[1]) > MAX_PDF_PAGE_TEXT_CHARACTERS
        ):
            raise SafeFetchError("pdf_parser_error", "The PDF parser returned an invalid result.")
        total_characters += len(item[1])
        if total_characters > MAX_PDF_TEXT_CHARACTERS:
            raise SafeFetchError("pdf_parser_error", "The PDF parser returned an invalid result.")
        pages.append((item[0], item[1]))
        previous_page = item[0]
    return tuple(pages), page_count, truncated


def extract_pdf_pages_in_worker(data: bytes) -> tuple[tuple[tuple[int, str], ...], int, bool]:
    """Worker entry point; never pass through the subprocess wrapper."""
    return _extract_pdf_pages_from_stream(BytesIO(data))


def extract_pdf_pages_from_file_in_worker(
    path: str | Path,
) -> tuple[tuple[tuple[int, str], ...], int, bool]:
    """Worker entry point for a parent-created bounded temporary PDF file."""
    pdf_path = Path(path)
    try:
        size = pdf_path.stat().st_size
        if not pdf_path.is_file() or size <= 0 or size > MAX_PDF_BYTES:
            raise SafeFetchError("response_too_large", "The PDF exceeds the byte limit.")
        with pdf_path.open("rb") as stream:
            if b"%PDF-" not in stream.read(1024):
                raise SafeFetchError(
                    "invalid_pdf_signature", "The source does not contain a valid PDF header."
                )
            stream.seek(0)
            return _extract_pdf_pages_from_stream(stream)
    except SafeFetchError:
        raise
    except OSError:
        raise SafeFetchError(
            "pdf_input_unavailable", "The temporary PDF could not be read safely."
        ) from None


def _extract_pdf_pages_from_stream(stream) -> tuple[tuple[tuple[int, str], ...], int, bool]:
    try:
        with apply_configuration(
            maximum_declared_stream_length=MAX_PDF_STREAM_BYTES,
            array_based_stream_maximum_output_length=MAX_PDF_STREAM_BYTES,
            array_maximum_element_count=10_000,
            dictionary_maximum_element_count=10_000,
            jbig2_maximum_output_length=MAX_PDF_STREAM_BYTES,
            lzw_maximum_output_length=MAX_PDF_STREAM_BYTES,
            run_length_maximum_output_length=MAX_PDF_STREAM_BYTES,
            zlib_maximum_output_length=MAX_PDF_STREAM_BYTES,
            zlib_maximum_recovery_input_length=MAX_PDF_STREAM_BYTES,
            brotli_maximum_output_length=MAX_PDF_STREAM_BYTES,
            flate_maximum_columns=100_000,
            flate_maximum_row_length=MAX_PDF_STREAM_BYTES,
            image_maximum_buffer_size=MAX_PDF_STREAM_BYTES,
            stream_filters_maximum_length=8,
            stream_decoding_work_maximum_length=MAX_PDF_DECODE_WORK,
            stream_parsing_work_maximum_count=500_000,
            xmp_maximum_input_length=250_000,
            xmp_maximum_element_count=2_000,
            outline_maximum_entries=1_000,
            outline_maximum_depth=20,
            page_tree_maximum_entries=MAX_PDF_PAGE_TREE_ENTRIES,
            page_tree_maximum_depth=30,
            page_tree_maximum_page_entries=MAX_PDF_PAGE_TREE_ENTRIES,
            form_fields_maximum_entries=1_000,
            form_fields_maximum_depth=20,
            xform_maximum_invocations_per_extraction=100,
            disable_legacy_handling=True,
        ):
            reader = PdfReader(
                stream,
                strict=True,
                root_object_recovery_limit=2_000,
                xref_stream_maximum_entries=50_000,
            )
            try:
                if reader.is_encrypted:
                    raise SafeFetchError(
                        "encrypted_pdf", "Password-protected PDFs are not processed."
                    )
                page_count = len(reader.pages)
                text_pages: list[tuple[int, str]] = []
                total_characters = 0
                truncated = page_count > MAX_PDF_PAGES
                for page_index in range(min(page_count, MAX_PDF_PAGES)):
                    remaining = MAX_PDF_TEXT_CHARACTERS - total_characters
                    if remaining <= 0:
                        truncated = True
                        break
                    page_text = reader.pages[page_index].extract_text(extraction_mode="plain") or ""
                    if len(page_text) > MAX_PDF_PAGE_TEXT_CHARACTERS:
                        page_text = page_text[:MAX_PDF_PAGE_TEXT_CHARACTERS]
                        truncated = True
                    if len(page_text) > remaining:
                        page_text = page_text[:remaining]
                        truncated = True
                    cleaned = re.sub(r"\x00", "", page_text).strip()
                    if cleaned:
                        text_pages.append((page_index + 1, cleaned))
                        total_characters += len(cleaned)
                if not text_pages:
                    raise SafeFetchError(
                        "empty_pdf_text",
                        "No extractable text was found; scanned pages are not OCR-processed.",
                    )
                return tuple(text_pages), page_count, truncated
            finally:
                reader.close()
    except SafeFetchError:
        raise
    except LimitReachedError:
        raise SafeFetchError(
            "pdf_parser_limit", "The PDF exceeded a safe parser resource limit."
        ) from None
    except (PdfReadError, ValueError, TypeError, KeyError, IndexError, RecursionError):
        raise SafeFetchError("invalid_pdf", "The PDF could not be safely parsed.") from None
    except Exception:
        raise SafeFetchError(
            "pdf_parser_error", "The PDF parser rejected the document safely."
        ) from None
