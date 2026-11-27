"""Linking documents of the store to items (FEA-0012, phase 5).

A link says "this item uses this document"; it is kept in the database (``item_documents``) while
the document stays in the document store. Deleting a document removes its links first, and every
link change is written to the item's activity.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core import events as live_events
from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import DocumentNotFound, ItemNotFound
from issuedeck.features.documents.link_repo import ItemDocumentRepo
from issuedeck.features.documents.service import DocumentService, summary
from issuedeck.features.items.repo import ItemRepo


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class ItemDocumentService:
    def __init__(
        self, documents: DocumentService, item_repo: ItemRepo, link_repo: ItemDocumentRepo,
        registry: ConfigRegistry, session: AsyncSession,
    ):
        self._documents = documents
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
                     document_id: str, actor: str) -> None:
        await self._items.add_event(
            item_pk=item_pk, event_type=event_type, actor_type="system",
            actor_name="issuedeck", body=body,
            metadata_json=json.dumps({"document_id": document_id, "actor": actor}),
            created_at=_iso_now(),
        )

    async def link(self, project_key: str, local_id: str, document_id: str,
                   actor: str = "api") -> dict[str, Any]:
        item = await self._item(project_key, local_id)
        document = self._documents.get(project_key, document_id)  # raises DocumentNotFound
        if not await self._links.exists(item.pk, document_id):  # linking twice is harmless
            await self._links.add(item.pk, document_id, _iso_now())
            await self._event(item.pk, "document_linked",
                              f"Linked document {document_id} ({document['name']}).",
                              document_id, actor)
            await self._s.commit()
            live_events.publish("item.updated", project_key, [local_id])
        return summary(document)

    async def unlink(self, project_key: str, local_id: str, document_id: str,
                     actor: str = "api") -> None:
        item = await self._item(project_key, local_id)
        if not await self._links.remove(item.pk, document_id):
            raise DocumentNotFound(
                f"document {document_id} is not linked to {local_id}",
                details={"project_key": project_key, "local_id": local_id,
                         "document_id": document_id},
            )
        await self._event(item.pk, "document_unlinked",
                          f"Removed the link to document {document_id}.", document_id, actor)
        await self._s.commit()
        live_events.publish("item.updated", project_key, [local_id])

    async def list(self, project_key: str, local_id: str) -> list[dict[str, Any]]:
        """The linked documents that are still in the store, by id."""
        item = await self._item(project_key, local_id)
        known = {d["id"]: d for d in self._documents.list(project_key)}
        return [known[i] for i in await self._links.document_ids_of_item(item.pk) if i in known]

    async def counts(self, project_key: str) -> dict[str, int]:
        self._reg.project(project_key)
        return await self._links.counts_by_document(project_key)

    async def items_of(self, project_key: str, document_id: str) -> list[dict[str, str]]:
        """The items that link the document: local id and title."""
        self._reg.project(project_key)
        rows = await self._links.items_of_document(project_key, document_id)
        return [{"local_id": local_id, "title": title} for _pk, local_id, title in rows]

    async def delete_document(self, project_key: str, document_id: str,
                              actor: str = "api") -> list[str]:
        """Delete a document and the links to it; returns the items that lost a link."""
        document = self._documents.get(project_key, document_id)  # raises before any change
        affected: list[str] = []
        for pk, local_id, _title in await self._links.items_of_document(
                project_key, document_id):
            await self._links.remove(pk, document_id)
            await self._event(
                pk, "document_unlinked",
                f"Document {document_id} ({document['name']}) was deleted; "
                "its link was removed.", document_id, actor)
            affected.append(local_id)
        await self._s.commit()
        self._documents.delete(project_key, document_id)
        if affected:
            live_events.publish("item.updated", project_key, affected)
        return affected
