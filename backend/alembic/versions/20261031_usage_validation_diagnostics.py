"""Persist bounded, sanitized structured-output validation diagnostics."""

import sqlalchemy as sa

from alembic import op

revision = "20261031_usage_validation_diagnostics"
down_revision = ("20261030_sarvam_budget_cooldown", "20261030_job_model_identity")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_ledger",
        sa.Column("validation_error_types_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "usage_ledger",
        sa.Column("validation_error_paths_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("usage_ledger", "validation_error_paths_json")
    op.drop_column("usage_ledger", "validation_error_types_json")
