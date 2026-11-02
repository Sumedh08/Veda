"""Add durable daily model call quotas and reservation ledger.

Revision ID: 20261029_model_quotas
Revises: 39762b1c2d78
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_model_quotas"
down_revision = "39762b1c2d78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_model_quotas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("calls_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "scope_id", "quota_date", name="uq_daily_model_quota_scope"),
    )
    op.create_index("ix_daily_model_quota_date", "daily_model_quotas", ["quota_date"], unique=False)
    op.create_table(
        "model_call_reservations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=True),
        sa.Column("quota_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("error_class", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_call_reservations_job_created",
        "model_call_reservations",
        ["job_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_model_call_reservations_user_date",
        "model_call_reservations",
        ["user_id", "quota_date"],
        unique=False,
    )
    with op.batch_alter_table("usage_ledger") as batch_op:
        batch_op.add_column(
            sa.Column(
                "quota_reservation_id",
                sa.String(length=36),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_usage_ledger_quota_reservation_id",
            "model_call_reservations",
            ["quota_reservation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("usage_ledger") as batch_op:
        batch_op.drop_constraint("fk_usage_ledger_quota_reservation_id", type_="foreignkey")
        batch_op.drop_column("quota_reservation_id")
    op.drop_index("ix_model_call_reservations_user_date", table_name="model_call_reservations")
    op.drop_index("ix_model_call_reservations_job_created", table_name="model_call_reservations")
    op.drop_table("model_call_reservations")
    op.drop_index("ix_daily_model_quota_date", table_name="daily_model_quotas")
    op.drop_table("daily_model_quotas")
