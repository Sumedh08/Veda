"""Reserve per-job model spend and persist validated structured-call results.

Revision ID: 20261029_job_model_spend_cache
Revises: 20261029_conversation_lineage
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_job_model_spend_cache"
down_revision = "20261029_conversation_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_jobs") as batch_op:
        batch_op.add_column(
            sa.Column("cost_reserved_usd", sa.Float(), nullable=False, server_default=sa.text("0"))
        )
    with op.batch_alter_table("model_call_reservations") as batch_op:
        batch_op.add_column(sa.Column("request_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("reserved_cost_usd", sa.Float(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(sa.Column("actual_cost_usd", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("structured_output", sa.JSON(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_model_reservation_operation_attempt",
            ["job_id", "operation", "request_hash", "attempt"],
        )


def downgrade() -> None:
    with op.batch_alter_table("model_call_reservations") as batch_op:
        batch_op.drop_constraint("uq_model_reservation_operation_attempt", type_="unique")
        batch_op.drop_column("structured_output")
        batch_op.drop_column("actual_cost_usd")
        batch_op.drop_column("reserved_cost_usd")
        batch_op.drop_column("request_hash")
    with op.batch_alter_table("research_jobs") as batch_op:
        batch_op.drop_column("cost_reserved_usd")
