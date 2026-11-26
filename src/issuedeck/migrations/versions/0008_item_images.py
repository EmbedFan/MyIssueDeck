"""item images (FEA-0013)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_images",
        sa.Column(
            "item_pk", sa.Integer(),
            sa.ForeignKey("items.pk", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column("image_id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_item_images_image", "item_images", ["image_id"])


def downgrade() -> None:
    op.drop_index("ix_item_images_image", table_name="item_images")
    op.drop_table("item_images")
