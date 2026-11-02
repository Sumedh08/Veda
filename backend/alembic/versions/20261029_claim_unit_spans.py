"""Store exact source-span and atomization metadata on claims.

Revision ID: 20261029_claim_unit_spans
Revises: 20261029_usage_response_repair
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_claim_unit_spans"
down_revision = "20261029_usage_response_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("span_start", sa.Integer(), nullable=True))
    op.add_column("claims", sa.Column("span_end", sa.Integer(), nullable=True))
    op.add_column(
        "claims",
        sa.Column(
            "atomization_status",
            sa.String(length=32),
            nullable=False,
            server_default="legacy_whole_sentence",
        ),
    )
    op.add_column(
        "claims",
        sa.Column(
            "atomization_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    claims = sa.table(
        "claims",
        sa.column("passage_id", sa.String()),
        sa.column("span_start", sa.Integer()),
        sa.column("span_end", sa.Integer()),
    )
    passages = sa.table(
        "passages",
        sa.column("id", sa.String()),
        sa.column("content", sa.Text()),
    )
    passage_length = (
        sa.select(sa.func.length(passages.c.content))
        .where(passages.c.id == claims.c.passage_id)
        .scalar_subquery()
    )
    op.get_bind().execute(sa.update(claims).values(span_start=0, span_end=passage_length))
    op.create_index(
        "uq_claim_passage_span",
        "claims",
        ["job_id", "passage_id", "atomization_version", "span_start", "span_end"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_claim_passage_span", table_name="claims")
    op.drop_column("claims", "atomization_version")
    op.drop_column("claims", "atomization_status")
    op.drop_column("claims", "span_end")
    op.drop_column("claims", "span_start")
