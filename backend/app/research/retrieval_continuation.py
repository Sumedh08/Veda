"""Create immutable, evidence-preserving child runs for deferred retrieval."""

from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    DiscoveryCandidate,
    Passage,
    ResearchJob,
    RetrievedDocument,
    Source,
)
from app.research.candidate_metadata_retention import normalize_candidate_abstract_snapshot
from app.research.document_identity import document_identity, passage_identity


def clone_job_evidence(
    db: Session,
    parent: ResearchJob,
    child: ResearchJob,
) -> dict[str, str]:
    """Copy a completed run's evidence graph into a linked continuation run.

    The original report and evidence stay immutable. New IDs are recomputed for
    source-associated snapshots, and the immediate parent IDs are retained as
    provenance metadata. Only the child run performs deferred network requests.
    """
    parent_sources = list(
        db.scalars(select(Source).where(Source.job_id == parent.id).order_by(Source.created_at))
    )
    source_ids: dict[str, str] = {}
    for original in parent_sources:
        source_id = str(uuid4())
        source_ids[original.id] = source_id
        metadata = deepcopy(original.metadata_json or {})
        metadata["retrieval_continuation_parent_source_id"] = original.id
        abstract_excerpt, abstract_retention_status = normalize_candidate_abstract_snapshot(
            abstract_excerpt=original.abstract_excerpt,
            retention_status=metadata.get("abstract_text_retention_status"),
        )
        if original.abstract_excerpt or "abstract_text_retention_status" in metadata:
            metadata["abstract_text_available_at_discovery"] = bool(original.abstract_excerpt) or (
                metadata.get("abstract_text_available_at_discovery") is True
            )
            metadata["abstract_text_retention_status"] = abstract_retention_status
        db.add(
            Source(
                id=source_id,
                job_id=child.id,
                external_id=original.external_id,
                title=original.title,
                doi=original.doi,
                url=original.url,
                authors_json=deepcopy(original.authors_json or []),
                published_year=original.published_year,
                publisher=original.publisher,
                source_type=original.source_type,
                retrieval_status=(
                    "metadata_only"
                    if original.retrieval_status == "abstract_only"
                    else original.retrieval_status
                ),
                abstract_excerpt=abstract_excerpt,
                discovery_query=original.discovery_query,
                appraisal_json=deepcopy(original.appraisal_json or {}),
                metadata_json=metadata,
                created_at=original.created_at,
            )
        )
    db.flush()

    parent_source_ids = list(source_ids)
    parent_documents = (
        list(
            db.scalars(
                select(RetrievedDocument)
                .where(RetrievedDocument.source_id.in_(parent_source_ids))
                .order_by(RetrievedDocument.retrieved_at, RetrievedDocument.id)
            )
        )
        if parent_source_ids
        else []
    )
    document_ids: dict[str, str] = {}
    for original in parent_documents:
        if original.access_class == "abstract_only":
            continue
        source_id = source_ids[original.source_id]
        document_id, identity_key = document_identity(
            source_id=source_id,
            source_version=original.source_version,
            document_sha256=original.document_sha256,
            media_type=original.media_type,
            access_class=original.access_class,
        )
        document_ids[original.id] = document_id
        metadata = deepcopy(original.metadata_json or {})
        metadata["retrieval_continuation_parent_document_id"] = original.id
        db.add(
            RetrievedDocument(
                id=document_id,
                source_id=source_id,
                identity_key=identity_key,
                source_version=original.source_version,
                document_sha256=original.document_sha256,
                retrieved_at=original.retrieved_at,
                locator=original.locator,
                media_type=original.media_type,
                access_class=original.access_class,
                hash_scope=original.hash_scope,
                schema_version=original.schema_version,
                metadata_json=metadata,
            )
        )
    db.flush()

    parent_passages = (
        list(
            db.scalars(
                select(Passage)
                .where(Passage.source_id.in_(parent_source_ids))
                .order_by(Passage.created_at, Passage.id)
            )
        )
        if parent_source_ids
        else []
    )
    passage_ids: dict[str, str] = {}
    excluded_abstract_passage_ids: set[str] = set()
    for original in parent_passages:
        if original.access_level in {"abstract_only", "abstract_excerpt"}:
            excluded_abstract_passage_ids.add(original.id)
            continue
        source_id = source_ids[original.source_id]
        document_id = document_ids.get(original.document_id)
        if document_id is None:
            raise ValueError("Continuation source evidence has a missing document snapshot.")
        passage_id, identity_key = passage_identity(
            source_id=source_id,
            document_id=document_id,
            locator=original.locator,
            content_sha256=original.content_hash,
        )
        passage_ids[original.id] = passage_id
        db.add(
            Passage(
                id=passage_id,
                source_id=source_id,
                document_id=document_id,
                identity_key=identity_key,
                identity_version=original.identity_version,
                ordinal=original.ordinal,
                locator=original.locator,
                content=original.content,
                content_hash=original.content_hash,
                access_level=original.access_level,
                truncated=original.truncated,
                created_at=original.created_at,
            )
        )
    db.flush()

    parent_claims = list(
        db.scalars(
            select(Claim).where(Claim.job_id == parent.id).order_by(Claim.created_at, Claim.id)
        )
    )
    for original in parent_claims:
        if original.passage_id in excluded_abstract_passage_ids:
            continue
        passage_id = passage_ids.get(original.passage_id)
        source_id = source_ids.get(original.source_id)
        if passage_id is None or source_id is None:
            raise ValueError("Continuation claim has no source-associated passage.")
        db.add(
            Claim(
                id=str(uuid4()),
                job_id=child.id,
                source_id=source_id,
                passage_id=passage_id,
                text=original.text,
                span_start=original.span_start,
                span_end=original.span_end,
                atomization_status=original.atomization_status,
                atomization_version=original.atomization_version,
                claim_type=original.claim_type,
                evidence_status=original.evidence_status,
                appraisal_json=deepcopy(original.appraisal_json or {}),
                created_at=original.created_at,
            )
        )

    candidates = list(
        db.scalars(
            select(DiscoveryCandidate)
            .where(DiscoveryCandidate.job_id == parent.id)
            .order_by(DiscoveryCandidate.discovered_at, DiscoveryCandidate.id)
        )
    )
    for original in candidates:
        abstract_excerpt, abstract_retention_status = normalize_candidate_abstract_snapshot(
            abstract_excerpt=original.abstract_excerpt,
            retention_status=original.abstract_excerpt_retention_status,
        )
        db.add(
            DiscoveryCandidate(
                job_id=child.id,
                candidate_key=original.candidate_key,
                provider=original.provider,
                provider_record_id=original.provider_record_id,
                canonical_identity=original.canonical_identity,
                title=original.title,
                abstract_excerpt=abstract_excerpt,
                abstract_excerpt_retention_status=abstract_retention_status,
                doi=original.doi,
                url=original.url,
                published_year=original.published_year,
                query_text=original.query_text,
                ranking_order=original.ranking_order,
                relevance_score=original.relevance_score,
                relevance_json=deepcopy(original.relevance_json),
                disposition=original.disposition,
                reason_code=original.reason_code,
                canonical_source_id=source_ids.get(original.canonical_source_id),
                discovered_at=original.discovered_at,
            )
        )
    db.flush()
    return source_ids
