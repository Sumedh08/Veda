"""Bounded Europe PMC full-text XML adapter with license preflight.

The adapter talks only to the documented Europe PMC REST host, follows no
redirects, validates the article identity and permissive license before the
full-text request, and never logs response bodies or request URLs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import httpx

from app.providers.retry import parse_retry_after_seconds
from app.research.retrieval_rights import PERMITTED_LICENSES

EUROPE_PMC_REST = "https://www.ebi.ac.uk/europepmc/webservices/rest"
MAX_METADATA_BYTES = 512_000
MAX_FULL_TEXT_BYTES = 2_000_000
PMCID_PATTERN = re.compile(r"^PMC[0-9]{1,10}$", re.IGNORECASE)
DOI_QUERY_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:a-z0-9]+$", re.IGNORECASE)


class EuropePMCError(Exception):
    """Sanitized transport or response error safe for persistence."""

    def __init__(self, code: str, *, retry_after_seconds: float | None = None):
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code)


@dataclass(frozen=True)
class EuropePMCArticleMetadata:
    pmcid: str
    doi: str | None
    title: str | None
    open_access: bool
    license_code: str | None
    raw_license: str | None

    @property
    def rights_decision(self) -> Literal["PERMITTED", "DENIED"]:
        if self.open_access and self.license_code in PERMITTED_LICENSES:
            return "PERMITTED"
        return "DENIED"


@dataclass(frozen=True)
class EuropePMCResolution:
    status: Literal["retrieved", "denied", "unavailable", "failed", "deferred"]
    reason_code: str | None
    metadata: EuropePMCArticleMetadata | None
    content: bytes | None = None
    content_type: str | None = None
    retry_after_seconds: float | None = None
    requests_attempted: int = 0


def _normalize_pmcid(value: str) -> str:
    if not isinstance(value, str):
        raise EuropePMCError("invalid_pmcid")
    bounded = value.strip().upper()
    if len(bounded) > 13 or not PMCID_PATTERN.fullmatch(bounded):
        raise EuropePMCError("invalid_pmcid")
    return bounded


def _normalize_doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return normalized.strip().rstrip(".,; ") or None


def _license_code(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if normalized in {"cc0", "cczero", "creativecommonszero"} or normalized.endswith(
        "creativecommonsorglicenseszero"
    ):
        return "cc0"
    if normalized in {
        "ccby",
        "creativecommonsattribution",
        "creativecommonsby",
        "ccby40",
        "creativecommonsattribution40international",
    } or re.fullmatch(r"(?:https)?creativecommonsorglicensesby(?:[0-9]+)?", normalized):
        return "cc-by"
    # Noncommercial, no-derivatives, and other variants require separate review.
    return None


class EuropePMCProvider:
    """Serial, single-attempt access to Europe PMC metadata and JATS XML."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timeout_seconds: float = 8,
        request_admission: Callable[[], None] | None = None,
    ) -> None:
        if not 0.1 <= timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0.1 and 30")
        self._owns_client = client is None
        self.requests_attempted = 0
        self._request_admission = request_admission
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=min(3, timeout_seconds)),
            headers={
                "User-Agent": "VedaResearch/0.1 (bounded scholarly full-text retrieval)",
                "Accept": "application/json, application/xml, text/xml",
            },
            follow_redirects=False,
        )
        if client is not None:
            client.follow_redirects = False
            client.headers.setdefault(
                "User-Agent", "VedaResearch/0.1 (bounded scholarly full-text retrieval)"
            )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get_bytes(self, path: str, *, params: dict[str, str], max_bytes: int) -> tuple[bytes, str]:
        try:
            if self._request_admission is not None:
                self._request_admission()
            self.requests_attempted += 1
            with self.client.stream("GET", f"{EUROPE_PMC_REST}/{path}", params=params) as response:
                if response.status_code == 429:
                    retry_after = parse_retry_after_seconds(response.headers)
                    raise EuropePMCError("rate_limited", retry_after_seconds=retry_after) from None
                if response.status_code in {404, 410}:
                    raise EuropePMCError("content_unavailable") from None
                if 300 <= response.status_code < 400:
                    raise EuropePMCError("redirect_rejected") from None
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise EuropePMCError("response_too_large") from None
                content_type = (
                    response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
                )
                return bytes(body), content_type
        except EuropePMCError:
            raise
        except httpx.TimeoutException:
            raise EuropePMCError("request_timeout") from None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                retry_after = parse_retry_after_seconds(exc.response.headers)
                raise EuropePMCError("rate_limited", retry_after_seconds=retry_after) from None
            raise EuropePMCError("provider_http_error") from None
        except httpx.HTTPError:
            raise EuropePMCError("provider_transport_error") from None

    def lookup_article(self, pmcid: str) -> EuropePMCArticleMetadata:
        canonical_pmcid = _normalize_pmcid(pmcid)
        return self._lookup_article(
            query=f"PMCID:{canonical_pmcid}", expected_pmcid=canonical_pmcid
        )

    def lookup_article_by_doi(self, doi: str) -> EuropePMCArticleMetadata:
        canonical_doi = _normalize_doi(doi)
        if not canonical_doi or not DOI_QUERY_PATTERN.fullmatch(canonical_doi):
            raise EuropePMCError("invalid_doi")
        return self._lookup_article(query=f"DOI:{canonical_doi}", expected_doi=canonical_doi)

    def _lookup_article(
        self,
        *,
        query: str,
        expected_pmcid: str | None = None,
        expected_doi: str | None = None,
    ) -> EuropePMCArticleMetadata:
        body, content_type = self._get_bytes(
            "search",
            params={"query": query, "format": "json", "resultType": "core", "pageSize": "1"},
            max_bytes=MAX_METADATA_BYTES,
        )
        if content_type not in {"application/json", "text/json", ""}:
            raise EuropePMCError("unexpected_metadata_content_type")
        try:
            payload = json.loads(body)
            results = payload["resultList"]["result"]
        except (ValueError, TypeError, KeyError):
            raise EuropePMCError("invalid_metadata_response") from None
        if not isinstance(results, list) or not results:
            raise EuropePMCError("article_metadata_unavailable")
        record = next(
            (
                item
                for item in results
                if isinstance(item, dict)
                and isinstance(item.get("pmcid"), str)
                and (
                    item["pmcid"].upper() == expected_pmcid
                    if expected_pmcid
                    else _normalize_doi(item.get("doi")) == expected_doi
                )
            ),
            None,
        )
        if record is None:
            raise EuropePMCError("article_identity_mismatch")
        canonical_pmcid = _normalize_pmcid(record["pmcid"])
        raw_license = record.get("license") if isinstance(record.get("license"), str) else None
        open_access = record.get("isOpenAccess") == "Y"
        return EuropePMCArticleMetadata(
            pmcid=canonical_pmcid,
            doi=_normalize_doi(record.get("doi")),
            title=record.get("title")[:1000] if isinstance(record.get("title"), str) else None,
            open_access=open_access,
            license_code=_license_code(raw_license),
            raw_license=raw_license[:100] if raw_license else None,
        )

    def resolve_full_text(
        self, pmcid: str | None, *, expected_doi: str | None = None
    ) -> EuropePMCResolution:
        """Preflight identity/rights; fetch at most one matching licensed JATS document.

        A known PMCID avoids a broader identifier lookup. When a source only has a
        DOI, resolve that exact DOI to a PMCID before any content request.
        """
        try:
            if isinstance(pmcid, str) and pmcid.strip():
                metadata = self.lookup_article(pmcid)
            elif expected_doi:
                metadata = self.lookup_article_by_doi(expected_doi)
            else:
                raise EuropePMCError("invalid_pmcid")
        except EuropePMCError as exc:
            status = (
                "deferred"
                if exc.code in {"rate_limited", "origin_request_deferred"}
                else "unavailable"
                if exc.code in {"content_unavailable", "article_metadata_unavailable"}
                else "failed"
            )
            retry_after = exc.retry_after_seconds
            if exc.code in {"rate_limited", "origin_request_deferred"}:
                status = "deferred"
            return EuropePMCResolution(
                status,
                exc.code,
                None,
                retry_after_seconds=retry_after,
                requests_attempted=self.requests_attempted,
            )

        expected = _normalize_doi(expected_doi)
        if expected and expected != metadata.doi:
            return EuropePMCResolution(
                "denied",
                "work_identity_mismatch",
                metadata,
                requests_attempted=self.requests_attempted,
            )
        if not metadata.open_access or metadata.license_code not in PERMITTED_LICENSES:
            return EuropePMCResolution(
                "denied",
                "license_not_permitted",
                metadata,
                requests_attempted=self.requests_attempted,
            )

        try:
            body, content_type = self._get_bytes(
                f"{metadata.pmcid}/fullTextXML", params={}, max_bytes=MAX_FULL_TEXT_BYTES
            )
        except EuropePMCError as exc:
            status = (
                "deferred"
                if exc.code in {"rate_limited", "origin_request_deferred"}
                else "unavailable"
                if exc.code == "content_unavailable"
                else "failed"
            )
            return EuropePMCResolution(
                status,
                exc.code,
                metadata,
                retry_after_seconds=exc.retry_after_seconds,
                requests_attempted=self.requests_attempted,
            )
        if content_type not in {"application/xml", "text/xml", "application/jats+xml"}:
            return EuropePMCResolution(
                "failed",
                "unexpected_full_text_content_type",
                metadata,
                requests_attempted=self.requests_attempted,
            )
        return EuropePMCResolution(
            "retrieved",
            None,
            metadata,
            body,
            content_type,
            requests_attempted=self.requests_attempted,
        )
