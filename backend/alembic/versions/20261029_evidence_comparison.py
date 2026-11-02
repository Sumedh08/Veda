"""Persist scope-aware evidence relationships and grounded hypotheses.

Revision ID: 20261029_comparison
Revises: 20261029_request_limits
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_comparison"
down_revision = "20261029_request_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_relationships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("claim_a_id", sa.String(length=36), nullable=False),
        sa.Column("claim_b_id", sa.String(length=36), nullable=False),
        sa.Column("relationship_type", sa.String(length=24), nullable=False),
        sa.Column("scope_alignment", sa.String(length=16), nullable=False),
        sa.Column("scope_differences", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.String(length=700), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_a_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_b_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "claim_a_id", "claim_b_id", name="uq_evidence_relation_pair"),
    )
    op.create_index(
        "ix_evidence_relationship_job",
        "evidence_relationships",
        ["job_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("comparison_group_id", sa.String(length=36), nullable=False),
        sa.Column("side", sa.String(length=1), nullable=False),
        sa.Column("statement", sa.String(length=700), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("uncertainty", sa.String(length=500), nullable=False),
        sa.Column("why_competing", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=48), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comparison_group_id", "side", name="uq_hypothesis_group_side"),
    )
    op.create_index(
        "ix_hypotheses_job_created", "hypotheses", ["job_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_hypotheses_job_created", table_name="hypotheses")
    op.drop_table("hypotheses")
    op.drop_index("ix_evidence_relationship_job", table_name="evidence_relationships")
    op.drop_table("evidence_relationships")
