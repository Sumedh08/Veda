"""Add opt-in archived-project expiration metadata.

Revision ID: 20261029_project_retention_policy
Revises: 20261029_retrieved_document_versions
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_project_retention_policy"
down_revision = "20261029_retrieved_document_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("purge_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_preferences", sa.Column("retention_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_preferences", "retention_days")
    op.drop_column("projects", "purge_at")
