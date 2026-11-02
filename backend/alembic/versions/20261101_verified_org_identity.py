"""Persist verified public organization identity facts for bounded reuse.

Revision ID: 20261101_verified_org_identity
Revises: 20261101_candidate_source_governance
Create Date: 2026-11-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261101_verified_org_identity"
down_revision = "20261101_candidate_source_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verified_organization_identities",
        sa.Column("ror_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("organization_types", sa.JSON(), nullable=False),
        sa.Column("official_domains", sa.JSON(), nullable=False),
        sa.Column("official_urls", sa.JSON(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("record_status", sa.String(length=24), nullable=False),
        sa.Column("source_record_updated_at", sa.String(length=32), nullable=True),
        sa.Column("verification_source", sa.String(length=500), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("openalex_institution_id", sa.String(length=32), nullable=True),
        sa.Column("openalex_resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ror_id"),
    )
    op.create_index(
        "ix_verified_org_identity_verified_at",
        "verified_organization_identities",
        ["verified_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_verified_org_identity_verified_at",
        table_name="verified_organization_identities",
    )
    op.drop_table("verified_organization_identities")
