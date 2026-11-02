"""Add native INR budget accounting and durable provider cooldowns.

Revision ID: 20261030_sarvam_budget_cooldown
Revises: 20261030_usage_reasoning_tokens
Create Date: 2026-10-30
"""

import sqlalchemy as sa

from alembic import op

revision = "20261030_sarvam_budget_cooldown"
down_revision = "20261030_usage_reasoning_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_jobs",
        sa.Column("budget_ceiling_inr", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "research_jobs",
        sa.Column("cost_spent_estimate_inr", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "research_jobs",
        sa.Column("cost_reserved_inr", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "model_call_reservations",
        sa.Column("reserved_cost_inr", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "model_call_reservations", sa.Column("actual_cost_inr", sa.Float(), nullable=True)
    )
    op.add_column("usage_ledger", sa.Column("reported_cost_inr", sa.Float(), nullable=True))
    op.add_column("usage_ledger", sa.Column("estimated_cost_inr", sa.Float(), nullable=True))
    op.create_table(
        "provider_cooldowns",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=16), server_default="account", nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("provider"),
    )


def downgrade() -> None:
    op.drop_table("provider_cooldowns")
    op.drop_column("usage_ledger", "estimated_cost_inr")
    op.drop_column("usage_ledger", "reported_cost_inr")
    op.drop_column("model_call_reservations", "actual_cost_inr")
    op.drop_column("model_call_reservations", "reserved_cost_inr")
    op.drop_column("research_jobs", "cost_reserved_inr")
    op.drop_column("research_jobs", "cost_spent_estimate_inr")
    op.drop_column("research_jobs", "budget_ceiling_inr")
