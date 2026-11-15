"""Notice changes made behind the server's back (FEA-0006).

Writes made through the server publish their own events. Writes made by another
process, such as the CLI, or by code that bypasses the services (imports), do not.
The watcher compares a cheap fingerprint of the tables the views show and
publishes one generic ``project.changed`` event when it moved without any event
having been published. It does nothing while nobody is watching.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.events import ALL_PROJECTS, EventBus
from issuedeck.features.items.models import (
    Item,
    ItemEvent,
    ItemRelationship,
    WorkSession,
    WorkSessionUpdate,
)

log = logging.getLogger("issuedeck.live")


async def fingerprint(session: AsyncSession) -> tuple[Any, ...]:
    """A value that changes whenever the data shown by the views changes."""
    items = (await session.execute(
        select(func.count(), func.coalesce(func.max(Item.updated_at), "")).select_from(Item)
    )).one()
    sessions = (await session.execute(
        select(func.count(), func.coalesce(func.max(WorkSession.updated_at), ""))
        .select_from(WorkSession)
    )).one()
    last_event = (await session.execute(
        select(func.coalesce(func.max(ItemEvent.id), 0))
    )).scalar_one()
    last_update = (await session.execute(
        select(func.coalesce(func.max(WorkSessionUpdate.id), 0))
    )).scalar_one()
    relationships = (await session.execute(
        select(func.count()).select_from(ItemRelationship)
    )).scalar_one()
    return (tuple(items), tuple(sessions), last_event, last_update, relationships)


class ChangeWatcher:
    def __init__(self, session_factory, bus: EventBus, interval: float = 2.0):
        self._session_factory = session_factory
        self._bus = bus
        self._interval = interval
        self._last: tuple[Any, ...] | None = None
        self._published_seen = bus.published

    async def tick(self) -> bool:
        """Check once; returns True when a ``project.changed`` event was published."""
        if self._bus.subscriber_count == 0:
            self._last = None  # nobody is watching: start from a fresh fingerprint later
            return False
        async with self._session_factory() as session:
            current = await fingerprint(session)
        published_meanwhile = self._bus.published != self._published_seen
        self._published_seen = self._bus.published
        changed = self._last is not None and current != self._last
        self._last = current
        if changed and not published_meanwhile:
            self._bus.publish("project.changed", ALL_PROJECTS)
            self._published_seen = self._bus.published
            return True
        return False

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # keep watching after a transient database error
                log.exception("live change watcher failed")
            await asyncio.sleep(self._interval)
