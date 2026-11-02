import json
import logging
import re
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session, selectinload

from app.config import settings
from app.db import get_db
from app.models import (
    Claim,
    Conversation,
    DailyModelQuota,
    DiscoveryCandidate,
    EvidenceRelationship,
    Hypothesis,
    JobEvent,
    Message,
    ModelCallReservation,
    Passage,
    Project,
    ResearchJob,
    ResearchReport,
    RetrievedDocument,
    Source,
    UsageEntry,
    UserPreference,
    utcnow,
)
from app.providers.metadata import versioned_provider_metadata
from app.providers.registry import configured_model
from app.research.abstract_text_rights import (
    WITHHELD_ABSTRACT_TEXT,
    WITHHELD_CLAIM_TEXT,
    WITHHELD_COMPARISON_TEXT,
    WITHHELD_HYPOTHESIS_TEXT,
    abstract_text_reuse_permitted,
    passage_abstract_text_reuse_permitted,
)
from app.research.candidate_metadata_retention import normalize_candidate_abstract_snapshot
from app.research.depth import depth_profile, profile_for_job, public_depth_profiles
from app.research.leases import acquire_job_lease
from app.research.retrieval_continuation import clone_job_evidence
from app.research.retrieval_outcomes import retrieval_metadata_for_api
from app.research.source_governance import source_governance_for_api
from app.research.workflow import (
    WorkflowError,
    append_event,
    execute_stage,
    job_snapshot,
    persist_result,
)
from app.schemas import (
    AdvanceRequest,
    EventPageOut,
    EvidenceSearchRequest,
    JobCreate,
    JobOut,
    MessageCreate,
    OfficialPublicationOut,
    OfficialSitePublicationOut,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    ProjectPurgeRequest,
    ReportHistoryOut,
    ReportInspectionOut,
    UserPreferencesPatch,
    VedaDataPurgeOut,
    VedaDataPurgeRequest,
    candidate_relevance_for_api,
    claim_appraisal_for_api,
    hypothesis_record_for_api,
    relationship_record_for_api,
    report_citation_map_for_api,
    report_verification_for_api,
    source_appraisal_for_api,
    versioned_checkpoint,
    versioned_event_data,
    versioned_report_citation_map,
    versioned_report_verification,
    versioned_scope,
)
from app.security import (
    AuthUser,
    create_local_token,
    get_current_user,
    require_loopback_dev_request,
)
from app.security_rate_limits import enforce_request_rate_limit

logger = logging.getLogger(__name__)
health_router = APIRouter()
router = APIRouter(dependencies=[Depends(enforce_request_rate_limit)])
MAX_PAGE_OFFSET = 100_000


def _bounded_page(db: Session, query, *, limit: int, offset: int) -> tuple[list[Any], bool]:
    rows = list(db.scalars(query.limit(limit + 1).offset(offset)))
    return rows[:limit], len(rows) > limit


def _query_total(db: Session, query) -> int:
    return int(db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0)


def _checkpoint_for_job(job: ResearchJob) -> dict[str, Any]:
    return versioned_checkpoint(dict(job.checkpoint_json or {}))


