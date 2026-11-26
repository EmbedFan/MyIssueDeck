"""Project-level database queries: deletion preview and project data removal."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.features.items.models import (
    ImportBatch,
    Item,
    ItemApplyTo,
    ItemEvent,
    ItemExternalLink,
    ItemImage,
    ItemRelationship,
    ItemTag,
    ShipCommit,
    ShipRecord,
    WorkSession,
    WorkSessionUpdate,
)

ACTIVE_WORK_SESSION_STATUSES = ("active", "paused")


@dataclass(frozen=True)
class ProjectDeletionPreview:
    items: int
    deleted_items: int
    work_sessions: int
    active_work_sessions: int
    import_batches: int


class ProjectRepo:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def deletion_preview(self, project_key: str) -> ProjectDeletionPreview:
        items = await self._count(
            select(func.count()).select_from(Item).where(
                Item.project_key == project_key, Item.deleted_at.is_(None),
            )
        )
        deleted_items = await self._count(
            select(func.count()).select_from(Item).where(
                Item.project_key == project_key, Item.deleted_at.is_not(None),
            )
        )
        work_sessions = await self._count(
            select(func.count()).select_from(WorkSession).where(
                WorkSession.project_key == project_key,
            )
        )
        active = await self._count(
            select(func.count()).select_from(WorkSession).where(
                WorkSession.project_key == project_key,
                WorkSession.status.in_(ACTIVE_WORK_SESSION_STATUSES),
            )
        )
        batches = await self._count(
            select(func.count()).select_from(ImportBatch).where(
                ImportBatch.project_key == project_key,
            )
        )
        return ProjectDeletionPreview(
            items=items,
            deleted_items=deleted_items,
            work_sessions=work_sessions,
            active_work_sessions=active,
            import_batches=batches,
        )

    async def delete_project_rows(self, project_key: str) -> None:
        """Delete every database row that belongs to the project.

        Child rows are deleted explicitly so the result does not depend on the
        SQLite `foreign_keys` pragma. The caller owns the transaction.
        """
        item_pks = select(Item.pk).where(Item.project_key == project_key)
        session_ids = select(WorkSession.id).where(WorkSession.project_key == project_key)
        record_ids = select(ShipRecord.id).where(ShipRecord.item_pk.in_(item_pks))

        await self._s.execute(
            delete(WorkSessionUpdate).where(WorkSessionUpdate.session_id.in_(session_ids))
        )
        await self._s.execute(
            delete(WorkSession).where(WorkSession.project_key == project_key)
        )
        await self._s.execute(
            delete(ImportBatch).where(ImportBatch.project_key == project_key)
        )
        await self._s.execute(
            delete(ItemRelationship).where(or_(
                ItemRelationship.from_item_pk.in_(item_pks),
                ItemRelationship.to_item_pk.in_(item_pks),
            ))
        )
        await self._s.execute(delete(ShipCommit).where(ShipCommit.ship_record_id.in_(record_ids)))
        await self._s.execute(delete(ShipRecord).where(ShipRecord.item_pk.in_(item_pks)))
        for model in (ItemTag, ItemApplyTo, ItemExternalLink, ItemEvent, ItemImage):
            await self._s.execute(delete(model).where(model.item_pk.in_(item_pks)))
        await self._s.execute(delete(Item).where(Item.project_key == project_key))

    async def _count(self, stmt) -> int:
        return int((await self._s.execute(stmt)).scalar() or 0)
