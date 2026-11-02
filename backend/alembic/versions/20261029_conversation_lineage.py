"""Link research runs into persistent project conversations.

Revision ID: 20261029_conversation_lineage
Revises: 20261029_comparison
Create Date: 2026-10-29
"""

import sqlalchemy as sa

from alembic import op

revision = "20261029_conversation_lineage"
down_revision = "20261029_comparison"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_jobs") as batch_op:
        batch_op.add_column(sa.Column("conversation_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            "fk_research_jobs_conversation_id_conversations",
            "conversations",
            ["conversation_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_research_jobs_conversation_id", "research_jobs", ["conversation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_research_jobs_conversation_id", table_name="research_jobs")
    with op.batch_alter_table("research_jobs") as batch_op:
        batch_op.drop_constraint(
            "fk_research_jobs_conversation_id_conversations", type_="foreignkey"
        )
        batch_op.drop_column("conversation_id")
