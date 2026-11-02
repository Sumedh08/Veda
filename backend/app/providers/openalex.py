import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import httpx

from app.config import settings
from app.providers.crossref import MAX_ABSTRACT_EXCERPT
from app.providers.retry import (
    MAX_SAFE_GET_RETRIES,
    SAFE_GET_RETRY_STATUSES,
    parse_retry_after_seconds,
    wait_for_retry,
)
from app.providers.scholarly import ScholarlyWork

MAX_RESPONSE_BYTES = 2_000_000
MAX_GROBID_TEI_BYTES = 2_000_000
MAX_RESULTS = 8
OPENALEX_API_URL = "https://api.openalex.org/works"
OPENALEX_INSTITUTIONS_URL = "https://api.openalex.org/institutions"
OPENALEX_CONTENT_BASE_URL = "https://content.openalex.org/works"
OPENALEX_CONTENT_FILE_PRICE_USD = Decimal("0.01")
SELECT_FIELDS = (
    "id,doi,title,publication_year,authorships,primary_location,ids,"
    "abstract_inverted_index,open_access,best_oa_location,has_content,type"
)


class OpenAlexError(Exception):
    """Sanitized OpenAlex provider failure safe to persist in job events."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_query_failed",
        retry_after_seconds: float | None = None,
        request_dispatched: bool = False,
        reserved_cost_usd: Decimal | None = None,
        reported_cost_usd: float | None = None,
        reported_cost_status: Literal["unknown", "not_observed"] = "not_observed",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.request_dispatched = request_dispatched
        self.reserved_cost_usd = reserved_cost_usd
        self.reported_cost_usd = reported_cost_usd
        self.reported_cost_status = reported_cost_status


@dataclass(frozen=True)
class OpenAlexContentAuthorization:
    """Rights and spending decision supplied by the persisted workflow gate."""

    rights_decision: Literal[
        "PERMITTED", "PERMITTED_WITH_RESTRICTIONS", "REQUIRES_REVIEW", "DENIED"
    ]
    rights_policy_id: str
    license_code: str
    cost_reserved_usd: Decimal


@dataclass(frozen=True)
class OpenAlexTEIContent:
    work_id: str
    content: bytes
    content_sha256: str
    content_type: str
    retrieved_at: str
    cost_reserved_usd: Decimal
    reported_cost_usd: Decimal | None
    reported_cost_status: Literal["unknown"] = "unknown"


@dataclass(frozen=True)
class CitationExpansionCandidate:
    direction: Literal["backward", "forward"]
    seed_openalex_id: str
    work: ScholarlyWork


@dataclass(frozen=True)
class CitationExpansionResult:
    status: Literal["completed", "partial", "failed", "not_attempted"]
    seed_openalex_ids: list[str]
    candidates: list[CitationExpansionCandidate]
    requests_attempted: int
    reported_cost_usd: float | None
    reported_cost_status: Literal["provider_reported_complete", "unknown", "not_observed"]
    omitted_backward_count: int
    backward_available_counts: dict[str, int]
    forward_result_counts: dict[str, int]
    forward_returned_counts: dict[str, int]
    errors: list[dict[str, Any]]


def _doi(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    normalized = normalized.strip().rstrip(".,; ")
    return normalized or None


def _abstract_excerpt_details(inverted_index: Any) -> tuple[str | None, bool]:
    if not isinstance(inverted_index, dict):
        return None, False
    positions: dict[int, list[str]] = {}
    for token, indexes in inverted_index.items():
        if not isinstance(token, str) or not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int) and 0 <= index < 100_000:
                positions.setdefault(index, []).append(token)
    if not positions:
        return None, False
    text = " ".join(" ".join(sorted(positions[index])) for index in sorted(positions)).strip()
    excerpt = text[:MAX_ABSTRACT_EXCERPT].strip() or None
    return excerpt, len(text) > MAX_ABSTRACT_EXCERPT


def _abstract_excerpt(inverted_index: Any) -> str | None:
    """Compatibility helper returning only the bounded text excerpt."""
    return _abstract_excerpt_details(inverted_index)[0]


def _authors(authorships: Any) -> list[dict[str, str]]:
    if not isinstance(authorships, list):
        return []
    names: list[dict[str, str]] = []
    for authorship in authorships[:12]:
        author = authorship.get("author") if isinstance(authorship, dict) else None
        name = author.get("display_name") if isinstance(author, dict) else None
        if isinstance(name, str) and name.strip():
            # Do not guess given/family boundaries across international name formats.
            names.append({"name": name.strip()[:160]})
    return names


def _publisher(work: dict[str, Any]) -> str | None:
    location = work.get("primary_location")
    source = location.get("source") if isinstance(location, dict) else None
    if not isinstance(source, dict):
        return None
    name = source.get("display_name")
    return name.strip()[:300] if isinstance(name, str) and name.strip() else None


def _pmcid(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(?:^|/)(PMC[0-9]{1,10})/?$", value.strip(), re.IGNORECASE)
    return match.group(1).upper() if match else None


def _openalex_work_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(?:https://openalex\.org/)?(W[0-9]{1,20})/?", value.strip())
    return match.group(1) if match else None


def _content_availability(value: Any) -> dict[str, bool] | None:
    """Retain only OpenAlex's explicit format-availability booleans.

    The content API URLs are deliberately not retained or followed here. They
    identify metered downloads, while availability alone says nothing about
    reuse rights for the underlying work.
    """
    if not isinstance(value, dict):
        return None
    availability = {
        key: value[key] for key in ("pdf", "grobid_xml") if type(value.get(key)) is bool
    }
    return availability or None


def _journal_issns(work: dict[str, Any]) -> list[str]:
    locations = [work.get("primary_location"), work.get("best_oa_location")]
    for location in locations:
        source = location.get("source") if isinstance(location, dict) else None
        if not isinstance(source, dict):
            continue
        values = source.get("issn")
        if not isinstance(values, list):
            values = []
        issn_l = source.get("issn_l")
        if isinstance(issn_l, str):
            values = [*values, issn_l]
        output = list(
            dict.fromkeys(
                value.strip() for value in values if isinstance(value, str) and value.strip()
            )
        )
        if output:
            return output[:16]
    return []


def _institution_ids(work: dict[str, Any]) -> dict[str, list[str]]:
    """Retain identifiers actually attached to author affiliations by OpenAlex."""
    openalex: list[str] = []
    ror: list[str] = []
    authorships = work.get("authorships")
    if not isinstance(authorships, list):
        return {}
    for authorship in authorships[:100]:
        institutions = authorship.get("institutions") if isinstance(authorship, dict) else None
        if not isinstance(institutions, list):
            continue
        for institution in institutions[:24]:
            if not isinstance(institution, dict):
                continue
            institution_id = institution.get("id")
            if isinstance(institution_id, str):
                match = re.fullmatch(
                    r"(?:https://openalex\.org/)?(I[0-9]{1,20})/?", institution_id.strip()
                )
                if match:
                    openalex.append(match.group(1))
            ror_id = institution.get("ror")
            if isinstance(ror_id, str) and re.fullmatch(
                r"https://ror\.org/[0-9a-z]{9}", ror_id.strip(), re.I
            ):
                ror.append(ror_id.strip().casefold())
    result = {}
    if openalex:
        result["openalex"] = list(dict.fromkeys(openalex))[:100]
    if ror:
        result["ror"] = list(dict.fromkeys(ror))[:100]
    return result


def _institution_records(work: dict[str, Any]) -> list[dict[str, str]]:
    """Keep bounded affiliation identity details attached to discovered works."""
    authorships = work.get("authorships")
    if not isinstance(authorships, list):
        return []
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for authorship in authorships[:100]:
        institutions = authorship.get("institutions") if isinstance(authorship, dict) else None
        if not isinstance(institutions, list):
            continue
        for institution in institutions[:24]:
            if not isinstance(institution, dict):
                continue
            raw_id = institution.get("id")
            match = (
                re.fullmatch(r"(?:https://openalex\.org/)?(I[0-9]{1,20})/?", raw_id.strip())
                if isinstance(raw_id, str)
                else None
            )
            if not match:
                continue
            openalex_id = match.group(1)
            if openalex_id in seen:
                continue
            seen.add(openalex_id)
            item = {"openalex_id": openalex_id}
            ror_id = institution.get("ror")
            if isinstance(ror_id, str) and re.fullmatch(
                r"https://ror\.org/[0-9a-z]{9}", ror_id.strip(), re.I
            ):
                item["ror_id"] = ror_id.strip().casefold()
            name = institution.get("display_name")
            if isinstance(name, str) and name.strip():
                item["display_name"] = " ".join(name.split())[:300]
            country = institution.get("country_code")
            if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country.strip()):
                item["country_code"] = country.strip().upper()
            kind = institution.get("type")
            if isinstance(kind, str) and kind.strip():
                item["type"] = kind.strip()[:50].casefold()
            records.append(item)
            if len(records) >= 100:
                return records
    return records


def _record(work: Any, query: str) -> ScholarlyWork | None:
    if not isinstance(work, dict):
        return None
    title = work.get("title") or work.get("display_name")
    if not isinstance(title, str) or not title.strip():
        return None
    doi = _doi(work.get("doi"))
    openalex_id = work.get("id")
    if not isinstance(openalex_id, str) or not openalex_id.strip():
        return None
    openalex_short_id = openalex_id.rstrip("/").rsplit("/", 1)[-1]
    external_id = f"doi:{doi}" if doi else f"openalex:{openalex_short_id}"
    location = work.get("primary_location")
    landing_url = location.get("landing_page_url") if isinstance(location, dict) else None
    url = f"https://doi.org/{doi}" if doi else landing_url
    year = work.get("publication_year")
    if not isinstance(year, int):
        year = None
    open_access = work.get("open_access")
    best_location = work.get("best_oa_location")
    abstract_excerpt, abstract_truncated = _abstract_excerpt_details(
        work.get("abstract_inverted_index")
    )
    ids = work.get("ids")
    pmcid = _pmcid(ids.get("pmcid")) if isinstance(ids, dict) else None
    metadata = {
        "openalex_id": openalex_id,
        "open_access": open_access if isinstance(open_access, dict) else {},
        "best_oa_location": best_location if isinstance(best_location, dict) else {},
        "work_type": work.get("type"),
        "abstract_excerpt_truncated": abstract_truncated,
        "pmcid": pmcid,
        "journal_issns": _journal_issns(work),
        "institution_ids": _institution_ids(work),
        "institution_records": _institution_records(work),
    }
    content_availability = _content_availability(work.get("has_content"))
    if content_availability is not None:
        metadata["has_content"] = content_availability
    return ScholarlyWork(
        external_id=external_id,
        title=" ".join(title.split())[:1000],
        doi=doi,
        url=url if isinstance(url, str) and url.startswith(("https://", "http://")) else None,
        authors=_authors(work.get("authorships")),
        published_year=year,
        publisher=_publisher(work),
        abstract_excerpt=abstract_excerpt,
        query=query,
        provider="OpenAlex",
        provider_metadata=metadata,
    )


class OpenAlexProvider:
    """Small, bounded Works search adapter. Account keys are opt-in to avoid billing."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        api_key: str | None = None,
        allow_billable_calls: bool = False,
        allow_metered_content_downloads: bool = False,
        force_keyless: bool = False,
    ) -> None:
        self._owns_client = client is None
        headers = {"User-Agent": "VedaResearch/0.1 (scholarly metadata client)"}
        selected_key = api_key if api_key is not None else settings.openalex_api_key
        self._api_key = (
            selected_key if selected_key and allow_billable_calls and not force_keyless else None
        )
        self._allow_metered_content_downloads = allow_metered_content_downloads
        if self._api_key is not None:
            # OpenAlex documents both bearer and query-parameter authentication;
            # bearer avoids placing credentials in request URLs.
            headers["Authorization"] = f"Bearer {self._api_key}"
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(12, connect=4), headers=headers, follow_redirects=False
        )
        if client is not None:
            self.client.headers.update(headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def download_grobid_tei(
        self,
        openalex_id: str,
        *,
        authorization: OpenAlexContentAuthorization,
    ) -> OpenAlexTEIContent:
        """Fetch one cached TEI file after separate rights and cost gates.

        No retry is attempted: OpenAlex meters content requests, and an
        interrupted request can leave usage uncertain. The returned TEI is
        untrusted input and still requires Veda's structured parser and source
        identity checks before it can become evidence.
        """
        if not self._allow_metered_content_downloads or not self._api_key:
            raise OpenAlexError(
                "OpenAlex content downloads are not enabled",
                code="content_download_not_authorized",
            )
        work_id = _openalex_work_id(openalex_id)
        if work_id is None:
            raise OpenAlexError("OpenAlex work identifier is invalid", code="invalid_work_id")
        if not isinstance(authorization, OpenAlexContentAuthorization):
            raise OpenAlexError(
                "A permitted source-specific rights decision is required",
                code="content_rights_not_permitted",
            )
        if (
            authorization.rights_decision != "PERMITTED"
            or not isinstance(authorization.license_code, str)
            or authorization.license_code.casefold() not in {"cc0", "cc-by"}
            or not isinstance(authorization.rights_policy_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", authorization.rights_policy_id)
        ):
            raise OpenAlexError(
                "A permitted source-specific rights decision is required",
                code="content_rights_not_permitted",
            )
        reserved = authorization.cost_reserved_usd
        if (
            not isinstance(reserved, Decimal)
            or not reserved.is_finite()
            or reserved < OPENALEX_CONTENT_FILE_PRICE_USD
        ):
            raise OpenAlexError(
                "A sufficient content-file cost reservation is required",
                code="content_budget_not_reserved",
            )

        url = f"{OPENALEX_CONTENT_BASE_URL}/{work_id}.grobid-xml"
        try:
            with self.client.stream("GET", url, follow_redirects=False) as response:
                if response.status_code == 429:
                    raise OpenAlexError(
                        "OpenAlex content rate limit reached",
                        code="provider_rate_limited",
                        retry_after_seconds=parse_retry_after_seconds(response.headers),
                        request_dispatched=True,
                        reserved_cost_usd=reserved,
                        reported_cost_status="unknown",
                    )
                if 300 <= response.status_code < 400:
                    raise OpenAlexError(
                        "OpenAlex content redirect was rejected",
                        code="content_redirect_rejected",
                        request_dispatched=True,
                        reserved_cost_usd=reserved,
                        reported_cost_status="unknown",
                    )
                if response.status_code in {404, 410}:
                    raise OpenAlexError(
                        "OpenAlex TEI content is unavailable",
                        code="content_unavailable",
                        request_dispatched=True,
                        reserved_cost_usd=reserved,
                        reported_cost_status="unknown",
                    )
                response.raise_for_status()
                content_type = (
                    response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
                )
                if content_type not in {"application/xml", "text/xml"}:
                    raise OpenAlexError(
                        "OpenAlex returned an unexpected content type",
                        code="content_type_rejected",
                        request_dispatched=True,
                        reserved_cost_usd=reserved,
                        reported_cost_status="unknown",
                    )
                length = response.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > MAX_GROBID_TEI_BYTES:
                    raise OpenAlexError(
                        "OpenAlex TEI exceeded the 10 MB safety limit",
                        code="content_response_too_large",
                        request_dispatched=True,
                        reserved_cost_usd=reserved,
                        reported_cost_status="unknown",
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_GROBID_TEI_BYTES:
                        raise OpenAlexError(
                            "OpenAlex TEI exceeded the 10 MB safety limit",
                            code="content_response_too_large",
                            request_dispatched=True,
                            reserved_cost_usd=reserved,
                            reported_cost_status="unknown",
                        )
        except OpenAlexError:
            raise
        except httpx.TimeoutException:
            raise OpenAlexError(
                "OpenAlex content request timed out",
                code="content_timeout",
                request_dispatched=True,
                reserved_cost_usd=reserved,
                reported_cost_status="unknown",
            ) from None
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise OpenAlexError(
                    "OpenAlex content rate limit reached",
                    code="provider_rate_limited",
                    retry_after_seconds=parse_retry_after_seconds(exc.response.headers),
                    request_dispatched=True,
                    reserved_cost_usd=reserved,
                    reported_cost_status="unknown",
                ) from None
            raise OpenAlexError(
                "OpenAlex content request failed",
                code="content_download_failed",
                request_dispatched=True,
                reserved_cost_usd=reserved,
                reported_cost_status="unknown",
            ) from None
        except httpx.HTTPError:
            raise OpenAlexError(
                "OpenAlex content transport failed",
                code="content_transport_failed",
                request_dispatched=True,
                reserved_cost_usd=reserved,
                reported_cost_status="unknown",
            ) from None

        content = bytes(body)
        return OpenAlexTEIContent(
            work_id=work_id,
            content=content,
            content_sha256=hashlib.sha256(content).hexdigest(),
            content_type=content_type,
            retrieved_at=datetime.now(UTC).isoformat(),
            cost_reserved_usd=reserved,
            reported_cost_usd=None,
            reported_cost_status="unknown",
        )

    def search(self, query: str, *, limit: int = 5) -> list[ScholarlyWork]:
        bounded_query = " ".join(query.split())[:300]
        if not bounded_query:
            return []
        params = {
            "search": bounded_query,
            "per_page": min(max(limit, 1), MAX_RESULTS),
            "select": SELECT_FIELDS,
        }
        for attempt in range(MAX_SAFE_GET_RETRIES + 1):
            try:
                with self.client.stream("GET", OPENALEX_API_URL, params=params) as response:
                    if (
                        response.status_code in SAFE_GET_RETRY_STATUSES
                        and attempt < MAX_SAFE_GET_RETRIES
                    ):
                        delay = wait_for_retry(response.headers, retry_number=attempt)
                        if delay is not None:
                            continue
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise OpenAlexError("OpenAlex response exceeded the 2 MB safety limit")
                payload = json.loads(body)
            except OpenAlexError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                # Do not persist provider response bodies, request URLs or authorization data.
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    raise OpenAlexError(
                        "OpenAlex rate limit reached; retry this step later"
                    ) from exc
                raise OpenAlexError("OpenAlex discovery failed; retry this step later") from exc
            break
        else:
            raise OpenAlexError("OpenAlex discovery failed; retry this step later")

        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            raise OpenAlexError("OpenAlex returned an invalid works response")
        records: list[ScholarlyWork] = []
        for item in results[: params["per_page"]]:
            record = _record(item, bounded_query)
            if record is not None:
                records.append(record)
        return records

    def search_for_institution(
        self, query: str, institution_id: str, *, limit: int = 3
    ) -> list[ScholarlyWork]:
        """Search works within one discovered OpenAlex institution, bounded to 3."""
        match = re.fullmatch(r"(?:https://openalex\.org/)?(I[0-9]{1,20})/?", institution_id.strip())
        if not match:
            raise ValueError("OpenAlex institution identifier is invalid")
        bounded_query = " ".join(query.split())[:300]
        if not bounded_query:
            return []
        params = {
            "search": bounded_query,
            "filter": f"institutions.id:{match.group(1)}",
            "per_page": min(max(limit, 1), 3),
            "select": SELECT_FIELDS,
        }
        for attempt in range(MAX_SAFE_GET_RETRIES + 1):
            try:
                with self.client.stream("GET", OPENALEX_API_URL, params=params) as response:
                    if (
                        response.status_code in SAFE_GET_RETRY_STATUSES
                        and attempt < MAX_SAFE_GET_RETRIES
                    ):
                        delay = wait_for_retry(response.headers, retry_number=attempt)
                        if delay is not None:
                            continue
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise OpenAlexError("OpenAlex response exceeded the 2 MB safety limit")
                payload = json.loads(body)
            except OpenAlexError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    raise OpenAlexError(
                        "OpenAlex rate limit reached; retry this step later",
                        code="provider_rate_limited",
                    ) from exc
                raise OpenAlexError("OpenAlex institution publication search failed") from exc
            break
        else:
            raise OpenAlexError("OpenAlex institution publication search failed")
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            raise OpenAlexError("OpenAlex returned an invalid works response")
        records = []
        for item in results[: params["per_page"]]:
            record = _record(item, bounded_query)
            if record is None:
                continue
            affiliations = record.provider_metadata.get("institution_ids", {})
            institution_ids = (
                affiliations.get("openalex", []) if isinstance(affiliations, dict) else []
            )
            if match.group(1) not in institution_ids:
                continue
            records.append(record)
        return records

    def resolve_institution_id_by_ror(self, ror_id: str) -> str:
        """Resolve one exact ROR identity to OpenAlex's institution ID.

        OpenAlex documents `/institutions/ror:<ROR-ID>` as a supported entity
        lookup. The response is accepted only if both identifiers point back to
        the requested ROR record; the ROR match itself never implies quality.
        """
        match = (
            re.fullmatch(r"(?:https://ror\.org/)?([0-9a-z]{9})/?", ror_id.strip(), re.IGNORECASE)
            if isinstance(ror_id, str)
            else None
        )
        if not match:
            raise ValueError("ROR identifier is invalid")
        requested_ror = f"https://ror.org/{match.group(1).casefold()}"
        url = f"{OPENALEX_INSTITUTIONS_URL}/ror:{match.group(1).casefold()}"
        try:
            with self.client.stream("GET", url, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise OpenAlexError(
                        "OpenAlex institution redirect was rejected",
                        code="institution_redirect_rejected",
                        request_dispatched=True,
                    )
                if response.status_code == 404:
                    raise OpenAlexError(
                        "OpenAlex institution identity was not found",
                        code="institution_not_found",
                        request_dispatched=True,
                    )
                if response.status_code == 429:
                    raise OpenAlexError(
                        "OpenAlex institution lookup was rate limited",
                        code="provider_rate_limited",
                        request_dispatched=True,
                    )
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise OpenAlexError(
                            "OpenAlex institution response exceeded the 2 MB safety limit",
                            code="institution_response_too_large",
                            request_dispatched=True,
                        )
                payload = json.loads(body)
        except OpenAlexError:
            raise
        except httpx.HTTPError:
            raise OpenAlexError(
                "OpenAlex institution lookup failed",
                code="institution_lookup_failed",
                request_dispatched=True,
            ) from None
        except (ValueError, TypeError):
            raise OpenAlexError(
                "OpenAlex returned an invalid institution record",
                code="institution_invalid_response",
                request_dispatched=True,
            ) from None

        if not isinstance(payload, dict):
            raise OpenAlexError(
                "OpenAlex returned an invalid institution record",
                code="institution_invalid_response",
                request_dispatched=True,
            )
        raw_id = payload.get("id")
        id_match = (
            re.fullmatch(r"(?:https://openalex\.org/)?(I[0-9]{1,20})/?", raw_id.strip())
            if isinstance(raw_id, str)
            else None
        )
        returned_ror = payload.get("ror")
        identifiers = payload.get("ids")
        if not isinstance(returned_ror, str) and isinstance(identifiers, dict):
            returned_ror = identifiers.get("ror")
        if (
            id_match is None
            or not isinstance(returned_ror, str)
            or returned_ror.rstrip("/").casefold() != requested_ror
        ):
            raise OpenAlexError(
                "OpenAlex institution identity did not match the requested ROR record",
                code="institution_identity_mismatch",
                request_dispatched=True,
            )
        return id_match.group(1)

    def expand_citation_neighborhood(
        self,
        seed_openalex_ids: list[str],
        *,
        limit_per_direction: int = 5,
        max_seeds: int = 2,
    ) -> CitationExpansionResult:
        """Collect a bounded one-hop sample of references and citing works.

        This is an explicit metadata operation: it performs no recursive expansion,
        makes no popularity claim, and does not retry requests. It returns the
        provider's reported API cost only when every attempted response includes it.
        """
        if not 1 <= limit_per_direction <= 10 or not 1 <= max_seeds <= 2:
            raise ValueError("citation expansion limits exceed the bounded policy")
        seeds = list(dict.fromkeys(_openalex_work_id(value) for value in seed_openalex_ids))
        seeds = [value for value in seeds if value is not None][:max_seeds]
        if not seeds:
            return CitationExpansionResult(
                status="not_attempted",
                seed_openalex_ids=[],
                candidates=[],
                requests_attempted=0,
                reported_cost_usd=None,
                reported_cost_status="not_observed",
                omitted_backward_count=0,
                backward_available_counts={},
                forward_result_counts={},
                forward_returned_counts={},
                errors=[],
            )

        requests_attempted = 0
        reported_cost_total = 0.0
        cost_complete = True
        candidates: list[CitationExpansionCandidate] = []
        errors: list[dict[str, str]] = []
        forward_result_counts: dict[str, int] = {}
        forward_returned_counts: dict[str, int] = {}
        omitted_backward_count = 0

        def request_payload(stage: str, params: dict[str, str]) -> dict[str, Any] | None:
            nonlocal requests_attempted, reported_cost_total, cost_complete
            request_params = dict(params)
            requests_attempted += 1
            try:
                with self.client.stream("GET", OPENALEX_API_URL, params=request_params) as response:
                    if response.status_code == 429:
                        raise OpenAlexError(
                            "OpenAlex rate limit reached",
                            code="provider_rate_limited",
                            retry_after_seconds=parse_retry_after_seconds(response.headers),
                        )
                    if 300 <= response.status_code < 400:
                        raise OpenAlexError(
                            "OpenAlex redirect was rejected", code="provider_redirect_rejected"
                        )
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise OpenAlexError(
                                "OpenAlex response exceeded the 2 MB safety limit",
                                code="response_too_large",
                            )
                    payload = json.loads(body)
            except OpenAlexError as exc:
                error = {"stage": stage, "error_code": exc.code}
                if exc.retry_after_seconds is not None:
                    error["retry_after_seconds"] = exc.retry_after_seconds
                errors.append(error)
                cost_complete = False
                return None
            except httpx.HTTPStatusError as exc:
                code = (
                    "provider_rate_limited"
                    if exc.response.status_code == 429
                    else "provider_http_error"
                )
                errors.append({"stage": stage, "error_code": code})
                cost_complete = False
                return None
            except (httpx.HTTPError, ValueError):
                errors.append({"stage": stage, "error_code": "provider_response_invalid"})
                cost_complete = False
                return None
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                errors.append({"stage": stage, "error_code": "provider_response_invalid"})
                cost_complete = False
                return None
            meta = payload.get("meta")
            cost = meta.get("cost_usd") if isinstance(meta, dict) else None
            if (
                isinstance(cost, (int, float))
                and not isinstance(cost, bool)
                and math.isfinite(cost)
                and cost >= 0
            ):
                reported_cost_total += float(cost)
            else:
                cost_complete = False
            return payload

        detail_payload = request_payload(
            "work_details",
            {
                "filter": "openalex:" + "|".join(seeds),
                "per_page": str(len(seeds)),
                "select": "id,referenced_works",
            },
        )
        if detail_payload is None:
            return CitationExpansionResult(
                status="failed",
                seed_openalex_ids=seeds,
                candidates=[],
                requests_attempted=requests_attempted,
                reported_cost_usd=None,
                reported_cost_status="unknown",
                omitted_backward_count=0,
                backward_available_counts={},
                forward_result_counts={},
                forward_returned_counts={},
                errors=errors,
            )

        references_by_seed: dict[str, list[str]] = {}
        backward_available_counts: dict[str, int] = {}
        returned_seed_ids: set[str] = set()
        for result in detail_payload["results"][: len(seeds)]:
            if not isinstance(result, dict):
                continue
            work_id = _openalex_work_id(result.get("id"))
            if work_id not in seeds:
                continue
            returned_seed_ids.add(work_id)
            referenced = result.get("referenced_works")
            parsed = (
                list(
                    dict.fromkeys(
                        work_id
                        for work_id in (_openalex_work_id(item) for item in referenced)
                        if work_id is not None
                    )
                )
                if isinstance(referenced, list)
                else []
            )
            backward_available_counts[work_id] = len(parsed)
            omitted_backward_count += max(0, len(parsed) - limit_per_direction)
            references_by_seed[work_id] = parsed[:limit_per_direction]
        missing_seeds = set(seeds) - returned_seed_ids
        if missing_seeds:
            errors.append({"stage": "work_details", "error_code": "seed_record_missing"})

        reference_owner: dict[str, str] = {}
        for seed in seeds:
            for referenced_id in references_by_seed.get(seed, []):
                reference_owner.setdefault(referenced_id, seed)
        if any(error["error_code"] == "provider_rate_limited" for error in errors):
            reference_owner.clear()
        if reference_owner:
            referenced_ids = list(reference_owner)
            reference_payload = request_payload(
                "backward_references",
                {
                    "filter": "openalex:" + "|".join(referenced_ids),
                    "per_page": str(len(referenced_ids)),
                    "select": SELECT_FIELDS,
                },
            )
            if reference_payload is not None:
                for item in reference_payload["results"][: len(referenced_ids)]:
                    record_id = (
                        _openalex_work_id(item.get("id")) if isinstance(item, dict) else None
                    )
                    if record_id not in reference_owner:
                        continue
                    seed_id = reference_owner[record_id]
                    record = _record(item, f"citation_backward from {seed_id}")
                    if record is None:
                        continue
                    candidates.append(CitationExpansionCandidate("backward", seed_id, record))

        for seed in seeds:
            if errors:
                break
            if seed not in returned_seed_ids:
                continue
            payload = request_payload(
                "forward_citations",
                {
                    "filter": f"cites:{seed}",
                    "per_page": str(limit_per_direction),
                    "sort": "-publication_date",
                    "select": SELECT_FIELDS,
                },
            )
            if payload is None:
                break
            meta = payload.get("meta")
            count = meta.get("count") if isinstance(meta, dict) else None
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                forward_result_counts[seed] = count
            returned = 0
            for item in payload["results"][:limit_per_direction]:
                record = (
                    _record(item, f"citation_forward from {seed}")
                    if isinstance(item, dict)
                    else None
                )
                if record is None:
                    continue
                candidates.append(CitationExpansionCandidate("forward", seed, record))
                returned += 1
            forward_returned_counts[seed] = returned

        status: Literal["completed", "partial", "failed"] = (
            "completed" if not errors else "partial" if candidates else "failed"
        )
        return CitationExpansionResult(
            status=status,
            seed_openalex_ids=seeds,
            candidates=candidates,
            requests_attempted=requests_attempted,
            reported_cost_usd=reported_cost_total if cost_complete else None,
            reported_cost_status="provider_reported_complete" if cost_complete else "unknown",
            omitted_backward_count=omitted_backward_count,
            backward_available_counts=backward_available_counts,
            forward_result_counts=forward_result_counts,
            forward_returned_counts=forward_returned_counts,
            errors=errors[:8],
        )


def configured_openalex_provider() -> OpenAlexProvider:
    return OpenAlexProvider(
        api_key=settings.openalex_api_key,
        allow_billable_calls=settings.openalex_allow_billable_calls,
    )
