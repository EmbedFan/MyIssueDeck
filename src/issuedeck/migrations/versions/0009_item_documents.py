"""item documents (FEA-0012)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_documents",
        sa.Column(
            "item_pk", sa.Integer(),
            sa.ForeignKey("items.pk", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("document_id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_item_documents_document", "item_documents", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_item_documents_document", table_name="item_documents")
    op.drop_table("item_documents")
