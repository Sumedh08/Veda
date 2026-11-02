"""Persist source identity governance alongside discovery occurrences.

Revision ID: 20261101_candidate_source_governance
Revises: 20261031_candidate_abstract_snapshot
Create Date: 2026-11-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261101_candidate_source_governance"
down_revision = "20261031_candidate_abstract_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("source_governance", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_candidates", "source_governance")
