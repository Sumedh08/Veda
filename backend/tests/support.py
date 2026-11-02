"""Shared typed evidence fixtures for database-backed tests."""

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Passage, RetrievedDocument, Source
from app.research.document_identity import document_identity, passage_identity


def add_test_passage(
    db: Session,
    source: Source,
    *,
    ordinal: int,
    locator: str,
    content: str,
    access_level: str = "abstract_only",
    source_version: str = "fixture-v1",
) -> Passage:
    """Create a passage with an immutable parent snapshot instead of an orphan fixture."""
    document_sha256 = hashlib.sha256(
        f"fixture:{source.id}:{source_version}:{access_level}".encode()
    ).hexdigest()
    document_id, document_key = document_identity(
        source_id=source.id,
        source_version=source_version,
        document_sha256=document_sha256,
        media_type="text/plain",
        access_class=access_level,
    )
    pending_document = any(
        isinstance(item, RetrievedDocument) and item.id == document_id for item in db.new
    )
    if not pending_document and db.get(RetrievedDocument, document_id) is None:
        db.add(
            RetrievedDocument(
                id=document_id,
                source_id=source.id,
                identity_key=document_key,
                source_version=source_version,
                document_sha256=document_sha256,
                retrieved_at=source.created_at or datetime.now(UTC),
                locator="test fixture document",
                media_type="text/plain",
                access_class=access_level,
                hash_scope="bounded_provider_excerpt",
                schema_version=1,
                metadata_json={"fixture": True},
            )
        )
        db.flush()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    passage_id, identity_key = passage_identity(
        source_id=source.id,
        document_id=document_id,
        locator=locator,
        content_sha256=content_hash,
    )
    passage = Passage(
        id=passage_id,
        source_id=source.id,
        document_id=document_id,
        identity_key=identity_key,
        identity_version=1,
        ordinal=ordinal,
        locator=locator,
        content=content,
        content_hash=content_hash,
        access_level=access_level,
        truncated=False,
    )
    db.add(passage)
    return passage
