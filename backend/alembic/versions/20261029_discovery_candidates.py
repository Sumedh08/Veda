"""Persist bounded metadata-only discovery candidates and dispositions.

Revision ID: 20261029_discovery_candidates
Revises: 20261029_user_preferences
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_discovery_candidates"
down_revision = "20261029_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_key", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_record_id", sa.String(length=500), nullable=False),
        sa.Column("canonical_identity", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("doi", sa.String(length=300), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=True),
        sa.Column("published_year", sa.Integer(), nullable=True),
        sa.Column("query_text", sa.String(length=300), nullable=False),
        sa.Column("disposition", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=48), nullable=False),
        sa.Column("canonical_source_id", sa.String(length=36), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["canonical_source_id"], ["sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "candidate_key", name="uq_discovery_candidate_job_key"),
    )
    op.create_index(
        "ix_discovery_candidates_job_disposition",
        "discovery_candidates",
        ["job_id", "disposition"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_candidates_job_disposition", table_name="discovery_candidates")
    op.drop_table("discovery_candidates")
