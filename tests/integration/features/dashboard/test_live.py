"""FEA-0006: agent sessions widget, live events and the pages' live configuration."""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core import events as live_events
from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import install_error_handlers
from issuedeck.core.events import EventBus
from issuedeck.core.runtime_settings import RuntimeSettings
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE
from issuedeck.features.dashboard.live_routes import router as live_router
from issuedeck.features.dashboard.routes import _record_import_batch
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.dashboard.settings_routes import router as settings_router
from issuedeck.features.items.models import Base, WorkSession
from issuedeck.features.items.routes import router as items_router
from issuedeck.features.relationships.routes import router as relationships_router
from issuedeck.features.work_sessions.routes import router as work_sessions_router


def _project(key: str) -> ProjectConfig:
    return ProjectConfig(
        key=key,
        name=f"Project {key}",
        kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
        statuses={
            "proposed": StatusConfig(label="Proposed"),
            "done": StatusConfig(label="Done", terminal=True, requires_ship=True),
        },
        branches=[BranchConfig(key="main", label="Main")],
    )


@pytest.fixture
def bus():
    fresh = EventBus()
    previous = live_events.set_bus(fresh)
    yield fresh
    live_events.set_bus(previous)


@pytest.fixture
async def env(tmp_path, bus):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    registry = ConfigRegistry(
        server=ServerConfig(api_token="t", data_dir=tmp_path / "data"),
        projects={"a": _project("a"), "b": _project("b")},
    )
    runtime = RuntimeSettings(tmp_path / "data")

    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    app.state.runtime_settings = runtime
    install_error_handlers(app)
    for router in (
        settings_router, live_router, dashboard_router, items_router,
        work_sessions_router, relationships_router,
    ):
        app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield {"client": client, "runtime": runtime, "Session": Session, "bus": bus}
    await engine.dispose()


def drain(queue):
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


