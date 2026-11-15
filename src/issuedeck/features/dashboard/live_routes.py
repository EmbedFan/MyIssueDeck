"""Server-sent events for the live dashboard views (FEA-0006).

``GET /dashboard/events`` streams the events published on the in-process bus
(``core.events``). It sits behind the dashboard login like every other dashboard
page. Events carry identifiers only, so nothing secret or large is sent; the page
fetches what it shows again.

The router must be included before the dashboard router, because the dashboard has
a catch-all ``/dashboard/{project_key}`` route.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from issuedeck.core.events import EventBus, get_bus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

HEARTBEAT_SECONDS = 15.0


def format_sse(event: dict) -> str:
    """One event in the text/event-stream format."""
    payload = json.dumps(event, separators=(",", ":"))
    return f"id: {event['id']}\nevent: message\ndata: {payload}\n\n"


async def event_stream(
    bus: EventBus,
    *,
    heartbeat: float = HEARTBEAT_SECONDS,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """Yield the stream text: a greeting, then events, with comment lines as heartbeat.

    Ends when the bus is closed (server shutdown) or the client has gone away.
    """
    queue = bus.subscribe()
    try:
        yield "retry: 3000\n\n"
        yield ": connected\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat)
            except TimeoutError:
                if is_disconnected is not None and await is_disconnected():
                    break
                yield ": ping\n\n"
                continue
            if event is None:
                break
            yield format_sse(event)
    finally:
        bus.unsubscribe(queue)


@router.get("/events")
async def dashboard_events(request: Request):
    return StreamingResponse(
        event_stream(get_bus(), is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # tell reverse proxies not to buffer the stream
        },
    )
