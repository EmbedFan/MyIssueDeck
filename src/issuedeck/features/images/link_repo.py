"""Data access for item_images: which image of the store is linked to which item (FEA-0013)."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.features.items.models import Item, ItemImage


class ItemImageRepo:
    def __init__(self, session: AsyncSession):
        self._s = session

    async def exists(self, item_pk: int, image_id: str) -> bool:
        stmt = select(ItemImage).where(
            ItemImage.item_pk == item_pk, ItemImage.image_id == image_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def add(self, item_pk: int, image_id: str, created_at: str) -> None:
        self._s.add(ItemImage(item_pk=item_pk, image_id=image_id, created_at=created_at))
        await self._s.flush()

    async def remove(self, item_pk: int, image_id: str) -> bool:
        result = await self._s.execute(delete(ItemImage).where(
            ItemImage.item_pk == item_pk, ItemImage.image_id == image_id,
        ))
        return (result.rowcount or 0) > 0

    async def image_ids_of_item(self, item_pk: int) -> list[str]:
        stmt = select(ItemImage.image_id).where(ItemImage.item_pk == item_pk)
        return sorted((await self._s.execute(stmt)).scalars().all())

    async def items_of_image(self, project_key: str, image_id: str) -> list[tuple[int, str]]:
        """(pk, local_id) of the items of the project that link the image."""
        stmt = (
            select(Item.pk, Item.local_id)
            .join(ItemImage, ItemImage.item_pk == Item.pk)
            .where(Item.project_key == project_key, ItemImage.image_id == image_id)
            .order_by(Item.local_id)
        )
        return [(pk, local_id) for pk, local_id in (await self._s.execute(stmt)).all()]

    async def counts_by_image(self, project_key: str) -> dict[str, int]:
        stmt = (
            select(ItemImage.image_id, func.count())
            .join(Item, Item.pk == ItemImage.item_pk)
            .where(Item.project_key == project_key, Item.deleted_at.is_(None))
            .group_by(ItemImage.image_id)
        )
        return {image_id: count for image_id, count in (await self._s.execute(stmt)).all()}
