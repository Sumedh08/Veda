"""Record lossless structured-response envelope normalization in usage rows.

Revision ID: 20261029_usage_response_repair
Revises: 20261029_discovery_candidates
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_usage_response_repair"
down_revision = "20261029_discovery_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger", sa.Column("response_repair", sa.String(length=48), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_ledger", "response_repair")
