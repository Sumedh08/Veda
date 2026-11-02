"""Persist explainable lexical relevance features for discovery candidates.

Revision ID: 20261029_candidate_relevance
Revises: 20261029_discovery_candidates, 20261029_claim_unit_spans
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_candidate_relevance"
down_revision = ("20261029_discovery_candidates", "20261029_claim_unit_spans")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("relevance_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "discovery_candidates",
        sa.Column("ranking_order", sa.Integer(), nullable=True),
    )
    op.add_column(
        "discovery_candidates",
        sa.Column("relevance", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_candidates", "relevance")
    op.drop_column("discovery_candidates", "ranking_order")
    op.drop_column("discovery_candidates", "relevance_score")
