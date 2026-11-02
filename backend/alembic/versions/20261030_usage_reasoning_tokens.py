"""Persist provider-reported reasoning-token counts in the usage ledger.

Revision ID: 20261030_usage_reasoning_tokens
Revises: 20261030_usage_finish_reason
Create Date: 2026-10-30
"""

import sqlalchemy as sa

from alembic import op

revision = "20261030_usage_reasoning_tokens"
down_revision = "20261030_usage_finish_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger", sa.Column("reasoning_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_ledger", "reasoning_tokens")
