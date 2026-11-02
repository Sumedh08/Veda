"""Bounded metadata discovery through the OpenAIRE Graph public API."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.scholarly import ScholarlyWork

OPENAIRE_API_BASE = "https://api.openaire.eu/graph/v4"
OPENAIRE_LICENSE_URL = "https://graph.openaire.eu/docs/apis/terms/"
MAX_OPENAIRE_RESPONSE_BYTES = 2_000_000
MAX_OPENAIRE_QUERY_CHARS = 500
MAX_OPENAIRE_RESULTS = 10
MAX_OPENAIRE_ORGANIZATIONS = 10
_DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s<>\x00-\x1f]{1,240}$", re.IGNORECASE)
_ROR_RE = re.compile(r"^https://ror\.org/[0-9a-z]{9}$", re.IGNORECASE)
_OPENAIRE_ID_RE = re.compile(r"^[A-Za-z0-9_:.\-]{1,300}$")


class OpenAIREError(Exception):
    """Sanitized OpenAIRE API failure; raw provider responses are never included."""

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


def _organization_result(item: Any) -> dict[str, str | None] | None:
    if not isinstance(item, dict):
        return None
    openaire_id = item.get("id")
    name = _clean_text(item.get("legalName"), limit=300)
    if not isinstance(openaire_id, str) or not _OPENAIRE_ID_RE.fullmatch(openaire_id) or not name:
        return None
    ror_id = None
    pids = item.get("pids")
    if isinstance(pids, list):
        for pid in pids[:100]:
            if (
                isinstance(pid, dict)
                and str(pid.get("scheme", "")).casefold() == "ror"
                and isinstance(pid.get("value"), str)
                and _ROR_RE.fullmatch(pid["value"])
            ):
                ror_id = pid["value"].casefold()
                break
    countries = item.get("countries")
    country_code = _country_code(countries) if isinstance(countries, list) else None
    return {
        "openaire_id": openaire_id,
        "canonical_name": name,
        "short_name": _clean_text(item.get("legalShortName"), limit=300),
        "website_url": _safe_https_url(item.get("websiteurl")),
        "country_code": country_code,
        "ror_id": ror_id,
        "organization_type": _clean_text(item.get("type"), limit=100),
    }


class _PlainTextParser(HTMLParser):
    _BLOCKED = {"script", "style", "iframe", "object", "svg", "math"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self._BLOCKED:
            self.blocked_depth += 1
        elif not self.blocked_depth and tag.casefold() in {"p", "br", "li", "div"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        folded = tag.casefold()
        if folded in self._BLOCKED and self.blocked_depth:
            self.blocked_depth -= 1
        elif not self.blocked_depth and folded in {"p", "li", "div"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.parts.append(data)


def _clean_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _PlainTextParser()
    try:
        parser.feed(value[:20_000])
        parser.close()
    except Exception:
        return None
    normalized = " ".join("".join(parser.parts).split())
    return normalized[:limit].strip() or None


def _safe_https_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parsed = urlsplit(value.strip())
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or re.search(r"[\r\n\x00]", value)
    ):
        return None
    return value.strip()


def _instance_license(instance: dict[str, Any]) -> tuple[str, str] | None:
    raw = instance.get("license", instance.get("licence"))
    code: str | None = None
    license_url: str | None = None
    if isinstance(raw, dict):
        for key in ("code", "classid", "label", "classname"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                code = value.strip()
                break
        for key in ("url", "uri", "href"):
            license_url = _safe_https_url(raw.get(key))
            if license_url:
                break
    elif isinstance(raw, str):
        code = raw.strip()
        license_url = _safe_https_url(raw)

    normalized = re.sub(r"[^a-z0-9]+", "", (code or "").casefold())
    code_license = None
    if normalized in {
        "ccby",
        "ccby4",
        "ccby40",
        "ccby3",
        "ccby30",
        "creativecommonsattribution40international",
        "creativecommonsattribution30unported",
    }:
        code_license = "cc-by"
    elif normalized in {"cc0", "cc01", "cc010", "creativecommonszero"}:
        code_license = "cc0"

    url_license = None
    if license_url:
        parsed = urlsplit(license_url)
        if not parsed.hostname or parsed.hostname.casefold() not in {
            "creativecommons.org",
            "www.creativecommons.org",
        }:
            return None
        path = parsed.path.casefold().rstrip("/")
        if re.fullmatch(r"/licenses/by/(?:3\.0|4\.0)", path):
            url_license = "cc-by"
            license_url = f"https://creativecommons.org{path}/"
        elif path == "/publicdomain/zero/1.0":
            url_license = "cc0"
            license_url = "https://creativecommons.org/publicdomain/zero/1.0/"
        else:
            # A restrictive variant (for example BY-NC-ND) must not be
            # normalized into the unrestricted BY family.
            return None

    if code_license and url_license and code_license != url_license:
        return None
    accepted = code_license or url_license
    if accepted == "cc-by":
        return "cc-by", license_url or "https://creativecommons.org/licenses/by/4.0/"
    if accepted == "cc0":
        return "cc0", license_url or "https://creativecommons.org/publicdomain/zero/1.0/"
    return None


def _repository_instances(instances: Any) -> list[dict[str, str | None]]:
    if not isinstance(instances, list):
        return []
    records: list[dict[str, str | None]] = []
    seen_urls: set[str] = set()
    for instance in instances[:16]:
        if not isinstance(instance, dict):
            continue
        rights = _instance_license(instance)
        if rights is None:
            continue
        instance_urls = instance.get("urls")
        if not isinstance(instance_urls, list):
            instance_urls = [instance.get("url")]
        instance_type = instance.get("type")
        content_version = instance.get("contentVersion", instance.get("version"))
        access_right = instance.get("accessRight", instance.get("accessright"))
        if isinstance(access_right, dict):
            access_right = access_right.get("label", access_right.get("code"))
        hosted_by = instance.get("hostedby", instance.get("hostedBy"))
        repository_name = hosted_by.get("name") if isinstance(hosted_by, dict) else None
        repository_url = hosted_by.get("url") if isinstance(hosted_by, dict) else None
        for raw_url in instance_urls[:8]:
            url = _safe_https_url(raw_url)
            if url is None or url in seen_urls:
                continue
            seen_urls.add(url)
            records.append(
                {
                    "url": url,
                    "license_code": rights[0],
                    "license_url": rights[1],
                    "content_version": content_version[:80]
                    if isinstance(content_version, str)
                    else None,
                    "instance_type": instance_type[:100]
                    if isinstance(instance_type, str)
                    else None,
                    "access_right": access_right[:80] if isinstance(access_right, str) else None,
                    "repository_name": repository_name[:200]
                    if isinstance(repository_name, str)
                    else None,
                    "repository_url": _safe_https_url(repository_url),
                }
            )
            if len(records) >= 24:
                return records
    return records


def _doi_from_pids(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value[:100]:
        if not isinstance(item, dict) or str(item.get("scheme", "")).casefold() != "doi":
            continue
        candidate = item.get("value")
        if not isinstance(candidate, str):
            continue
        doi = candidate.strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi.casefold().startswith(prefix):
                doi = doi[len(prefix) :]
                break
        if _DOI_RE.fullmatch(doi):
            return doi.casefold()
    return None


def _country_code(value: Any) -> str | None:
    values = value if isinstance(value, list) else [value]
    for item in values[:8]:
        code = item.get("code") if isinstance(item, dict) else None
        if isinstance(code, str) and re.fullmatch(r"[A-Za-z]{2}", code.strip()):
            return code.strip().upper()
    return None


def _organization_records(value: Any) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for item in value[:40]:
        if not isinstance(item, dict):
            continue
        openaire_id = item.get("id")
        name = _clean_text(item.get("legalName"), limit=300)
        if (
            not isinstance(openaire_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_:-]{1,300}", openaire_id)
            or name is None
            or openaire_id in seen
        ):
            continue
        seen.add(openaire_id)
        pids = item.get("pids")
        ror_id = None
        if isinstance(pids, list):
            for pid in pids[:100]:
                candidate = pid.get("value") if isinstance(pid, dict) else None
                if isinstance(candidate, str) and _ROR_RE.fullmatch(candidate):
                    ror_id = candidate.casefold()
                    break
        result.append(
            {
                "openaire_id": openaire_id,
                "ror_id": ror_id,
                "display_name": name,
                "website_url": _safe_https_url(item.get("websiteurl")),
                "country_code": _country_code(item.get("countries")),
                "type": "openaire_affiliation",
            }
        )
    return result


def _work_from_result(item: dict[str, Any], *, query: str) -> ScholarlyWork | None:
    title = _clean_text(item.get("mainTitle"), limit=1000)
    product_id = item.get("id")
    if (
        title is None
        or not isinstance(product_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_:.\-]{1,300}", product_id)
    ):
        return None
    doi = _doi_from_pids(item.get("pids"))
    external_id = f"doi:{doi}" if doi else f"openaire:{product_id}"
    instances = item.get("instances")
    instance_types: list[str] = []
    urls: list[str] = []
    if isinstance(instances, list):
        for instance in instances[:16]:
            if not isinstance(instance, dict):
                continue
            instance_type = instance.get("type")
            if isinstance(instance_type, str) and instance_type.strip():
                instance_types.append(instance_type.strip()[:100])
            instance_urls = instance.get("urls")
            if isinstance(instance_urls, list):
                urls.extend(
                    safe_url
                    for safe_url in (_safe_https_url(raw) for raw in instance_urls[:8])
                    if safe_url is not None
                )
    repository_instances = _repository_instances(instances)
    url = f"https://doi.org/{doi}" if doi else next(iter(dict.fromkeys(urls)), None)
    raw_authors = item.get("authors")
    authors: list[dict[str, str]] = []
    if isinstance(raw_authors, list):
        for author in raw_authors[:32]:
            name = (
                _clean_text(author.get("fullName"), limit=160) if isinstance(author, dict) else None
            )
            if name:
                authors.append({"name": name})
    raw_date = item.get("publicationDate")
    year_match = re.match(r"^(\d{4})", raw_date) if isinstance(raw_date, str) else None
    abstract_excerpt = None
    abstract_excerpt_truncated = False
    descriptions = item.get("descriptions")
    if isinstance(descriptions, list):
        for description in descriptions[:4]:
            full_excerpt = _clean_text(description, limit=2400)
            if full_excerpt:
                abstract_excerpt_truncated = len(full_excerpt) > 600
                abstract_excerpt = full_excerpt[:600].rstrip() or None
                break
    organization_records = _organization_records(item.get("organizations"))
    sources = item.get("sources")
    source_names = (
        [value[:200] for value in sources[:16] if isinstance(value, str)]
        if isinstance(sources, list)
        else []
    )

    original_ids = (
        [value[:300] for value in item.get("originalIds", [])[:32] if isinstance(value, str)]
        if isinstance(item.get("originalIds"), list)
        else []
    )
    subjects = (
        [
            str(subject.get("subject", {}).get("value"))[:240]
            for subject in item.get("subjects", [])[:32]
            if isinstance(subject, dict)
            and isinstance(subject.get("subject"), dict)
            and isinstance(subject["subject"].get("value"), str)
        ]
        if isinstance(item.get("subjects"), list)
        else []
    )
    return ScholarlyWork(
        external_id=external_id,
        title=title,
        doi=doi,
        url=url,
        authors=authors,
        published_year=int(year_match.group(1)) if year_match else None,
        publisher=_clean_text(item.get("publisher"), limit=300),
        abstract_excerpt=abstract_excerpt,
        query=query,
        provider="OpenAIRE",
        provider_metadata={
            "openaire_id": product_id,
            "metadata_license": "CC-BY-4.0",
            "metadata_attribution": "OpenAIRE Graph; attribution required under CC-BY",
            "metadata_license_url": OPENAIRE_LICENSE_URL,
            "organization_records": organization_records,
            "abstract_excerpt_truncated": abstract_excerpt_truncated,
            "original_ids": original_ids,
            "source_names": source_names,
            "instance_types": list(dict.fromkeys(instance_types))[:16],
            "repository_instances": repository_instances,
            "subjects": list(dict.fromkeys(subjects))[:32],
        },
    )


def exact_repository_instances(
    works: list[ScholarlyWork], *, doi: str, title: str, license_code: str
) -> list[dict[str, Any]]:
    """Return licensed locations only from an exact DOI and title match.

    OpenAIRE search is fuzzy. A location is not joined to a Crossref record unless
    both canonical identifiers and normalized titles agree.
    """
    expected_doi = doi.strip().removeprefix("https://doi.org/").casefold()
    expected_title = " ".join(re.findall(r"[a-z0-9]+", title.casefold()))
    expected_license = license_code.strip().casefold()
    if not expected_doi or not expected_title or expected_license not in {"cc0", "cc-by"}:
        return []
    for work in works:
        if work.provider.casefold() != "openaire" or not work.doi:
            continue
        work_doi = work.doi.strip().removeprefix("https://doi.org/").casefold()
        work_title = " ".join(re.findall(r"[a-z0-9]+", work.title.casefold()))
        if work_doi != expected_doi or work_title != expected_title:
            continue
        instances = work.provider_metadata.get("repository_instances")
        if not isinstance(instances, list):
            return []
        return [
            instance
            for instance in instances[:24]
            if isinstance(instance, dict)
            and instance.get("license_code") == expected_license
            and isinstance(instance.get("url"), str)
        ]
    return []


class OpenAIREProvider:
    """Search OpenAIRE metadata; no documents or full-text URLs are fetched."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        before_request: Callable[[], None] | None = None,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(10, connect=4),
            headers={"User-Agent": "VedaResearch/0.1 (scholarly metadata discovery)"},
            follow_redirects=False,
        )
        if client is not None:
            self.client.follow_redirects = False
        self.before_request = before_request

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _request_v3_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.before_request is not None:
            try:
                self.before_request()
            except OpenAIREError:
                raise
            except Exception:
                raise OpenAIREError(
                    "OpenAIRE metadata request was deferred before dispatch",
                    code="origin_request_deferred",
                    request_dispatched=False,
                ) from None
        try:
            with self.client.stream(
                "GET",
                f"https://api.openaire.eu/graph/v3/{endpoint}",
                params=params,
                headers={"Accept": "application/json"},
            ) as response:
                if 300 <= response.status_code < 400:
                    raise OpenAIREError(
                        "OpenAIRE redirect was rejected",
                        code="redirect_rejected",
                        request_dispatched=True,
                    )
                if response.status_code == 429:
                    raw_retry = response.headers.get("Retry-After")
                    retry_after = float(raw_retry) if raw_retry and raw_retry.isdigit() else None
                    raise OpenAIREError(
                        "OpenAIRE rate limit reached",
                        code="rate_limited",
                        retry_after_seconds=retry_after,
                        request_dispatched=True,
                    )
                if response.status_code >= 400:
                    raise OpenAIREError(
                        "OpenAIRE metadata search failed",
                        code="provider_unavailable"
                        if response.status_code >= 500
                        else "provider_rejected_request",
                        request_dispatched=True,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_OPENAIRE_RESPONSE_BYTES:
                        raise OpenAIREError(
                            "OpenAIRE response exceeded the size limit",
                            code="too_large",
                            request_dispatched=True,
                        )
                payload = json.loads(body)
        except OpenAIREError:
            raise
        except httpx.HTTPError:
            raise OpenAIREError(
                "OpenAIRE metadata search failed",
                code="provider_unavailable",
                request_dispatched=True,
            ) from None
        except (ValueError, TypeError):
            raise OpenAIREError(
                "OpenAIRE returned an invalid response",
                code="invalid_response",
                request_dispatched=True,
            ) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise OpenAIREError(
                "OpenAIRE returned an invalid result set",
                code="invalid_response",
                request_dispatched=True,
            )
        return payload

    def search_organizations(self, query: str, *, limit: int = 8) -> list[dict[str, str | None]]:
        """Find organizations by topic-related research content, not user-supplied names."""
        normalized = " ".join(query.split()) if isinstance(query, str) else ""
        if (
            not normalized
            or len(normalized) > MAX_OPENAIRE_QUERY_CHARS
            or re.search(r"[\x00-\x1f\x7f]", normalized)
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
        ):
            raise OpenAIREError("OpenAIRE organization query is invalid", code="invalid_query")
        page_size = min(limit, MAX_OPENAIRE_ORGANIZATIONS)
        payload = self._request_v3_json(
            "organizations",
            {
                "search": normalized,
                "page": 1,
                "pageSize": page_size,
                "sortBy": "relevance DESC",
            },
        )
        organizations: list[dict[str, str | None]] = []
        seen: set[str] = set()
        for item in payload["results"][:page_size]:
            organization = _organization_result(item)
            if organization is None or organization["openaire_id"] in seen:
                continue
            seen.add(str(organization["openaire_id"]))
            organizations.append(organization)
        return organizations

    def search_organization_publications(
        self,
        organization_ids: list[str],
        *,
        query: str,
        limit: int = 8,
    ) -> list[ScholarlyWork]:
        """Retrieve real products linked to discovered organizations, then rank locally.

        OpenAIRE's documented `relOrganizationId` filter supports logical OR. The
        topic query is retained as provenance but is deliberately not sent here: a
        local lexical filter can then compare the bounded, organization-linked set
        without requiring every query token to match OpenAIRE's index fields.
        """
        normalized_query = " ".join(query.split()) if isinstance(query, str) else ""
        if (
            not normalized_query
            or len(normalized_query) > MAX_OPENAIRE_QUERY_CHARS
            or re.search(r"[\x00-\x1f\x7f]", normalized_query)
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
            or not isinstance(organization_ids, list)
            or not 1 <= len(organization_ids) <= 2
            or any(
                not isinstance(value, str) or not _OPENAIRE_ID_RE.fullmatch(value)
                for value in organization_ids
            )
            or len(set(organization_ids)) != len(organization_ids)
        ):
            raise OpenAIREError(
                "OpenAIRE organization publication request is invalid", code="invalid_query"
            )
        relation = (
            organization_ids[0]
            if len(organization_ids) == 1
            else "(" + " OR ".join(f'"{value}"' for value in organization_ids) + ")"
        )
        page_size = min(limit, MAX_OPENAIRE_RESULTS)
        payload = self._request_v3_json(
            "research-products",
            {
                "type": "publication",
                "relOrganizationId": relation,
                "page": 1,
                "pageSize": page_size,
                "sortBy": "relevance DESC",
            },
        )
        records: list[ScholarlyWork] = []
        for item in payload["results"][:page_size]:
            if not isinstance(item, dict):
                continue
            record = _work_from_result(item, query=normalized_query)
            if record is not None:
                records.append(record)
        return records

    def search(self, query: str, *, limit: int = 8) -> list[ScholarlyWork]:
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_OPENAIRE_QUERY_CHARS:
            raise OpenAIREError("OpenAIRE query is invalid", code="invalid_query")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise OpenAIREError("OpenAIRE result limit is invalid", code="invalid_limit")
        page_size = min(limit, MAX_OPENAIRE_RESULTS)
        if self.before_request is not None:
            try:
                self.before_request()
            except OpenAIREError:
                raise
            except Exception:
                raise OpenAIREError(
                    "OpenAIRE request was deferred before dispatch",
                    code="origin_request_deferred",
                    request_dispatched=False,
                ) from None

        try:
            with self.client.stream(
                "GET",
                f"{OPENAIRE_API_BASE}/research-products",
                params={
                    "search": query.strip(),
                    "filter": "type:publication",
                    "page_size": page_size,
                },
                headers={"Accept": "application/json"},
            ) as response:
                if 300 <= response.status_code < 400:
                    raise OpenAIREError(
                        "OpenAIRE redirect was rejected",
                        code="redirect_rejected",
                        request_dispatched=True,
                    )
                if response.status_code == 429:
                    raw_retry = response.headers.get("Retry-After")
                    retry_after = float(raw_retry) if raw_retry and raw_retry.isdigit() else None
                    raise OpenAIREError(
                        "OpenAIRE rate limit reached",
                        code="rate_limited",
                        retry_after_seconds=retry_after,
                        request_dispatched=True,
                    )
                if response.status_code >= 400:
                    raise OpenAIREError(
                        "OpenAIRE metadata search failed",
                        code="provider_unavailable"
                        if response.status_code >= 500
                        else "provider_rejected_request",
                        request_dispatched=True,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_OPENAIRE_RESPONSE_BYTES:
                        raise OpenAIREError(
                            "OpenAIRE response exceeded the size limit",
                            code="too_large",
                            request_dispatched=True,
                        )
                payload = json.loads(body)
        except OpenAIREError:
            raise
        except httpx.HTTPError:
            raise OpenAIREError(
                "OpenAIRE metadata search failed",
                code="provider_unavailable",
                request_dispatched=True,
            ) from None
        except (ValueError, TypeError):
            raise OpenAIREError(
                "OpenAIRE returned an invalid response",
                code="invalid_response",
                request_dispatched=True,
            ) from None

        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise OpenAIREError(
                "OpenAIRE returned an invalid result set",
                code="invalid_response",
                request_dispatched=True,
            )
        records = []
        for item in payload["results"][:page_size]:
            if not isinstance(item, dict):
                continue
            record = _work_from_result(item, query=query.strip())
            if record is not None:
                records.append(record)
        return records
