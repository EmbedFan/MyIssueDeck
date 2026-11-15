"""FEA-0006: the in-process event bus."""

import asyncio

import pytest

from issuedeck.core import events
from issuedeck.core.events import ALL_PROJECTS, EVENT_CATEGORIES, EventBus


@pytest.fixture
def bus():
    fresh = EventBus()
    previous = events.set_bus(fresh)
    yield fresh
    events.set_bus(previous)


def test_published_events_reach_every_subscriber_in_order():
    bus = EventBus()
    first, second = bus.subscribe(), bus.subscribe()

    bus.publish("item.created", "a", ["FEAT-0001"])
    bus.publish("item.updated", "a", ["FEAT-0001"])

    for queue in (first, second):
        got = [queue.get_nowait(), queue.get_nowait()]
        assert [e["type"] for e in got] == ["item.created", "item.updated"]
        assert got[0]["id"] < got[1]["id"]


def test_events_carry_identifiers_only():
    bus = EventBus()
    queue = bus.subscribe()

    bus.publish("session.updated", "a", ["FEAT-0001"], session_id=7)

    event = queue.get_nowait()
    assert set(event) == {"id", "type", "project_key", "local_ids", "at", "session_id"}
    assert event["project_key"] == "a"
    assert event["local_ids"] == ["FEAT-0001"]
    assert event["session_id"] == 7


def test_default_project_means_every_project_and_empty_ids_are_dropped():
    bus = EventBus()
    queue = bus.subscribe()

    bus.publish("relationship.changed", local_ids=["", "FEAT-0002", None])

    event = queue.get_nowait()
    assert event["project_key"] == ALL_PROJECTS
    assert event["local_ids"] == ["FEAT-0002"]


def test_unsubscribed_queues_get_nothing():
    bus = EventBus()
    queue = bus.subscribe()
    bus.unsubscribe(queue)

    bus.publish("item.created", "a", ["X-1"])

    assert queue.empty()
    assert bus.subscriber_count == 0


def test_a_slow_subscriber_is_told_to_resync_instead_of_blocking_publishers():
    bus = EventBus()
    queue = bus.subscribe()

    for index in range(501):  # one more than the queue holds; publishing never blocks
        bus.publish("item.updated", "a", [f"FEAT-{index}"])

    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    assert seen[-1]["type"] == "resync"
    assert len(seen) < 501  # what the client had not read was dropped


def test_close_ends_every_stream_but_new_subscribers_still_work():
    bus = EventBus()
    queue = bus.subscribe()

    bus.close()

    assert queue.get_nowait() is None
    assert bus.subscriber_count == 0
    later = bus.subscribe()
    bus.publish("item.created", "a", ["X-1"])
    assert later.get_nowait()["type"] == "item.created"


def test_module_publish_uses_the_current_bus_and_never_raises(bus):
    queue = bus.subscribe()

    events.publish("activity.added", "a", ["FEAT-0003"])

    assert queue.get_nowait()["type"] == "activity.added"

    class Broken(EventBus):
        def publish(self, *args, **kwargs):
            raise RuntimeError("boom")

    events.set_bus(Broken())
    events.publish("item.created", "a", ["X-1"])  # must not raise


def test_every_event_type_has_a_category_the_settings_know():
    assert set(EVENT_CATEGORIES.values()) == {"items", "sessions", "activity"}
    assert EVENT_CATEGORIES["session.started"] == "sessions"
    assert EVENT_CATEGORIES["activity.added"] == "activity"
    assert EVENT_CATEGORIES["item.shipped"] == "items"


async def test_a_waiting_consumer_wakes_up_when_an_event_arrives():
    bus = EventBus()
    queue = bus.subscribe()

    async def publish_soon():
        await asyncio.sleep(0.01)
        bus.publish("item.created", "a", ["X-1"])

    task = asyncio.create_task(publish_soon())
    event = await asyncio.wait_for(queue.get(), timeout=1)
    await task

    assert event["type"] == "item.created"
