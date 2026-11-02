"""Discover relevant organizations from observed scholarly affiliations."""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.providers.ror import ROROrganization, RORProviderError
from app.providers.scholarly import ScholarlyWork
from app.research.source_governance import default_registry


class OrganizationEvidenceV1(BaseModel):
    """Identity and publication evidence; this record is not a quality rating."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    organization_id: str = Field(min_length=1, max_length=300)
    openalex_ids: list[str] = Field(default_factory=list, max_length=12)
    openaire_ids: list[str] = Field(default_factory=list, max_length=12)
    canonical_name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=32)
    organization_types: list[str] = Field(default_factory=list, max_length=16)
    official_domains: list[str] = Field(default_factory=list, max_length=32)
    official_urls: list[str] = Field(default_factory=list, max_length=8)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    identity_status: Literal[
        "VERIFIED_ESTABLISHED",
        "VERIFIED_DOMAIN_SPECIALIST",
        "PENDING_VERIFICATION",
        "UNVERIFIED_OR_REJECTED",
    ]
    verification_method: str = Field(min_length=1, max_length=80)
    verification_source: str | None = Field(default=None, max_length=1000)
    verification_date: str | None = Field(default=None, max_length=32)
    verification_timestamp: str | None = Field(default=None, max_length=40)
    source_record_updated_at: str | None = Field(default=None, max_length=32)
    registry_match: bool
    quality_assessment: Literal["not_assessed"] = "not_assessed"
    related_publications: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=12)


def _normalized_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _registry_contains(openalex_id: str, ror_id: str | None) -> bool:
    registry = default_registry()
    wanted = {
        "openalex": {openalex_id.casefold()},
        "ror": {ror_id.casefold()} if ror_id else set(),
    }
    for record in [*registry.organizations, *registry.universities]:
        for namespace, values in record.identifiers.items():
            namespace_key = namespace.casefold()
            if (
                namespace_key in wanted
                and {value.casefold() for value in values} & wanted[namespace_key]
            ):
                return True
    return False


def organization_registry_match(
    *, openalex_id: str | None = None, openaire_id: str | None = None, ror_id: str | None = None
) -> bool:
    """Check whether verified external identifiers occur in the curated identity registry."""
    if _registry_contains(openalex_id or "", ror_id):
        return True
    if not isinstance(openaire_id, str) or not openaire_id.strip():
        return False
    return any(
        "openaire" in namespace.casefold()
        and openaire_id.casefold() in {value.casefold() for value in values}
        for record in [*default_registry().organizations, *default_registry().universities]
        for namespace, values in record.identifiers.items()
    )


def _publication_reference(work: ScholarlyWork) -> dict[str, Any]:
    metadata = work.provider_metadata if isinstance(work.provider_metadata, dict) else {}
    return {
        "canonical_identity": work.external_id,
        "title": work.title,
        "doi": work.doi,
        "provider": work.provider,
        "publication_year": work.published_year,
        "openalex_id": metadata.get("openalex_id"),
        "openaire_id": metadata.get("openaire_id"),
        "discovery_query": work.query,
    }


def deduplicate_organization_candidates(
    candidates: Sequence[dict[str, Any]], *, limit: int = 2
) -> list[dict[str, Any]]:
    """Keep first-seen distinct identities/names before bounded verification calls.

    Organization catalogs can return duplicate source records for the same legal
    name. Deduplication prevents duplicates from consuming the small identity
    verification budget while retaining same-named organizations in different
    countries or on distinct official domains.
    """
    if not 1 <= limit <= 10:
        raise ValueError("organization candidate limit must be between 1 and 10")
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("canonical_name") or candidate.get("display_name")
        if not isinstance(name, str) or not name.strip():
            continue
        normalized_name = _normalized_name(name)
        if not normalized_name:
            continue
        ror_id = candidate.get("ror_id")
        openaire_id = candidate.get("openaire_id")
        identity = (
            str(ror_id).casefold()
            if isinstance(ror_id, str) and ror_id.strip()
            else str(openaire_id).casefold()
            if isinstance(openaire_id, str) and openaire_id.strip()
            else ""
        )
        country = candidate.get("country_code")
        country_key = country.strip().upper() if isinstance(country, str) else ""
        website = candidate.get("website_url")
        domain_key = ""
        if isinstance(website, str):
            match = re.match(r"^https://([^/:?#]+)", website.strip(), re.IGNORECASE)
            if match:
                domain_key = match.group(1).casefold().removeprefix("www.")
        name_key = (normalized_name, country_key, domain_key)
        if (identity and identity in seen_ids) or name_key in seen_names:
            continue
        if identity:
            seen_ids.add(identity)
        seen_names.add(name_key)
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


def select_official_publication_search_organization(
    organizations: Sequence[dict[str, Any]],
    *,
    planned_source_classes: Sequence[str],
) -> dict[str, Any] | None:
    """Choose a verified organization for the single bounded official-site search.

    When the question calls for government or multilateral coverage, prefer a
    ROR-verified government body over an earlier-ranked publisher. This selects
    which domain receives the limited site-search request; it is not a relevance,
    authority, methodology, or publication-quality score. If no matching body is
    available, preserve the discovery order.
    """
    if not organizations:
        return None
    planned = {item.casefold() for item in planned_source_classes if isinstance(item, str)}
    if planned & {"government", "multilateral"}:
        for organization in organizations:
            if not isinstance(organization, dict):
                continue
            if organization.get("identity_status") != "VERIFIED_ESTABLISHED":
                continue
            types = organization.get("organization_types")
            if isinstance(types, list) and any(
                isinstance(item, str) and item.casefold() == "government" for item in types
            ):
                return organization
    return organizations[0]


def discover_affiliated_organizations(
    works: Sequence[ScholarlyWork],
    *,
    verify_ror: Callable[[str], ROROrganization],
    max_organizations: int = 4,
) -> list[OrganizationEvidenceV1]:
    """Resolve unique affiliations from relevant works; unknowns remain pending.

    Callers must apply Veda's question-relevance eligibility gate to works
    before discovery. At most max_organizations exact ROR lookups occur.
    """
    if not 1 <= max_organizations <= 6:
        raise ValueError("organization discovery limit must be between 1 and 6")
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for work in works:
        metadata = work.provider_metadata if isinstance(work.provider_metadata, dict) else {}
        extensions = metadata.get("extensions")
        extension_metadata = extensions if isinstance(extensions, dict) else {}
        affiliations: list[tuple[dict[str, Any], str]] = []
        openalex_affiliations = metadata.get("institution_records")
        if not isinstance(openalex_affiliations, list):
            openalex_affiliations = extension_metadata.get("institution_records")
        if isinstance(openalex_affiliations, list):
            affiliations.extend(
                (item, "openalex") for item in openalex_affiliations[:100] if isinstance(item, dict)
            )
        openaire_affiliations = metadata.get("organization_records")
        if not isinstance(openaire_affiliations, list):
            openaire_affiliations = extension_metadata.get("organization_records")
        if isinstance(openaire_affiliations, list):
            affiliations.extend(
                (item, "openaire") for item in openaire_affiliations[:40] if isinstance(item, dict)
            )
        for affiliation, discovery_provider in affiliations:
            if not isinstance(affiliation, dict):
                continue
            openalex_id = affiliation.get("openalex_id")
            name = affiliation.get("display_name")
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(openalex_id, str) or not re.fullmatch(r"I[0-9]{1,20}", openalex_id):
                openalex_id = None
            openaire_id = affiliation.get("openaire_id")
            if not isinstance(openaire_id, str) or not re.fullmatch(
                r"[A-Za-z0-9_:\-]{1,300}", openaire_id
            ):
                openaire_id = None
            if openalex_id is None and openaire_id is None:
                continue
            ror_id = affiliation.get("ror_id")
            if not isinstance(ror_id, str) or not re.fullmatch(
                r"https://ror\.org/[0-9a-z]{9}", ror_id, re.I
            ):
                ror_id = None
            key = (
                ror_id.casefold()
                if ror_id
                else f"openalex:{openalex_id}"
                if openalex_id
                else f"openaire:{openaire_id}"
            )
            item = grouped.setdefault(
                key,
                {
                    "openalex_id": openalex_id,
                    "openalex_ids": [],
                    "openaire_id": openaire_id,
                    "openaire_ids": [],
                    "ror_id": ror_id,
                    "affiliation_name": " ".join(name.split())[:300],
                    "country_code": affiliation.get("country_code"),
                    "type": affiliation.get("type"),
                    "discovery_providers": [],
                    "publications": [],
                },
            )
            if openalex_id and openalex_id not in item["openalex_ids"]:
                item["openalex_ids"].append(openalex_id)
                item["openalex_ids"] = item["openalex_ids"][:12]
            if openaire_id and openaire_id not in item["openaire_ids"]:
                item["openaire_ids"].append(openaire_id)
                item["openaire_ids"] = item["openaire_ids"][:12]
            if discovery_provider not in item["discovery_providers"]:
                item["discovery_providers"].append(discovery_provider)
            reference = _publication_reference(work)
            if all(
                entry["canonical_identity"] != reference["canonical_identity"]
                for entry in item["publications"]
            ):
                item["publications"].append(reference)
                item["publications"] = item["publications"][:12]

    output: list[OrganizationEvidenceV1] = []
    for item in list(grouped.values())[:max_organizations]:
        ror_id = item["ror_id"]
        registry_match = organization_registry_match(
            openalex_id=item["openalex_id"],
            openaire_id=item["openaire_id"],
            ror_id=ror_id,
        )
        fallback_id = (
            f"openalex:{item['openalex_id']}"
            if item["openalex_id"]
            else f"openaire:{item['openaire_id']}"
        )
        if not ror_id:
            output.append(
                OrganizationEvidenceV1(
                    organization_id=fallback_id,
                    openalex_ids=item["openalex_ids"],
                    openaire_ids=item["openaire_ids"],
                    canonical_name=item["affiliation_name"],
                    organization_types=[item["type"]] if item["type"] else [],
                    country_code=item["country_code"],
                    identity_status="PENDING_VERIFICATION",
                    verification_method=(
                        "openaire_publication_affiliation_only"
                        if item["openaire_ids"] and not item["openalex_ids"]
                        else "openalex_author_affiliation_only"
                    ),
                    registry_match=registry_match,
                    related_publications=item["publications"],
                    limitations=[
                        "No ROR identifier was attached to the affiliation; official identity and domain remain unverified."
                    ],
                )
            )
            continue
        try:
            verified = verify_ror(ror_id)
        except RORProviderError as exc:
            output.append(
                OrganizationEvidenceV1(
                    organization_id=fallback_id,
                    openalex_ids=item["openalex_ids"],
                    openaire_ids=item["openaire_ids"],
                    canonical_name=item["affiliation_name"],
                    organization_types=[item["type"]] if item["type"] else [],
                    country_code=item["country_code"],
                    identity_status="PENDING_VERIFICATION",
                    verification_method="ror_exact_id_lookup_failed",
                    verification_source=f"https://api.ror.org/v2/organizations/{ror_id.rsplit('/', 1)[-1]}",
                    registry_match=registry_match,
                    related_publications=item["publications"],
                    limitations=[f"ROR identity lookup was not confirmed ({exc.code})."],
                )
            )
            continue
        name_set = {_normalized_name(verified.canonical_name)}
        name_set.update(_normalized_name(alias) for alias in verified.aliases)
        names_match = _normalized_name(item["affiliation_name"]) in name_set
        active = verified.record_status == "active"
        status = "VERIFIED_ESTABLISHED" if active and names_match else "PENDING_VERIFICATION"
        limitations = [
            "ROR verifies organization identity; it does not establish publication quality or methodological reliability."
        ]
        if not names_match:
            limitations.append(
                "OpenAlex affiliation name does not exactly match a ROR name or alias."
            )
        if not active:
            limitations.append(f"ROR organization status is {verified.record_status}.")
        output.append(
            OrganizationEvidenceV1(
                organization_id=verified.ror_id,
                openalex_ids=item["openalex_ids"],
                openaire_ids=item["openaire_ids"],
                canonical_name=verified.canonical_name,
                aliases=list(verified.aliases),
                organization_types=list(verified.organization_types),
                official_domains=list(verified.domains),
                official_urls=list(verified.official_urls),
                country_code=verified.country_code,
                identity_status=status,
                verification_method=(
                    "openalex_and_openaire_affiliation_plus_ror_exact_id"
                    if len(item["discovery_providers"]) > 1
                    else "openaire_publication_affiliation_plus_ror_exact_id"
                    if item["openaire_ids"] and not item["openalex_ids"]
                    else "openalex_affiliation_plus_ror_exact_id"
                ),
                verification_source=verified.api_url,
                verification_date=verified.retrieved_at[:10],
                verification_timestamp=verified.retrieved_at,
                source_record_updated_at=verified.last_modified,
                registry_match=registry_match,
                related_publications=item["publications"],
                limitations=limitations,
            )
        )
    return output