def _job_out(job: ResearchJob) -> dict[str, Any]:
    db = object_session(job)
    unknown_cost_calls = (
        int(
            db.scalar(
                select(func.count(UsageEntry.id)).where(
                    UsageEntry.job_id == job.id,
                    UsageEntry.reported_cost_usd.is_(None),
                    UsageEntry.estimated_cost_usd.is_(None),
                    UsageEntry.reported_cost_inr.is_(None),
                    UsageEntry.estimated_cost_inr.is_(None),
                )
            )
            or 0
        )
        if db is not None
        else None
    )
    return {
        "schema_version": 1,
        "id": job.id,
        "project_id": job.project_id,
        "parent_job_id": job.parent_job_id,
        "conversation_id": job.conversation_id,
        "question": job.question,
        "scope": versioned_scope(job.scope_json),
        "depth": job.depth,
        "model_provider": job.model_provider,
        "model_name": job.model_name,
        "budget_ceiling_usd": job.budget_ceiling_usd,
        "cost_spent_estimate_usd": job.cost_spent_estimate_usd,
        "unknown_cost_calls": unknown_cost_calls,
        "cost_estimate_complete": unknown_cost_calls == 0
        if unknown_cost_calls is not None
        else False,
        "cost_reserved_usd": job.cost_reserved_usd,
        "budget_ceiling_inr": job.budget_ceiling_inr,
        "cost_spent_estimate_inr": job.cost_spent_estimate_inr,
        "cost_reserved_inr": job.cost_reserved_inr,
        "model_calls_reserved": job.model_calls_reserved,
        "prompt_characters_reserved": job.prompt_characters_reserved,
        "prompt_token_budget_reserved": job.prompt_token_budget_reserved,
        "output_token_budget_reserved": job.output_token_budget_reserved,
        "resource_limits": profile_for_job(
            job.depth, _checkpoint_for_job(job).get("depth_profile")
        ).as_dict(),
        "status": job.status,
        "current_stage": job.current_stage,
        "version": job.version,
        "attempt": job.attempt,
        "error_class": job.error_class,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _mark_retry_limit_if_exhausted(db: Session, job: ResearchJob) -> bool:
    if job.status != "retryable_failure":
        return False
    profile = profile_for_job(job.depth, _checkpoint_for_job(job).get("depth_profile"))
    if job.attempt <= profile.max_retries:
        return False
    now = utcnow()
    job.status = "terminal_failure"
    job.error_class = "depth_retry_limit"
    job.error_message = "The selected research depth retry limit has been reached."
    job.lease_owner = None
    job.lease_expires_at = None
    job.version += 1
    job.updated_at = now
    append_event(
        db,
        job.id,
        event_type="retry_limit_reached",
        stage=job.current_stage,
        message=job.error_message,
        data={"depth": job.depth, "max_retries": profile.max_retries},
    )
    db.commit()
    db.refresh(job)
    return True


def _project_out(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "domain": project.domain,
        "archived_at": project.archived_at,
        "purge_at": project.purge_at,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _conversation_out(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "project_id": conversation.project_id,
        "title": conversation.title,
        "created_at": conversation.created_at,
    }


def _message_out(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "related_job_id": message.related_job_id,
        "created_at": message.created_at,
    }


def _source_out(source: Source) -> dict[str, Any]:
    provider = source.metadata_json.get("provider", "unknown")
    try:
        provider_metadata = versioned_provider_metadata(
            provider, source.metadata_json.get("provider_metadata", {})
        )
    except (TypeError, ValueError):
        # Legacy/corrupt optional metadata must not make otherwise inspectable
        # source, passage, or citation records unavailable through the API.
        logger.warning(
            "Source %s has invalid provider metadata; omitting metadata details", source.id
        )
        provider_metadata = {}
    statistics = (
        provider_metadata.get("statistics")
        if source.source_type == "official_statistics" and isinstance(provider_metadata, dict)
        else None
    )
    openalex_fulltext_availability = None
    if isinstance(provider, str) and provider.casefold() == "openalex":
        has_content = provider_metadata.get("has_content")
        if isinstance(has_content, dict):
            safe_formats = {
                key: has_content[key]
                for key in ("pdf", "grobid_xml")
                if type(has_content.get(key)) is bool
            }
            if safe_formats:
                openalex_fulltext_availability = safe_formats
    institutional_publication = None
    if (
        isinstance(provider, str)
        and provider.casefold() == "world bank documents & reports"
        and isinstance(provider_metadata, dict)
        and re.fullmatch(
            r"[A-Za-z0-9_-]{1,100}",
            str(provider_metadata.get("world_bank_document_id") or ""),
        )
    ):
        institutional_publication = {
            "publisher_record_id": provider_metadata["world_bank_document_id"],
            "document_type": provider_metadata.get("document_type"),
            "report_number": provider_metadata.get("report_number"),
            "metadata_access": "public_official_api",
            "metadata_reuse_rights_status": "not_assessed",
            "full_text_retrieved": False,
            "full_text_rights_status": "not_assessed",
        }
    official_publication = None
    if (
        isinstance(provider, str)
        and provider.casefold() == "gov.uk search api"
        and isinstance(provider_metadata, dict)
        and isinstance(provider_metadata.get("record_path"), str)
    ):
        try:
            official_publication = OfficialPublicationOut.model_validate(
                {
                    "provider": "GOV.UK Search API",
                    "record_path": provider_metadata["record_path"],
                    "document_type": provider_metadata.get("document_type"),
                    "publishing_organizations": provider_metadata.get(
                        "publishing_organizations", []
                    ),
                    "publishing_organization_records": provider_metadata.get(
                        "verified_publishing_organizations", []
                    ),
                    "metadata_access": "public_official_api",
                    "metadata_reuse_status": "metadata_only_content_rights_not_assessed",
                    "api_support_status": "unsupported_best_effort",
                    "full_text_retrieved": False,
                    "full_text_rights_status": "not_assessed",
                }
            ).model_dump(mode="json")
        except (TypeError, ValueError):
            official_publication = None
    extensions = provider_metadata.get("extensions")
    raw_site_publication = (
        extensions.get("official_site_discovery") if isinstance(extensions, dict) else None
    )
    official_site_publication = None
    if isinstance(raw_site_publication, dict):
        try:
            official_site_publication = OfficialSitePublicationOut.model_validate(
                raw_site_publication
            ).model_dump(mode="json")
        except (TypeError, ValueError):
            official_site_publication = None
    organization_provenance = None
    raw_organization = (
        extensions.get("organization_discovery") if isinstance(extensions, dict) else None
    )
    if isinstance(raw_organization, dict):
        organization_id = raw_organization.get("organization_id")
        organization_name = raw_organization.get("organization_name")
        identity_status = raw_organization.get("identity_status")
        institution_id = raw_organization.get("openalex_institution_id")
        verification_source = raw_organization.get("verification_source")
        if (
            isinstance(organization_id, str)
            and len(organization_id) <= 300
            and isinstance(organization_name, str)
            and organization_name.strip()
            and len(organization_name) <= 300
            and identity_status
            in {
                "VERIFIED_ESTABLISHED",
                "VERIFIED_DOMAIN_SPECIALIST",
                "PENDING_VERIFICATION",
                "UNVERIFIED_OR_REJECTED",
            }
        ):
            verification_source_is_ror = (
                isinstance(verification_source, str)
                and re.fullmatch(
                    r"https://api\.ror\.org/v2/organizations/[0-9a-z]{9}",
                    verification_source,
                )
                is not None
            )
            verification_source_is_crossref = False
            if isinstance(verification_source, str):
                try:
                    parsed_verification_source = urlsplit(verification_source)
                    decoded_crossref_doi = unquote(
                        parsed_verification_source.path.removeprefix("/works/")
                    )
                except (TypeError, ValueError):
                    decoded_crossref_doi = ""
                    parsed_verification_source = None
                try:
                    verification_source_port = (
                        parsed_verification_source.port
                        if parsed_verification_source is not None
                        else None
                    )
                except ValueError:
                    verification_source_port = -1
                verification_source_is_crossref = bool(
                    parsed_verification_source is not None
                    and parsed_verification_source.scheme == "https"
                    and (parsed_verification_source.hostname or "").casefold() == "api.crossref.org"
                    and parsed_verification_source.username is None
                    and parsed_verification_source.password is None
                    and verification_source_port in {None, 443}
                    and parsed_verification_source.path.startswith("/works/")
                    and not parsed_verification_source.query
                    and not parsed_verification_source.fragment
                    and re.fullmatch(
                        r"10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+",
                        decoded_crossref_doi,
                        re.IGNORECASE,
                    )
                    is not None
                )
            organization_provenance = {
                "organization_id": organization_id,
                "organization_name": organization_name,
                "identity_status": identity_status,
                "verification_method": str(raw_organization.get("verification_method", ""))[:80],
                "verification_source": (
                    verification_source[:1000]
                    if isinstance(verification_source, str)
                    and (verification_source_is_ror or verification_source_is_crossref)
                    else None
                ),
                "openalex_institution_id": (
                    institution_id
                    if isinstance(institution_id, str)
                    and re.fullmatch(r"I[0-9]{1,20}", institution_id)
                    else None
                ),
                "quality_assessment": "not_assessed",
            }
            verification_method = organization_provenance["verification_method"]
            crossref_linked_domain_only = "crossref" in verification_method.casefold() and (
                "linked" in verification_method.casefold()
                and "domain" in verification_method.casefold()
            )
            publisher_verification = raw_organization.get("publisher_verification")
            if publisher_verification in {
                "official_domain_linked_from_ror_verified_site",
                "verified_organization_domain_and_crossref_publisher_identity",
                "crossref_doi_title_publisher_and_link_domain_match",
                "verified_organization_domain_and_catalog_record_match",
                "official_page_metadata_verified",
            }:
                organization_provenance["publisher_verification"] = publisher_verification
            publication_provider = raw_organization.get("publication_discovery_provider")
            if publication_provider in {
                "Crawl4AI Cloud site search plus Crossref DOI resolution",
                "Crawl4AI Cloud question search plus Crossref publisher record",
                "Crawl4AI Cloud site search plus bounded official page metadata verification",
            }:
                organization_provenance["publication_discovery_provider"] = publication_provider
            publication_content_access = raw_organization.get("publication_content_access")
            if publication_content_access == "not_retrieved":
                organization_provenance["publication_content_access"] = publication_content_access
            publication_rights_status = raw_organization.get("publication_rights_status")
            if publication_rights_status in {
                "metadata_only_not_assessed",
                "not_assessed_metadata_only",
            }:
                organization_provenance["publication_rights_status"] = publication_rights_status
            official_domain = raw_organization.get("official_domain")
            publisher_linked_domain = raw_organization.get("publisher_linked_domain")
            if crossref_linked_domain_only and not isinstance(publisher_linked_domain, str):
                # Historical records stored a Crossref-linked host in the field
                # reserved for independently verified official domains.
                publisher_linked_domain = official_domain
            if isinstance(publisher_linked_domain, str) and re.fullmatch(
                r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", publisher_linked_domain.casefold()
            ):
                organization_provenance["publisher_linked_domain"] = (
                    publisher_linked_domain.casefold().rstrip(".")
                )
            if (
                not crossref_linked_domain_only
                and isinstance(official_domain, str)
                and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", official_domain.casefold())
            ):
                organization_provenance["official_domain"] = official_domain.casefold().rstrip(".")
            publication_url = raw_organization.get("official_publication_url")
            if isinstance(publication_url, str) and len(publication_url) <= 2000:
                try:
                    parsed_publication_url = urlsplit(publication_url)
                    publication_host = (
                        (parsed_publication_url.hostname or "").casefold().rstrip(".")
                    )
                    verified_domain = organization_provenance.get("official_domain")
                    same_domain = isinstance(verified_domain, str) and (
                        publication_host == verified_domain
                        or publication_host.endswith("." + verified_domain)
                    )
                    if (
                        parsed_publication_url.scheme.casefold() == "https"
                        and parsed_publication_url.username is None
                        and parsed_publication_url.password is None
                        and same_domain
                    ):
                        organization_provenance["official_publication_url"] = publication_url
                except ValueError:
                    pass
    retrieval = retrieval_metadata_for_api(
        source.metadata_json.get("retrieval"), source.retrieval_status
    )
    if organization_provenance is not None:
        if source.retrieval_status in {"full_text_html", "full_text_pdf", "full_text_jats"}:
            organization_provenance["publication_content_access"] = source.retrieval_status
            organization_provenance["publication_rights_status"] = "permitted"
        else:
            organization_provenance.setdefault("publication_content_access", "not_retrieved")
            organization_provenance.setdefault(
                "publication_rights_status", "metadata_only_not_assessed"
            )
    abstract_available = source.metadata_json.get("abstract_text_available_at_discovery")
    abstract_retention_status = source.metadata_json.get("abstract_text_retention_status")
    if not isinstance(abstract_available, bool) and source.abstract_excerpt:
        abstract_available = True
    if not isinstance(abstract_retention_status, str) and source.abstract_excerpt:
        abstract_retention_status = "legacy_not_recorded"
    abstract_excerpt = (
        source.abstract_excerpt
        if abstract_text_reuse_permitted(source, source.abstract_excerpt)
        else None
    )
    return {
        "id": source.id,
        "title": source.title,
        "doi": source.doi,
        "url": source.url,
        "authors": source.authors_json,
        "published_year": source.published_year,
        "publisher": source.publisher,
        "provider": provider,
        "provider_metadata_schema_version": provider_metadata.get("schema_version") or None,
        "source_governance": source_governance_for_api(
            source.metadata_json.get("source_governance")
        ),
        "organization_provenance": organization_provenance,
        "openalex_fulltext_availability": openalex_fulltext_availability,
        "institutional_publication": institutional_publication,
        "official_publication": official_publication,
        "official_site_publication": official_site_publication,
        "source_type": source.source_type,
        "retrieval_status": source.retrieval_status,
        "retrieval": retrieval,
        "statistics": statistics,
        "abstract_excerpt": abstract_excerpt,
        "abstract_text_available_at_discovery": abstract_available,
        "abstract_text_retention_status": abstract_retention_status,
        "appraisal": _redact_export_value(
            source_appraisal_for_api(
                source.appraisal_json
                if not source.abstract_excerpt
                or abstract_text_reuse_permitted(source, source.abstract_excerpt)
                else {}
            )
        ),
    }


def _candidate_out(candidate: DiscoveryCandidate) -> dict[str, Any]:
    relevance = candidate_relevance_for_api(candidate.relevance_json)
    abstract_excerpt, retention_status = normalize_candidate_abstract_snapshot(
        abstract_excerpt=candidate.abstract_excerpt,
        retention_status=candidate.abstract_excerpt_retention_status,
    )
    return {
        "id": candidate.id,
        "provider": candidate.provider,
        "provider_record_id": candidate.provider_record_id,
        "canonical_identity": candidate.canonical_identity,
        "title": candidate.title,
        "publisher": getattr(candidate, "publisher", None),
        "publisher_organizations": (
            [
                item
                for item in (getattr(candidate, "publisher_organizations_json", None) or [])[:2]
                if isinstance(item, dict)
            ]
            if isinstance(getattr(candidate, "publisher_organizations_json", None), list)
            else []
        ),
        "abstract_excerpt": abstract_excerpt,
        "abstract_excerpt_retention_status": retention_status,
        "doi": candidate.doi,
        "url": candidate.url,
        "published_year": candidate.published_year,
        "query": candidate.query_text,
        "ranking_order": candidate.ranking_order,
        "relevance_score": relevance.get("score") if relevance else None,
        "planned_query_score": (
            relevance.get("planned_query_alignment", {}).get("score") if relevance else None
        ),
        "selection_score": relevance.get("selection_score") if relevance else None,
        "relevance": relevance,
        "source_governance": source_governance_for_api(
            getattr(candidate, "source_governance_json", None)
        ),
        "disposition": candidate.disposition,
        "reason_code": candidate.reason_code,
        "canonical_source_id": candidate.canonical_source_id,
        "discovered_at": candidate.discovered_at,
    }


def _structured_document_metadata_out(value: object) -> dict[str, Any] | None:
    """Expose an allowlisted extraction provenance summary, never raw document XML."""
    if not isinstance(value, dict) or value.get("representation_format") != "jats":
        return None
    output: dict[str, Any] = {}
    for key, max_length in (
        ("retrieval_origin", 80),
        ("pmcid", 20),
        ("doi", 300),
        ("rights_decision", 40),
        ("retention_display_rights", 40),
        ("license", 40),
        ("raw_license", 100),
        ("license_evidence", 120),
        ("representation_format", 16),
        ("parser_name", 80),
        ("parser_version", 40),
        ("extraction_status", 40),
    ):
        item = value.get(key)
        if isinstance(item, str):
            output[key] = item[:max_length]
    sections = value.get("sections")
    if isinstance(sections, list):
        safe_sections = []
        for section in sections[:256]:
            if not isinstance(section, dict):
                continue
            safe_path = section.get("section_path")
            safe_sections.append(
                {
                    "section_id": str(section.get("section_id", ""))[:40],
                    "original_heading": str(section.get("original_heading", ""))[:300],
                    "normalized_type": str(section.get("normalized_type", "other"))[:32],
                    "section_path": [str(item)[:300] for item in safe_path[:12]]
                    if isinstance(safe_path, list)
                    else [],
                    "ordinal": section.get("ordinal")
                    if isinstance(section.get("ordinal"), int)
                    and not isinstance(section.get("ordinal"), bool)
                    else None,
                    "source_locator": str(section.get("source_locator", ""))[:500],
                }
            )
        output["sections"] = safe_sections
    warnings = value.get("extraction_warnings")
    if isinstance(warnings, list):
        output["extraction_warnings"] = [str(item)[:80] for item in warnings[:32]]
    if isinstance(value.get("section_metadata_truncated"), bool):
        output["section_metadata_truncated"] = value["section_metadata_truncated"]
    return output


def _passage_out(passage: Passage) -> dict[str, Any]:
    document = passage.document
    content_permitted = passage.access_level not in {"abstract_only", "abstract_excerpt"} or (
        passage_abstract_text_reuse_permitted(passage)
    )
    return {
        "id": passage.id,
        "source_id": passage.source_id,
        "document_id": passage.document_id,
        "identity_version": passage.identity_version,
        "ordinal": passage.ordinal,
        "locator": passage.locator,
        "content": passage.content if content_permitted else WITHHELD_ABSTRACT_TEXT,
        "content_withheld_reason": (
            None if content_permitted else "item_version_reuse_rights_not_recorded"
        ),
        "content_hash": passage.content_hash,
        "access_level": passage.access_level,
        "truncated": passage.truncated,
        "document": (
            {
                "id": document.id,
                "schema_version": document.schema_version,
                "source_version": document.source_version,
                "document_sha256": document.document_sha256,
                "retrieved_at": document.retrieved_at,
                "locator": document.locator,
                "media_type": document.media_type,
                "access_class": document.access_class,
                "hash_scope": document.hash_scope,
                "metadata": _structured_document_metadata_out(document.metadata_json),
            }
            if document is not None
            else None
        ),
    }


def _claim_out(claim: Claim) -> dict[str, Any]:
    text_permitted = claim.passage is None or (
        claim.passage.access_level not in {"abstract_only", "abstract_excerpt"}
        or passage_abstract_text_reuse_permitted(claim.passage)
    )
    appraisal = claim_appraisal_for_api(claim.appraisal_json if text_permitted else {})
    economic_facets = appraisal["economic_facets"]
    return {
        "id": claim.id,
        "source_id": claim.source_id,
        "passage_id": claim.passage_id,
        "text": claim.text if text_permitted else WITHHELD_CLAIM_TEXT,
        "source_sentence": (
            (claim.passage.content if claim.passage else claim.text)
            if text_permitted
            else WITHHELD_ABSTRACT_TEXT
        ),
        "text_withheld_reason": (
            None if text_permitted else "item_version_reuse_rights_not_recorded"
        ),
        "span_start": claim.span_start if text_permitted else None,
        "span_end": claim.span_end if text_permitted else None,
        "span_offset_unit": "unicode_codepoint_exclusive_end",
        "atomization_status": claim.atomization_status,
        "atomization_version": claim.atomization_version,
        "claim_type": claim.claim_type,
        "evidence_status": claim.evidence_status,
        "appraisal": _redact_export_value(appraisal),
        "economic_facets": economic_facets,
    }


def _claims_have_unverified_abstract_text(db: Session, claim_ids: list[str]) -> bool:
    """Fail closed for free-form comparison text tied to withheld abstract claims."""
    ids = {item for item in claim_ids if isinstance(item, str) and item}
    if not ids:
        return False
    cache = db.info.setdefault("unverified_abstract_claim_text", {})
    pending_ids = ids - cache.keys()
    if pending_ids:
        claims = list(
            db.scalars(
                select(Claim)
                .options(
                    selectinload(Claim.passage).selectinload(Passage.source),
                    selectinload(Claim.passage).selectinload(Passage.document),
                )
                .where(Claim.id.in_(pending_ids))
            )
        )
        for claim in claims:
            passage = claim.passage
            cache[claim.id] = passage is None or (
                passage.access_level in {"abstract_only", "abstract_excerpt"}
                and not passage_abstract_text_reuse_permitted(passage)
            )
        for missing_id in pending_ids - cache.keys():
            cache[missing_id] = True
    return any(cache[claim_id] for claim_id in ids)


def _relationship_out(item: EvidenceRelationship, db: Session) -> dict[str, Any]:
    result = relationship_record_for_api(
        {
            "claim_a_id": item.claim_a_id,
            "claim_b_id": item.claim_b_id,
            "relationship_type": item.relationship_type,
            "scope_alignment": item.scope_alignment,
            "scope_differences": item.scope_differences_json,
            "rationale": item.rationale,
            "evidence": item.evidence_json,
            "status": item.status,
            "schema_version": item.schema_version,
            "provider": item.provider,
            "model_name": item.model_name,
        }
    )
    if _claims_have_unverified_abstract_text(db, [item.claim_a_id, item.claim_b_id]):
        result["rationale"] = WITHHELD_COMPARISON_TEXT
        result["text_withheld_reason"] = "item_version_reuse_rights_not_recorded"
    return {"id": item.id, **result, "created_at": item.created_at}


def _hypothesis_out(item: Hypothesis, db: Session) -> dict[str, Any]:
    result = hypothesis_record_for_api(
        {
            "comparison_group_id": item.comparison_group_id,
            "side": item.side,
            "statement": item.statement,
            "evidence": item.evidence_json,
            "uncertainty": item.uncertainty,
            "why_competing": item.why_competing,
            "status": item.status,
            "schema_version": item.schema_version,
            "provider": item.provider,
            "model_name": item.model_name,
        }
    )
    evidence = item.evidence_json if isinstance(item.evidence_json, list) else []
    claim_ids = [link.get("claim_id") for link in evidence if isinstance(link, dict)]
    if _claims_have_unverified_abstract_text(db, claim_ids):
        result.update(
            statement=WITHHELD_HYPOTHESIS_TEXT,
            uncertainty=WITHHELD_HYPOTHESIS_TEXT,
            why_competing=WITHHELD_HYPOTHESIS_TEXT,
            text_withheld_reason="item_version_reuse_rights_not_recorded",
        )
    return {"id": item.id, **result, "created_at": item.created_at}


def _report_verification_without_source_text(value: dict[str, Any]) -> dict[str, Any]:
    """Keep check outcomes while withholding free-text evaluations tied to denied excerpts."""
    output = dict(value)
    for key in (
        "claim_units",
        "decision_implications",
        "semantic_audit_items",
        "uncited_material_claims",
        "rejected_semantic_audit_records",
    ):
        if key in output:
            output[key] = []
    semantic = output.get("semantic_assessment")
    if isinstance(semantic, dict):
        safe_fields = {
            "schema_version",
            "method",
            "support_check",
            "uncited_material_claim_scan",
            "provider",
            "model",
            "audit_schema_version",
            "input_truncated",
            "skip_reason",
        }
        output["semantic_assessment"] = {
            key: item for key, item in semantic.items() if key in safe_fields
        }
    absence_guard = output.get("measurement_absence_guard_v1")
    if isinstance(absence_guard, dict):
        output["measurement_absence_guard_v1"] = {
            key: item
            for key, item in absence_guard.items()
            if key in {"schema_version", "status", "rejected_count", "checked_count"}
        }
    output["historical_evidence_text_withheld"] = True
    return output


def _report_out(report: ResearchReport) -> dict[str, Any]:
    citation_map = report_citation_map_for_api(report.citation_map_json)
    verification = report_verification_for_api(report.verification_json)
    content_withheld = False
    if report.job is not None:
        for source in report.job.sources:
            if source.abstract_excerpt and not abstract_text_reuse_permitted(
                source, source.abstract_excerpt
            ):
                content_withheld = True
                break
            if any(
                passage.access_level in {"abstract_only", "abstract_excerpt"}
                and not passage_abstract_text_reuse_permitted(passage)
                for passage in source.passages
            ):
                content_withheld = True
                break
    if content_withheld:
        verification = _report_verification_without_source_text(verification)
    version = verification.get("report_schema_version", 1)
    return {
        "id": report.id,
        "job_id": report.job_id,
        "version": version if isinstance(version, int) and not isinstance(version, bool) else 1,
        "citation_map_schema_version": 1,
        "verification_schema_version": 1,
        "status": report.status,
        "body_markdown": (
            "# Historical report text withheld\n\n"
            "This saved report cites abstract-only evidence whose item/version text reuse rights "
            "were not recorded. The stored report and evidence records are unchanged; their text "
            "is withheld from this view and export pending a rights decision."
            if content_withheld
            else report.body_markdown
        ),
        "evidence_content_withheld": content_withheld,
        "content_withheld_reason": (
            "item_version_reuse_rights_not_recorded" if content_withheld else None
        ),
        "citation_map": citation_map,
        "verification": verification,
        "model_name": report.model_name,
        "created_at": report.created_at,
    }


def _source_is_citation_only(source: Source) -> bool:
    metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
    retrieval = metadata.get("retrieval")
    rights = retrieval.get("rights_assessment") if isinstance(retrieval, dict) else None
    return isinstance(rights, dict) and rights.get("sharing") == "CITATION_ONLY"


def _claim_ids_include_citation_only_source(db: Session, claim_ids: list[str]) -> bool:
    ids = {value for value in claim_ids if isinstance(value, str) and value}
    if not ids:
        return False
    cache = db.info.setdefault("citation_only_claim_export", {})
    pending = ids - cache.keys()
    if pending:
        claims = list(
            db.scalars(
                select(Claim)
                .options(selectinload(Claim.passage).selectinload(Passage.source))
                .where(Claim.id.in_(pending))
            )
        )
        for claim in claims:
            cache[claim.id] = bool(
                claim.passage is None or _source_is_citation_only(claim.passage.source)
            )
        for missing_id in pending - cache.keys():
            cache[missing_id] = True
    return any(cache[claim_id] for claim_id in ids)


def _report_out_for_export(report: ResearchReport) -> dict[str, Any]:
    result = _report_out(report)
    job = report.job
    if job is None:
        return result
    citation_only_sources = {
        source.id
        for source in job.sources
        if _source_is_citation_only(source) and bool(source.passages)
    }
    if not citation_only_sources:
        return result
    citation_map = result.get("citation_map")
    citation_entries = list(citation_map.values()) if isinstance(citation_map, dict) else []
    cited_source_ids: set[str] = set()
    citation_provenance_incomplete = not citation_entries
    for citation in citation_entries:
        source_id = citation.get("source_id") if isinstance(citation, dict) else None
        if isinstance(source_id, str) and source_id:
            cited_source_ids.add(source_id)
        else:
            citation_provenance_incomplete = True
    if not citation_provenance_incomplete and not citation_only_sources.intersection(
        cited_source_ids
    ):
        return result
    citation_lines = []
    for label, citation in result["citation_map"].items():
        if not isinstance(citation, dict):
            continue
        title = citation.get("title")
        location = citation.get("doi") or citation.get("url")
        if isinstance(title, str) and title.strip():
            citation_lines.append(
                f"- [{label}] {title.strip()}"
                + (f" - {location}" if isinstance(location, str) and location else "")
            )
    result["body_markdown"] = (
        "# Report text withheld from export\n\n"
        "This report includes evidence retained under a private-research policy whose sharing "
        "scope is citation-only. The report remains inspectable in Veda for the configured "
        "private research use; this export contains bibliographic citations only and does not "
        "grant redistribution rights.\n\n## Bibliographic citations\n\n"
        + ("\n".join(citation_lines) if citation_lines else "No citation metadata is available.")
    )
    result["evidence_content_withheld"] = True
    result["content_withheld_reason"] = "source_sharing_citation_only"
    result["verification"] = _report_verification_without_source_text(result["verification"])
    return result


def _owned_project(
    db: Session,
    project_id: str,
    user: AuthUser,
    *,
    include_archived: bool = False,
    for_update: bool = False,
) -> Project:
    query = select(Project).where(Project.id == project_id, Project.owner_id == user.id)
    if not include_archived:
        query = query.where(Project.archived_at.is_(None))
    if for_update:
        query = query.with_for_update()
    project = db.scalar(query)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _owned_job(db: Session, job_id: str, user: AuthUser) -> ResearchJob:
    job = db.scalar(
        select(ResearchJob)
        .join(Project, ResearchJob.project_id == Project.id)
        .where(ResearchJob.id == job_id, Project.owner_id == user.id, Project.archived_at.is_(None))
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found")
    return job


def _owned_source(db: Session, source_id: str, user: AuthUser) -> Source:
    source = db.scalar(
        select(Source)
        .join(ResearchJob, Source.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .where(Source.id == source_id, Project.owner_id == user.id, Project.archived_at.is_(None))
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


def _owned_passage(db: Session, passage_id: str, user: AuthUser) -> Passage:
    passage = db.scalar(
        select(Passage)
        .join(Source, Passage.source_id == Source.id)
        .join(ResearchJob, Source.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .where(Passage.id == passage_id, Project.owner_id == user.id, Project.archived_at.is_(None))
    )
    if passage is None:
        raise HTTPException(status_code=404, detail="Passage not found")
    return passage


def _owned_claim(db: Session, claim_id: str, user: AuthUser) -> Claim:
    claim = db.scalar(
        select(Claim)
        .join(ResearchJob, Claim.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .where(Claim.id == claim_id, Project.owner_id == user.id, Project.archived_at.is_(None))
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


@router.post("/auth/dev-session")
def dev_session(request: Request, _=Depends(require_loopback_dev_request)) -> dict[str, Any]:
    return {
        "access_token": create_local_token(),
        "token_type": "bearer",
        "expires_in": 43200,
        "user": {"id": "00000000-0000-4000-8000-000000000001", "provider": "local-development"},
    }


@router.get("/me")
def me(user: AuthUser = Depends(get_current_user)) -> dict[str, str]:
    return {"id": user.id, "provider": user.provider}


@router.get("/me/preferences")
def get_preferences(
    db: Session = Depends(get_db), user: AuthUser = Depends(get_current_user)
) -> dict[str, Any]:
    preference = db.get(UserPreference, user.id)
    return {
        "default_depth": preference.default_depth if preference else "standard",
        "default_budget_ceiling_usd": preference.default_budget_ceiling_usd if preference else 0.0,
        "retention_days": preference.retention_days if preference else None,
        "is_customized": preference is not None,
        "updated_at": preference.updated_at if preference else None,
    }


@router.patch("/me/preferences")
def update_preferences(
    payload: UserPreferencesPatch,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    changes = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None or key == "retention_days"
    }
    if not changes:
        raise HTTPException(status_code=422, detail="At least one preference must be supplied")
    preference = db.get(UserPreference, user.id)
    if preference is None:
        preference = UserPreference(user_id=user.id)
        db.add(preference)
    for field, value in changes.items():
        setattr(preference, field, value)
    preference.updated_at = utcnow()
    try:
        db.commit()
    except IntegrityError:
        # Two first-time PATCH requests can race to insert the same user key.
        db.rollback()
        preference = db.get(UserPreference, user.id)
        if preference is None:
            raise
        for field, value in changes.items():
            setattr(preference, field, value)
        preference.updated_at = utcnow()
        db.commit()
    db.refresh(preference)
    return {
        "default_depth": preference.default_depth,
        "default_budget_ceiling_usd": preference.default_budget_ceiling_usd,
        "retention_days": preference.retention_days,
        "is_customized": True,
        "updated_at": preference.updated_at,
    }


@router.delete("/me/preferences")
def reset_preferences(
    db: Session = Depends(get_db), user: AuthUser = Depends(get_current_user)
) -> dict[str, Any]:
    preference = db.get(UserPreference, user.id)
    if preference is not None:
        db.delete(preference)
        db.commit()
    return {
        "default_depth": "standard",
        "default_budget_ceiling_usd": 0.0,
        "retention_days": None,
        "is_customized": False,
        "updated_at": None,
    }


@router.get("/me/data-lifecycle")
def get_data_lifecycle(user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    _ = user  # Authentication is required; this response contains product-wide capabilities.
    return {
        "report_exports": {
            "status": "available",
            "formats": ["markdown", "json"],
            "scope": "One report at a time; owner access is required, including after project archive.",
        },
        "project_archive": {
            "status": "available",
            "effect": "Soft archive: hides a project from the default workspace and research routes; stored records are retained.",
            "restore_supported": True,
        },
        "project_permanent_deletion": {
            "status": "available",
            "detail": "Archived projects can be permanently deleted after typing DELETE and the exact project title. Deletion is blocked while a research step is still running; try again after it finishes or stops. This removes Veda-stored project research records and cannot be undone.",
        },
        "full_account_export": {
            "status": "available",
            "alternative": "Download Veda-stored account research records as JSON. Identity-provider records and original HTML/PDF bytes are not stored or included.",
            "endpoint": "/api/v1/me/export",
            "format": "json",
        },
        "account_deletion": {
            "status": "unsupported",
            "detail": "The Veda-data purge does not remove your sign-in account. Identity-provider account deletion must be requested from the configured authentication provider.",
        },
        "veda_data_deletion": {
            "status": "available",
            "endpoint": "/api/v1/me/data",
            "confirmation_phrase": "DELETE VEDA DATA",
            "detail": "Permanently removes your Veda-stored projects and research records and resets your saved preferences. It is blocked while a bounded research step is running. Your sign-in account, operator-held backups, and current UTC day's quota safety counter are not deleted; export your data first if you need a copy.",
        },
        "retention": {
            "status": "configurable_archived_project_retention",
            "options_days": [30, 90, 365],
            "maintenance_command": "python -m app.maintenance.purge_expired_projects --apply",
            "detail": "Choose never, 30, 90, or 365 days in Preferences. The choice applies when you next archive a project; restoring cancels its scheduled purge. Expired projects are removed only when the deployment's scheduled maintenance command runs. No scheduler is configured by this local build, and operators remain responsible for database-backup retention.",
        },
    }


@router.delete("/me/data", response_model=VedaDataPurgeOut)
def delete_veda_data(
    payload: VedaDataPurgeRequest,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Erase an owner's Veda records without deleting their identity-provider account."""
    projects = list(
        db.scalars(
            select(Project)
            .where(Project.owner_id == user.id)
            .order_by(Project.id)
            .with_for_update()
        ).all()
    )
    project_ids = [project.id for project in projects]
    jobs = (
        list(
            db.scalars(
                select(ResearchJob)
                .where(ResearchJob.project_id.in_(project_ids))
                .order_by(ResearchJob.project_id, ResearchJob.id)
                .with_for_update()
            ).all()
        )
        if project_ids
        else []
    )
    now = utcnow()
    if any(
        job.lease_expires_at
        and job.lease_expires_at.replace(tzinfo=job.lease_expires_at.tzinfo or now.tzinfo) > now
        for job in jobs
    ):
        raise HTTPException(
            status_code=409,
            detail="A research step is still running. Wait for it to save or finish before deleting Veda data.",
        )

    deleted_projects = len(projects)
    for project in projects:
        db.delete(project)
    preference = db.get(UserPreference, user.id)
    deleted_preferences = preference is not None
    if preference is not None:
        db.delete(preference)

    current_utc_date = utcnow().date()
    db.execute(
        delete(DailyModelQuota).where(
            DailyModelQuota.scope == "user",
            DailyModelQuota.scope_id == user.id,
            DailyModelQuota.quota_date < current_utc_date,
        )
    )
    db.commit()
    return {
        "deleted_projects": deleted_projects,
        "deleted_preferences": deleted_preferences,
        "daily_quota_counters_preserved_until_utc_date": current_utc_date,
        "identity_provider_account_deleted": False,
    }


def _export_json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Unsupported export value: {type(value).__name__}")


def _redact_export_value(value: Any) -> Any:
    secret_fragments = (
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "secret",
    )
    if isinstance(value, dict):
        return {
            key: "[redacted]"
            if any(fragment in str(key).casefold() for fragment in secret_fragments)
            else _redact_export_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_export_value(item) for item in value]
    return value


def _export_row(record: Any) -> dict[str, Any]:
    mapper = sa_inspect(record).mapper
    return _redact_export_value(
        {attribute.key: getattr(record, attribute.key) for attribute in mapper.column_attrs}
    )


@router.get("/me/export")
def export_account_data(
    db: Session = Depends(get_db), user: AuthUser = Depends(get_current_user)
) -> StreamingResponse:
    """Stream Veda-owned account records without credentials or original document bytes."""
    project_ids = select(Project.id).where(Project.owner_id == user.id)
    job_ids = select(ResearchJob.id).where(ResearchJob.project_id.in_(project_ids))
    conversation_ids = select(Conversation.id).where(Conversation.project_id.in_(project_ids))
    source_ids = select(Source.id).where(Source.job_id.in_(job_ids))
    collections = [
        ("projects", select(Project).where(Project.owner_id == user.id), Project.id),
        (
            "user_preferences",
            select(UserPreference).where(UserPreference.user_id == user.id),
            UserPreference.user_id,
        ),
        (
            "daily_model_quotas",
            select(DailyModelQuota).where(
                DailyModelQuota.scope == "user", DailyModelQuota.scope_id == user.id
            ),
            DailyModelQuota.id,
        ),
        (
            "conversations",
            select(Conversation).where(Conversation.project_id.in_(project_ids)),
            Conversation.id,
        ),
        (
            "messages",
            select(Message).where(Message.conversation_id.in_(conversation_ids)),
            Message.id,
        ),
        (
            "research_jobs",
            select(ResearchJob).where(ResearchJob.project_id.in_(project_ids)),
            ResearchJob.id,
        ),
        ("job_events", select(JobEvent).where(JobEvent.job_id.in_(job_ids)), JobEvent.id),
        ("sources", select(Source).where(Source.job_id.in_(job_ids)), Source.id),
        (
            "discovery_candidates",
            select(DiscoveryCandidate).where(DiscoveryCandidate.job_id.in_(job_ids)),
            DiscoveryCandidate.id,
        ),
        (
            "retrieved_documents",
            select(RetrievedDocument).where(RetrievedDocument.source_id.in_(source_ids)),
            RetrievedDocument.id,
        ),
        ("passages", select(Passage).where(Passage.source_id.in_(source_ids)), Passage.id),
        ("claims", select(Claim).where(Claim.job_id.in_(job_ids)), Claim.id),
        (
            "evidence_relationships",
            select(EvidenceRelationship).where(EvidenceRelationship.job_id.in_(job_ids)),
            EvidenceRelationship.id,
        ),
        ("hypotheses", select(Hypothesis).where(Hypothesis.job_id.in_(job_ids)), Hypothesis.id),
        (
            "reports",
            select(ResearchReport).where(ResearchReport.job_id.in_(job_ids)),
            ResearchReport.id,
        ),
        (
            "model_call_reservations",
            select(ModelCallReservation).where(ModelCallReservation.job_id.in_(job_ids)),
            ModelCallReservation.id,
        ),
        ("usage_ledger", select(UsageEntry).where(UsageEntry.job_id.in_(job_ids)), UsageEntry.id),
    ]

    def stream() -> Any:
        header = {
            "schema_version": 1,
            "generated_at": utcnow().isoformat(),
            "account_user_id": user.id,
            "scope": "all Veda-stored records owned by this authenticated user",
            "excludes": [
                "identity-provider account records",
                "API credentials and authentication tokens",
                "original downloaded HTML/PDF bytes",
            ],
        }
        yield '{"export":'
        yield json.dumps(header, ensure_ascii=False, separators=(",", ":"))
        yield ',"collections":{'
        for collection_index, (name, statement, order_column) in enumerate(collections):
            if collection_index:
                yield ","
            yield json.dumps(name)
            yield ":["
            first = True
            rows = db.scalars(statement.order_by(order_column).execution_options(yield_per=100))
            for record in rows:
                if not first:
                    yield ","
                first = False
                exported_record = _export_row(record)
                if isinstance(record, Source):
                    citation_only = _source_is_citation_only(record)
                    if citation_only or not abstract_text_reuse_permitted(
                        record, record.abstract_excerpt
                    ):
                        exported_record["abstract_excerpt"] = None
                        metadata = dict(exported_record.get("metadata_json") or {})
                        metadata.setdefault(
                            "abstract_text_retention_status",
                            "not_exported_citation_only"
                            if citation_only
                            else "legacy_not_recorded",
                        )
                        exported_record["metadata_json"] = metadata
                    exported_record["appraisal_json"] = _redact_export_value(
                        source_appraisal_for_api(
                            record.appraisal_json
                            if not citation_only
                            and (
                                not record.abstract_excerpt
                                or abstract_text_reuse_permitted(record, record.abstract_excerpt)
                            )
                            else {}
                        )
                    )
                elif isinstance(record, Passage):
                    if _source_is_citation_only(record.source) or (
                        record.access_level in {"abstract_only", "abstract_excerpt"}
                        and not passage_abstract_text_reuse_permitted(record)
                    ):
                        exported_record["content"] = WITHHELD_ABSTRACT_TEXT
                        exported_record["content_withheld_reason"] = (
                            "source_sharing_citation_only"
                            if _source_is_citation_only(record.source)
                            else "item_version_reuse_rights_not_recorded"
                        )
                elif isinstance(record, Claim):
                    citation_only = bool(
                        record.passage and _source_is_citation_only(record.passage.source)
                    )
                    abstract_text_unverified = bool(
                        record.passage
                        and record.passage.access_level in {"abstract_only", "abstract_excerpt"}
                        and not passage_abstract_text_reuse_permitted(record.passage)
                    )
                    if citation_only or abstract_text_unverified:
                        exported_record.update(
                            text=WITHHELD_CLAIM_TEXT,
                            span_start=None,
                            span_end=None,
                            atomization_status="text_withheld_pending_rights_review",
                            text_withheld_reason=(
                                "source_sharing_citation_only"
                                if citation_only
                                else "item_version_reuse_rights_not_recorded"
                            ),
                        )
                        exported_record["appraisal_json"] = claim_appraisal_for_api({})
                    else:
                        exported_record["appraisal_json"] = _redact_export_value(
                            claim_appraisal_for_api(record.appraisal_json)
                        )
                elif isinstance(record, EvidenceRelationship):
                    exported_record.update(_redact_export_value(_relationship_out(record, db)))
                    if _claim_ids_include_citation_only_source(
                        db, [record.claim_a_id, record.claim_b_id]
                    ):
                        exported_record.update(
                            rationale=WITHHELD_COMPARISON_TEXT,
                            scope_differences_json=[],
                            evidence_json=[],
                            text_withheld_reason="source_sharing_citation_only",
                        )
                elif isinstance(record, Hypothesis):
                    exported_record.update(_redact_export_value(_hypothesis_out(record, db)))
                    evidence = (
                        record.evidence_json if isinstance(record.evidence_json, list) else []
                    )
                    claim_ids = [
                        item.get("claim_id") for item in evidence if isinstance(item, dict)
                    ]
                    if _claim_ids_include_citation_only_source(db, claim_ids):
                        exported_record.update(
                            statement=WITHHELD_HYPOTHESIS_TEXT,
                            uncertainty=WITHHELD_HYPOTHESIS_TEXT,
                            why_competing=WITHHELD_HYPOTHESIS_TEXT,
                            evidence_json=[],
                            text_withheld_reason="source_sharing_citation_only",
                        )
                elif isinstance(record, ResearchReport):
                    api_report = _report_out_for_export(record)
                    exported_record["body_markdown"] = api_report["body_markdown"]
                    exported_record["evidence_content_withheld"] = api_report[
                        "evidence_content_withheld"
                    ]
                    exported_record["content_withheld_reason"] = api_report[
                        "content_withheld_reason"
                    ]
                    exported_record["citation_map_json"] = _redact_export_value(
                        versioned_report_citation_map(record.citation_map_json)
                    )
                    exported_record["verification_json"] = _redact_export_value(
                        {
                            "schema_version": 1,
                            "record": api_report["verification"],
                            "extensions": {},
                        }
                        if api_report["evidence_content_withheld"]
                        else versioned_report_verification(record.verification_json)
                    )
                yield json.dumps(
                    exported_record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=_export_json_default,
                )
            yield "]"
        yield "}}"

    filename = f"veda-account-export-{utcnow().date().isoformat()}.json"
    return StreamingResponse(
        stream(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/settings/providers")
def get_provider_status(user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    configured = configured_model()
    return {
        "user_id": user.id,
        "active_provider": settings.llm_provider,
        "provider_ready": settings.llm_provider == "disabled" or configured.ready,
        "configuration_reason": configured.reason,
        "model": configured.model,
        "cost_currency": configured.currency,
        "strict_json_schema_supported": configured.strict_json_schema,
        "paid_calls_allowed": bool(settings.allow_paid_llm_calls),
        "daily_call_limit": settings.max_daily_model_calls,
        "per_user_daily_call_limit": settings.max_daily_model_calls_per_user,
    }


@router.get("/settings/depth-profiles")
def get_depth_profiles(user: AuthUser = Depends(get_current_user)) -> dict[str, Any]:
    return {"profiles": public_depth_profiles()}


@health_router.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "alive"}


@health_router.get("/health/ready")
def health_ready(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(select(1))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc
    return {"status": "ready", "database": "reachable"}


@router.get("/projects")
def list_projects(
    include_archived: bool = False,
    archived_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    query = select(Project).where(Project.owner_id == user.id)
    if archived_only:
        query = query.where(Project.archived_at.is_not(None))
    elif not include_archived:
        query = query.where(Project.archived_at.is_(None))
    total = _query_total(db, query)
    query = query.order_by(Project.updated_at.desc(), Project.id.desc())
    projects, has_more = _bounded_page(db, query, limit=limit, offset=offset)
    return {
        "items": [_project_out(project) for project in projects],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.post("/projects", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Project:
    project = Project(
        owner_id=user.id,
        title=payload.title,
        description=payload.description,
        domain=payload.domain,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Project:
    return _owned_project(db, project_id, user)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def patch_project(
    project_id: str,
    payload: ProjectPatch,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Project:
    project = _owned_project(db, project_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(
                project,
                field,
                value.strip() if isinstance(value, str) and field in {"title", "domain"} else value,
            )
    project.updated_at = utcnow()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Response:
    project = _owned_project(db, project_id, user)
    project.archived_at = utcnow()
    preference = db.get(UserPreference, user.id)
    project.purge_at = (
        project.archived_at + timedelta(days=preference.retention_days)
        if preference and preference.retention_days
        else None
    )
    project.updated_at = utcnow()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/restore", response_model=ProjectOut)
def restore_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Project:
    project = _owned_project(db, project_id, user, include_archived=True)
    if project.archived_at is not None:
        project.archived_at = None
        project.purge_at = None
        project.updated_at = utcnow()
        db.commit()
        db.refresh(project)
    return project


@router.delete("/projects/{project_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_project(
    project_id: str,
    payload: ProjectPurgeRequest,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Response:
    project = _owned_project(db, project_id, user, include_archived=True, for_update=True)
    if project.archived_at is None:
        raise HTTPException(
            status_code=409,
            detail="Archive the project before permanently deleting its Veda records.",
        )
    if payload.project_title != project.title:
        raise HTTPException(
            status_code=409,
            detail="Type DELETE and the exact project title to permanently remove its Veda data.",
        )
    now = utcnow()
    project_jobs = list(
        db.scalars(
            select(ResearchJob)
            .where(ResearchJob.project_id == project.id)
            .order_by(ResearchJob.id)
            .with_for_update()
        ).all()
    )
    for job in project_jobs:
        lease_expiry = job.lease_expires_at
        if lease_expiry and lease_expiry.replace(tzinfo=lease_expiry.tzinfo or now.tzinfo) > now:
            raise HTTPException(
                status_code=409,
                detail="A research step is still running. Wait for it to save or finish before deleting this project.",
            )
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/conversations")
def list_conversations(
    project_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_project(db, project_id, user)
    query = select(Conversation).where(Conversation.project_id == project_id)
    total = _query_total(db, query)
    conversations, has_more = _bounded_page(
        db,
        query.order_by(Conversation.created_at.desc(), Conversation.id.desc()),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_conversation_out(conversation) for conversation in conversations],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.post("/projects/{project_id}/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(
    project_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_project(db, project_id, user)
    conversation = Conversation(project_id=project_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_out(conversation)


@router.get("/conversations/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    conversation = db.scalar(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
            Conversation.id == conversation_id,
            Project.owner_id == user.id,
            Project.archived_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    query = select(Message).where(Message.conversation_id == conversation_id)
    total = _query_total(db, query)
    newest_first = list(
        db.scalars(
            query.order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit + 1)
            .offset(offset)
        )
    )
    has_more = len(newest_first) > limit
    page = newest_first[:limit]
    return {
        "items": [_message_out(message) for message in reversed(page)],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def create_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    conversation = db.scalar(
        select(Conversation)
        .join(Project, Conversation.project_id == Project.id)
        .where(
            Conversation.id == conversation_id,
            Project.owner_id == user.id,
            Project.archived_at.is_(None),
        )
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    related_job_id = payload.related_job_id
    if related_job_id:
        related_job = _owned_job(db, related_job_id, user)
        if related_job.project_id != conversation.project_id:
            raise HTTPException(
                status_code=422, detail="Message jobs must stay within the conversation project"
            )
    message = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content.strip(),
        related_job_id=related_job_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return _message_out(message)


@router.get("/projects/{project_id}/research-jobs")
def list_project_jobs(
    project_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_project(db, project_id, user)
    query = select(ResearchJob).where(ResearchJob.project_id == project_id)
    total = _query_total(db, query)
    jobs, has_more = _bounded_page(
        db,
        query.order_by(ResearchJob.created_at.desc(), ResearchJob.id.desc()),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_job_out(job) for job in jobs],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.post(
    "/projects/{project_id}/research-jobs",
    status_code=status.HTTP_201_CREATED,
    response_model=JobOut,
)
def create_job(
    project_id: str,
    payload: JobCreate,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_project(db, project_id, user)
    existing = db.scalar(
        select(ResearchJob).where(
            ResearchJob.project_id == project_id,
            ResearchJob.idempotency_key == payload.idempotency_key,
        )
    )
    if existing:
        return _job_out(existing)
    if payload.budget_ceiling_usd > settings.max_job_cost_usd:
        raise HTTPException(
            status_code=422,
            detail=f"Budget exceeds configured per-job limit (${settings.max_job_cost_usd:.2f})",
        )
    if payload.budget_ceiling_inr > settings.sarvam_max_job_cost_inr:
        raise HTTPException(
            status_code=422,
            detail=(
                "INR budget exceeds the configured per-job Sarvam limit "
                f"(₹{settings.sarvam_max_job_cost_inr:.2f})"
            ),
        )
    parent_id = payload.parent_job_id
    parent: ResearchJob | None = None
    if parent_id:
        parent = _owned_job(db, parent_id, user)
        if parent.project_id != project_id:
            raise HTTPException(
                status_code=422, detail="Follow-up jobs must stay within the same project"
            )
    inherit_parent_model = (
        parent is not None and payload.model_provider is None and payload.model_name is None
    )
    selected_provider = (
        (parent.model_provider or settings.llm_provider)
        if inherit_parent_model and parent
        else payload.model_provider or settings.llm_provider
    )
    selected_model = parent.model_name if inherit_parent_model and parent else payload.model_name
    model_profile = configured_model(selected_provider, selected_model, config=settings)
    if selected_provider == "disabled" and payload.model_name is not None:
        raise HTTPException(status_code=422, detail="A disabled provider cannot select a model")
    if (
        payload.model_provider is not None or payload.model_name is not None
    ) and not model_profile.supported:
        raise HTTPException(
            status_code=422,
            detail=model_profile.reason or "The selected provider/model is not supported.",
        )
    selected_provider = model_profile.provider
    selected_model = model_profile.model
    if selected_provider != "sarvam" and payload.budget_ceiling_inr > 0:
        raise HTTPException(
            status_code=422,
            detail="INR model budget can be supplied only when Sarvam is the configured provider",
        )
    conversation: Conversation | None = None
    if payload.conversation_id:
        conversation = db.scalar(
            select(Conversation)
            .join(Project, Conversation.project_id == Project.id)
            .where(
                Conversation.id == payload.conversation_id,
                Conversation.project_id == project_id,
                Project.owner_id == user.id,
                Project.archived_at.is_(None),
            )
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    if parent and parent.conversation_id:
        if conversation and conversation.id != parent.conversation_id:
            raise HTTPException(
                status_code=422,
                detail="Follow-up jobs must stay in the parent research conversation",
            )
        parent_conversation = db.scalar(
            select(Conversation)
            .join(Project, Conversation.project_id == Project.id)
            .where(
                Conversation.id == parent.conversation_id,
                Conversation.project_id == project_id,
                Project.owner_id == user.id,
                Project.archived_at.is_(None),
            )
        )
        if parent_conversation is None:
            raise HTTPException(
                status_code=409, detail="The parent research conversation is unavailable"
            )
        conversation = conversation or parent_conversation
    if conversation is None:
        conversation = Conversation(project_id=project_id)
        db.add(conversation)
        db.flush()
    if parent:
        parent.conversation_id = conversation.id
        if not db.scalar(
            select(Message.id).where(Message.related_job_id == parent.id, Message.role == "user")
        ):
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=parent.question,
                    related_job_id=parent.id,
                )
            )
        if parent.report and not db.scalar(
            select(Message.id).where(
                Message.related_job_id == parent.id, Message.role == "assistant"
            )
        ):
            db.add(
                Message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=(
                        f"A preliminary evidence map was saved for this run as report "
                        f"{parent.report.id}. Open the report to inspect its source links and limitations."
                    ),
                    related_job_id=parent.id,
                )
            )
    scope = versioned_scope(
        {
            "context": payload.context,
            "geography": payload.geography,
            "population": payload.population,
            "time_horizon": payload.time_horizon,
            "decision_objective": payload.decision_objective,
            "comparator": payload.comparator,
            "target_outcome": payload.target_outcome,
            "denominator": payload.denominator,
            "assumptions_to_test": payload.assumptions_to_test,
        }
    )
    follow_up_context = None
    if parent:
        parent_evidence = list(
            db.execute(
                select(Claim, Source, Passage)
                .join(Source, Claim.source_id == Source.id)
                .join(Passage, Claim.passage_id == Passage.id)
                .where(Claim.job_id == parent.id)
                .order_by(Claim.created_at.desc())
                .limit(100)
            )
        )
        stop_words = {
            "about",
            "after",
            "also",
            "between",
            "from",
            "have",
            "into",
            "that",
            "their",
            "there",
            "these",
            "this",
            "what",
            "when",
            "where",
            "which",
            "with",
        }
        terms = set(re.findall(r"[a-z0-9]{4,}", payload.question.casefold())) - stop_words
        parent_evidence.sort(
            key=lambda row: (
                len(
                    terms & (set(re.findall(r"[a-z0-9]{4,}", row[0].text.casefold())) - stop_words)
                ),
                row[0].created_at,
            ),
            reverse=True,
        )
        scored_evidence = [
            (
                row,
                len(
                    terms & (set(re.findall(r"[a-z0-9]{4,}", row[0].text.casefold())) - stop_words)
                ),
            )
            for row in parent_evidence
        ]
        reused_claim_ids = [row[0].id for row, score in scored_evidence if score > 0][:8]
        follow_up_context = {
            "schema_version": 1,
            "parent_job_id": parent.id,
            "parent_question": parent.question,
            "parent_report_id": parent.report.id if parent.report else None,
            "parent_report_status": parent.report.status if parent.report else None,
            "reused_claim_ids": reused_claim_ids,
            "reuse_method": "lexical_token_overlap_top8_with_parent_evidence",
            "reuse_boundary": (
                "Parent claims are context for follow-up planning only. They are not copied into this run's claims or citations; "
                "the follow-up must retrieve and link its own evidence."
            ),
        }
    checkpoint = {
        "schema_version": 1,
        "workflow_version": 1,
        "depth_profile": depth_profile(payload.depth).as_dict(),
    }
    if follow_up_context:
        checkpoint["follow_up_context"] = follow_up_context
    job = ResearchJob(
        project_id=project_id,
        parent_job_id=parent_id,
        conversation_id=conversation.id,
        question=payload.question.strip(),
        scope_json=scope,
        depth=payload.depth,
        model_provider=selected_provider,
        model_name=selected_model,
        budget_ceiling_usd=payload.budget_ceiling_usd,
        budget_ceiling_inr=payload.budget_ceiling_inr,
        idempotency_key=payload.idempotency_key,
        checkpoint_json=versioned_checkpoint(checkpoint, strict=True),
    )
    db.add(job)
    db.flush()
    if conversation.title == "Research conversation":
        title = payload.question.strip()
        conversation.title = title[:157] + ("..." if len(title) > 160 else "")
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=job.question,
            related_job_id=job.id,
        )
    )
    append_event(
        db,
        job.id,
        event_type="job_created",
        stage="planning",
        message="Research job created and queued.",
    )
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.get("/research-jobs/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _job_out(_owned_job(db, job_id, user))


@router.get("/research-jobs/{job_id}/follow-up-context")
def get_follow_up_context(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    job = _owned_job(db, job_id, user)
    if not job.parent_job_id:
        return {"status": "not_a_follow_up", "parent": None, "claims": []}
    parent = _owned_job(db, job.parent_job_id, user)
    if parent.project_id != job.project_id:
        raise HTTPException(status_code=404, detail="Parent research run not found")
    checkpoint = _checkpoint_for_job(job)
    context = checkpoint.get("follow_up_context", {})
    continuation = checkpoint.get("retrieval_continuation")
    if isinstance(continuation, dict):
        return {
            "status": "retrieval_continuation",
            "parent": {
                "job_id": parent.id,
                "question": parent.question,
                "report_id": parent.report.id if parent.report else None,
                "report_status": parent.report.status if parent.report else None,
            },
            "reuse_method": "source_snapshot_copy_and_deferred_fetch_retry",
            "reuse_boundary": continuation.get("evidence_copy_boundary"),
            "claims": [],
        }
    requested_ids = context.get("reused_claim_ids", []) if isinstance(context, dict) else []
    if not isinstance(requested_ids, list):
        requested_ids = []
    rows = (
        list(
            db.execute(
                select(Claim, Source, Passage)
                .join(Source, Claim.source_id == Source.id)
                .join(Passage, Claim.passage_id == Passage.id)
                .where(Claim.job_id == parent.id, Claim.id.in_(requested_ids))
            )
        )
        if requested_ids
        else []
    )
    by_id = {
        claim.id: {
            "claim": _claim_out(claim),
            "source": {
                "id": source.id,
                "title": source.title,
                "retrieval_status": source.retrieval_status,
            },
            "passage": {"id": passage.id, "locator": passage.locator},
        }
        for claim, source, passage in rows
    }
    claims = [by_id[claim_id] for claim_id in requested_ids if claim_id in by_id]
    return {
        "status": ("context_attached" if claims else "context_no_relevant_claims")
        if context
        else "parent_linked_without_saved_context",
        "parent": {
            "job_id": parent.id,
            "question": parent.question,
            "report_id": parent.report.id if parent.report else None,
            "report_status": parent.report.status if parent.report else None,
        },
        "reuse_method": context.get("reuse_method") if isinstance(context, dict) else None,
        "reuse_boundary": context.get("reuse_boundary") if isinstance(context, dict) else None,
        "claims": claims,
    }


@router.post("/research-jobs/{job_id}/advance")
def advance_job(
    job_id: str,
    payload: AdvanceRequest,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    job = _owned_job(db, job_id, user)
    previous_event = db.scalar(
        select(JobEvent).where(
            JobEvent.job_id == job.id, JobEvent.operation_key == payload.operation_key
        )
    )
    if previous_event:
        return _job_out(job)
    if job.status in {
        "completed",
        "completed_with_limitations",
        "canceled",
        "terminal_failure",
        "budget_exhausted",
    }:
        return _job_out(job)
    if _mark_retry_limit_if_exhausted(db, job):
        return _job_out(job)
    now = utcnow()
    lease_token = str(uuid4())
    acquired = acquire_job_lease(
        db,
        job_id=job.id,
        expected_version=job.version,
        lease_token=lease_token,
        now=now,
        lease_seconds=180,
    )
    if not acquired:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another request is advancing this job; refresh before continuing",
        )
    db.commit()
    db.refresh(job)
    snapshot = job_snapshot(job)
    stage_started = time.monotonic()

    try:
        stage_result = execute_stage(db, snapshot)
        db.flush()
    except WorkflowError as exc:
        db.rollback()
        job = db.get(ResearchJob, job_id)
        if job is None or job.lease_owner != lease_token:
            raise HTTPException(
                status_code=409, detail="Job lease expired; refresh and retry"
            ) from exc
        job.attempt += 1
        job.status = "retryable_failure" if exc.retryable else "terminal_failure"
        job.error_class = exc.code
        job.error_message = str(exc)[:500]
        job.lease_owner = None
        job.lease_expires_at = None
        job.version += 1
        job.updated_at = utcnow()
        append_event(
            db,
            job.id,
            event_type="step_failed",
            stage=snapshot["current_stage"],
            message=str(exc),
            operation_key=payload.operation_key,
            data={
                "error_class": exc.code,
                "provider_error_class": exc.provider_error_class,
                "retryable": exc.retryable,
                "elapsed_seconds": round(max(0.0, time.monotonic() - stage_started), 3),
            },
        )
        db.commit()
        db.refresh(job)
        return _job_out(job)
    except Exception as exc:
        logger.error(
            "Research stage failed",
            extra={
                "job_id": job_id,
                "stage": snapshot["current_stage"],
                "error_class": type(exc).__name__,
            },
        )
        db.rollback()
        job = db.get(ResearchJob, job_id)
        if job is None or job.lease_owner != lease_token:
            raise HTTPException(
                status_code=409, detail="Job lease expired; refresh and retry"
            ) from exc
        job.attempt += 1
        job.status = "retryable_failure"
        job.error_class = "unexpected_stage_error"
        job.error_message = "The step failed unexpectedly. Retry it or contact an administrator."
        job.lease_owner = None
        job.lease_expires_at = None
        job.version += 1
        job.updated_at = utcnow()
        failure_data: dict[str, Any] = {
            "error_class": job.error_class,
            "exception_type": type(exc).__name__[:80],
            "retryable": True,
            "elapsed_seconds": round(max(0.0, time.monotonic() - stage_started), 3),
        }
        if isinstance(exc, ValidationError):
            title = getattr(exc, "title", None)
            if isinstance(title, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", title):
                failure_data["validation_model"] = title
            validation_errors = exc.errors(
                include_input=False, include_url=False, include_context=False
            )
            failure_data["validation_error_count"] = min(len(validation_errors), 1000)
            failure_data["validation_error_types"] = list(
                dict.fromkeys(
                    error["type"][:80]
                    for error in validation_errors
                    if isinstance(error.get("type"), str)
                    and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,79}", error["type"])
                )
            )[:8]
        append_event(
            db,
            job.id,
            event_type="step_failed",
            stage=snapshot["current_stage"],
            message=job.error_message,
            operation_key=payload.operation_key,
            data=failure_data,
        )
        db.commit()
        db.refresh(job)
        return _job_out(job)

    job = db.get(ResearchJob, job_id)
    if job is None or job.lease_owner != lease_token:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Job lease expired; refresh before saving this step"
        )
    persist_result(db, job, stage_result)
    if job.cancel_requested:
        job.status = "canceled"
        job.current_stage = stage_result.next_stage
        stage_result.message += " Cancellation was requested; saved this bounded step and stopped."
    job.lease_owner = None
    job.lease_expires_at = None
    job.version += 1
    job.updated_at = utcnow()
    append_event(
        db,
        job.id,
        event_type="step_completed",
        stage=snapshot["current_stage"],
        message=stage_result.message,
        operation_key=payload.operation_key,
        data=stage_result.event_data.model_dump(mode="json", exclude_none=True),
    )
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.post("/research-jobs/{job_id}/resume")
def resume_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    job = _owned_job(db, job_id, user)
    if _mark_retry_limit_if_exhausted(db, job):
        return _job_out(job)
    if job.status not in {"retryable_failure", "paused", "active", "queued"}:
        return _job_out(job)
    now = utcnow()
    if (
        job.lease_expires_at
        and job.lease_expires_at.replace(tzinfo=job.lease_expires_at.tzinfo or now.tzinfo) > now
    ):
        raise HTTPException(status_code=409, detail="A live worker lease is still active")
    job.status = "queued"
    job.error_class = None
    job.error_message = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.version += 1
    job.updated_at = now
    append_event(
        db,
        job.id,
        event_type="job_resumed",
        stage=job.current_stage,
        message="Research job queued to resume.",
    )
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.post("/research-jobs/{job_id}/retry-deferred")
def retry_deferred_retrieval(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Create an immutable child run for due deferred source requests."""
    parent = _owned_job(db, job_id, user)
    if parent.status not in {"completed", "completed_with_limitations"}:
        raise HTTPException(
            status_code=409,
            detail="Deferred retrieval can be continued only after its report is saved.",
        )
    now = utcnow()
    lease_expiry = parent.lease_expires_at
    if lease_expiry and lease_expiry.tzinfo is None:
        lease_expiry = lease_expiry.replace(tzinfo=now.tzinfo)
    if lease_expiry and lease_expiry > now:
        raise HTTPException(status_code=409, detail="A live worker lease is still active.")

    existing_sources = list(
        db.scalars(select(Source).where(Source.job_id == parent.id).order_by(Source.created_at))
    )
    due: list[tuple[Source, str, dict[str, Any]]] = []
    future_due_times: list[datetime] = []
    scheduled_child_ids: set[str] = set()
    for source in existing_sources:
        metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
        retrieval = metadata.get("retrieval") if isinstance(metadata.get("retrieval"), dict) else {}
        retries = retrieval.get("deferred_retries")
        if not isinstance(retries, dict):
            continue
        for kind in ("html", "pdf", "jats"):
            retry = retries.get(kind)
            if not isinstance(retry, dict):
                continue
            if retry.get("status") == "scheduled":
                child_id = retry.get("continuation_job_id")
                if isinstance(child_id, str):
                    scheduled_child_ids.add(child_id)
                continue
            if retry.get("status") != "pending":
                continue
            due_at_text = retry.get("due_at")
            if not isinstance(due_at_text, str):
                raise HTTPException(
                    status_code=409,
                    detail="A deferred request has no valid persisted retry time.",
                )
            try:
                due_at = datetime.fromisoformat(due_at_text.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=409,
                    detail="A deferred request has an invalid persisted retry time.",
                ) from None
            if due_at.tzinfo is None:
                raise HTTPException(
                    status_code=409,
                    detail="A deferred request has a timezone-ambiguous retry time.",
                )
            if due_at > now:
                future_due_times.append(due_at)
            else:
                due.append((source, kind, dict(retry)))

    scheduled_children = [db.get(ResearchJob, child_id) for child_id in sorted(scheduled_child_ids)]
    scheduled_children = [child for child in scheduled_children if child is not None]
    active_child = next(
        (
            child
            for child in scheduled_children
            if child.status
            not in {
                "completed",
                "completed_with_limitations",
                "canceled",
                "terminal_failure",
                "budget_exhausted",
            }
        ),
        None,
    )
    if active_child is not None:
        return {
            "job": _job_out(active_child),
            "queued_retry_count": len(
                _checkpoint_for_job(active_child)
                .get("deferred_retrieval_retry", {})
                .get("sources", [])
            ),
            "idempotent_replay": True,
        }
    if not due:
        if future_due_times:
            earliest = min(future_due_times)
            retry_after = max(0, int((earliest - now).total_seconds()))
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "deferred_retrieval_not_due",
                    "retry_after_seconds": retry_after,
                    "due_at": earliest.isoformat(),
                },
            )
        if scheduled_children:
            latest_child = max(scheduled_children, key=lambda child: child.created_at)
            return {
                "job": _job_out(latest_child),
                "queued_retry_count": len(
                    _checkpoint_for_job(latest_child)
                    .get("retrieval_continuation", {})
                    .get("retries", [])
                ),
                "idempotent_replay": True,
            }
        raise HTTPException(
            status_code=409,
            detail="No due deferred scholarly requests are available.",
        )

    due.sort(key=lambda item: (item[0].id, item[1]))
    batch_fingerprint = sha256(
        json.dumps(
            [(source.id, kind, retry["due_at"]) for source, kind, retry in due],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:32]
    idempotency_key = f"deferred-continuation-{parent.id[:12]}-{batch_fingerprint}"
    existing_child = db.scalar(
        select(ResearchJob).where(
            ResearchJob.project_id == parent.project_id,
            ResearchJob.idempotency_key == idempotency_key,
        )
    )
    if existing_child is not None:
        return {
            "job": _job_out(existing_child),
            "queued_retry_count": len(
                _checkpoint_for_job(existing_child)
                .get("retrieval_continuation", {})
                .get("retries", [])
            ),
            "idempotent_replay": True,
        }

    inherited_checkpoint = versioned_checkpoint(dict(parent.checkpoint_json))
    inherited_checkpoint.pop("citation_map", None)
    inherited_checkpoint.pop("citation_audit", None)
    inherited_checkpoint.pop("follow_up_context", None)
    inherited_checkpoint.pop("deferred_retrieval_retry", None)
    prior_continuation = inherited_checkpoint.get("retrieval_continuation")
    budget_ceiling = (
        prior_continuation.get("budget_ceiling_usd")
        if isinstance(prior_continuation, dict)
        else parent.budget_ceiling_usd
    )
    if (
        isinstance(budget_ceiling, bool)
        or not isinstance(budget_ceiling, (int, float))
        or budget_ceiling < parent.cost_spent_estimate_usd
    ):
        budget_ceiling = parent.cost_spent_estimate_usd
    budget_ceiling_inr = (
        prior_continuation.get("budget_ceiling_inr")
        if isinstance(prior_continuation, dict)
        else parent.budget_ceiling_inr
    )
    if (
        isinstance(budget_ceiling_inr, bool)
        or not isinstance(budget_ceiling_inr, (int, float))
        or budget_ceiling_inr < parent.cost_spent_estimate_inr
    ):
        budget_ceiling_inr = parent.cost_spent_estimate_inr
    child = ResearchJob(
        id=str(uuid4()),
        project_id=parent.project_id,
        parent_job_id=parent.id,
        conversation_id=parent.conversation_id,
        question=parent.question,
        scope_json=versioned_scope(parent.scope_json or {}),
        depth=parent.depth,
        model_provider=parent.model_provider or settings.llm_provider,
        model_name=parent.model_name,
        budget_ceiling_usd=float(budget_ceiling),
        budget_ceiling_inr=float(budget_ceiling_inr),
        cost_spent_estimate_usd=parent.cost_spent_estimate_usd,
        cost_reserved_usd=0.0,
        cost_spent_estimate_inr=parent.cost_spent_estimate_inr,
        cost_reserved_inr=0.0,
        model_calls_reserved=parent.model_calls_reserved,
        prompt_characters_reserved=parent.prompt_characters_reserved,
        prompt_token_budget_reserved=parent.prompt_token_budget_reserved,
        output_token_budget_reserved=parent.output_token_budget_reserved,
        status="queued",
        current_stage="extraction",
        checkpoint_json=versioned_checkpoint(inherited_checkpoint, strict=True),
        idempotency_key=idempotency_key,
    )
    db.add(child)
    db.flush()

    source_ids = clone_job_evidence(db, parent, child)
    retry_sources: dict[str, set[str]] = {}
    retry_lineage: list[dict[str, str]] = []
    for source, kind, _retry in due:
        child_source_id = source_ids.get(source.id)
        if child_source_id is None:
            raise HTTPException(status_code=409, detail="Deferred source snapshot is unavailable.")
        retry_sources.setdefault(child_source_id, set()).add(kind)
        retry_lineage.append(
            {
                "parent_source_id": source.id,
                "source_id": child_source_id,
                "kind": kind,
            }
        )
        metadata = deepcopy(source.metadata_json or {})
        retrieval = metadata.get("retrieval")
        retries = retrieval.get("deferred_retries") if isinstance(retrieval, dict) else None
        if not isinstance(retries, dict) or not isinstance(retries.get(kind), dict):
            raise HTTPException(
                status_code=409, detail="Deferred source state changed; refresh and retry."
            )
        retry_state = dict(retries[kind])
        retry_state.update(
            status="scheduled",
            continuation_job_id=child.id,
            scheduled_at=now.isoformat(),
        )
        retries[kind] = retry_state
        retrieval["deferred_retries"] = retries
        metadata["retrieval"] = retrieval
        source.metadata_json = metadata

    checkpoint = _checkpoint_for_job(child)
    checkpoint["retrieval_continuation"] = {
        "schema_version": 1,
        "parent_job_id": parent.id,
        "budget_ceiling_usd": float(budget_ceiling),
        "budget_ceiling_inr": float(budget_ceiling_inr),
        "retries": retry_lineage,
        "evidence_copy_boundary": (
            "Previously saved source metadata, immutable snapshots, passages, and claims are copied with source/document lineage IDs. "
            "Only the listed due URLs are fetched again; the parent report remains an immutable prior version."
        ),
    }
    checkpoint["deferred_retrieval_retry"] = {
        "sources": [
            {"source_id": source_id, "kinds": sorted(kinds)}
            for source_id, kinds in sorted(retry_sources.items())
        ]
    }
    child.checkpoint_json = versioned_checkpoint(checkpoint, strict=True)
    db.add(
        Message(
            conversation_id=parent.conversation_id,
            role="user",
            content=(
                f"Continue the saved research run by retrying {len(retry_lineage)} due, "
                "deferred scholarly request(s)."
            ),
            related_job_id=child.id,
        )
    )
    append_event(
        db,
        child.id,
        event_type="job_created",
        stage="extraction",
        message="Evidence-preserving retrieval continuation queued.",
        data={"parent_job_id": parent.id, "deferred_request_count": len(retry_lineage)},
    )
    append_event(
        db,
        parent.id,
        event_type="deferred_retrieval_continued",
        stage="complete",
        message="A linked continuation run was queued for due deferred scholarly requests.",
        operation_key=idempotency_key,
        data={"continuation_job_id": child.id, "deferred_request_count": len(retry_lineage)},
    )
    parent.version += 1
    parent.updated_at = now
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_child = db.scalar(
            select(ResearchJob).where(
                ResearchJob.project_id == parent.project_id,
                ResearchJob.idempotency_key == idempotency_key,
            )
        )
        if existing_child is None:
            raise
        return {
            "job": _job_out(existing_child),
            "queued_retry_count": len(retry_lineage),
            "idempotent_replay": True,
        }
    db.refresh(child)
    return {
        "job": _job_out(child),
        "queued_retry_count": len(retry_lineage),
        "idempotent_replay": False,
    }


@router.post("/research-jobs/{job_id}/pause")
def pause_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    job = _owned_job(db, job_id, user)
    if job.status in {"completed", "completed_with_limitations", "canceled", "terminal_failure"}:
        return _job_out(job)
    now = utcnow()
    if (
        job.lease_expires_at
        and job.lease_expires_at.replace(tzinfo=job.lease_expires_at.tzinfo or now.tzinfo) > now
    ):
        raise HTTPException(
            status_code=409, detail="A bounded step is still running; pause again after it saves."
        )
    job.status = "paused"
    job.lease_owner = None
    job.lease_expires_at = None
    job.version += 1
    job.updated_at = now
    append_event(
        db,
        job.id,
        event_type="job_paused",
        stage=job.current_stage,
        message="Research job paused at a saved checkpoint.",
    )
    db.commit()
    db.refresh(job)
    return _job_out(job)


@router.post("/research-jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    job = _owned_job(db, job_id, user)
    if job.status not in {
        "completed",
        "completed_with_limitations",
        "canceled",
        "terminal_failure",
    }:
        job.cancel_requested = True
        if not job.lease_owner:
            job.status = "canceled"
        job.version += 1
        job.updated_at = utcnow()
        append_event(
            db,
            job.id,
            event_type="cancel_requested",
            stage=job.current_stage,
            message="Cancellation requested.",
        )
        db.commit()
        db.refresh(job)
    return _job_out(job)


@router.get("/research-jobs/{job_id}/plan")
def get_job_plan(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    job = _owned_job(db, job_id, user)
    return _checkpoint_for_job(job).get("plan", {"status": "not_created"})


@router.get(
    "/research-jobs/{job_id}/events",
    response_model=EventPageOut,
    response_model_exclude_unset=True,
)
def get_job_events(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    query = select(JobEvent).where(JobEvent.job_id == job_id)
    total = _query_total(db, query)
    events, has_more = _bounded_page(
        db,
        query.order_by(JobEvent.created_at, JobEvent.id),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            {
                "schema_version": 1,
                "id": e.id,
                "event_type": e.event_type,
                "stage": e.stage,
                "message": e.message,
                "data": versioned_event_data(e.data_json),
                "created_at": e.created_at,
            }
            for e in events
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.get("/research-jobs/{job_id}/sources")
def get_job_sources(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    query = select(Source).where(Source.job_id == job_id)
    total = _query_total(db, query)
    sources, has_more = _bounded_page(
        db,
        query.order_by(Source.created_at, Source.id),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_source_out(source) for source in sources],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.post("/evidence/search")
def search_evidence(
    payload: EvidenceSearchRequest,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Search a bounded set of the caller's saved source metadata and passages."""
    terms = list(
        dict.fromkeys(re.findall(r"[\w-]{2,}", payload.query.casefold(), flags=re.UNICODE))
    )[:8]
    if not terms:
        raise HTTPException(status_code=422, detail="Search query must contain searchable terms")

    source_matches = []
    passage_matches = []
    for term in terms:
        pattern = f"%{term}%"
        source_matches.extend(
            [
                Source.title.ilike(pattern),
                Source.publisher.ilike(pattern),
                Source.doi.ilike(pattern),
            ]
        )
        passage_matches.append(Passage.content.ilike(pattern))

    matching_source_ids = list(
        db.scalars(
            select(Source.id)
            .join(ResearchJob, ResearchJob.id == Source.job_id)
            .join(Project, Project.id == ResearchJob.project_id)
            .outerjoin(Passage, Passage.source_id == Source.id)
            .where(
                Project.owner_id == user.id,
                or_(*source_matches, *passage_matches),
            )
            .group_by(Source.id, ResearchJob.updated_at, Source.created_at)
            .order_by(ResearchJob.updated_at.desc(), Source.created_at.desc(), Source.id)
            .limit(payload.limit)
        )
    )
    items = []
    for source_id in matching_source_ids:
        source = _owned_source(db, source_id, user)
        passages = list(
            db.scalars(
                select(Passage)
                .where(
                    Passage.source_id == source.id,
                    or_(*passage_matches),
                )
                .order_by(Passage.ordinal, Passage.id)
                .limit(2)
            )
        )
        items.append(
            {
                "source": _source_out(source),
                "passages": [_passage_out(passage) for passage in passages],
            }
        )
    return {"items": items, "limit": payload.limit}


@router.get("/research-jobs/{job_id}/candidates")
def get_job_candidates(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    query = select(DiscoveryCandidate).where(DiscoveryCandidate.job_id == job_id)
    total = _query_total(db, query)
    candidates, has_more = _bounded_page(
        db,
        query.order_by(
            DiscoveryCandidate.ranking_order.nullslast(),
            DiscoveryCandidate.relevance_score.desc().nullslast(),
            DiscoveryCandidate.discovered_at,
            DiscoveryCandidate.id,
        ),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_candidate_out(candidate) for candidate in candidates],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.get("/research-jobs/{job_id}/claims")
def get_job_claims(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    query = select(Claim).where(Claim.job_id == job_id)
    total = _query_total(db, query)
    claims, has_more = _bounded_page(
        db,
        query.order_by(Claim.created_at, Claim.id),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_claim_out(claim) for claim in claims],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
    }


@router.get("/research-jobs/{job_id}/hypotheses")
def get_job_hypotheses(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    query = select(Hypothesis).where(Hypothesis.job_id == job_id)
    total = _query_total(db, query)
    items, has_more = _bounded_page(
        db,
        query.order_by(
            Hypothesis.created_at,
            Hypothesis.comparison_group_id,
            Hypothesis.side,
            Hypothesis.id,
        ),
        limit=limit,
        offset=offset,
    )
    comparison_event = db.scalar(
        select(JobEvent)
        .where(
            JobEvent.job_id == job_id,
            JobEvent.stage == "comparison",
            JobEvent.event_type == "step_completed",
        )
        .order_by(JobEvent.created_at.desc())
        .limit(1)
    )
    status_value = (
        "model_assessed_not_independently_verified"
        if total
        else (
            comparison_event.data_json.get("status", "not_assessed")
            if comparison_event
            else "not_assessed"
        )
    )
    return {
        "items": [_hypothesis_out(item, db) for item in items],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "status": status_value,
        "message": (
            "Competing explanations are provisional model-generated interpretations linked to source claims and passages."
            if items
            else (
                "The comparison model ran but returned no evidence-linked competing hypothesis pair."
                if status_value == "no_supported_relationships_or_hypotheses"
                or status_value == "model_assessed_not_independently_verified"
                else "No evidence-linked competing hypotheses were produced; comparison may be unassessed or unavailable."
            )
        ),
    }


@router.get("/research-jobs/{job_id}/relationships")
def get_job_relationships(
    job_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    query = select(EvidenceRelationship).where(EvidenceRelationship.job_id == job_id)
    total = _query_total(db, query)
    items, has_more = _bounded_page(
        db,
        query.order_by(EvidenceRelationship.created_at, EvidenceRelationship.id),
        limit=limit,
        offset=offset,
    )
    comparison_event = db.scalar(
        select(JobEvent)
        .where(
            JobEvent.job_id == job_id,
            JobEvent.stage == "comparison",
            JobEvent.event_type == "step_completed",
        )
        .order_by(JobEvent.created_at.desc())
        .limit(1)
    )
    status_value = (
        "model_assessed_not_independently_verified"
        if total
        else (
            comparison_event.data_json.get("status", "not_assessed")
            if comparison_event
            else "not_assessed"
        )
    )
    return {
        "items": [_relationship_out(item, db) for item in items],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "status": status_value,
    }


@router.get("/research-jobs/{job_id}/report")
def get_job_report(
    job_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_job(db, job_id, user)
    report = db.scalar(select(ResearchReport).where(ResearchReport.job_id == job_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report is not available yet")
    return _report_out(report)


@router.get("/sources/{source_id}")
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    source = _owned_source(db, source_id, user)
    passages = list(
        db.scalars(select(Passage).where(Passage.source_id == source.id).order_by(Passage.ordinal))
    )
    return {**_source_out(source), "passages": [_passage_out(passage) for passage in passages]}


@router.get("/sources/{source_id}/provenance")
def get_source_provenance(
    source_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return bounded source and passage locator metadata without passage bodies."""
    source = _owned_source(db, source_id, user)
    passage_columns = (
        Passage.id,
        Passage.document_id,
        Passage.locator,
        Passage.content_hash,
        Passage.access_level,
        Passage.truncated,
    )
    passages = list(
        db.execute(
            select(*passage_columns)
            .where(Passage.source_id == source.id)
            .order_by(Passage.ordinal, Passage.id)
            .limit(51)
        ).mappings()
    )
    passage_count = (
        db.scalar(select(func.count(Passage.id)).where(Passage.source_id == source.id)) or 0
    )
    return {
        "source": _source_out(source),
        "passages": [dict(passage) for passage in passages[:50]],
        "total_passages": passage_count,
        "has_more": passage_count > 50,
    }


@router.get("/passages/{passage_id}")
def get_passage(
    passage_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    return _passage_out(_owned_passage(db, passage_id, user))


@router.get("/claims/{claim_id}/evidence")
def get_claim_evidence(
    claim_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    claim = _owned_claim(db, claim_id, user)
    source = _owned_source(db, claim.source_id, user)
    passage = _owned_passage(db, claim.passage_id, user)
    methodology_appraisal = claim_appraisal_for_api(claim.appraisal_json)["methodology_appraisal"]
    linked_passage_ids = methodology_appraisal.get("passage_ids", [])
    methodology_passages = []
    if linked_passage_ids:
        linked = db.scalars(
            select(Passage)
            .join(Source, Passage.source_id == Source.id)
            .where(
                Passage.id.in_(linked_passage_ids),
                Passage.source_id == source.id,
                Source.job_id == claim.job_id,
            )
            .order_by(Passage.ordinal, Passage.id)
        )
        methodology_passages = [_passage_out(item) for item in linked]
    return {
        "claim": _claim_out(claim),
        "source": _source_out(source),
        "passage": _passage_out(passage),
        # Only return locators from this claim's own source and research job.
        # Legacy or corrupt cross-source appraisal IDs remain unresolvable.
        "methodology_passages": methodology_passages,
    }


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    report = db.scalar(
        select(ResearchReport)
        .join(ResearchJob, ResearchReport.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .where(
            ResearchReport.id == report_id,
            Project.owner_id == user.id,
        )
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_out(report)


@router.get("/reports/{report_id}/inspection", response_model=ReportInspectionOut)
def inspect_report(
    report_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Load one report and its citation evidence, including for archived owned projects."""
    report = db.scalar(
        select(ResearchReport)
        .join(ResearchJob, ResearchReport.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .options(
            selectinload(ResearchReport.job).options(
                selectinload(ResearchJob.project),
                selectinload(ResearchJob.sources).selectinload(Source.passages),
                selectinload(ResearchJob.claims).selectinload(Claim.passage),
            )
        )
        .where(ResearchReport.id == report_id, Project.owner_id == user.id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    job = report.job
    sources = sorted(job.sources, key=lambda source: (source.created_at, source.id))
    claims = sorted(job.claims, key=lambda claim: (claim.created_at, claim.id))
    return {
        "report": _report_out(report),
        "job": _job_out(job),
        "project": _project_out(job.project),
        "sources": [
            {
                **_source_out(source),
                "passages": [
                    _passage_out(passage)
                    for passage in sorted(
                        source.passages, key=lambda passage: (passage.ordinal, passage.id)
                    )
                ],
            }
            for source in sources
        ],
        "claims": [_claim_out(claim) for claim in claims],
    }


@router.get("/reports", response_model=ReportHistoryOut)
def list_reports(
    project_id: str | None = None,
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=MAX_PAGE_OFFSET),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    """List this user's immutable per-run reports in stable, bounded pages."""
    if project_id is not None:
        _owned_project(db, project_id, user, include_archived=include_archived)
    query = (
        select(ResearchReport)
        .join(ResearchJob, ResearchReport.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .options(selectinload(ResearchReport.job).selectinload(ResearchJob.project))
        .where(Project.owner_id == user.id)
    )
    if project_id is not None:
        query = query.where(Project.id == project_id)
    if not include_archived:
        query = query.where(Project.archived_at.is_(None))
    total = _query_total(db, query)
    reports, has_more = _bounded_page(
        db,
        query.order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc()),
        limit=limit,
        offset=offset,
    )
    return {
        "items": [
            {
                **_report_out(report),
                "project_id": report.job.project.id,
                "project_title": report.job.project.title,
                "project_archived_at": report.job.project.archived_at,
                "question": report.job.question,
            }
            for report in reports
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "version_semantics": "Each immutable research run has one report; version is its report-schema version.",
    }


@router.get("/reports/{report_id}/export")
def export_report(
    report_id: str,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> Response:
    report = db.scalar(
        select(ResearchReport)
        .join(ResearchJob, ResearchReport.job_id == ResearchJob.id)
        .join(Project, ResearchJob.project_id == Project.id)
        .where(
            ResearchReport.id == report_id,
            Project.owner_id == user.id,
        )
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if format == "json":
        return Response(
            content=__import__("json").dumps(
                _report_out_for_export(report), default=str, ensure_ascii=False
            ),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="veda-report-{report.id}.json"'},
        )
    return Response(
        content=_report_out_for_export(report)["body_markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="veda-report-{report.id}.md"'},
    )


@router.get("/projects/{project_id}/usage")
def project_usage(
    project_id: str,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> dict[str, Any]:
    _owned_project(db, project_id, user)
    spent = db.scalar(
        select(func.coalesce(func.sum(ResearchJob.cost_spent_estimate_usd), 0.0)).where(
            ResearchJob.project_id == project_id
        )
    )
    spent_inr = db.scalar(
        select(func.coalesce(func.sum(ResearchJob.cost_spent_estimate_inr), 0.0)).where(
            ResearchJob.project_id == project_id
        )
    )
    calls = db.scalar(
        select(func.count(UsageEntry.id))
        .join(ResearchJob, UsageEntry.job_id == ResearchJob.id)
        .where(ResearchJob.project_id == project_id)
    )
    unknown_cost_calls = db.scalar(
        select(func.count(UsageEntry.id))
        .join(ResearchJob, UsageEntry.job_id == ResearchJob.id)
        .where(
            ResearchJob.project_id == project_id,
            UsageEntry.reported_cost_usd.is_(None),
            UsageEntry.estimated_cost_usd.is_(None),
            UsageEntry.reported_cost_inr.is_(None),
            UsageEntry.estimated_cost_inr.is_(None),
        )
    )
    return {
        "project_id": project_id,
        "estimated_cost_usd": float(spent or 0.0),
        "estimated_cost_inr": float(spent_inr or 0.0),
        "model_calls": int(calls or 0),
        "unknown_cost_calls": int(unknown_cost_calls or 0),
        "cost_estimate_complete": int(unknown_cost_calls or 0) == 0,
        "cost_note": "Known reported costs and estimates are shown; calls missing both cost fields are counted as unknown. No model calls are configured by default.",
    }
