"""Bounded identity verification against the Research Organization Registry."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

ROR_API_BASE = "https://api.ror.org/v2/organizations"
ROR_ID_RE = re.compile(r"(?:https://ror\.org/)?([0-9a-z]{9})/?", re.IGNORECASE)
MAX_ROR_RESPONSE_BYTES = 512_000
_DOMAIN_PATTERN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")


def _normalized_domain(value: object, *, website_url: bool = False) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if website_url:
        try:
            parsed = urlsplit(candidate)
            if (
                parsed.scheme.casefold() != "https"
                or parsed.username is not None
                or parsed.password is not None
                or parsed.port not in {None, 443}
            ):
                return None
            candidate = parsed.hostname or ""
        except ValueError:
            return None
    try:
        normalized = candidate.encode("idna").decode("ascii").casefold().rstrip(".")
    except UnicodeError:
        return None
    normalized = normalized.removeprefix("www.")
    return normalized if _DOMAIN_PATTERN.fullmatch(normalized) else None


class RORProviderError(Exception):
    """Sanitized failure from one exact ROR identity lookup."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ROROrganization:
    ror_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    organization_types: tuple[str, ...]
    domains: tuple[str, ...]
    official_urls: tuple[str, ...]
    country_code: str | None
    record_status: str
    last_modified: str | None
    retrieved_at: str
    api_url: str

    def matches_domain(self, expected_domain: str) -> bool:
        """Match exact official domains or HTTPS website links from the ROR record."""
        expected = _normalized_domain(expected_domain)
        if expected is None:
            return False
        if any(_normalized_domain(value) == expected for value in self.domains):
            return True
        return any(
            _normalized_domain(value, website_url=True) == expected for value in self.official_urls
        )


