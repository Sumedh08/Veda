"""Persist depth-profile resource usage for research runs.

Revision ID: 20261029_depth_profile_budgets
Revises: 20261029_job_model_spend_cache
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_depth_profile_budgets"
down_revision = "20261029_job_model_spend_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("model_calls_reserved", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column(
                "prompt_characters_reserved", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "prompt_token_budget_reserved", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "output_token_budget_reserved", sa.Integer(), nullable=False, server_default="0"
            )
        )
    with op.batch_alter_table("model_call_reservations") as batch_op:
        batch_op.add_column(
            sa.Column("prompt_characters", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("output_token_cap", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("prompt_token_upper_bound", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("model_call_reservations") as batch_op:
        batch_op.drop_column("prompt_token_upper_bound")
        batch_op.drop_column("output_token_cap")
        batch_op.drop_column("prompt_characters")
    with op.batch_alter_table("research_jobs") as batch_op:
        batch_op.drop_column("output_token_budget_reserved")
        batch_op.drop_column("prompt_token_budget_reserved")
        batch_op.drop_column("prompt_characters_reserved")
        batch_op.drop_column("model_calls_reserved")