async def make_item(client, project="a", title="x", **extra):
    r = await client.post(
        f"/api/v1/projects/{project}/items", json={"kind": "feature", "title": title, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()["local_id"]


async def start_session(client, local_id, project="a", agent="agent-1", goal="do things"):
    r = await client.post(
        f"/api/v1/projects/{project}/work-sessions",
        json={"local_id": local_id, "agent_name": agent, "goal": goal},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- events from every write path ------------------------------------------------------


async def test_item_changes_publish_events(env):
    client, queue = env["client"], env["bus"].subscribe()

    local_id = await make_item(client)
    await client.patch(f"/api/v1/projects/a/items/{local_id}", json={"title": "new"})
    await client.post(
        f"/api/v1/projects/a/items/{local_id}/ship", json={"branch": "main", "version": "1"},
    )
    await client.delete(f"/api/v1/projects/a/items/{local_id}")
    await client.post(f"/api/v1/projects/a/items/{local_id}/restore")

    got = drain(queue)
    assert [e["type"] for e in got] == [
        "item.created", "item.updated", "item.shipped", "item.deleted", "item.restored",
    ]
    assert all(e["project_key"] == "a" and e["local_ids"] == [local_id] for e in got)


async def test_bulk_updates_publish_one_event_per_item(env):
    client = env["client"]
    ids = [await make_item(client, title=str(n)) for n in range(2)]
    queue = env["bus"].subscribe()

    r = await client.post(
        "/api/v1/projects/a/items/bulk",
        json={"action": "update", "local_ids": ids, "tags": ["x"]},
    )

    assert r.status_code == 200, r.text
    got = drain(queue)
    assert sorted(i for e in got for i in e["local_ids"]) == sorted(ids)
    assert {e["type"] for e in got} == {"item.updated"}


async def test_activity_entries_publish_an_event(env):
    client = env["client"]
    local_id = await make_item(client)
    queue = env["bus"].subscribe()

    r = await client.post(
        f"/dashboard/a/items/{local_id}/events", data={"body": "a note"}, follow_redirects=False,
    )

    assert r.status_code in (200, 303)
    got = drain(queue)
    assert [e["type"] for e in got] == ["activity.added"]
    assert got[0]["local_ids"] == [local_id]


async def test_relationship_changes_publish_events(env):
    client = env["client"]
    one, two = await make_item(client, title="1"), await make_item(client, title="2")
    queue = env["bus"].subscribe()

    added = await client.post(
        f"/api/v1/projects/a/items/{one}/relationships",
        json={"to_local_id": two, "relation_type": "related_to"},
    )
    removed = await client.delete(f"/api/v1/projects/a/relationships/{added.json()['rel_id']}")

    assert removed.status_code == 204
    first, second = drain(queue)
    assert first["type"] == "relationship.changed"
    assert first["project_key"] == "a" and first["local_ids"] == [one, two]
    assert second["type"] == "relationship.changed" and second["project_key"] == "*"


async def test_work_sessions_publish_events_with_the_session_id(env):
    client = env["client"]
    local_id = await make_item(client)
    queue = env["bus"].subscribe()

    session_id = await start_session(client, local_id)
    await client.post(
        f"/api/v1/projects/a/work-sessions/{session_id}/updates", json={"message": "progress"},
    )
    await client.post(f"/api/v1/projects/a/work-sessions/{session_id}/finish", json={})

    got = drain(queue)
    types = [e["type"] for e in got]
    assert types.count("session.started") == 1
    assert types.count("session.updated") == 1
    assert types.count("session.finished") == 1
    for e in got:
        if e["type"].startswith("session."):
            assert e["session_id"] == session_id and e["local_ids"] == [local_id]


async def test_a_failed_write_publishes_nothing(env):
    queue = env["bus"].subscribe()

    r = await env["client"].post(
        "/api/v1/projects/a/items", json={"kind": "nonsense", "title": "x"},
    )

    assert r.status_code == 422
    assert drain(queue) == []


async def test_imports_publish_a_project_changed_event(env):
    queue = env["bus"].subscribe()

    async with env["Session"]() as session:
        await _record_import_batch(
            session, project_key="a", batch_tag="t", source_type="csv",
            source_name="x.csv", items_planned=2, items_written=2,
        )

    got = drain(queue)
    assert [e["type"] for e in got] == ["project.changed"]
    assert got[0]["project_key"] == "a"


async def test_an_import_that_wrote_nothing_publishes_nothing(env):
    queue = env["bus"].subscribe()

    async with env["Session"]() as session:
        await _record_import_batch(
            session, project_key="a", batch_tag="t", source_type="csv",
            source_name="x.csv", items_planned=2, items_written=0,
        )

    assert drain(queue) == []


# --- the stream endpoint ---------------------------------------------------------------


async def test_the_events_endpoint_streams_published_events(env):
    client, bus = env["client"], env["bus"]
    request = asyncio.create_task(client.get("/dashboard/events"))
    for _ in range(100):
        if bus.subscriber_count:
            break
        await asyncio.sleep(0.01)
    assert bus.subscriber_count == 1

    bus.publish("item.created", "a", ["FEAT-0001"])
    bus.publish("session.started", "a", ["FEAT-0001"], session_id=4)
    bus.close()
    response = await asyncio.wait_for(request, timeout=3)

    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    assert body.startswith("retry: 3000")
    sent = [json.loads(m) for m in re.findall(r"^data: (.*)$", body, re.M)]
    assert [e["type"] for e in sent] == ["item.created", "session.started"]


# --- the widget -----------------------------------------------------------------------


async def test_the_widget_is_on_the_overview_but_not_on_the_kanban_board_by_default(env):
    client = env["client"]

    overview = await client.get("/dashboard/a")
    kanban = await client.get("/dashboard/a/kanban")

    assert "data-agent-widget" in overview.text
    assert "data-agent-widget" not in kanban.text


async def test_switching_the_widget_on_for_kanban_and_off_for_the_overview(env):
    client = env["client"]
    local_id = await make_item(client, title="Widget item")
    await start_session(client, local_id, goal="visible goal")

    r = await client.post(
        "/dashboard/settings/agent-widget",
        data={"show_kanban": "1", "statuses": ["active", "paused"], "completed_minutes": "0",
              "max_sessions": "8", "scope": "project", "initial_state": "expanded",
              "info_agent": "1", "info_item": "1", "info_goal": "1",
              "info_last_update": "1", "info_updates": "1"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    kanban = await client.get("/dashboard/a/kanban")
    assert "data-agent-widget" in kanban.text
    assert "visible goal" in kanban.text
    assert f'href="/dashboard/a/items/{local_id}"' in kanban.text
    overview = await client.get("/dashboard/a")
    assert "data-agent-widget" not in overview.text  # show_overview was not ticked


async def test_the_widget_is_hidden_without_leaving_any_space(env):
    env["runtime"].update_settings({"agent_widget": {"show_overview": False}})

    page = await env["client"].get("/dashboard/a")

    assert "data-agent-widget" not in page.text
    assert "No active agent work sessions" not in page.text


async def test_the_widget_shows_an_empty_text_when_there_is_no_session(env):
    page = await env["client"].get("/dashboard/a")

    assert "data-agent-widget" in page.text
    assert "No active agent work sessions" in page.text


async def test_statuses_filter_which_sessions_are_listed(env):
    client = env["client"]
    one = await make_item(client, title="one")
    two = await make_item(client, title="two")
    await start_session(client, one, agent="runner")
    paused = await start_session(client, two, agent="sleeper")
    await client.post(
        f"/api/v1/projects/a/work-sessions/{paused}/updates",
        json={"message": "pausing", "status": "paused"},
    )

    env["runtime"].update_settings({"agent_widget": {"statuses": ["paused"]}})
    only_paused = await client.get("/dashboard/a")
    env["runtime"].update_settings({"agent_widget": {"statuses": ["active"]}})
    only_active = await client.get("/dashboard/a")

    assert "sleeper" in only_paused.text and "runner" not in only_paused.text
    assert "runner" in only_active.text and "sleeper" not in only_active.text


async def test_completed_sessions_appear_only_within_the_chosen_window(env):
    client = env["client"]
    recent_item = await make_item(client, title="recent")
    old_item = await make_item(client, title="old")
    recent = await start_session(client, recent_item, agent="fresh-agent")
    old = await start_session(client, old_item, agent="stale-agent")
    for session_id in (recent, old):
        await client.post(f"/api/v1/projects/a/work-sessions/{session_id}/finish", json={})
    two_hours_ago = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    async with env["Session"]() as session:
        await session.execute(
            update(WorkSession).where(WorkSession.id == old)
            .values(ended_at=two_hours_ago, updated_at=two_hours_ago)
        )
        await session.commit()

    default = await client.get("/dashboard/a")
    env["runtime"].update_settings({"agent_widget": {"completed_minutes": 10}})
    ten_minutes = await client.get("/dashboard/a")
    env["runtime"].update_settings({"agent_widget": {"completed_minutes": 240}})
    four_hours = await client.get("/dashboard/a")

    assert "fresh-agent" not in default.text and "stale-agent" not in default.text
    assert "fresh-agent" in ten_minutes.text and "stale-agent" not in ten_minutes.text
    assert "fresh-agent" in four_hours.text and "stale-agent" in four_hours.text


async def test_the_maximum_number_of_sessions_is_respected(env):
    client = env["client"]
    for n in range(3):
        await start_session(client, await make_item(client, title=str(n)), agent=f"agent-{n}")

    env["runtime"].update_settings({"agent_widget": {"max_sessions": 2}})
    page = await client.get("/dashboard/a")

    assert len(re.findall(r'data-live-key="session-a-', page.text)) == 2
    assert "agent-2" in page.text  # the newest are kept


async def test_scope_all_lists_the_sessions_of_every_project(env):
    client = env["client"]
    await start_session(client, await make_item(client, "a"), project="a", agent="in-a")
    await start_session(client, await make_item(client, "b"), project="b", agent="in-b")

    project_only = await client.get("/dashboard/a")
    env["runtime"].update_settings({"agent_widget": {"scope": "all"}})
    everything = await client.get("/dashboard/a")

    assert "in-a" in project_only.text and "in-b" not in project_only.text
    assert "in-a" in everything.text and "in-b" in everything.text
    assert '>b</span>' in everything.text  # the project key is shown next to the entry
    assert "/dashboard/b/items/" in everything.text


async def test_the_details_shown_for_a_session_follow_the_settings(env):
    client = env["client"]
    await start_session(
        client, await make_item(client, title="Item title"),
        agent="agent-name", goal="the goal text",
    )

    everything = await client.get("/dashboard/a")
    env["runtime"].update_settings(
        {"agent_widget": {"info": {"agent": False, "goal": False, "updates": False}}},
    )
    trimmed = await client.get("/dashboard/a")

    for text in ("agent-name", "the goal text", "Item title"):
        assert text in everything.text
    assert "agent-name" not in trimmed.text and "the goal text" not in trimmed.text
    assert "Item title" in trimmed.text  # still on
    assert "updates" not in trimmed.text.split("data-agent-widget", 1)[1].split("</section>", 1)[0]


async def test_the_initial_state_can_be_collapsed(env):
    expanded = await env["client"].get("/dashboard/a")
    env["runtime"].update_settings({"agent_widget": {"initial_state": "collapsed"}})
    collapsed = await env["client"].get("/dashboard/a")

    assert re.search(r'<details class="group" open>', expanded.text)
    assert re.search(r'<details class="group" >', collapsed.text)


async def test_the_widget_follows_the_selected_language(env):
    env["client"].cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    page = await env["client"].get("/dashboard/a")

    assert "data-agent-widget" in page.text
    assert "Nincs aktív ügynöki munkamenet" in page.text


# --- live configuration and regions on the pages ---------------------------------------


def live_config(page_text: str):
    match = re.search(r'<script type="application/json" id="live-config">(.*?)</script>',
                      page_text, re.S)
    return json.loads(match.group(1)) if match else None


async def test_every_followed_view_carries_its_live_configuration(env):
    client = env["client"]
    local_id = await make_item(client)

    expected = {
        "/dashboard/a": "overview",
        "/dashboard/a/kanban": "kanban",
        "/dashboard/a/list": "list",
        f"/dashboard/a/items/{local_id}": "item",
    }
    for path, view in expected.items():
        page = await client.get(path)
        config = live_config(page.text)
        assert config is not None, path
        assert config["view"] == view and config["project_key"] == "a"
        assert "/dashboard/static/js/live.js" in page.text
    item_config = live_config((await client.get(f"/dashboard/a/items/{local_id}")).text)
    assert item_config["local_id"] == local_id


async def test_pages_that_do_not_follow_have_no_live_configuration(env):
    for path in ("/dashboard/settings", "/dashboard/a/items-new", "/dashboard/projects-new"):
        page = await env["client"].get(path)
        assert live_config(page.text) is None, path
        assert "/dashboard/static/js/live.js" not in page.text, path


async def test_the_configuration_carries_the_settings(env):
    env["runtime"].update_settings({"live": {
        "fallback_seconds": 45, "highlight_seconds": 7, "while_editing": "after_save",
        "events": {"activity": False},
    }})

    config = live_config((await env["client"].get("/dashboard/a/kanban")).text)

    assert config["fallback_seconds"] == 45 and config["highlight_seconds"] == 7
    assert config["while_editing"] == "after_save"
    assert config["events"] == {"items": True, "sessions": True, "activity": False}
    assert config["all_projects"] is False
    assert set(config["strings"]) == {"connecting", "connected", "offline", "notice", "apply"}


async def test_all_projects_is_announced_when_the_widget_shows_every_project(env):
    env["runtime"].update_settings({"agent_widget": {"scope": "all"}})

    config = live_config((await env["client"].get("/dashboard/a")).text)

    assert config["all_projects"] is True


async def test_live_updates_can_be_switched_off_completely(env):
    env["runtime"].update_settings({"live": {"enabled": False}})

    for path in ("/dashboard/a", "/dashboard/a/kanban", "/dashboard/a/list"):
        page = await env["client"].get(path)
        assert live_config(page.text) is None
        assert "/dashboard/static/js/live.js" not in page.text  # the script tag is absent
        assert 'id="live-indicator"' not in page.text


async def test_a_single_view_can_be_switched_off(env):
    env["runtime"].update_settings({"live": {"views": {"kanban": False}}})

    kanban = await env["client"].get("/dashboard/a/kanban")
    list_page = await env["client"].get("/dashboard/a/list")

    assert live_config(kanban.text) is None
    assert live_config(list_page.text) is not None


async def test_the_connection_indicator_can_be_hidden(env):
    shown = await env["client"].get("/dashboard/a")
    env["runtime"].update_settings({"live": {"indicator": False}})
    hidden = await env["client"].get("/dashboard/a")

    assert 'id="live-indicator"' in shown.text
    assert 'id="live-indicator"' not in hidden.text
    assert live_config(hidden.text) is not None  # still following, just not showing it


async def test_the_live_texts_follow_the_language(env):
    env["client"].cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    config = live_config((await env["client"].get("/dashboard/a")).text)

    assert config["strings"]["apply"] == "Módosítások alkalmazása"
    assert config["strings"]["connected"] == "Élő"


async def test_the_pages_mark_the_regions_that_are_swapped(env):
    client = env["client"]
    local_id = await make_item(client)
    expected = {
        "/dashboard/a": {"stats", "charts", "recent", "agent-sessions", "agent-sessions-count"},
        "/dashboard/a/kanban": {"board"},
        "/dashboard/a/list": {"list"},
        f"/dashboard/a/items/{local_id}": {
            "details", "content", "sessions", "activity", "ship", "relationships",
        },
    }
    for path, regions in expected.items():
        page = await client.get(path)
        found = set(re.findall(r'data-live-region="([^"]+)"', page.text))
        assert regions <= found, (path, regions - found)


async def test_the_kanban_widget_region_appears_when_it_is_enabled(env):
    env["runtime"].update_settings({"agent_widget": {"show_kanban": True}})

    page = await env["client"].get("/dashboard/a/kanban")

    assert {"board", "agent-sessions"} <= set(re.findall(r'data-live-region="([^"]+)"', page.text))


async def test_the_overview_charts_get_their_data_from_a_json_element(env):
    page = await env["client"].get("/dashboard/a")

    match = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>',
                      page.text, re.S)
    assert match
    data = json.loads(match.group(1))
    assert set(data) == {"status", "kind", "time"}
    assert data["status"]["labels"] == ["Proposed", "Done"]
    assert "initCharts" in page.text and "live:applied" in page.text


async def test_changed_entries_are_marked_for_highlighting(env):
    client = env["client"]
    local_id = await make_item(client)
    await start_session(client, local_id, agent="marked")
    await client.post(f"/dashboard/a/items/{local_id}/events", data={"body": "a note"})

    overview = await client.get("/dashboard/a")
    kanban = await client.get("/dashboard/a/kanban")
    listing = await client.get("/dashboard/a/list")
    item = await client.get(f"/dashboard/a/items/{local_id}")

    assert 'data-live-key="session-a-' in overview.text
    assert f'data-live-key="kanban-a-{local_id}"' in kanban.text
    assert f'data-live-key="list-a-{local_id}"' in listing.text
    assert f'data-live-key="mobile-a-{local_id}"' in listing.text
    assert 'data-live-key="session-' in item.text
    assert 'data-live-key="event-' in item.text


async def test_the_three_card_variants_never_share_a_key(env):
    local_id = await make_item(env["client"])

    listing = await env["client"].get("/dashboard/a/list")

    keys = re.findall(r'data-live-key="([^"]+)"', listing.text)
    assert len(keys) == len(set(keys)) and len(keys) >= 2, keys
    assert any(k.startswith("list-") for k in keys) and any(k.startswith("mobile-") for k in keys)
    assert all(local_id in k for k in keys)


def test_the_live_script_ignores_its_own_highlight_class_when_comparing():
    """A region carrying the highlight class must not look changed (it would be swapped again)."""
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[4] / "src" / "issuedeck" / "features" / "dashboard"
        / "static" / "js" / "live.js"
    ).read_text(encoding="utf-8")

    assert "function plain(html)" in script
    assert "plain(region.innerHTML) === replacement.innerHTML" in script
    assert "plain(element.outerHTML)" in script


# --- the settings forms ------------------------------------------------------------------


async def test_the_settings_page_shows_both_new_sections_with_the_current_values(env):
    env["runtime"].update_settings({"agent_widget": {"max_sessions": 5},
                                    "live": {"fallback_seconds": 60}})

    page = await env["client"].get("/dashboard/settings")

    assert "Agent sessions widget" in page.text and "Live updates" in page.text
    assert 'name="max_sessions" type="number" min="1" max="20" step="1" value="5"' in page.text
    assert (
        'name="fallback_seconds" type="number" min="5" max="300" step="1" value="60"'
        in page.text
    )
    assert 'action="/dashboard/settings/agent-widget/reset"' in page.text
    assert 'action="/dashboard/settings/live/reset"' in page.text


async def test_the_widget_form_saves_and_an_unticked_box_means_off(env):
    r = await env["client"].post(
        "/dashboard/settings/agent-widget",
        data={"show_kanban": "1", "show_overview": "1", "statuses": ["paused"],
              "completed_minutes": "30", "max_sessions": "3", "scope": "all",
              "initial_state": "collapsed", "info_agent": "1"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    widget = env["runtime"].settings()["agent_widget"]
    assert widget["show_kanban"] and widget["show_overview"]
    assert widget["statuses"] == ["paused"] and widget["completed_minutes"] == 30
    assert widget["max_sessions"] == 3 and widget["scope"] == "all"
    assert widget["initial_state"] == "collapsed"
    assert widget["info"] == {"agent": True, "item": False, "goal": False,
                              "last_update": False, "updates": False}


@pytest.mark.parametrize("data", [
    {"completed_minutes": "999", "max_sessions": "8", "scope": "project"},
    {"completed_minutes": "0", "max_sessions": "0", "scope": "project"},
    {"completed_minutes": "soon", "max_sessions": "8", "scope": "project"},
    {"completed_minutes": "0", "max_sessions": "8", "scope": "everywhere"},
])
async def test_the_widget_form_refuses_bad_values_and_saves_nothing(env, data):
    r = await env["client"].post(
        "/dashboard/settings/agent-widget", data={"initial_state": "expanded", **data},
    )

    assert r.status_code == 422
    assert env["runtime"].settings()["agent_widget"]["max_sessions"] == 8


async def test_the_live_form_saves_and_an_unticked_box_means_off(env):
    r = await env["client"].post(
        "/dashboard/settings/live",
        data={"enabled": "1", "fallback_seconds": "20", "highlight_seconds": "0",
              "while_editing": "after_save", "view_kanban": "1", "view_item": "1",
              "event_items": "1", "event_sessions": "1"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    live = env["runtime"].settings()["live"]
    assert live["enabled"] and live["fallback_seconds"] == 20 and live["highlight_seconds"] == 0
    assert live["while_editing"] == "after_save"
    assert live["views"] == {"kanban": True, "list": False, "overview": False, "item": True}
    assert live["events"] == {"items": True, "sessions": True, "activity": False}
    assert live["indicator"] is False


@pytest.mark.parametrize("data", [
    {"fallback_seconds": "2", "highlight_seconds": "3", "while_editing": "notice"},
    {"fallback_seconds": "30", "highlight_seconds": "99", "while_editing": "notice"},
    {"fallback_seconds": "30", "highlight_seconds": "3", "while_editing": "never"},
    {"fallback_seconds": "often", "highlight_seconds": "3", "while_editing": "notice"},
])
async def test_the_live_form_refuses_bad_values_and_saves_nothing(env, data):
    r = await env["client"].post("/dashboard/settings/live", data={"enabled": "1", **data})

    assert r.status_code == 422
    assert env["runtime"].settings()["live"]["fallback_seconds"] == 30


async def test_each_group_has_a_reset_that_leaves_the_others_alone(env):
    env["runtime"].update_settings({"agent_widget": {"max_sessions": 2},
                                    "live": {"fallback_seconds": 99}})

    await env["client"].post("/dashboard/settings/agent-widget/reset", follow_redirects=False)

    settings = env["runtime"].settings()
    assert settings["agent_widget"]["max_sessions"] == 8
    assert settings["live"]["fallback_seconds"] == 99
    await env["client"].post("/dashboard/settings/live/reset", follow_redirects=False)
    assert env["runtime"].settings()["live"]["fallback_seconds"] == 30


async def test_settings_changes_are_recorded_in_the_audit_log(env):
    await env["client"].post(
        "/dashboard/settings/live",
        data={"enabled": "1", "fallback_seconds": "40", "highlight_seconds": "3",
              "while_editing": "notice"},
    )
    await env["client"].post("/dashboard/settings/agent-widget/reset")

    actions = [e["action"] for e in env["runtime"].audit_log()]
    assert "settings.updated" in actions and "agent_widget.reset" in actions


async def test_the_new_settings_sections_are_translated(env):
    env["client"].cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    page = await env["client"].get("/dashboard/settings")

    assert "Ügynöki munkamenetek modul" in page.text
    assert "Élő frissítés" in page.text
