"""Bounded discovery of public World Bank Documents & Reports metadata.

This adapter searches the official metadata API only. It does not fetch document
content or infer rights to download, retain, or redistribute linked files.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.scholarly import ScholarlyWork

API_URL = "https://search.worldbank.org/api/v3/wds"
API_DOCUMENTATION_URL = "https://documents.worldbank.org/en/publication/documents-reports/api"
MAX_RESPONSE_BYTES = 512_000
MAX_QUERY_CHARS = 300
MAX_RESULTS = 5
MAX_ABSTRACT_CHARS = 600
_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class WorldBankDocumentsError(Exception):
    """Sanitized metadata API failure; response bodies are never included."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        retry_after_seconds: float | None = None,
        request_dispatched: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.request_dispatched = request_dispatched


class _Text(HTMLParser):
    _SKIP = {"script", "style", "iframe", "object", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        folded = tag.casefold()
        if folded in self._SKIP:
            self.skip_depth += 1
        elif self.skip_depth == 0 and folded in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        folded = tag.casefold()
        if folded in self._SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and folded in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)


def _plain_text(value: Any, *, limit: int) -> str | None:
    if isinstance(value, dict):
        value = value.get("cdata!") or value.get("#text")
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _Text()
    try:
        parser.feed(value[:20_000])
        parser.close()
    except Exception:
        return None
    text = " ".join("".join(parser.parts).split())
    return text[:limit].strip() or None


def _official_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2000 or _CONTROL.search(value):
        return None
    try:
        parsed = urlsplit(value.strip())
        _ = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not (host == "worldbank.org" or host.endswith(".worldbank.org"))
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return parsed._replace(scheme="https", netloc=host).geturl()


def _date_year(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).year
    except ValueError:
        return None


def _records(payload: Any, *, query: str, limit: int) -> list[ScholarlyWork]:
    if not isinstance(payload, dict):
        raise WorldBankDocumentsError(
            "World Bank Documents API returned an invalid record set",
            code="invalid_response",
            request_dispatched=True,
        )
    documents = payload.get("documents")
    if not isinstance(documents, dict) or len(documents) > 100:
        raise WorldBankDocumentsError(
            "World Bank Documents API returned an invalid record set",
            code="invalid_response",
            request_dispatched=True,
        )
    rows: list[ScholarlyWork] = []
    for item in list(documents.values())[:limit]:
        if not isinstance(item, dict):
            continue
        document_id = str(item.get("id") or "").strip()
        title = _plain_text(item.get("display_title"), limit=1000)
        if not _DOCUMENT_ID.fullmatch(document_id) or title is None:
            continue
        abstract = _plain_text(item.get("abstracts"), limit=MAX_ABSTRACT_CHARS)
        raw_abstract = item.get("abstracts")
        if isinstance(raw_abstract, dict):
            raw_abstract = raw_abstract.get("cdata!") or raw_abstract.get("#text")
        truncated = (
            isinstance(raw_abstract, str)
            and len(_plain_text(raw_abstract, limit=20_001) or "") > MAX_ABSTRACT_CHARS
        )
        document_url = _official_url(item.get("url"))
        pdf_url = _official_url(item.get("pdfurl"))
        author_value = _plain_text(item.get("authr"), limit=1000)
        authors = [{"name": author_value}] if author_value else []
        metadata = {
            "api_documentation_url": API_DOCUMENTATION_URL,
            "world_bank_document_id": document_id,
            "report_number": _plain_text(item.get("repnb"), limit=100),
            "document_type": _plain_text(item.get("docty"), limit=160),
            "official_document_url": document_url,
            "official_pdf_url": pdf_url,
            "metadata_access": "public_official_api",
            "metadata_reuse_rights_status": "not_assessed",
            "full_text_retrieved": False,
            "full_text_rights_status": "not_assessed",
            "abstract_excerpt_truncated": truncated,
        }
        rows.append(
            ScholarlyWork(
                external_id=f"worldbank:{document_id}",
                title=title,
                doi=None,
                url=document_url,
                authors=authors,
                published_year=_date_year(item.get("docdt")),
                publisher="World Bank Group",
                abstract_excerpt=abstract,
                query=query,
                provider="World Bank Documents & Reports",
                provider_metadata=metadata,
                source_type="institutional_report",
            )
        )
    return rows


class WorldBankDocumentsProvider:
    """Search a single official metadata page, without fetching linked document bytes."""

    provider_name = "World Bank Documents & Reports"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=False,
            headers={"User-Agent": "Veda research metadata client"},
        )
        self._owns_client = client is None
        self._before_request = before_request

    def search(self, query: str, *, limit: int = MAX_RESULTS) -> list[ScholarlyWork]:
        normalized = " ".join(query.split()) if isinstance(query, str) else ""
        if (
            not normalized
            or len(normalized) > MAX_QUERY_CHARS
            or _CONTROL.search(normalized)
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
        ):
            raise WorldBankDocumentsError(
                "World Bank document query is outside its configured bounds",
                code="invalid_query",
            )
        capped = min(limit, MAX_RESULTS)
        params = {
            "format": "json",
            "qterm": normalized,
            "rows": capped,
            "os": 0,
            "fl": "docdt,docty,display_title,abstracts,pdfurl,url,id,repnb,authr",
        }
        if self._before_request is not None:
            self._before_request()
        try:
            with self._client.stream("GET", API_URL, params=params) as response:
                if (
                    response.url.host != "search.worldbank.org"
                    or response.url.path != "/api/v3/wds"
                ):
                    raise WorldBankDocumentsError(
                        "World Bank document API returned an unexpected origin",
                        code="unexpected_origin",
                        request_dispatched=True,
                    )
                if response.is_redirect:
                    raise WorldBankDocumentsError(
                        "World Bank document API redirect was rejected",
                        code="redirect_rejected",
                        request_dispatched=True,
                    )
                if response.status_code == 429:
                    try:
                        retry_after = min(
                            300.0,
                            max(0.0, float(response.headers.get("Retry-After", ""))),
                        )
                    except (TypeError, ValueError):
                        retry_after = None
                    raise WorldBankDocumentsError(
                        "World Bank document API rate limit was reached",
                        code="rate_limited",
                        retry_after_seconds=retry_after,
                        request_dispatched=True,
                    )
                if response.status_code >= 400:
                    raise WorldBankDocumentsError(
                        "World Bank document API returned an unsuccessful status",
                        code=f"http_{response.status_code}",
                        request_dispatched=True,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise WorldBankDocumentsError(
                            "World Bank document API response exceeded its size limit",
                            code="too_large",
                            request_dispatched=True,
                        )
        except httpx.TimeoutException as exc:
            raise WorldBankDocumentsError(
                "World Bank document metadata request timed out",
                code="timeout",
                request_dispatched=True,
            ) from exc
        except httpx.RequestError as exc:
            raise WorldBankDocumentsError(
                "World Bank document metadata request failed",
                code="request_failed",
                request_dispatched=True,
            ) from exc
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WorldBankDocumentsError(
                "World Bank document API response was not valid JSON",
                code="invalid_response",
                request_dispatched=True,
            ) from exc
        return _records(payload, query=normalized, limit=capped)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
