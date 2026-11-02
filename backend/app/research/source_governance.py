"""Versioned, evidence-neutral classification of research source identities.

Institutional identity and verified list membership are provenance metadata,
not judgments that a publication is true, relevant, or methodologically sound.
The registry intentionally ships without ranking or quartile claims: those
datasets require reviewed, licensed, year-specific imports.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RegistryProvenance(_StrictModel):
    source_url: str = Field(min_length=8, max_length=1000)
    verified_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: str | None = Field(default=None, max_length=500)

    @field_validator("source_url")
    @classmethod
    def require_https(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("registry provenance must be an HTTPS URL")
        return value

    @field_validator("verified_at")
    @classmethod
    def require_calendar_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class _Identity(_StrictModel):
    canonical_id: str = Field(min_length=1, max_length=120)
    canonical_name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=32)
    identity_provenance: list[RegistryProvenance] = Field(default_factory=list, max_length=16)


class OrganizationRecord(_Identity):
    category: Literal[
        "multilateral",
        "consulting",
        "think_tank",
        "government",
        "official_statistics",
        "research_institute",
    ]
    official_domains: list[str] = Field(default_factory=list, max_length=24)
    identifiers: dict[str, list[str]] = Field(default_factory=dict, max_length=16)
    identity_status: Literal["verified", "unverified"]
    quality_review_status: Literal["not_assessed", "review_pending", "reviewed"] = "not_assessed"
    discovery_adapters: list[str] = Field(default_factory=list, max_length=24)


class RankingRecord(_StrictModel):
    system: str = Field(min_length=1, max_length=100)
    ranking_year: int = Field(ge=1900, le=3000)
    rank: int = Field(ge=1, le=100000)
    subject_category: str = Field(min_length=1, max_length=160)
    status: Literal["verified", "unverified"]
    provenance: RegistryProvenance | None = None


class UniversityRecord(_Identity):
    identifiers: dict[str, list[str]] = Field(default_factory=dict, max_length=16)
    rankings: list[RankingRecord] = Field(default_factory=list, max_length=32)


class JournalQuartileRecord(_StrictModel):
    system: str = Field(min_length=1, max_length=100)
    ranking_year: int = Field(ge=1900, le=3000)
    subject_category: str = Field(min_length=1, max_length=160)
    quartile: Literal["Q1", "Q2", "Q3", "Q4"]
    status: Literal["verified", "unverified"]
    provenance: RegistryProvenance | None = None


class FT50MembershipRecord(_StrictModel):
    list_year: int = Field(ge=1900, le=3000)
    status: Literal["verified", "unverified"]
    provenance: RegistryProvenance | None = None


class JournalRecord(_Identity):
    issns: list[str] = Field(default_factory=list, max_length=16)
    quartiles: list[JournalQuartileRecord] = Field(default_factory=list, max_length=32)
    ft50_memberships: list[FT50MembershipRecord] = Field(default_factory=list, max_length=16)


class SourceRegistryV1(_StrictModel):
    schema_version: Literal[1]
    registry_version: str = Field(min_length=1, max_length=100)
    updated_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    organizations: list[OrganizationRecord] = Field(default_factory=list, max_length=500)
    universities: list[UniversityRecord] = Field(default_factory=list, max_length=10000)
    journals: list[JournalRecord] = Field(default_factory=list, max_length=10000)

    @field_validator("updated_at")
    @classmethod
    def require_update_calendar_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class MatchedInstitutionRanking(_StrictModel):
    canonical_id: str
    system: str
    ranking_year: int
    rank: int
    subject_category: str
    provenance: RegistryProvenance


class MatchedIdentityProvenance(_StrictModel):
    registry_id: str
    source_url: str
    verified_at: str


class MatchedInstitutionIdentifier(_StrictModel):
    registry_id: str
    namespace: str
    identifier: str


class MatchedOrganizationIdentifier(_StrictModel):
    registry_id: str
    namespace: str
    identifier: str


class MatchedJournalClassification(_StrictModel):
    registry_id: str
    issn: str
    classification: Literal["Q1", "FT50"]
    system: str
    ranking_year: int
    subject_category: str | None = None
    provenance: RegistryProvenance


class SourceGovernanceDecision(_StrictModel):
    registry_version: str
    source_classes: list[str]
    matched_registry_ids: list[str]
    matched_identity_provenance: list[MatchedIdentityProvenance]
    matched_institution_identifiers: list[MatchedInstitutionIdentifier]
    matched_organization_identifiers: list[MatchedOrganizationIdentifier] = Field(
        default_factory=list
    )
    identity_status: Literal["verified", "unverified", "unregistered"]
    quality_review_status: Literal["not_assessed", "review_pending", "reviewed"]
    methodological_quality: Literal["not_assessed"]
    methodology_review_required: bool
    academic_preference: Literal["QS_TOP_100", "QS_101_250_ELIGIBLE", "Q1", "FT50", "NONE"]
    quality_claim_is_truth_claim: Literal[False] = False
    matched_institution_rankings: list[MatchedInstitutionRanking]
    matched_journal_classifications: list[MatchedJournalClassification]
    unverified_classification_count: int = Field(ge=0)
    discovery_status: str
    selection_guidance: Literal[
        "eligible_by_relevance_and_methodology_review",
        "do_not_promote_to_fill_coverage",
        "eligible_for_counterevidence_review",
    ]
    counterevidence_exception: bool


_ISSN_RE = re.compile(r"^\d{7}[\dX]$", re.IGNORECASE)


def normalize_issn(value: str) -> str | None:
    normalized = re.sub(r"[^0-9X]", "", value.upper())
    if not _ISSN_RE.fullmatch(normalized):
        return None
    check_digit = 10 if normalized[-1] == "X" else int(normalized[-1])
    checksum = sum(
        int(digit) * weight for digit, weight in zip(normalized[:7], range(8, 1, -1), strict=True)
    )
    return normalized if (checksum + check_digit) % 11 == 0 else None


def validate_registry(value: Mapping[str, Any] | SourceRegistryV1) -> SourceRegistryV1:
    """Validate registry shape and refuse purported verified claims without provenance."""
    if isinstance(value, SourceRegistryV1):
        registry = value
    else:
        try:
            registry = SourceRegistryV1.model_validate(value)
        except ValidationError as exc:
            raise ValueError(f"invalid source governance registry: {exc}") from exc
    identities: set[tuple[str, str]] = set()
    for organization in registry.organizations:
        key = ("organization", organization.canonical_id.casefold())
        if key in identities:
            raise ValueError("duplicate canonical registry identity")
        identities.add(key)
        if organization.identity_status == "verified" and not organization.identity_provenance:
            raise ValueError("verified organization identity requires provenance")
        if organization.identifiers and not organization.identity_provenance:
            raise ValueError("organization identifiers require identity provenance")
        for domain in organization.official_domains:
            normalized = domain.casefold().strip().rstrip(".")
            if not normalized or "/" in normalized or ":" in normalized or " " in normalized:
                raise ValueError("official domain must be a hostname")
        if any(
            not namespace.strip()
            or not values
            or len(values) > 64
            or any(not item.strip() or len(item) > 200 for item in values)
            for namespace, values in organization.identifiers.items()
        ):
            raise ValueError("organization identifiers must be bounded and non-empty")
    for university in registry.universities:
        key = ("university", university.canonical_id.casefold())
        if key in identities:
            raise ValueError("duplicate canonical registry identity")
        identities.add(key)
        if university.rankings and not university.identity_provenance:
            raise ValueError("ranked university identity requires provenance")
        for ranking in university.rankings:
            if ranking.ranking_year > int(registry.updated_at[:4]):
                raise ValueError("ranking year cannot postdate the registry update year")
            if ranking.status == "verified" and ranking.provenance is None:
                raise ValueError("verified ranking requires provenance")
    for journal in registry.journals:
        key = ("journal", journal.canonical_id.casefold())
        if key in identities:
            raise ValueError("duplicate canonical registry identity")
        identities.add(key)
        if any(normalize_issn(issn) is None for issn in journal.issns):
            raise ValueError("journal ISSN is invalid")
        if (journal.quartiles or journal.ft50_memberships) and not journal.identity_provenance:
            raise ValueError("classified journal identity requires provenance")
        for classification in [*journal.quartiles, *journal.ft50_memberships]:
            classification_year = getattr(
                classification, "ranking_year", getattr(classification, "list_year", None)
            )
            if classification_year > int(registry.updated_at[:4]):
                raise ValueError(
                    "journal classification year cannot postdate the registry update year"
                )
            if classification.status == "verified" and classification.provenance is None:
                raise ValueError("verified journal classification requires provenance")
    return registry


@lru_cache(maxsize=1)
def default_registry() -> SourceRegistryV1:
    path = Path(__file__).with_name("source-governance-registry.json")
    return validate_registry(json.loads(path.read_text(encoding="utf-8")))


def _values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [item for item in value if isinstance(item, str)]
    return []


def _host_matches(host: str, domain: str) -> bool:
    host = host.casefold().rstrip(".")
    domain = domain.casefold().strip().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def classify_source(
    *,
    registry: SourceRegistryV1 | Mapping[str, Any] | None = None,
    institution_ids: Mapping[str, Sequence[str]] | None = None,
    organization_identifiers: Mapping[str, Sequence[str]] | None = None,
    journal_issns: Sequence[str] | None = None,
    ranking_year: int | None = None,
    relevant_subject_categories: Sequence[str] | None = None,
    publisher: str | None = None,
    source_url: str | None = None,
    source_type: str | None = None,
    provider: str | None = None,
    is_material_counterevidence: bool = False,
) -> SourceGovernanceDecision:
    """Resolve known identities and versioned classifications without prestige scoring."""
    reg = (
        registry
        if isinstance(registry, SourceRegistryV1)
        else validate_registry(registry)
        if registry
        else default_registry()
    )
    org_matches: list[OrganizationRecord] = []
    verified_org_identity_ids: set[str] = set()
    matched_organization_identifiers: list[MatchedOrganizationIdentifier] = []
    publisher_key = " ".join((publisher or "").casefold().split())
    supplied_org_ids = {
        namespace.casefold(): {item.casefold().rstrip("/") for item in _values(raw)}
        for namespace, raw in (organization_identifiers or {}).items()
    }
    host = ""
    if source_url:
        try:
            parsed = urlsplit(source_url)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                host = parsed.hostname.casefold()
        except ValueError:
            host = ""
    for organization in reg.organizations:
        names = {
            " ".join(name.casefold().split())
            for name in [organization.canonical_name, *organization.aliases]
        }
        domain_match = any(_host_matches(host, domain) for domain in organization.official_domains)
        identifier_match = False
        for namespace, identifiers in organization.identifiers.items():
            intersecting = supplied_org_ids.get(namespace.casefold(), set()) & {
                str(item).casefold().rstrip("/") for item in identifiers
            }
            if intersecting:
                identifier_match = True
                matched_organization_identifiers.extend(
                    MatchedOrganizationIdentifier(
                        registry_id=organization.canonical_id,
                        namespace=namespace,
                        identifier=identifier,
                    )
                    for identifier in sorted(intersecting)
                )
        if publisher_key in names or domain_match or identifier_match:
            org_matches.append(organization)
        if organization.identity_status == "verified" and (domain_match or identifier_match):
            verified_org_identity_ids.add(organization.canonical_id)

    supplied_ids = {
        namespace.casefold(): {item.casefold().rstrip("/") for item in values}
        for namespace, raw in (institution_ids or {}).items()
        for values in [_values(raw)]
    }
    matched_rankings: list[MatchedInstitutionRanking] = []
    matched_identity_provenance: list[MatchedIdentityProvenance] = []
    matched_institution_identifiers: list[MatchedInstitutionIdentifier] = []
    unverified_count = 0
    institution_matched = False
    for university in reg.universities:
        identity_matches = False
        for namespace, identifiers in university.identifiers.items():
            supplied = supplied_ids.get(namespace.casefold(), set())
            known = {str(item).casefold().rstrip("/") for item in identifiers}
            intersecting = supplied & known
            identity_matches |= bool(intersecting)
            if intersecting:
                matched_institution_identifiers.extend(
                    MatchedInstitutionIdentifier(
                        registry_id=university.canonical_id,
                        namespace=namespace,
                        identifier=source_id,
                    )
                    for source_id in _values((institution_ids or {}).get(namespace, []))
                    if source_id.casefold().rstrip("/") in intersecting
                )
        if not identity_matches:
            continue
        institution_matched = True
        matched_identity_provenance.extend(
            MatchedIdentityProvenance(
                registry_id=university.canonical_id,
                source_url=provenance.source_url,
                verified_at=provenance.verified_at,
            )
            for provenance in university.identity_provenance
        )
        qs_rankings = [ranking for ranking in university.rankings if ranking.system == "QS_WUR"]
        effective_qs_year = ranking_year
        if effective_qs_year is None and qs_rankings:
            effective_qs_year = max(ranking.ranking_year for ranking in qs_rankings)
        for ranking in qs_rankings:
            if effective_qs_year is not None and ranking.ranking_year != effective_qs_year:
                continue
            if ranking.status != "verified" or ranking.provenance is None:
                unverified_count += 1
                continue
            matched_rankings.append(
                MatchedInstitutionRanking(
                    canonical_id=university.canonical_id,
                    system=ranking.system,
                    ranking_year=ranking.ranking_year,
                    rank=ranking.rank,
                    subject_category=ranking.subject_category,
                    provenance=ranking.provenance,
                )
            )

    requested_subjects = {
        " ".join(item.casefold().split()) for item in (relevant_subject_categories or [])
    }
    input_issns = {
        normalized for item in (journal_issns or []) if (normalized := normalize_issn(item))
    }
    matched_journal: list[MatchedJournalClassification] = []
    for journal in reg.journals:
        journal_issn = sorted(
            input_issns.intersection(
                {normalize_issn(item) for item in journal.issns if normalize_issn(item)}
            )
        )
        if not journal_issn:
            continue
        matched_identity_provenance.extend(
            MatchedIdentityProvenance(
                registry_id=journal.canonical_id,
                source_url=provenance.source_url,
                verified_at=provenance.verified_at,
            )
            for provenance in journal.identity_provenance
        )
        quartiles = list(journal.quartiles)
        if ranking_year is None:
            latest_by_classification: dict[tuple[str, str], int] = {}
            for item in quartiles:
                category = " ".join(item.subject_category.casefold().split())
                key = (item.system.casefold(), category)
                latest_by_classification[key] = max(
                    latest_by_classification.get(key, 0), item.ranking_year
                )
            quartiles = [
                item
                for item in quartiles
                if item.ranking_year
                == latest_by_classification[
                    (item.system.casefold(), " ".join(item.subject_category.casefold().split()))
                ]
            ]
        for item in quartiles:
            effective_quartile_year = ranking_year
            if effective_quartile_year is not None and item.ranking_year != effective_quartile_year:
                continue
            if (
                requested_subjects
                and " ".join(item.subject_category.casefold().split()) not in requested_subjects
            ):
                continue
            category_key = " ".join(item.subject_category.casefold().split())
            if (
                not requested_subjects
                or category_key in requested_subjects
                or category_key == "multidisciplinary"
            ):
                if (
                    item.status == "verified"
                    and item.provenance is not None
                    and item.quartile == "Q1"
                ):
                    matched_journal.append(
                        MatchedJournalClassification(
                            registry_id=journal.canonical_id,
                            issn=journal_issn[0],
                            classification="Q1",
                            system=item.system,
                            ranking_year=item.ranking_year,
                            subject_category=item.subject_category,
                            provenance=item.provenance,
                        )
                    )
                elif item.status != "verified" or item.provenance is None:
                    unverified_count += 1
        memberships = list(journal.ft50_memberships)
        effective_ft50_year = ranking_year
        if effective_ft50_year is None and memberships:
            effective_ft50_year = max(item.list_year for item in memberships)
        for item in memberships:
            if effective_ft50_year is not None and item.list_year != effective_ft50_year:
                continue
            if item.status == "verified" and item.provenance is not None:
                matched_journal.append(
                    MatchedJournalClassification(
                        registry_id=journal.canonical_id,
                        issn=journal_issn[0],
                        classification="FT50",
                        system="FT50",
                        ranking_year=item.list_year,
                        subject_category=None,
                        provenance=item.provenance,
                    )
                )
            else:
                unverified_count += 1

    verified_orgs = [item for item in org_matches if item.canonical_id in verified_org_identity_ids]
    for organization in org_matches:
        matched_identity_provenance.extend(
            MatchedIdentityProvenance(
                registry_id=organization.canonical_id,
                source_url=provenance.source_url,
                verified_at=provenance.verified_at,
            )
            for provenance in organization.identity_provenance
        )
    unverified_count += sum(
        item.canonical_id not in verified_org_identity_ids for item in org_matches
    )
    classes: list[str] = []
    for organization in org_matches:
        if organization.category not in classes:
            classes.append(organization.category)
    if (
        institution_matched
        or input_issns
        or source_type == "scholarly_article"
        or (provider or "").casefold() in {"crossref", "openalex"}
    ):
        classes.insert(0, "academic")
    if source_type == "official_statistics" and "official_statistics" not in classes:
        classes.insert(0, "official_statistics")
    classes = list(dict.fromkeys(classes))
    identity_status: Literal["verified", "unverified", "unregistered"]
    if verified_orgs or institution_matched or matched_journal:
        identity_status = "verified"
    elif (
        org_matches
        or (institution_ids and any(_values(value) for value in institution_ids.values()))
        or input_issns
    ):
        identity_status = "unverified"
    else:
        identity_status = "unregistered"
    quality_status: Literal["not_assessed", "review_pending", "reviewed"] = "not_assessed"
    if any(item.quality_review_status == "review_pending" for item in org_matches):
        quality_status = "review_pending"
    elif org_matches and all(item.quality_review_status == "reviewed" for item in org_matches):
        quality_status = "reviewed"
    rankings = sorted(
        matched_rankings, key=lambda item: (item.ranking_year, item.rank, item.canonical_id)
    )
    journal_classes = sorted(
        matched_journal, key=lambda item: (item.classification, item.registry_id, item.issn)
    )
    if any(item.rank <= 100 for item in rankings):
        preference: Literal["QS_TOP_100", "QS_101_250_ELIGIBLE", "Q1", "FT50", "NONE"] = (
            "QS_TOP_100"
        )
    elif any(item.rank <= 250 for item in rankings):
        preference = "QS_101_250_ELIGIBLE"
    elif any(
        item.classification == "Q1"
        and (
            item.subject_category is None
            or " ".join(item.subject_category.casefold().split()) == "multidisciplinary"
            or " ".join(item.subject_category.casefold().split()) in requested_subjects
        )
        for item in journal_classes
    ):
        preference = "Q1"
    elif any(item.classification == "FT50" for item in journal_classes):
        preference = "FT50"
    else:
        preference = "NONE"
    if is_material_counterevidence and identity_status != "verified":
        guidance = "eligible_for_counterevidence_review"
    elif classes and (identity_status == "verified" or "academic" in classes):
        guidance = "eligible_by_relevance_and_methodology_review"
    else:
        guidance = "do_not_promote_to_fill_coverage"
    adapters = sorted({adapter for item in org_matches for adapter in item.discovery_adapters})
    registered_adapters = [item for item in adapters if item != "not_integrated"]

    def normalize_adapter_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    used_registered_adapter = bool(provider) and normalize_adapter_name(provider) in {
        normalize_adapter_name(item) for item in registered_adapters
    }
    discovery = (
        "discovered_by_registered_adapter"
        if used_registered_adapter
        else "registered_adapter_available"
        if registered_adapters
        else "not_integrated"
    )
    return SourceGovernanceDecision(
        registry_version=reg.registry_version,
        source_classes=classes,
        matched_registry_ids=sorted(
            {
                *(item.canonical_id for item in org_matches),
                *(item.canonical_id for item in rankings),
                *(item.registry_id for item in journal_classes),
            }
        ),
        matched_identity_provenance=sorted(
            {
                (item.registry_id, item.source_url, item.verified_at): item
                for item in matched_identity_provenance
            }.values(),
            key=lambda item: (item.registry_id, item.source_url, item.verified_at),
        ),
        matched_institution_identifiers=sorted(
            {
                (item.registry_id, item.namespace, item.identifier): item
                for item in matched_institution_identifiers
            }.values(),
            key=lambda item: (item.registry_id, item.namespace, item.identifier),
        ),
        matched_organization_identifiers=sorted(
            {
                (item.registry_id, item.namespace, item.identifier): item
                for item in matched_organization_identifiers
            }.values(),
            key=lambda item: (item.registry_id, item.namespace, item.identifier),
        ),
        identity_status=identity_status,
        quality_review_status=quality_status,
        methodological_quality="not_assessed",
        methodology_review_required=True,
        academic_preference=preference,
        matched_institution_rankings=rankings,
        matched_journal_classifications=journal_classes,
        unverified_classification_count=unverified_count,
        discovery_status=discovery,
        selection_guidance=guidance,
        counterevidence_exception=bool(
            is_material_counterevidence and identity_status != "verified"
        ),
    )


def classify_work_record(
    record: Any,
    *,
    is_material_counterevidence: bool = False,
) -> SourceGovernanceDecision:
    """Classify a provider-neutral work using only identifiers it actually supplied."""
    metadata = getattr(record, "provider_metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    institution_ids = metadata.get("institution_ids")
    if not isinstance(institution_ids, Mapping):
        institution_ids = {}
    journal_issns = metadata.get("journal_issns")
    if not isinstance(journal_issns, list):
        journal_issns = []
    return classify_source(
        institution_ids=institution_ids,
        organization_identifiers=(
            {"crossref_prefix": [record.doi.split("/", 1)[0]]}
            if isinstance(getattr(record, "doi", None), str) and "/" in record.doi
            else {}
        ),
        journal_issns=journal_issns,
        publisher=getattr(record, "publisher", None),
        source_url=getattr(record, "url", None),
        source_type=getattr(record, "source_type", None),
        provider=getattr(record, "provider", None),
        is_material_counterevidence=is_material_counterevidence,
    )


def academic_preference_tier(value: SourceGovernanceDecision | Mapping[str, Any]) -> int:
    """A categorical exact-relevance tie-break; not a weighted source-quality score."""
    decision = (
        value
        if isinstance(value, SourceGovernanceDecision)
        else SourceGovernanceDecision.model_validate(value)
    )
    return 0 if decision.academic_preference != "NONE" else 1


_COMMERCIAL_OR_POLICY_CUES = (
    "productivity",
    "workplace",
    "company",
    "business",
    "industry",
    "organization",
    "organisation",
    "firm",
    "investment",
    "deployment",
    "market entry",
    "industrial policy",
    "regulation",
    "regulatory",
    "compliance",
    "strategy",
    "renewable energy",
    "energy transition",
)
_THINK_TANK_CUES = _COMMERCIAL_OR_POLICY_CUES + (
    "policy",
    "policies",
    "economic",
    "economy",
    "trade",
    "development",
    "climate",
)
_PUBLIC_AUTHORITY_CUES = (
    "employment",
    "labor",
    "labour",
    "productivity",
    "economy",
    "economic",
    "country",
    "policy",
    "policies",
    "development",
    "health",
    "hospital",
    "hospital admissions",
    "cardiovascular",
    "clinical",
    "disease",
    "medicine",
    "mortality",
    "trade",
    "statistics",
    "energy",
    "renewable",
    "electricity",
    "climate",
    "carbon",
    "emissions",
    "grid",
    "battery",
    "power",
    "regulation",
    "regulatory",
    "compliance",
)
_STATISTICS_CUES = tuple(
    item
    for item in _PUBLIC_AUTHORITY_CUES
    if item not in {"policy", "policies", "regulation", "regulatory", "compliance"}
) + ("food price volatility", "food prices")
_RESEARCH_INSTITUTE_CUES = ("research institute", "think tank", "policy institute")


def _matched_question_cues(question: str, cues: Sequence[str]) -> list[str]:
    text = " ".join(question.casefold().split())
    return [cue for cue in cues if re.search(rf"(?<![a-z]){re.escape(cue)}(?![a-z])", text)]


def planned_source_classes(question: str) -> list[str]:
    """Select applicable source classes from question cues, without claiming they ran."""
    planned = ["academic"]
    if _matched_question_cues(question, _COMMERCIAL_OR_POLICY_CUES):
        planned.append("consulting")
    if _matched_question_cues(question, _THINK_TANK_CUES):
        planned.append("think_tank")
    if _matched_question_cues(question, _PUBLIC_AUTHORITY_CUES):
        planned.append("multilateral")
    if _matched_question_cues(question, _STATISTICS_CUES):
        planned.append("official_statistics")
    if _matched_question_cues(question, _PUBLIC_AUTHORITY_CUES):
        planned.append("government")
    if _matched_question_cues(question, _RESEARCH_INSTITUTE_CUES):
        planned.append("research_institute")
    return list(dict.fromkeys(planned))


def _explicit_uk_geography(geography: str | None) -> bool:
    normalized = " ".join((geography or "").casefold().replace(".", "").split())
    return normalized in {
        "uk",
        "united kingdom",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
    }


def build_source_governance_plan(question: str, *, geography: str | None = None) -> dict[str, Any]:
    """Create a versioned source-class coverage intent for the persisted job plan."""
    registry = default_registry()
    planned = planned_source_classes(question)
    selection_reasons = {"academic": ["default scholarly discovery route"]}
    cue_groups = {
        "consulting": _COMMERCIAL_OR_POLICY_CUES,
        "think_tank": _THINK_TANK_CUES,
        "multilateral": _PUBLIC_AUTHORITY_CUES,
        "government": _PUBLIC_AUTHORITY_CUES,
        "official_statistics": _STATISTICS_CUES,
        "research_institute": _RESEARCH_INSTITUTE_CUES,
    }
    for source_class in planned:
        if source_class == "academic":
            continue
        matched = _matched_question_cues(question, cue_groups.get(source_class, ()))
        if matched:
            selection_reasons[source_class] = matched
    adapters = {
        "academic": "crossref_openalex",
        "multilateral": "world_bank_documents_reports_api_confirmation_required",
        "official_statistics": "conditional_world_bank_data360_ilostat",
        "government": (
            "govuk_search_api_unsupported_best_effort"
            if _explicit_uk_geography(geography)
            else "not_applicable_explicit_uk_geography_required"
        ),
        "consulting": "not_integrated",
        "think_tank": "not_integrated",
        "research_institute": "not_integrated",
    }
    return {
        "schema_version": 1,
        "policy_version": "topic-cues-source-classes-v5",
        "planner": "deterministic_topic_cues",
        "registry_version": registry.registry_version,
        "planned_classes": planned,
        "class_selection_reasons": selection_reasons,
        "planned_adapter_status": {name: adapters.get(name, "not_integrated") for name in planned},
        "interpretation_limit": "Planned source classes are coverage intent, not proof a connector ran or a source is high quality.",
    }


def source_governance_for_api(value: Any) -> dict[str, Any] | None:
    """Return a validated, bounded classification; omit corrupt legacy metadata."""
    if not isinstance(value, Mapping):
        return None
    try:
        return SourceGovernanceDecision.model_validate(value).model_dump(mode="json")
    except (ValidationError, TypeError, ValueError):
        return None


def summarize_source_coverage(
    *,
    planned_classes: Sequence[str],
    searched_classes: Sequence[str],
    candidate_class_counts: Mapping[str, int],
    selected_class_counts: Mapping[str, int],
    adapter_status: Mapping[str, str],
) -> dict[str, Any]:
    """Build an explicit, non-inferential source-class coverage summary."""
    planned = list(dict.fromkeys(str(item) for item in planned_classes))
    searched = list(dict.fromkeys(str(item) for item in searched_classes))
    missing = [item for item in planned if item not in searched]
    class_names = list(
        dict.fromkeys([*planned, *searched, *candidate_class_counts, *selected_class_counts])
    )
    class_status: dict[str, dict[str, Any]] = {}
    for source_class in class_names:
        status = (
            "searched"
            if source_class in searched
            else adapter_status.get(source_class, "not_searched")
        )
        class_status[source_class] = {
            "status": status,
            "candidate_count": max(0, int(candidate_class_counts.get(source_class, 0))),
            "selected_count": max(0, int(selected_class_counts.get(source_class, 0))),
        }
    return {
        "schema_version": 1,
        "planned_classes": planned,
        "searched_classes": searched,
        "missing_classes": missing,
        "class_status": class_status,
        "coverage_complete": not missing,
        "interpretation_limit": "Source identity/classification is not document relevance, methodological quality, evidence strength, or truth.",
    }
