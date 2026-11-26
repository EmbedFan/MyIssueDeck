"""Linking images of the store to items (FEA-0013, phase 4).

A link says "this item uses this image"; it is kept in the database (``item_images``) while the
image stays in the image store. Deleting an image removes its links first, and every link
change is written to the item's activity.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core import events as live_events
from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import ImageNotFound, ItemNotFound
from issuedeck.features.images.link_repo import ItemImageRepo
from issuedeck.features.images.service import ImageService
from issuedeck.features.items.repo import ItemRepo


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class ItemImageService:
    def __init__(
        self, images: ImageService, item_repo: ItemRepo, link_repo: ItemImageRepo,
        registry: ConfigRegistry, session: AsyncSession,
    ):
        self._images = images
        self._items = item_repo
        self._links = link_repo
        self._reg = registry
        self._s = session

    async def _item(self, project_key: str, local_id: str):
        self._reg.project(project_key)
        item = await self._items.get_by_local_id(project_key, local_id)
        if item is None:
            raise ItemNotFound(
                f"item {local_id} not found",
                details={"project_key": project_key, "local_id": local_id},
            )
        return item

    async def _event(self, item_pk: int, event_type: str, body: str,
                     image_id: str, actor: str) -> None:
        await self._items.add_event(
            item_pk=item_pk, event_type=event_type, actor_type="system",
            actor_name="issuedeck", body=body,
            metadata_json=json.dumps({"image_id": image_id, "actor": actor}),
            created_at=_iso_now(),
        )

    async def link(self, project_key: str, local_id: str, image_id: str,
                   actor: str = "api") -> dict[str, Any]:
        item = await self._item(project_key, local_id)
        entry = self._images.get(project_key, image_id)  # raises ImageNotFound
        if not await self._links.exists(item.pk, image_id):  # linking twice is harmless
            await self._links.add(item.pk, image_id, _iso_now())
            await self._event(item.pk, "image_linked", f"Linked image {image_id}.",
                              image_id, actor)
            await self._s.commit()
            live_events.publish("item.updated", project_key, [local_id])
        return entry

    async def unlink(self, project_key: str, local_id: str, image_id: str,
                     actor: str = "api") -> None:
        item = await self._item(project_key, local_id)
        if not await self._links.remove(item.pk, image_id):
            raise ImageNotFound(
                f"image {image_id} is not linked to {local_id}",
                details={"project_key": project_key, "local_id": local_id,
                         "image_id": image_id},
            )
        await self._event(item.pk, "image_unlinked", f"Removed the link to image {image_id}.",
                          image_id, actor)
        await self._s.commit()
        live_events.publish("item.updated", project_key, [local_id])

    async def list(self, project_key: str, local_id: str) -> list[dict[str, Any]]:
        """The linked images that are still in the store, by id."""
        item = await self._item(project_key, local_id)
        known = {entry["id"]: entry for entry in self._images.list(project_key)["items"]}
        return [known[i] for i in await self._links.image_ids_of_item(item.pk) if i in known]

    async def counts(self, project_key: str) -> dict[str, int]:
        self._reg.project(project_key)
        return await self._links.counts_by_image(project_key)

    async def delete_image(self, project_key: str, image_id: str,
                           actor: str = "api") -> list[str]:
        """Delete an image and the links to it; returns the items that lost a link."""
        self._images.get(project_key, image_id)  # raises ImageNotFound before anything changes
        affected: list[str] = []
        for pk, local_id in await self._links.items_of_image(project_key, image_id):
            await self._links.remove(pk, image_id)
            await self._event(pk, "image_unlinked",
                              f"Image {image_id} was deleted; its link was removed.",
                              image_id, actor)
            affected.append(local_id)
        await self._s.commit()
        self._images.delete(project_key, image_id)
        if affected:
            live_events.publish("item.updated", project_key, affected)
        return affected
