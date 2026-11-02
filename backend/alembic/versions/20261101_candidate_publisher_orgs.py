"""Persist verified official publisher identities on discovery candidates.

Revision ID: 20261101_candidate_publisher_orgs
Revises: 20261101_candidate_publisher
Create Date: 2026-11-01
"""

import sqlalchemy as sa

from alembic import op

revision = "20261101_candidate_publisher_orgs"
down_revision = "20261101_candidate_publisher"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_candidates",
        sa.Column("publisher_organizations", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovery_candidates", "publisher_organizations")
