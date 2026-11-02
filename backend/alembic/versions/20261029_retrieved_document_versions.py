"""Add immutable retrieved-document snapshots and stable passage identity.

Revision ID: 20261029_retrieved_document_versions
Revises: 20261029_candidate_relevance
Create Date: 2026-10-29
"""

import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid5

import sqlalchemy as sa

from alembic import op

revision = "20261029_retrieved_document_versions"
down_revision = "20261029_candidate_relevance"
branch_labels = None
depends_on = None

_NAMESPACE = UUID("1c621c12-38c9-4d3d-a7ce-4cf7ca10ba5a")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def upgrade() -> None:
    op.create_table(
        "retrieved_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("identity_key", sa.String(length=64), nullable=False),
        sa.Column("source_version", sa.String(length=200), nullable=False),
        sa.Column("document_sha256", sa.String(length=64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locator", sa.String(length=300), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("access_class", sa.String(length=32), nullable=False),
        sa.Column("hash_scope", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "identity_key", name="uq_document_source_identity"),
    )
    op.create_index(
        "ix_retrieved_documents_source_date",
        "retrieved_documents",
        ["source_id", "retrieved_at"],
        unique=False,
    )
    op.add_column("passages", sa.Column("document_id", sa.String(length=36), nullable=True))
    op.add_column("passages", sa.Column("identity_key", sa.String(length=64), nullable=True))
    op.add_column("passages", sa.Column("identity_version", sa.Integer(), nullable=True))

    bind = op.get_bind()
    source_table = sa.table(
        "sources",
        sa.column("id", sa.String(length=36)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    passage_table = sa.table(
        "passages",
        sa.column("id", sa.String(length=36)),
        sa.column("source_id", sa.String(length=36)),
        sa.column("locator", sa.String(length=160)),
        sa.column("content_hash", sa.String(length=64)),
        sa.column("access_level", sa.String(length=32)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("document_id", sa.String(length=36)),
        sa.column("identity_key", sa.String(length=64)),
        sa.column("identity_version", sa.Integer()),
    )
    sources = {
        row.id: row for row in bind.execute(sa.select(source_table.c.id, source_table.c.created_at))
    }
    passages = list(
        bind.execute(
            sa.select(
                passage_table.c.id,
                passage_table.c.source_id,
                passage_table.c.locator,
                passage_table.c.content_hash,
                passage_table.c.access_level,
                passage_table.c.created_at,
            )
        )
    )
    grouped: dict[tuple[str, str], list[object]] = {}
    for row in passages:
        grouped.setdefault((row.source_id, row.access_level), []).append(row)

    documents = sa.table(
        "retrieved_documents",
        sa.column("id", sa.String(length=36)),
        sa.column("source_id", sa.String(length=36)),
        sa.column("identity_key", sa.String(length=64)),
        sa.column("source_version", sa.String(length=200)),
        sa.column("document_sha256", sa.String(length=64)),
        sa.column("retrieved_at", sa.DateTime(timezone=True)),
        sa.column("locator", sa.String(length=300)),
        sa.column("media_type", sa.String(length=120)),
        sa.column("access_class", sa.String(length=32)),
        sa.column("hash_scope", sa.String(length=40)),
        sa.column("schema_version", sa.Integer()),
        sa.column("metadata", sa.JSON()),
    )
    for (source_id, access_class), group in grouped.items():
        source_row = sources.get(source_id)
        group_signature = _sha256(
            _canonical(sorted((row.id, row.locator, row.content_hash) for row in group))
        )
        document_key = _sha256(f"legacy-document-v1:{source_id}:{access_class}:{group_signature}")
        document_id = str(uuid5(_NAMESPACE, f"document:legacy:{document_key}"))
        media_type = {
            "full_text_html": "text/html",
            "full_text_pdf": "application/pdf",
        }.get(access_class, "text/plain")
        retrieved_at = (
            source_row.created_at
            if source_row is not None and source_row.created_at is not None
            else min(row.created_at for row in group if row.created_at is not None)
            if any(row.created_at is not None for row in group)
            else datetime(1970, 1, 1)
        )
        bind.execute(
            documents.insert().values(
                id=document_id,
                source_id=source_id,
                identity_key=document_key,
                source_version="legacy_unknown",
                document_sha256=group_signature,
                retrieved_at=retrieved_at,
                locator=f"legacy backfill: {access_class}",
                media_type=media_type,
                access_class=access_class,
                hash_scope="legacy_passage_snapshot",
                schema_version=1,
                metadata={
                    "provenance_status": "legacy_backfill",
                    "original_document_bytes_available": False,
                    "retrieval_date_precision": "source_created_at"
                    if source_row is not None and source_row.created_at is not None
                    else "passage_created_at_fallback",
                    "passage_count": len(group),
                    "snapshot_hash_scope": "sorted legacy passage ids, locators and content hashes",
                },
            )
        )
        for row in group:
            bind.execute(
                passage_table.update()
                .where(passage_table.c.id == row.id)
                .values(
                    document_id=document_id,
                    identity_key=_sha256(f"legacy-passage-v0:{source_id}:{row.id}"),
                    identity_version=0,
                )
            )

    with op.batch_alter_table("passages") as batch:
        batch.alter_column("document_id", existing_type=sa.String(length=36), nullable=False)
        batch.alter_column("identity_key", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("identity_version", existing_type=sa.Integer(), nullable=False)
        batch.drop_constraint("uq_passage_source_hash", type_="unique")
        batch.create_foreign_key(
            "fk_passages_document_id_retrieved_documents",
            "retrieved_documents",
            ["document_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint("uq_passage_source_identity", ["source_id", "identity_key"])


def downgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT source_id, content_hash FROM passages "
            "GROUP BY source_id, content_hash HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot downgrade retrieved-document versioning: passages with identical text "
            "exist in distinct document versions and cannot be represented by the legacy key."
        )
    with op.batch_alter_table("passages") as batch:
        batch.drop_constraint("uq_passage_source_identity", type_="unique")
        batch.drop_constraint("fk_passages_document_id_retrieved_documents", type_="foreignkey")
        batch.drop_column("identity_version")
        batch.drop_column("identity_key")
        batch.drop_column("document_id")
        batch.create_unique_constraint("uq_passage_source_hash", ["source_id", "content_hash"])
    op.drop_index("ix_retrieved_documents_source_date", table_name="retrieved_documents")
    op.drop_table("retrieved_documents")
