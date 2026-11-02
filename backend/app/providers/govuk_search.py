"""Bounded, metadata-only discovery through the public GOV.UK Search API.

The upstream documents this API as unsupported. Veda uses a single short query
only for an explicitly UK-scoped job and never follows publication links.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.scholarly import ScholarlyWork
from app.research.search_queries import compact_bibliographic_query

API_URL = "https://www.gov.uk/api/search.json"
ORGANIZATIONS_API_URL = "https://www.gov.uk/api/organisations"
API_DOCUMENTATION_URL = (
    "https://docs.publishing.service.gov.uk/repos/search-api/using-the-search-api.html"
)
API_REUSE_URL = "https://www.gov.uk/help/reuse-govuk-content"
MAX_RESPONSE_BYTES = 512_000
MAX_QUERY_CHARS = 240
MAX_RESULTS = 10
MAX_ORGANIZATIONS = 16
MAX_ORGANIZATION_RESPONSE_BYTES = 256_000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_PUBLICATION_PATH = re.compile(r"^/government/publications/[a-z0-9][a-z0-9-]{0,180}/?$", re.I)
_ORGANIZATION_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){0,39}$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I
)
_UK_GEOGRAPHIES = {
    "uk",
    "u.k.",
    "united kingdom",
    "great britain",
    "england",
    "scotland",
    "wales",
    "northern ireland",
}
_GOVUK_QUERY_BOILERPLATE = frozenset(
    {
        "uk",
        "united",
        "kingdom",
        "government",
        "gov",
        "policy",
        "policies",
        "affect",
        "affects",
    }
)


def build_govuk_search_query(question: str) -> str:
    """Keep topic terms for the UK catalogue; its host and format already imply policy.

    Geography is enforced separately. Dropping jurisdiction and question boilerplate
    prevents those early words from consuming the bounded query before the subject.
    """
    if not isinstance(question, str) or not question.strip():
        return ""
    tokens = re.findall(r"[a-z0-9]+", question.casefold())
    subject = [token for token in tokens if token not in _GOVUK_QUERY_BOILERPLATE]
    if not subject:
        return ""
    return compact_bibliographic_query([" ".join(subject)], max_terms=10, max_chars=MAX_QUERY_CHARS)


class GovUKSearchError(Exception):
    """Sanitized failure from the unsupported public metadata endpoint."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        request_dispatched: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_dispatched = request_dispatched
        self.retry_after_seconds = retry_after_seconds


def supports_uk_geography(value: str | None) -> bool:
    """Require an explicit persisted geography; never infer UK scope from topic."""
    normalized = " ".join((value or "").casefold().replace(".", "").split())
    return normalized in {item.replace(".", "") for item in _UK_GEOGRAPHIES}


def _safe_publication_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2000 or _CONTROL.search(value):
        return None
    try:
        parsed = urlsplit(value.strip())
        _ = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").casefold().rstrip(".")
    relative_official_path = (
        not parsed.scheme and not parsed.netloc and value.strip().startswith("/")
    )
    absolute_official_url = (
        parsed.scheme.casefold() in {"http", "https"}
        and host in {"gov.uk", "www.gov.uk"}
        and parsed.username is None
        and parsed.password is None
    )
    if (
        not (relative_official_path or absolute_official_url)
        or parsed.query
        or parsed.fragment
        or not _PUBLICATION_PATH.fullmatch(parsed.path)
    ):
        return None
    return f"https://www.gov.uk{parsed.path.rstrip('/')}"


def _organization_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:MAX_ORGANIZATIONS]:
        raw = item.get("title") if isinstance(item, dict) else item
        if not isinstance(raw, str):
            continue
        name = " ".join(raw.split())
        if name and len(name) <= 240 and not _CONTROL.search(name):
            result.append(name)
    return list(dict.fromkeys(result))


