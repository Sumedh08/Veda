"""Persist allowlisted provider finish reasons alongside usage outcomes."""

import sqlalchemy as sa

from alembic import op

revision = "20261030_usage_finish_reason"
down_revision = "20261029_usage_error_class"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger", sa.Column("finish_reason", sa.String(length=40), nullable=True))
    op.execute(
        "UPDATE usage_ledger SET finish_reason = 'length' "
        "WHERE error_class = 'provider_output_truncated'"
    )


def downgrade() -> None:
    op.drop_column("usage_ledger", "finish_reason")
