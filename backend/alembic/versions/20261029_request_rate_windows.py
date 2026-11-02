"""Add persistent database-backed API request rate windows.

Revision ID: 20261029_request_limits
Revises: 20261029_model_quotas
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_request_limits"
down_revision = "20261029_model_quotas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_rate_windows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("bucket_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket_hash", "window_start", name="uq_request_rate_window"),
    )
    op.create_index(
        "ix_request_rate_window_start",
        "request_rate_windows",
        ["window_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_request_rate_window_start", table_name="request_rate_windows")
    op.drop_table("request_rate_windows")
