"""Versioned, provider-aware metadata contracts for persisted sources.

Provider metadata is descriptive provenance. It is deliberately separate from
source rights, retrieved evidence, and methodological appraisal records.
"""

import json
import math
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _NestedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)


class StatisticsDataSourceV1(_NestedMetadata):
    name: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    publisher: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)


class StatisticsObservationV1(_NestedMetadata):
    value: str | int | float | None = None
    period: str | None = Field(default=None, max_length=64)
    geography_code: str | None = Field(default=None, max_length=64)
    geography_name: str | None = Field(default=None, max_length=160)
    unit_measure: str | None = Field(default=None, max_length=100)
    unit_type: str | None = Field(default=None, max_length=100)
    unit_multiplier: int | None = Field(default=None, ge=-30, le=30)
    observation_status: str | None = Field(default=None, max_length=40)


class StatisticsMetadataV1(_NestedMetadata):
    indicator_id: str | None = Field(default=None, max_length=180)
    indicator_name: str | None = Field(default=None, max_length=300)
    database_id: str | None = Field(default=None, max_length=100)
    dataset_name: str | None = Field(default=None, max_length=300)
    dataset_url: str | None = Field(default=None, max_length=1000)
    dataset_terms_url: str | None = Field(default=None, max_length=1000)
    license: str | None = Field(default=None, max_length=500)
    license_url: str | None = Field(default=None, max_length=1000)
    attribution: str | None = Field(default=None, max_length=1000)
    definition: str | None = Field(default=None, max_length=2000)
    statistical_concept: str | None = Field(default=None, max_length=2000)
    methodology: str | None = Field(default=None, max_length=2000)
    limitations: str | None = Field(default=None, max_length=2000)
    periodicity: str | None = Field(default=None, max_length=120)
    source_update_date: str | None = Field(default=None, max_length=64)
    measurement_unit: str | None = Field(default=None, max_length=100)
    retrieved_at: str | None = Field(default=None, max_length=80)
    source_type: str | None = Field(default=None, max_length=80)
    data_sources: list[StatisticsDataSourceV1] | None = Field(default=None, max_length=16)
    observations: list[StatisticsObservationV1] | None = Field(default=None, max_length=64)


class OpenAccessMetadataV1(_NestedMetadata):
    is_oa: bool | None = None
    oa_status: str | None = Field(default=None, max_length=80)
    oa_url: str | None = Field(default=None, max_length=1000)


class OpenAlexSourceMetadataV1(_NestedMetadata):
    id: str | None = Field(default=None, max_length=500)
    display_name: str | None = Field(default=None, max_length=300)
    issn_l: str | None = Field(default=None, max_length=32)
    issn: list[str] | None = Field(default=None, max_length=32)
    host_organization: str | None = Field(default=None, max_length=500)
    host_organization_name: str | None = Field(default=None, max_length=300)
    type: str | None = Field(default=None, max_length=100)


class OpenAlexLocationMetadataV1(_NestedMetadata):
    landing_page_url: str | None = Field(default=None, max_length=1000)
    pdf_url: str | None = Field(default=None, max_length=1000)
    license: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=120)
    is_oa: bool | None = None
    source: OpenAlexSourceMetadataV1 | None = None


class OpenAlexContentAvailabilityV1(_NestedMetadata):
    pdf: bool | None = None
    grobid_xml: bool | None = None


class OpenAlexInstitutionMetadataV1(_NestedMetadata):
    openalex_id: str = Field(pattern=r"^I[0-9]{1,20}$")
    ror_id: str | None = Field(default=None, pattern=r"^https://ror\.org/[0-9a-z]{9}$")
    display_name: str | None = Field(default=None, max_length=300)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    type: str | None = Field(default=None, max_length=50)


class OpenAIREOrganizationMetadataV1(_NestedMetadata):
    openaire_id: str = Field(pattern=r"^[A-Za-z0-9_:\-]{1,300}$")
    ror_id: str | None = Field(default=None, pattern=r"^https://ror\.org/[0-9a-z]{9}$")
    display_name: str = Field(min_length=1, max_length=300)
    website_url: str | None = Field(default=None, max_length=1000)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    type: str | None = Field(default=None, max_length=80)


