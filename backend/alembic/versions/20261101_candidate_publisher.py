"""Persist publisher identity on discovery candidates.

Revision ID: 20261101_candidate_publisher
Revises: 20261101_verified_org_identity
Create Date: 2026-11-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261101_candidate_publisher"
down_revision = "20261101_verified_org_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("publisher", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_candidates", "publisher")
