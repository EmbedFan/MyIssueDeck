"""In-process event bus for live dashboard updates (FEA-0006).

Services publish a small event after a change has been committed; the dashboard's
server-sent-events endpoint forwards the events to the open views, which then
fetch what they show again. Events carry identifiers only (type, project, item
ids, session id, time), never item content or secrets.

The bus lives in the server process. Changes written by another process (the CLI)
are noticed by ``core.live_watch`` instead.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from datetime import UTC, datetime
from typing import Any

#: Event types and the settings category that decides whether a view follows them.
EVENT_CATEGORIES: dict[str, str] = {
    "item.created": "items",
    "item.updated": "items",
    "item.shipped": "items",
    "item.deleted": "items",
    "item.restored": "items",
    "relationship.changed": "items",
    "project.changed": "items",
    "session.started": "sessions",
    "session.updated": "sessions",
    "session.finished": "sessions",
    "activity.added": "activity",
}

#: Project key used by events that concern every project (changes seen by the watcher).
ALL_PROJECTS = "*"

_MAX_QUEUE = 500


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._ids = itertools.count(1)
        self.published = 0
        self.last_published_at = 0.0

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(
        self,
        type: str,
        project_key: str = ALL_PROJECTS,
        local_ids: list[str] | tuple[str, ...] = (),
        **extra: Any,
    ) -> dict[str, Any]:
        event = {
            "id": next(self._ids),
            "type": type,
            "project_key": project_key,
            "local_ids": [i for i in local_ids if i],
            "at": datetime.now(UTC).isoformat(),
            **extra,
        }
        self.published += 1
        self.last_published_at = time.monotonic()
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A slow client: drop what it has not read and tell it to resync.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({**event, "type": "resync", "local_ids": []})
        return event

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def close(self) -> None:
        """End every open stream (server shutdown). New subscriptions are still allowed."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
        self._subscribers.clear()


_bus = EventBus()


def get_bus() -> EventBus:
    return _bus


def set_bus(bus: EventBus) -> EventBus:
    """Replace the process-wide bus (tests); returns the previous one."""
    global _bus
    previous, _bus = _bus, bus
    return previous


def publish(type: str, project_key: str = ALL_PROJECTS, local_ids=(), **extra: Any) -> None:
    """Publish on the process-wide bus. Never raises: a live update must not break a write."""
    try:
        _bus.publish(type, project_key, local_ids, **extra)
    except Exception:  # pragma: no cover - defensive
        pass
