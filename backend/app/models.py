from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    domain: Mapped[str] = mapped_column(
        String(120), default="AI adoption economics", nullable=False
    )
    settings_json: Mapped[dict] = mapped_column("settings", JSON, default=dict, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    jobs: Mapped[list["ResearchJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    default_depth: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    default_budget_ceiling_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class VerifiedOrganizationIdentity(Base):
    """Public ROR identity facts reusable across research runs, never topic relevance."""

    __tablename__ = "verified_organization_identities"
    __table_args__ = (Index("ix_verified_org_identity_verified_at", "verified_at"),)

    ror_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    aliases_json: Mapped[list] = mapped_column("aliases", JSON, default=list, nullable=False)
    organization_types_json: Mapped[list] = mapped_column(
        "organization_types", JSON, default=list, nullable=False
    )
    official_domains_json: Mapped[list] = mapped_column(
        "official_domains", JSON, default=list, nullable=False
    )
    official_urls_json: Mapped[list] = mapped_column(
        "official_urls", JSON, default=list, nullable=False
    )
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    record_status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_record_updated_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_source: Mapped[str] = mapped_column(String(500), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    openalex_institution_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    openalex_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), default="Research conversation", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    related_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ResearchJob(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_job_project_idempotency"),
        Index("ix_jobs_project_created", "project_id", "created_at"),
        Index("ix_jobs_status_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    parent_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    scope_json: Mapped[dict] = mapped_column("scope", JSON, default=dict, nullable=False)
    depth: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    budget_ceiling_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_spent_estimate_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_reserved_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    budget_ceiling_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_spent_estimate_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_reserved_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model_calls_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_characters_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_token_budget_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_token_budget_reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    current_stage: Mapped[str] = mapped_column(String(32), default="planning", nullable=False)
    checkpoint_json: Mapped[dict] = mapped_column("checkpoint", JSON, default=dict, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="jobs")
    events: Mapped[list["JobEvent"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    claims: Mapped[list["Claim"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    report: Mapped["ResearchReport | None"] = relationship(
        back_populates="job", cascade="all, delete-orphan", uselist=False
    )
    candidates: Mapped[list["DiscoveryCandidate"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (
        UniqueConstraint("job_id", "operation_key", name="uq_job_event_operation"),
        Index("ix_job_events_job_created", "job_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    operation_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    data_json: Mapped[dict] = mapped_column("data", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped[ResearchJob] = relationship(back_populates="events")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("job_id", "external_id", name="uq_source_job_external"),
        Index("ix_sources_job_status", "job_id", "retrieval_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    doi: Mapped[str | None] = mapped_column(String(300), index=True, nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    authors_json: Mapped[list] = mapped_column("authors", JSON, default=list, nullable=False)
    published_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(40), default="scholarly_article", nullable=False
    )
    retrieval_status: Mapped[str] = mapped_column(
        String(32), default="metadata_only", nullable=False
    )
    abstract_excerpt: Mapped[str | None] = mapped_column(String(600), nullable=True)
    discovery_query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    appraisal_json: Mapped[dict] = mapped_column("appraisal", JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped[ResearchJob] = relationship(back_populates="sources")
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    retrieved_documents: Mapped[list["RetrievedDocument"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class DiscoveryCandidate(Base):
    """Metadata-only discovery occurrence, including candidates not selected as sources."""

    __tablename__ = "discovery_candidates"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_key", name="uq_discovery_candidate_job_key"),
        Index("ix_discovery_candidates_job_disposition", "job_id", "disposition"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_record_id: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_identity: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher_organizations_json: Mapped[list | None] = mapped_column(
        "publisher_organizations", JSON, nullable=True
    )
    abstract_excerpt: Mapped[str | None] = mapped_column(String(600), nullable=True)
    abstract_excerpt_retention_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(300), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    query_text: Mapped[str] = mapped_column(String(300), nullable=False)
    ranking_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_json: Mapped[dict | None] = mapped_column("relevance", JSON, nullable=True)
    source_governance_json: Mapped[dict | None] = mapped_column(
        "source_governance", JSON, nullable=True
    )
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    canonical_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    job: Mapped[ResearchJob] = relationship(back_populates="candidates")


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("source_id", "identity_key", name="uq_passage_source_identity"),
        Index("ix_passages_source_order", "source_id", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("retrieved_documents.id", ondelete="CASCADE"), nullable=False
    )
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locator: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(String(600), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    access_level: Mapped[str] = mapped_column(String(32), nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    source: Mapped[Source] = relationship(back_populates="passages")
    document: Mapped["RetrievedDocument"] = relationship(back_populates="passages")
    claims: Mapped[list["Claim"]] = relationship(back_populates="passage")


class RetrievedDocument(Base):
    """Immutable source-associated snapshot metadata, never the downloaded document bytes."""

    __tablename__ = "retrieved_documents"
    __table_args__ = (
        UniqueConstraint("source_id", "identity_key", name="uq_document_source_identity"),
        Index("ix_retrieved_documents_source_date", "source_id", "retrieved_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(200), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locator: Mapped[str] = mapped_column(String(300), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    access_class: Mapped[str] = mapped_column(String(32), nullable=False)
    hash_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)

    source: Mapped[Source] = relationship(back_populates="retrieved_documents")
    passages: Mapped[list[Passage]] = relationship(back_populates="document")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_job_status", "job_id", "evidence_status"),
        Index(
            "uq_claim_passage_span",
            "job_id",
            "passage_id",
            "atomization_version",
            "span_start",
            "span_end",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    passage_id: Mapped[str] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(600), nullable=False)
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atomization_status: Mapped[str] = mapped_column(
        String(32), default="legacy_whole_sentence", nullable=False
    )
    atomization_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), default="source_reported", nullable=False)
    evidence_status: Mapped[str] = mapped_column(
        String(40), default="not_independently_verified", nullable=False
    )
    appraisal_json: Mapped[dict] = mapped_column("appraisal", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped[ResearchJob] = relationship(back_populates="claims")
    passage: Mapped[Passage] = relationship(back_populates="claims")


class EvidenceRelationship(Base):
    __tablename__ = "evidence_relationships"
    __table_args__ = (
        UniqueConstraint("job_id", "claim_a_id", "claim_b_id", name="uq_evidence_relation_pair"),
        Index("ix_evidence_relationship_job", "job_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    claim_a_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    claim_b_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_alignment: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_differences_json: Mapped[list] = mapped_column(
        "scope_differences", JSON, default=list, nullable=False
    )
    rationale: Mapped[str] = mapped_column(String(700), nullable=False)
    evidence_json: Mapped[list] = mapped_column("evidence", JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    __table_args__ = (
        UniqueConstraint("comparison_group_id", "side", name="uq_hypothesis_group_side"),
        Index("ix_hypotheses_job_created", "job_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    comparison_group_id: Mapped[str] = mapped_column(String(36), nullable=False)
    side: Mapped[str] = mapped_column(String(1), nullable=False)
    statement: Mapped[str] = mapped_column(String(700), nullable=False)
    evidence_json: Mapped[list] = mapped_column("evidence", JSON, default=list, nullable=False)
    uncertainty: Mapped[str] = mapped_column(String(500), nullable=False)
    why_competing: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(48), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ResearchReport(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    citation_map_json: Mapped[dict] = mapped_column(
        "citation_map", JSON, default=dict, nullable=False
    )
    verification_json: Mapped[dict] = mapped_column(
        "verification", JSON, default=dict, nullable=False
    )
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    job: Mapped[ResearchJob] = relationship(back_populates="report")


class RequestRateWindow(Base):
    __tablename__ = "request_rate_windows"
    __table_args__ = (
        UniqueConstraint("bucket_hash", "window_start", name="uq_request_rate_window"),
        Index("ix_request_rate_window_start", "window_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    bucket_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class OriginRequestSlot(Base):
    """Shared per-origin request slots; epoch milliseconds avoid dialect timestamp math."""

    __tablename__ = "origin_request_slots"
    __table_args__ = (Index("ix_origin_request_slots_updated", "updated_at"),)

    origin: Mapped[str] = mapped_column(String(512), primary_key=True)
    last_slot_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    next_slot_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class DailyModelQuota(Base):
    __tablename__ = "daily_model_quotas"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "quota_date", name="uq_daily_model_quota_scope"),
        Index("ix_daily_model_quota_date", "quota_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    quota_date: Mapped[date] = mapped_column(Date, nullable=False)
    calls_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ModelCallReservation(Base):
    __tablename__ = "model_call_reservations"
    __table_args__ = (
        Index("ix_model_call_reservations_job_created", "job_id", "created_at"),
        Index("ix_model_call_reservations_user_date", "user_id", "quota_date"),
        UniqueConstraint(
            "job_id",
            "operation",
            "request_hash",
            "attempt",
            name="uq_model_reservation_operation_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reserved_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reserved_cost_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    prompt_characters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_token_upper_bound: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_token_cap: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_cost_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    structured_output_json: Mapped[dict | None] = mapped_column(
        "structured_output", JSON, nullable=True
    )
    quota_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="reserved", nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UsageEntry(Base):
    __tablename__ = "usage_ledger"
    __table_args__ = (Index("ix_usage_job_created", "job_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    quota_reservation_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_call_reservations.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_cost_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_repair: Mapped[str | None] = mapped_column(String(48), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validation_error_types_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    validation_error_paths_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ProviderCooldown(Base):
    """Durable provider-account cooldown prevents repeated calls after a 429."""

    __tablename__ = "provider_cooldowns"

    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), default="account", nullable=False)
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
