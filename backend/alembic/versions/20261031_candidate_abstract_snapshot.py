"""Add rights-aware candidate abstract snapshot and retention-status fields.

Revision ID: 20261031_candidate_abstract_snapshot
Revises: 20261031_usage_validation_diagnostics
Create Date: 2026-10-31
"""

import sqlalchemy as sa

from alembic import op

revision = "20261031_candidate_abstract_snapshot"
down_revision = "20261031_usage_validation_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("abstract_excerpt", sa.String(length=600), nullable=True),
    )
    op.add_column(
        "discovery_candidates",
        sa.Column("abstract_excerpt_retention_status", sa.String(length=48), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_candidates", "abstract_excerpt_retention_status")
    op.drop_column("discovery_candidates", "abstract_excerpt")
