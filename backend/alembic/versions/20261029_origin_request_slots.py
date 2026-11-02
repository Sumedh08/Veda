"""Add shared database-backed per-origin request reservations.

Revision ID: 20261029_origin_request_slots
Revises: 20261029_project_retention_policy
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_origin_request_slots"
down_revision = "20261029_project_retention_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "origin_request_slots",
        sa.Column("origin", sa.String(length=512), primary_key=True, nullable=False),
        sa.Column("last_slot_ms", sa.BigInteger(), nullable=False),
        sa.Column("next_slot_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_origin_request_slots_updated", "origin_request_slots", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_origin_request_slots_updated", table_name="origin_request_slots")
    op.drop_table("origin_request_slots")
