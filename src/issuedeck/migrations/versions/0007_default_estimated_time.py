"""backfill default estimated_time

Items created before the built-in ``estimated_time`` custom field existed have
no value for it. Give every item that lacks one the default of 0.5 hours
(30 minutes). ``updated_at`` is left unchanged because this is a silent
backfill, not a user edit.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-15
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE items
        SET custom_fields_json = json_set(
            CASE WHEN json_valid(custom_fields_json) THEN custom_fields_json ELSE '{}' END,
            '$.estimated_time', 0.5
        )
        WHERE json_extract(
            CASE WHEN json_valid(custom_fields_json) THEN custom_fields_json ELSE '{}' END,
            '$.estimated_time'
        ) IS NULL
        """
    )


def downgrade() -> None:
    # A backfilled 0.5 cannot be told apart from a value set on purpose, so the
    # downgrade deliberately leaves the data as it is.
    pass