class RORProvider:
    """Resolve exact ROR IDs; it does not infer quality from registry membership."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(8, connect=3),
            headers={"User-Agent": "VedaResearch/0.1 (organization identity lookup)"},
            follow_redirects=False,
        )
        if client is not None:
            self.client.follow_redirects = False

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def search_exact_id(self, expected_name: str) -> str | None:
        """Find a ROR ID only when the official result has an exact name/alias match."""
        normalized = " ".join(expected_name.split()) if isinstance(expected_name, str) else ""
        if not normalized or len(normalized) > 300 or re.search(r"[\x00-\x1f\x7f]", normalized):
            raise RORProviderError("ROR organization name is invalid", code="invalid_name")
        try:
            with self.client.stream(
                "GET",
                ROR_API_BASE,
                params={"query": normalized, "page": 1},
                headers={"Accept": "application/json"},
            ) as response:
                if 300 <= response.status_code < 400:
                    raise RORProviderError("ROR redirect was rejected", code="redirect_rejected")
                if response.status_code == 429:
                    raise RORProviderError("ROR rate limit reached", code="rate_limited")
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_ROR_RESPONSE_BYTES:
                        raise RORProviderError("ROR search exceeded size limit", code="too_large")
                payload = json.loads(body)
        except RORProviderError:
            raise
        except httpx.HTTPError:
            raise RORProviderError(
                "ROR identity search failed", code="provider_unavailable"
            ) from None
        except (ValueError, TypeError):
            raise RORProviderError(
                "ROR returned an invalid search result", code="invalid_response"
            ) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise RORProviderError("ROR returned an invalid search result", code="invalid_response")

        def normalized_name(value: str) -> str:
            return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))

        wanted = normalized_name(normalized)
        matches: set[str] = set()
        for item in payload["items"][:10]:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            match = ROR_ID_RE.fullmatch(raw_id.strip()) if isinstance(raw_id, str) else None
            names = item.get("names")
            if not match or not isinstance(names, list):
                continue
            values = [
                value
                for entry in names
                if isinstance(entry, dict)
                and isinstance((value := entry.get("value")), str)
                and value.strip()
            ]
            if wanted in {normalized_name(value) for value in values}:
                matches.add(match.group(1).casefold())
        if len(matches) > 1:
            raise RORProviderError(
                "ROR name resolves to multiple exact identities", code="ambiguous_identity"
            )
        return f"https://ror.org/{next(iter(matches))}" if matches else None

    def search_exact_domain(self, expected_domain: str) -> str | None:
        """Resolve a web-discovered host only when ROR records that exact domain.

        ROR's advanced query supports website-domain lookup. The result is still
        rechecked locally against its domains and HTTPS website links; search
        ranking alone is not accepted as identity evidence. Some records publish
        an official website link but omit the redundant domains field.
        """
        domain = _normalized_domain(expected_domain)
        if domain is None:
            raise RORProviderError("ROR domain query is invalid", code="invalid_domain")
        try:
            with self.client.stream(
                "GET",
                ROR_API_BASE,
                params={
                    "query.advanced": f'(domains:"{domain}" OR links.value:"{domain}")',
                    "page": 1,
                },
                headers={"Accept": "application/json"},
            ) as response:
                if 300 <= response.status_code < 400:
                    raise RORProviderError("ROR redirect was rejected", code="redirect_rejected")
                if response.status_code == 429:
                    raise RORProviderError("ROR rate limit reached", code="rate_limited")
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_ROR_RESPONSE_BYTES:
                        raise RORProviderError("ROR search exceeded size limit", code="too_large")
                payload = json.loads(body)
        except RORProviderError:
            raise
        except httpx.HTTPError:
            raise RORProviderError(
                "ROR identity search failed", code="provider_unavailable"
            ) from None
        except (ValueError, TypeError):
            raise RORProviderError(
                "ROR returned an invalid search result", code="invalid_response"
            ) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise RORProviderError("ROR returned an invalid search result", code="invalid_response")
        matches: set[str] = set()
        for item in payload["items"][:20]:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            id_match = ROR_ID_RE.fullmatch(raw_id.strip()) if isinstance(raw_id, str) else None
            domains = item.get("domains")
            links = item.get("links")
            exact_domain = isinstance(domains, list) and any(
                _normalized_domain(value) == domain for value in domains
            )
            if not exact_domain and isinstance(links, list):
                exact_domain = any(
                    isinstance(link, dict)
                    and link.get("type") == "website"
                    and _normalized_domain(link.get("value"), website_url=True) == domain
                    for link in links
                )
            if id_match and exact_domain:
                matches.add(id_match.group(1).casefold())
        if len(matches) > 1:
            raise RORProviderError(
                "ROR domain resolves to multiple identities", code="ambiguous_domain"
            )
        return f"https://ror.org/{next(iter(matches))}" if matches else None

    def verify(self, value: str) -> ROROrganization:
        match = ROR_ID_RE.fullmatch(value.strip()) if isinstance(value, str) else None
        if not match:
            raise RORProviderError("ROR identifier is malformed", code="invalid_ror_id")
        ror_id = match.group(1).casefold()
        try:
            with self.client.stream(
                "GET", f"{ROR_API_BASE}/{ror_id}", headers={"Accept": "application/json"}
            ) as response:
                if 300 <= response.status_code < 400:
                    raise RORProviderError("ROR redirect was rejected", code="redirect_rejected")
                if response.status_code == 404:
                    raise RORProviderError("ROR identity was not found", code="identity_not_found")
                if response.status_code == 429:
                    raise RORProviderError("ROR rate limit reached", code="rate_limited")
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_ROR_RESPONSE_BYTES:
                        raise RORProviderError("ROR record exceeded size limit", code="too_large")
                payload = json.loads(body)
        except RORProviderError:
            raise
        except httpx.HTTPError:
            raise RORProviderError(
                "ROR identity lookup failed", code="provider_unavailable"
            ) from None
        except (ValueError, TypeError):
            raise RORProviderError(
                "ROR returned an invalid record", code="invalid_response"
            ) from None

        if not isinstance(payload, dict):
            raise RORProviderError("ROR returned an invalid record", code="invalid_response")
        returned_id = payload.get("id")
        returned_match = (
            ROR_ID_RE.fullmatch(returned_id.strip()) if isinstance(returned_id, str) else None
        )
        if not returned_match or returned_match.group(1).casefold() != ror_id:
            raise RORProviderError(
                "ROR record identity did not match request", code="identity_mismatch"
            )

        names = payload.get("names")
        if not isinstance(names, list):
            raise RORProviderError("ROR record omitted its names", code="invalid_response")
        name_values = list(
            dict.fromkeys(
                " ".join(item["value"].split())[:300]
                for item in names
                if isinstance(item, dict)
                and isinstance(item.get("value"), str)
                and item["value"].strip()
            )
        )
        if not name_values:
            raise RORProviderError("ROR record omitted its names", code="invalid_response")
        preferred = next(
            (
                item["value"].strip()
                for item in names
                if isinstance(item, dict)
                and "ror_display" in item.get("types", [])
                and isinstance(item.get("value"), str)
                and item["value"].strip()
            ),
            name_values[0],
        )
        types = payload.get("types")
        domains = payload.get("domains")
        links = payload.get("links")
        locations = payload.get("locations")
        if (
            not isinstance(types, list)
            or not isinstance(domains, list)
            or not isinstance(links, list)
        ):
            raise RORProviderError("ROR record fields were malformed", code="invalid_response")
        country_code = None
        if isinstance(locations, list):
            for location in locations:
                details = location.get("geonames_details") if isinstance(location, dict) else None
                country = details.get("country_code") if isinstance(details, dict) else None
                if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country):
                    country_code = country.upper()
                    break
        official_urls = []
        for link in links:
            url = (
                link.get("value")
                if isinstance(link, dict) and link.get("type") == "website"
                else None
            )
            if not isinstance(url, str):
                continue
            parsed = urlsplit(url)
            if (
                parsed.scheme == "https"
                and parsed.hostname
                and not parsed.username
                and not parsed.password
            ):
                official_urls.append(url[:1000])
        admin = payload.get("admin")
        modified = admin.get("last_modified") if isinstance(admin, dict) else None
        modified_date = modified.get("date") if isinstance(modified, dict) else None
        return ROROrganization(
            ror_id=f"https://ror.org/{ror_id}",
            canonical_name=preferred[:300],
            aliases=tuple(
                value for value in name_values if value.casefold() != preferred.casefold()
            )[:32],
            organization_types=tuple(
                dict.fromkeys(value.casefold() for value in types if isinstance(value, str))
            )[:16],
            domains=tuple(
                dict.fromkeys(
                    value.casefold().strip().rstrip(".")
                    for value in domains[:32]
                    if isinstance(value, str)
                    and value.strip()
                    and "/" not in value
                    and ":" not in value
                    and " " not in value
                )
            ),
            official_urls=tuple(dict.fromkeys(official_urls))[:8],
            country_code=country_code,
            record_status=payload.get("status")
            if payload.get("status") in {"active", "inactive", "withdrawn"}
            else "unknown",
            last_modified=modified_date if isinstance(modified_date, str) else None,
            retrieved_at=datetime.now(UTC).isoformat(),
            api_url=f"{ROR_API_BASE}/{ror_id}",
        )
