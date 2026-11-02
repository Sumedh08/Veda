"""Persist preferences by authenticated user identity.

Revision ID: 20261029_user_preferences
Revises: 20261029_depth_profile_budgets
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_user_preferences"
down_revision = "20261029_depth_profile_budgets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.String(length=128), primary_key=True),
        sa.Column("default_depth", sa.String(length=16), nullable=False, server_default="standard"),
        sa.Column(
            "default_budget_ceiling_usd",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
