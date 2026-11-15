"""FEA-0006: noticing changes made behind the server's back (CLI, imports)."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.events import ALL_PROJECTS, EventBus
from issuedeck.core.live_watch import ChangeWatcher, fingerprint
from issuedeck.features.items.models import Base, Item, ItemEvent


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _item(local_id: str, updated_at: str = "2026-01-01T00:00:00+00:00") -> Item:
    return Item(
        project_key="a", local_id=local_id, kind="feature", status="proposed",
        title=local_id, created_at=updated_at, updated_at=updated_at,
    )


async def _write(session_factory, *rows):
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()


async def test_fingerprint_changes_when_the_data_changes(session_factory):
    async with session_factory() as session:
        empty = await fingerprint(session)

    await _write(session_factory, _item("FEAT-0001"))

    async with session_factory() as session:
        assert await fingerprint(session) != empty


async def test_nothing_is_checked_while_nobody_is_watching(session_factory):
    bus = EventBus()
    watcher = ChangeWatcher(session_factory, bus)

    assert await watcher.tick() is False
    await _write(session_factory, _item("FEAT-0001"))
    assert await watcher.tick() is False
    assert bus.published == 0


async def test_a_change_made_behind_the_servers_back_publishes_one_event(session_factory):
    bus = EventBus()
    queue = bus.subscribe()
    watcher = ChangeWatcher(session_factory, bus)
    assert await watcher.tick() is False  # first look: only a baseline

    await _write(session_factory, _item("FEAT-0001"))  # e.g. written by the CLI

    assert await watcher.tick() is True
    event = queue.get_nowait()
    assert event["type"] == "project.changed"
    assert event["project_key"] == ALL_PROJECTS
    assert await watcher.tick() is False  # nothing new since
    assert queue.empty()


async def test_changes_that_already_published_their_own_event_are_not_repeated(session_factory):
    bus = EventBus()
    queue = bus.subscribe()
    watcher = ChangeWatcher(session_factory, bus)
    await watcher.tick()

    await _write(session_factory, _item("FEAT-0001"))
    bus.publish("item.created", "a", ["FEAT-0001"])  # what the service would have done

    assert await watcher.tick() is False
    assert [queue.get_nowait()["type"]] == ["item.created"]
    assert queue.empty()


async def test_new_activity_entries_and_edits_are_noticed(session_factory):
    bus = EventBus()
    bus.subscribe()
    item = _item("FEAT-0001")
    await _write(session_factory, item)
    watcher = ChangeWatcher(session_factory, bus)
    await watcher.tick()

    async with session_factory() as session:
        session.add(ItemEvent(
            item_pk=item.pk, event_type="comment", actor_type="agent", actor_name="x",
            body="hi", created_at="2026-01-02T00:00:00+00:00",
        ))
        await session.commit()
    assert await watcher.tick() is True

    async with session_factory() as session:
        stored = await session.get(Item, item.pk)
        stored.updated_at = "2026-01-03T00:00:00+00:00"
        await session.commit()
    assert await watcher.tick() is True


async def test_after_everyone_left_the_watcher_starts_from_a_fresh_baseline(session_factory):
    bus = EventBus()
    queue = bus.subscribe()
    watcher = ChangeWatcher(session_factory, bus)
    await watcher.tick()
    bus.unsubscribe(queue)
    await watcher.tick()
    await _write(session_factory, _item("FEAT-0001"))  # changed while nobody watched

    bus.subscribe()

    assert await watcher.tick() is False  # a new viewer loads the current page anyway
