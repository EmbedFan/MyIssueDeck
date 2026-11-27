"""Data access for item_documents: which store document is linked to which item (FEA-0012)."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.features.items.models import Item, ItemDocument


class ItemDocumentRepo:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def exists(self, item_pk: int, document_id: str) -> bool:
        stmt = select(ItemDocument).where(
            ItemDocument.item_pk == item_pk, ItemDocument.document_id == document_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def add(self, item_pk: int, document_id: str, created_at: str) -> None:
        self._s.add(ItemDocument(
            item_pk=item_pk, document_id=document_id, created_at=created_at,
        ))
        await self._s.flush()

    async def remove(self, item_pk: int, document_id: str) -> bool:
        result = await self._s.execute(delete(ItemDocument).where(
            ItemDocument.item_pk == item_pk, ItemDocument.document_id == document_id,
        ))
        return (result.rowcount or 0) > 0

    async def document_ids_of_item(self, item_pk: int) -> list[str]:
        stmt = select(ItemDocument.document_id).where(ItemDocument.item_pk == item_pk)
        return sorted((await self._s.execute(stmt)).scalars().all())

    async def items_of_document(
        self, project_key: str, document_id: str,
    ) -> list[tuple[int, str, str]]:
        """(pk, local_id, title) of the items of the project that link the document."""
        stmt = (
            select(Item.pk, Item.local_id, Item.title)
            .join(ItemDocument, ItemDocument.item_pk == Item.pk)
            .where(Item.project_key == project_key, ItemDocument.document_id == document_id)
            .order_by(Item.local_id)
        )
        rows = (await self._s.execute(stmt)).all()
        return [(pk, local_id, title) for pk, local_id, title in rows]

    async def counts_by_document(self, project_key: str) -> dict[str, int]:
        stmt = (
            select(ItemDocument.document_id, func.count())
            .join(Item, Item.pk == ItemDocument.item_pk)
            .where(Item.project_key == project_key, Item.deleted_at.is_(None))
            .group_by(ItemDocument.document_id)
        )
        return {document_id: count for document_id, count in (await self._s.execute(stmt)).all()}
