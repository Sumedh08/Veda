"""Persist bounded provider error classifications in the usage ledger."""

import sqlalchemy as sa

from alembic import op

revision = "20261029_usage_error_class"
down_revision = "20261029_origin_request_slots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_ledger", sa.Column("error_class", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_ledger", "error_class")
