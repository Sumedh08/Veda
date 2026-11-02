"""Item-scoped corroboration for DOI-less OpenAIRE publication leads.

This module verifies a particular catalog record and its linked location. It
does not infer an organization's general authority, publication quality, or
content rights from that record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from app.providers.scholarly import ScholarlyWork

_OPENAIRE_ID = re.compile(r"^[A-Za-z0-9_:.-]{1,300}$")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_GENERIC_PUBLICATION_PATHS = {
    "document",
    "documents",
    "index",
    "index.html",
    "insights",
    "news",
    "publication",
    "publication-details",
    "publications",
    "report",
    "reports",
    "research",
    "research-publications",
    "resources",
}


@dataclass(frozen=True)
class OpenAIREPublicationLeadMatch:
    status: Literal["corroborated", "unverified"]
    reason_code: str
    catalog_record_id: str | None = None
    organization: dict[str, Any] | None = None
    official_domain: str | None = None


def _normalized_title(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold())) if isinstance(value, str) else ""


def _safe_https_host(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        return None
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
        host = (parsed.hostname or "").encode("idna").decode("ascii").casefold().rstrip(".")
    except (UnicodeError, ValueError):
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or host in {"localhost", "localhost.localdomain"}
        or not all(_HOST_LABEL.fullmatch(label) for label in host.split("."))
    ):
        return None
    return host


def _domain_key(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().casefold().rstrip(".")
    if candidate.startswith("www."):
        candidate = candidate[4:]
    if not candidate or "/" in candidate or ":" in candidate:
        return None
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if not all(_HOST_LABEL.fullmatch(label) for label in candidate.split(".")):
        return None
    return candidate


def _name_key(value: object) -> str:
    return _normalized_title(value)


def _has_item_specific_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    leaf = parsed.path.rstrip("/").rsplit("/", 1)[-1].casefold()
    return bool(leaf and leaf not in _GENERIC_PUBLICATION_PATHS)


def corroborate_openaire_publication_lead(
    work: ScholarlyWork,
    search_hit: dict[str, Any],
) -> OpenAIREPublicationLeadMatch:
    """Match a web lead to an external catalog record and linked organization.

    Acceptance requires exact normalized title agreement, a stable OpenAIRE
    product identifier, the same HTTPS host for the result and catalog
    location, and exactly one OpenAIRE organization record whose website host
    and canonical name agree with the catalog publisher. The result is scoped
    to this work; it is not evidence of organization-wide quality or rights.
    """
    if work.provider.casefold() != "openaire":
        return OpenAIREPublicationLeadMatch("unverified", "unsupported_catalog_provider")

    metadata = work.provider_metadata if isinstance(work.provider_metadata, dict) else {}
    raw_record_id = metadata.get("openaire_id")
    if not isinstance(raw_record_id, str) or not _OPENAIRE_ID.fullmatch(raw_record_id):
        return OpenAIREPublicationLeadMatch("unverified", "catalog_record_id_missing")
    external_id = work.external_id.strip()
    if work.doi:
        if external_id.casefold() != f"doi:{work.doi}".casefold():
            return OpenAIREPublicationLeadMatch("unverified", "catalog_record_identity_mismatch")
    elif external_id != f"openaire:{raw_record_id}":
        return OpenAIREPublicationLeadMatch("unverified", "catalog_record_identity_mismatch")

    title_key = _normalized_title(work.title)
    lead_title_key = _normalized_title(search_hit.get("title"))
    if not title_key or title_key != lead_title_key:
        return OpenAIREPublicationLeadMatch("unverified", "catalog_title_mismatch")

    hit_domain = _domain_key(search_hit.get("domain"))
    hit_host = _safe_https_host(search_hit.get("url"))
    catalog_host = _safe_https_host(work.url)
    if not _has_item_specific_path(search_hit.get("url")) or not _has_item_specific_path(work.url):
        return OpenAIREPublicationLeadMatch("unverified", "catalog_location_not_item_specific")
    if (
        hit_domain is None
        or hit_host is None
        or catalog_host is None
        or _domain_key(hit_host) != hit_domain
        or _domain_key(catalog_host) != hit_domain
        or _safe_https_host(search_hit.get("url")) is None
        or urlsplit(str(search_hit.get("url"))).path in {"", "/"}
        or urlsplit(str(work.url)).path in {"", "/"}
    ):
        return OpenAIREPublicationLeadMatch("unverified", "catalog_location_domain_mismatch")

    publisher_key = _name_key(work.publisher)
    organization_records = metadata.get("organization_records")
    if not publisher_key or not isinstance(organization_records, list):
        return OpenAIREPublicationLeadMatch("unverified", "publisher_organization_domain_mismatch")

    domain_records = []
    for item in organization_records[:40]:
        if not isinstance(item, dict):
            continue
        organization_id = item.get("openaire_id")
        if not isinstance(organization_id, str) or not _OPENAIRE_ID.fullmatch(organization_id):
            continue
        organization_host = _safe_https_host(item.get("website_url"))
        if organization_host and _domain_key(organization_host) == hit_domain:
            domain_records.append(item)
    if not domain_records:
        return OpenAIREPublicationLeadMatch("unverified", "publisher_organization_domain_mismatch")

    named_records = [
        item for item in domain_records if _name_key(item.get("display_name")) == publisher_key
    ]
    if not named_records:
        return OpenAIREPublicationLeadMatch("unverified", "publisher_organization_name_mismatch")
    if len(named_records) != 1:
        return OpenAIREPublicationLeadMatch("unverified", "publisher_organization_ambiguous")

    organization = named_records[0]
    return OpenAIREPublicationLeadMatch(
        status="corroborated",
        reason_code="exact_catalog_title_location_and_publisher_domain_match",
        catalog_record_id=raw_record_id,
        organization=organization,
        official_domain=hit_domain,
    )
