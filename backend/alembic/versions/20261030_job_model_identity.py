"""Persist selected provider/model identity on each research job.

Revision ID: 20261030_job_model_identity
Revises: 20261030_sarvam_budget_cooldown
Create Date: 2026-10-30
"""

import sqlalchemy as sa

from alembic import op

revision = "20261030_job_model_identity"
down_revision = "20261030_sarvam_budget_cooldown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_jobs", sa.Column("model_provider", sa.String(40), nullable=True))
    op.add_column("research_jobs", sa.Column("model_name", sa.String(160), nullable=True))


def downgrade() -> None:
    op.drop_column("research_jobs", "model_name")
    op.drop_column("research_jobs", "model_provider")