def _organization_references(value: Any) -> list[dict[str, str | None]]:
    """Extract only official organization references from GOV.UK search results."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for item in value[:MAX_ORGANIZATIONS]:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        name = item.get("title")
        link = item.get("link")
        if (
            not isinstance(slug, str)
            or not _ORGANIZATION_SLUG.fullmatch(slug)
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 240
            or _CONTROL.search(name)
            or link != f"/government/organisations/{slug}"
            or slug in seen
        ):
            continue
        seen.add(slug)
        raw_content_id = item.get("content_id")
        content_id = (
            raw_content_id
            if isinstance(raw_content_id, str) and _UUID.fullmatch(raw_content_id)
            else None
        )
        organization_type = item.get("organisation_type")
        directory_status = item.get("organisation_state")
        result.append(
            {
                "slug": slug,
                "canonical_name": " ".join(name.split()),
                "content_id": content_id,
                "organization_type": (
                    organization_type[:80]
                    if isinstance(organization_type, str) and organization_type.strip()
                    else None
                ),
                "directory_status": (
                    directory_status[:24]
                    if isinstance(directory_status, str) and directory_status.strip()
                    else None
                ),
                "official_url": f"https://www.gov.uk/government/organisations/{slug}",
            }
        )
    return result


def _identity_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _year(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).year
    except ValueError:
        return None


def _safe_description(value: Any) -> str | None:
    """Keep a short, in-memory API description for relevance selection only."""
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 2000 or _CONTROL.search(normalized):
        return None
    return normalized[:1000]


def _parse_results(payload: Any, *, query: str, limit: int) -> list[ScholarlyWork]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise GovUKSearchError(
            "GOV.UK Search API returned an invalid result set",
            code="invalid_response",
            request_dispatched=True,
        )
    rows: list[ScholarlyWork] = []
    for item in payload["results"][:limit]:
        if not isinstance(item, dict) or item.get("format") != "policy_paper":
            continue
        title = item.get("title")
        link = _safe_publication_url(item.get("link"))
        if not isinstance(title, str):
            continue
        title = " ".join(title.split())
        if not title or len(title) > 1000 or _CONTROL.search(title) or not link:
            continue
        organizations = _organization_names(item.get("organisations"))
        organization_references = _organization_references(item.get("organisations"))
        path = urlsplit(link).path
        metadata = {
            "api_documentation_url": API_DOCUMENTATION_URL,
            "api_reuse_url": API_REUSE_URL,
            "record_path": path,
            "document_type": "policy_paper",
            "publishing_organizations": organizations,
            "publishing_organization_candidates": organization_references,
            # Selection-only metadata. Workflow scoring removes the raw value before
            # persistence and keeps only matched query terms and its field provenance.
            "selection_description": _safe_description(item.get("description")),
            "metadata_access": "public_official_api",
            "metadata_reuse_status": "metadata_only_content_rights_not_assessed",
            "full_text_retrieved": False,
            "full_text_rights_status": "not_assessed",
            "api_support_status": "unsupported_best_effort",
        }
        rows.append(
            ScholarlyWork(
                external_id=f"govuk:{path}",
                title=title,
                doi=None,
                url=link,
                authors=[],
                published_year=_year(item.get("public_timestamp")),
                publisher="; ".join(organizations) if organizations else "GOV.UK",
                abstract_excerpt=None,
                query=query,
                provider="GOV.UK Search API",
                provider_metadata=metadata,
                source_type="institutional_report",
            )
        )
    return rows


class GovUKSearchProvider:
    """Execute one bounded UK policy-paper metadata request, without redirects."""

    provider_name = "GOV.UK Search API"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(10.0, connect=4.0),
            follow_redirects=False,
            headers={"User-Agent": "Veda bounded research metadata client"},
        )
        self._owns_client = client is None
        self._before_request = before_request

    def search(
        self,
        query: str,
        *,
        geography: str | None,
        limit: int = MAX_RESULTS,
    ) -> list[ScholarlyWork]:
        normalized = " ".join(query.split()) if isinstance(query, str) else ""
        if not supports_uk_geography(geography):
            raise GovUKSearchError(
                "GOV.UK search requires an explicit UK geography", code="unsupported_geography"
            )
        if (
            not normalized
            or len(normalized) > MAX_QUERY_CHARS
            or _CONTROL.search(normalized)
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
        ):
            raise GovUKSearchError(
                "GOV.UK query is outside its configured bounds", code="invalid_query"
            )

        capped = min(limit, MAX_RESULTS)
        params: list[tuple[str, str | int]] = [
            ("q", normalized),
            ("count", capped),
            ("filter_format", "policy_paper"),
            *(
                ("fields", field)
                for field in (
                    "title",
                    "link",
                    "public_timestamp",
                    "organisations",
                    "format",
                    "description",
                )
            ),
        ]
        if self._before_request is not None:
            try:
                self._before_request()
            except GovUKSearchError:
                raise
            except Exception:
                raise GovUKSearchError(
                    "GOV.UK request was deferred by the local rate limiter", code="request_deferred"
                ) from None

        dispatched = False
        try:
            with self._client.stream("GET", API_URL, params=params) as response:
                dispatched = True
                if 300 <= response.status_code < 400:
                    raise GovUKSearchError(
                        "GOV.UK search redirects are not followed",
                        code="redirect_rejected",
                        request_dispatched=True,
                    )
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        retry_seconds = (
                            min(3600.0, max(0.0, float(retry_after))) if retry_after else None
                        )
                    except ValueError:
                        retry_seconds = None
                    raise GovUKSearchError(
                        "GOV.UK Search API rate limited the request",
                        code="rate_limited",
                        request_dispatched=True,
                        retry_after_seconds=retry_seconds,
                    )
                if response.status_code >= 400:
                    raise GovUKSearchError(
                        "GOV.UK Search API returned an HTTP error",
                        code="http_error",
                        request_dispatched=True,
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise GovUKSearchError(
                            "GOV.UK response exceeded its size limit",
                            code="response_too_large",
                            request_dispatched=True,
                        )
                    chunks.append(chunk)
        except GovUKSearchError:
            raise
        except httpx.TimeoutException:
            raise GovUKSearchError(
                "GOV.UK request timed out", code="timeout", request_dispatched=dispatched
            ) from None
        except httpx.RequestError:
            raise GovUKSearchError(
                "GOV.UK request failed", code="request_failed", request_dispatched=dispatched
            ) from None
        try:
            payload = json.loads(b"".join(chunks))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GovUKSearchError(
                "GOV.UK Search API returned malformed JSON",
                code="invalid_response",
                request_dispatched=True,
            ) from None
        return _parse_results(payload, query=normalized, limit=capped)

    def verify_organization(
        self,
        slug: str,
        *,
        expected_name: str,
        expected_content_id: str | None = None,
    ) -> dict[str, Any]:
        """Resolve one exact publisher slug through the official GOV.UK organization API.

        A verified status establishes directory identity and live status only. It does not
        establish research quality, publication relevance, or methodological reliability.
        This operation performs one request and never follows redirects or retries.
        """
        if (
            not isinstance(slug, str)
            or not _ORGANIZATION_SLUG.fullmatch(slug)
            or not isinstance(expected_name, str)
            or not expected_name.strip()
            or len(expected_name) > 240
            or _CONTROL.search(expected_name)
            or (
                expected_content_id is not None
                and (
                    not isinstance(expected_content_id, str)
                    or not _UUID.fullmatch(expected_content_id)
                )
            )
        ):
            raise GovUKSearchError(
                "GOV.UK organization identity request was invalid",
                code="invalid_organization_identity",
            )

        endpoint = f"{ORGANIZATIONS_API_URL}/{slug}"
        if self._before_request is not None:
            try:
                self._before_request()
            except GovUKSearchError:
                raise
            except Exception:
                raise GovUKSearchError(
                    "GOV.UK organization request was deferred by the local rate limiter",
                    code="request_deferred",
                ) from None

        dispatched = False
        try:
            with self._client.stream("GET", endpoint) as response:
                dispatched = True
                if 300 <= response.status_code < 400:
                    raise GovUKSearchError(
                        "GOV.UK organization redirects are not followed",
                        code="redirect_rejected",
                        request_dispatched=True,
                    )
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        retry_seconds = (
                            min(3600.0, max(0.0, float(retry_after))) if retry_after else None
                        )
                    except ValueError:
                        retry_seconds = None
                    raise GovUKSearchError(
                        "GOV.UK organization lookup was rate limited",
                        code="rate_limited",
                        request_dispatched=True,
                        retry_after_seconds=retry_seconds,
                    )
                if response.status_code >= 400:
                    raise GovUKSearchError(
                        "GOV.UK organization lookup returned an HTTP error",
                        code="http_error",
                        request_dispatched=True,
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_ORGANIZATION_RESPONSE_BYTES:
                        raise GovUKSearchError(
                            "GOV.UK organization response exceeded its size limit",
                            code="response_too_large",
                            request_dispatched=True,
                        )
                    chunks.append(chunk)
        except GovUKSearchError:
            raise
        except httpx.TimeoutException:
            raise GovUKSearchError(
                "GOV.UK organization request timed out",
                code="timeout",
                request_dispatched=dispatched,
            ) from None
        except httpx.RequestError:
            raise GovUKSearchError(
                "GOV.UK organization request failed",
                code="request_failed",
                request_dispatched=dispatched,
            ) from None

        try:
            payload = json.loads(b"".join(chunks))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GovUKSearchError(
                "GOV.UK organization lookup returned malformed JSON",
                code="invalid_response",
                request_dispatched=True,
            ) from None
        if not isinstance(payload, dict):
            raise GovUKSearchError(
                "GOV.UK organization lookup returned an invalid record",
                code="invalid_response",
                request_dispatched=True,
            )
        details = payload.get("details")
        if not isinstance(details, dict):
            raise GovUKSearchError(
                "GOV.UK organization lookup returned an invalid record",
                code="invalid_response",
                request_dispatched=True,
            )

        canonical_name = payload.get("title")
        resolved_slug = details.get("slug")
        content_id = details.get("content_id")
        status = details.get("govuk_status")
        format_name = payload.get("format")
        if (
            not isinstance(canonical_name, str)
            or not canonical_name.strip()
            or len(canonical_name) > 240
            or _CONTROL.search(canonical_name)
            or resolved_slug != slug
            or not isinstance(content_id, str)
            or not _UUID.fullmatch(content_id)
            or not isinstance(status, str)
            or not isinstance(format_name, str)
        ):
            raise GovUKSearchError(
                "GOV.UK organization lookup returned an invalid identity record",
                code="invalid_response",
                request_dispatched=True,
            )

        match = (
            _identity_name(canonical_name) == _identity_name(expected_name)
            and (
                expected_content_id is None
                or content_id.casefold() == expected_content_id.casefold()
            )
            and status.casefold() == "live"
            and details.get("closed_at") is None
        )
        limitations = [
            "The official directory verifies organization identity only; publication methodology and quality are not assessed."
        ]
        if not match:
            limitations.append(
                "The official record did not match the expected name/content ID or is not live."
            )
        return {
            "schema_version": 1,
            "organization_id": f"govuk:{slug}",
            "canonical_name": " ".join(canonical_name.split()),
            "content_id": content_id.casefold(),
            "organization_type": format_name[:80],
            "directory_status": status[:24],
            "identity_status": "VERIFIED_ESTABLISHED" if match else "PENDING_VERIFICATION",
            "verification_method": "govuk_organizations_api_exact_slug",
            "verification_source": endpoint,
            "verification_timestamp": datetime.now(UTC).isoformat(),
            "official_url": f"https://www.gov.uk/government/organisations/{slug}",
            "quality_assessment": "not_assessed",
            "limitations": limitations,
        }

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