class OpenAIRERepositoryInstanceMetadataV1(_NestedMetadata):
    url: str = Field(pattern=r"^https://", max_length=2000)
    license_code: Literal["cc0", "cc-by"]
    license_url: str = Field(pattern=r"^https://creativecommons\.org/", max_length=1000)
    content_version: str | None = Field(default=None, max_length=80)
    instance_type: str | None = Field(default=None, max_length=100)
    access_right: str | None = Field(default=None, max_length=80)
    repository_name: str | None = Field(default=None, max_length=200)
    repository_url: str | None = Field(default=None, pattern=r"^https://", max_length=1000)


class _ProviderMetadataV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    extensions: dict[str, Any] = Field(default_factory=dict, max_length=128)


class CrossrefMetadataV1(_ProviderMetadataV1):
    work_type: str | None = Field(default=None, max_length=80)


class OpenAlexMetadataV1(_ProviderMetadataV1):
    openalex_id: str | None = Field(default=None, max_length=500)
    pmcid: str | None = Field(default=None, pattern=r"^PMC[0-9]{1,10}$")
    institution_ids: dict[str, list[str]] | None = Field(default=None, max_length=4)
    institution_records: list[OpenAlexInstitutionMetadataV1] | None = Field(
        default=None, max_length=100
    )
    journal_issns: list[str] | None = Field(default=None, max_length=32)
    open_access: OpenAccessMetadataV1 | None = None
    best_oa_location: OpenAlexLocationMetadataV1 | None = None
    has_content: OpenAlexContentAvailabilityV1 | None = None
    work_type: str | None = Field(default=None, max_length=80)


class OpenAIREMetadataV1(_ProviderMetadataV1):
    openaire_id: str = Field(pattern=r"^[A-Za-z0-9_:\-]{1,300}$")
    metadata_license: Literal["CC-BY-4.0"]
    metadata_attribution: str = Field(min_length=1, max_length=240)
    metadata_license_url: str = Field(min_length=8, max_length=1000)
    organization_records: list[OpenAIREOrganizationMetadataV1] = Field(
        default_factory=list, max_length=40
    )
    repository_instances: list[OpenAIRERepositoryInstanceMetadataV1] = Field(
        default_factory=list, max_length=24
    )
    original_ids: list[str] = Field(default_factory=list, max_length=32)
    source_names: list[str] = Field(default_factory=list, max_length=16)
    instance_types: list[str] = Field(default_factory=list, max_length=16)
    subjects: list[str] = Field(default_factory=list, max_length=32)


class WorldBankMetadataV1(_ProviderMetadataV1):
    statistics: StatisticsMetadataV1 | None = None
    selection_block_reason: (
        Literal["license_not_verified", "no_requested_geography_observation"] | None
    ) = None


class WorldBankDocumentsMetadataV1(_ProviderMetadataV1):
    api_documentation_url: str = Field(min_length=8, max_length=1000)
    world_bank_document_id: str = Field(min_length=1, max_length=100)
    report_number: str | None = Field(default=None, max_length=100)
    document_type: str | None = Field(default=None, max_length=160)
    official_document_url: str | None = Field(default=None, max_length=2000)
    official_pdf_url: str | None = Field(default=None, max_length=2000)
    metadata_access: Literal["public_official_api"]
    metadata_reuse_rights_status: Literal["not_assessed"]
    full_text_retrieved: Literal[False]
    full_text_rights_status: Literal["not_assessed"]
    abstract_excerpt_truncated: bool


class GovUKOrganizationReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+){0,39}$", max_length=240)
    canonical_name: str = Field(min_length=1, max_length=240)
    content_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
    organization_type: str | None = Field(default=None, max_length=80)
    directory_status: str | None = Field(default=None, max_length=24)
    official_url: str = Field(pattern=r"^https://www\.gov\.uk/government/organisations/[a-z0-9-]+$")


class VerifiedGovUKOrganizationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    organization_id: str = Field(pattern=r"^govuk:[a-z0-9-]+$", max_length=250)
    canonical_name: str = Field(min_length=1, max_length=240)
    content_id: str = Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
    )
    organization_type: str = Field(min_length=1, max_length=80)
    directory_status: str = Field(min_length=1, max_length=24)
    identity_status: Literal["VERIFIED_ESTABLISHED", "PENDING_VERIFICATION"]
    verification_method: Literal["govuk_organizations_api_exact_slug"]
    verification_source: str = Field(pattern=r"^https://www\.gov\.uk/api/organisations/[a-z0-9-]+$")
    verification_timestamp: str = Field(min_length=20, max_length=40)
    official_url: str = Field(pattern=r"^https://www\.gov\.uk/government/organisations/[a-z0-9-]+$")
    quality_assessment: Literal["not_assessed"]
    limitations: list[str] = Field(max_length=12)
    publication_ids: list[str] = Field(max_length=10)
    discovery_result_count: int = Field(ge=1, le=10)


class GovUKSearchMetadataV1(_ProviderMetadataV1):
    api_documentation_url: str = Field(min_length=8, max_length=1000)
    api_reuse_url: str = Field(min_length=8, max_length=1000)
    record_path: str = Field(pattern=r"^/government/publications/[A-Za-z0-9][A-Za-z0-9-]{0,180}/?$")
    document_type: Literal["policy_paper"]
    publishing_organizations: list[str] = Field(default_factory=list, max_length=16)
    publishing_organization_candidates: list[GovUKOrganizationReferenceV1] = Field(
        default_factory=list, max_length=16
    )
    verified_publishing_organizations: list[VerifiedGovUKOrganizationV1] = Field(
        default_factory=list, max_length=2
    )
    metadata_access: Literal["public_official_api"]
    metadata_reuse_status: Literal["metadata_only_content_rights_not_assessed"]
    full_text_retrieved: Literal[False]
    full_text_rights_status: Literal["not_assessed"]
    api_support_status: Literal["unsupported_best_effort"]


class IloStatMetadataV1(_ProviderMetadataV1):
    statistics: StatisticsMetadataV1 | None = None


class UnknownProviderMetadataV1(_ProviderMetadataV1):
    pass


_PROVIDER_MODELS: dict[str, tuple[str, type[_ProviderMetadataV1]]] = {
    "crossref": ("Crossref", CrossrefMetadataV1),
    "openalex": ("OpenAlex", OpenAlexMetadataV1),
    "openaire": ("OpenAIRE", OpenAIREMetadataV1),
    "world bank data360": ("World Bank Data360", WorldBankMetadataV1),
    "world bank documents & reports": (
        "World Bank Documents & Reports",
        WorldBankDocumentsMetadataV1,
    ),
    "gov.uk search api": ("GOV.UK Search API", GovUKSearchMetadataV1),
    "ilostat": ("ILOSTAT", IloStatMetadataV1),
}


