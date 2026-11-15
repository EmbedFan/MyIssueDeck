"""FEA-0006: the server-sent events stream."""

import asyncio
import json

from issuedeck.core.events import EventBus
from issuedeck.features.dashboard.live_routes import event_stream, format_sse


def test_event_format_follows_the_event_stream_protocol():
    text = format_sse({"id": 5, "type": "item.updated", "project_key": "a"})

    assert text.startswith("id: 5\nevent: message\ndata: ")
    assert text.endswith("\n\n")
    data = text.split("data: ", 1)[1].strip()
    assert json.loads(data) == {"id": 5, "type": "item.updated", "project_key": "a"}
    assert "\n" not in data  # one line: an event never spans lines


async def _collect(stream, limit=20):
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
        if len(chunks) >= limit:
            break
    return chunks


async def test_stream_greets_forwards_events_and_ends_when_the_bus_closes():
    bus = EventBus()
    stream = event_stream(bus, heartbeat=5)

    async def drive():
        await asyncio.sleep(0.02)
        bus.publish("item.created", "a", ["FEAT-0001"])
        bus.publish("session.started", "a", ["FEAT-0001"], session_id=3)
        await asyncio.sleep(0.02)
        bus.close()

    task = asyncio.create_task(drive())
    chunks = await asyncio.wait_for(_collect(stream), timeout=2)
    await task

    assert chunks[0] == "retry: 3000\n\n"
    assert chunks[1].startswith(":")  # a comment line, ignored by EventSource
    events = [json.loads(c.split("data: ", 1)[1]) for c in chunks if "data: " in c]
    assert [e["type"] for e in events] == ["item.created", "session.started"]
    assert events[1]["session_id"] == 3
    assert bus.subscriber_count == 0  # unsubscribed when the stream ended


async def test_stream_sends_a_heartbeat_when_idle_and_stops_when_the_client_is_gone():
    bus = EventBus()
    calls = {"count": 0}

    async def gone():
        calls["count"] += 1
        return calls["count"] >= 2  # connected for one heartbeat, then disconnected

    chunks = await asyncio.wait_for(
        _collect(event_stream(bus, heartbeat=0.02, is_disconnected=gone)), timeout=2,
    )

    assert ": ping\n\n" in chunks
    assert bus.subscriber_count == 0


async def test_a_stream_that_is_abandoned_unsubscribes():
    bus = EventBus()
    stream = event_stream(bus, heartbeat=5)
    await stream.__anext__()  # greeting
    assert bus.subscriber_count == 1

    await stream.aclose()

    assert bus.subscriber_count == 0
