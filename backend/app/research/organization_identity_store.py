"""Persist bounded public ROR identity facts, separate from question relevance."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import VerifiedOrganizationIdentity, utcnow
from app.providers.ror import ROROrganization

IDENTITY_FRESHNESS = timedelta(days=90)
_ROR_ID = re.compile(r"^https://ror\.org/[0-9a-z]{9}$", re.IGNORECASE)
_OPENALEX_ID = re.compile(r"^I[0-9]{1,20}$")


@dataclass(frozen=True)
class CachedOrganizationIdentity:
    profile: ROROrganization
    openalex_institution_id: str | None
    verified_at: datetime
    openalex_resolved_at: datetime | None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _parse_retrieved_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return utcnow()
    return _as_utc(parsed)


def load_recent_identity(
    db: Session, ror_id: str, *, now: datetime | None = None
) -> CachedOrganizationIdentity | None:
    """Return a recent exact-ID ROR snapshot; stale or malformed records are not trusted."""
    if not isinstance(ror_id, str) or not _ROR_ID.fullmatch(ror_id):
        return None
    row = db.get(VerifiedOrganizationIdentity, ror_id.casefold())
    if row is None or row.record_status.casefold() != "active":
        return None
    current = _as_utc(now or utcnow())
    verified_at = _as_utc(row.verified_at)
    age = current - verified_at
    if age < timedelta(0) or age > IDENTITY_FRESHNESS:
        return None
    api_url = row.verification_source
    profile = ROROrganization(
        ror_id=row.ror_id,
        canonical_name=row.canonical_name,
        aliases=tuple(row.aliases_json or []),
        organization_types=tuple(row.organization_types_json or []),
        domains=tuple(row.official_domains_json or []),
        official_urls=tuple(row.official_urls_json or []),
        country_code=row.country_code,
        record_status=row.record_status,
        last_modified=row.source_record_updated_at,
        retrieved_at=verified_at.isoformat(),
        api_url=api_url,
    )
    openalex_resolved_at = (
        _as_utc(row.openalex_resolved_at) if row.openalex_resolved_at is not None else None
    )
    openalex_id = row.openalex_institution_id
    if openalex_id is not None and (
        not _OPENALEX_ID.fullmatch(openalex_id)
        or openalex_resolved_at is None
        or current - openalex_resolved_at > IDENTITY_FRESHNESS
        or current < openalex_resolved_at
    ):
        openalex_id = None
        openalex_resolved_at = None
    return CachedOrganizationIdentity(
        profile=profile,
        openalex_institution_id=openalex_id,
        verified_at=verified_at,
        openalex_resolved_at=openalex_resolved_at,
    )


def persist_verified_identity(
    db: Session,
    profile: ROROrganization,
    *,
    openalex_institution_id: str | None = None,
    now: datetime | None = None,
) -> None:
    """Upsert ROR facts without persisting question-specific relevance or publication quality."""
    if not _ROR_ID.fullmatch(profile.ror_id):
        raise ValueError("verified organization ROR identity is invalid")
    if openalex_institution_id is not None and not _OPENALEX_ID.fullmatch(openalex_institution_id):
        raise ValueError("verified OpenAlex institution identity is invalid")
    current = _as_utc(now or _parse_retrieved_at(profile.retrieved_at))
    existing = db.get(VerifiedOrganizationIdentity, profile.ror_id.casefold())
    source_record_changed = (
        existing is not None and existing.source_record_updated_at != profile.last_modified
    )
    stored_openalex_id = (
        openalex_institution_id
        if openalex_institution_id is not None
        else None
        if source_record_changed
        else existing.openalex_institution_id
        if existing is not None
        else None
    )
    stored_openalex_at = (
        current
        if openalex_institution_id is not None
        else None
        if source_record_changed
        else existing.openalex_resolved_at
        if existing is not None
        else None
    )
    values = {
        "ror_id": profile.ror_id.casefold(),
        "canonical_name": profile.canonical_name[:300],
        "aliases": list(profile.aliases)[:32],
        "organization_types": list(profile.organization_types)[:16],
        "official_domains": list(profile.domains)[:32],
        "official_urls": list(profile.official_urls)[:8],
        "country_code": profile.country_code,
        "record_status": profile.record_status[:24],
        "source_record_updated_at": profile.last_modified,
        "verification_source": profile.api_url[:500],
        "verified_at": current,
        "openalex_institution_id": stored_openalex_id,
        "openalex_resolved_at": stored_openalex_at,
        "created_at": existing.created_at if existing is not None else current,
        "updated_at": current,
    }
    table = VerifiedOrganizationIdentity.__table__
    dialect = db.get_bind().dialect.name
    insert = (
        sqlite_insert(table)
        if dialect == "sqlite"
        else postgres_insert(table)
        if dialect == "postgresql"
        else None
    )
    if insert is None:
        if existing is None:
            db.add(VerifiedOrganizationIdentity(**values))
        else:
            for column, value in values.items():
                setattr(existing, column if column != "aliases" else "aliases_json", value)
            existing.organization_types_json = values["organization_types"]
            existing.official_domains_json = values["official_domains"]
            existing.official_urls_json = values["official_urls"]
        db.flush()
        return
    update_values = {
        key: value for key, value in values.items() if key not in {"ror_id", "created_at"}
    }
    statement = insert.values(**values).on_conflict_do_update(
        index_elements=[table.c.ror_id], set_=update_values
    )
    db.execute(statement)


def persist_openalex_mapping(
    db: Session, ror_id: str, openalex_institution_id: str, *, now: datetime | None = None
) -> bool:
    """Attach a resolved OpenAlex ID only to an already verified ROR identity."""
    if (
        not isinstance(ror_id, str)
        or not _ROR_ID.fullmatch(ror_id)
        or not isinstance(openalex_institution_id, str)
        or not _OPENALEX_ID.fullmatch(openalex_institution_id)
    ):
        return False
    result = db.execute(
        update(VerifiedOrganizationIdentity)
        .where(VerifiedOrganizationIdentity.ror_id == ror_id.casefold())
        .values(
            openalex_institution_id=openalex_institution_id,
            openalex_resolved_at=_as_utc(now or utcnow()),
            updated_at=_as_utc(now or utcnow()),
        )
    )
    return result.rowcount == 1