def versioned_provider_metadata(provider: str, value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate known provider fields and retain bounded legacy keys as extensions.

    The function is used at provider ingress and API read time. It never writes
    a legacy upcast back to the database. Provider-specific fields remain at the
    same top level for existing consumers, with only the additive version field.
    """
    if not isinstance(provider, str) or not provider.strip() or len(provider) > 100:
        raise ValueError("provider name must be a non-empty bounded string")
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("provider metadata must be an object")
    raw = dict(value)
    _validate_json_value(raw)
    encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > 65_536:
        raise ValueError("provider metadata exceeds its 64 KiB storage boundary")

    model_name, model = _PROVIDER_MODELS.get(
        provider.strip().casefold(), (provider.strip()[:100], UnknownProviderMetadataV1)
    )
    version = raw.pop("schema_version", 1)
    if version != 1 or isinstance(version, bool):
        raise ValueError("unsupported provider metadata schema version")
    prior_extensions = raw.pop("extensions", {})
    if not isinstance(prior_extensions, Mapping):
        raise ValueError("provider metadata extensions must be an object")
    extensions = dict(prior_extensions)
    known_fields = set(model.model_fields) - {"schema_version", "extensions"}
    fields = {key: raw.pop(key) for key in list(raw) if key in known_fields}
    for key, item in raw.items():
        if key in extensions:
            raise ValueError("provider metadata extension conflicts with a legacy field")
        extensions[key] = item
    fields["schema_version"] = 1
    fields["extensions"] = extensions
    if model is OpenAlexMetadataV1:
        records = fields.get("institution_records")
        if isinstance(records, list):
            fields["institution_records"] = [
                _versioned_nested(record, OpenAlexInstitutionMetadataV1) for record in records
            ]
        for key, nested_model in (
            ("open_access", OpenAccessMetadataV1),
            ("best_oa_location", OpenAlexLocationMetadataV1),
            ("has_content", OpenAlexContentAvailabilityV1),
        ):
            if fields.get(key) is not None:
                fields[key] = _versioned_nested(fields[key], nested_model)
    if model is OpenAIREMetadataV1:
        records = fields.get("organization_records")
        if isinstance(records, list):
            fields["organization_records"] = [
                _versioned_nested(record, OpenAIREOrganizationMetadataV1) for record in records
            ]
        instances = fields.get("repository_instances")
        if isinstance(instances, list):
            fields["repository_instances"] = [
                _versioned_nested(record, OpenAIRERepositoryInstanceMetadataV1)
                for record in instances
            ]
    if model in {WorldBankMetadataV1, IloStatMetadataV1} and fields.get("statistics") is not None:
        fields["statistics"] = _versioned_statistics(fields["statistics"])
    try:
        validated = model.model_validate(fields)
    except ValidationError as exc:
        raise ValueError(f"invalid {model_name} provider metadata") from exc
    result = validated.model_dump(mode="json", exclude_none=True)
    for key, item in result.items():
        if key != "extensions":
            _remove_empty_nested_extensions(item)
    return result


def _versioned_statistics(value: Any) -> dict[str, Any]:
    return _versioned_nested(value, StatisticsMetadataV1)


def _versioned_nested(value: Any, model: type[_NestedMetadata]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("provider metadata object has an invalid nested shape")
    raw = dict(value)
    extensions = raw.pop("extensions", {})
    if not isinstance(extensions, Mapping):
        raise ValueError("provider metadata extensions must be an object")
    extensions = dict(extensions)
    known_fields = set(model.model_fields) - {"extensions"}
    fields = {key: raw.pop(key) for key in list(raw) if key in known_fields}
    if model is StatisticsMetadataV1:
        for key, nested_model in (
            ("data_sources", StatisticsDataSourceV1),
            ("observations", StatisticsObservationV1),
        ):
            records = fields.get(key)
            if isinstance(records, list):
                fields[key] = [_versioned_nested(record, nested_model) for record in records]
    for key, item in raw.items():
        if key in extensions:
            raise ValueError("provider metadata extension conflicts with a legacy field")
        extensions[key] = item
    fields["extensions"] = extensions
    if model is OpenAlexLocationMetadataV1 and fields.get("source") is not None:
        fields["source"] = _versioned_nested(fields["source"], OpenAlexSourceMetadataV1)
    nested = model.model_validate(fields)
    result = nested.model_dump(mode="json", exclude_none=True)
    if not result.get("extensions"):
        result.pop("extensions", None)
    return result


def _remove_empty_nested_extensions(value: Any) -> None:
    if isinstance(value, dict):
        if not value.get("extensions"):
            value.pop("extensions", None)
        for item in value.values():
            _remove_empty_nested_extensions(item)
    elif isinstance(value, list):
        for item in value:
            _remove_empty_nested_extensions(item)


def _validate_json_value(value: Any, *, depth: int = 0) -> None:
    if depth > 12:
        raise ValueError("provider metadata nesting exceeds its limit")
    if isinstance(value, Mapping):
        if len(value) > 128 or any(not isinstance(key, str) or len(key) > 200 for key in value):
            raise ValueError("provider metadata object exceeds its key boundary")
        for item in value.values():
            _validate_json_value(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > 1000:
            raise ValueError("provider metadata array exceeds its item boundary")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 16_384:
            raise ValueError("provider metadata string exceeds its character boundary")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("provider metadata numbers must be finite")
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("provider metadata must contain only JSON values")
