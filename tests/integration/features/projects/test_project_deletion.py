"""FEA-0003: safe project deletion."""

import json
import zipfile

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.app import _build_registry, _validate_db_against_registry
from issuedeck.core.config import ProjectConfig
from issuedeck.core.errors import ProjectNotFound, install_error_handlers
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.dashboard.saved_filters import (
    delete_project_filters,
    list_saved_dashboard_filters,
    save_dashboard_filter,
)
from issuedeck.features.items.models import (
    Base,
    ImportBatch,
    Item,
    ItemApplyTo,
    ItemEvent,
    ItemExternalLink,
    ItemRelationship,
    ItemTag,
    ShipCommit,
    ShipRecord,
    WorkSession,
    WorkSessionUpdate,
)
from issuedeck.features.items.routes import router as items_router
from issuedeck.features.relationships.routes import router as relationships_router
from issuedeck.features.work_sessions.routes import router as work_sessions_router

PROJECT_TOML = """\
key = "{key}"
name = "Project {key}"

[kinds.feature]
label = "Feature"
prefix = "FEAT"

[statuses.proposed]
label = "Proposed"
"""

CHILD_MODELS = (
    ItemTag, ItemApplyTo, ItemExternalLink, ItemEvent, ItemRelationship,
    ShipRecord, ShipCommit, WorkSession, WorkSessionUpdate, ImportBatch,
)


@pytest.fixture
async def env(tmp_path):
    projects_dir = tmp_path / "projects"
    data_dir = tmp_path / "data"
    projects_dir.mkdir()
    for key in ("a", "b"):
        (projects_dir / f"{key}.toml").write_text(PROJECT_TOML.format(key=key), encoding="utf-8")
    server_toml = tmp_path / "server.toml"
    server_toml.write_text(
        'api_token = "t"\n'
        f'projects_dir = "{projects_dir.as_posix()}"\n'
        f'data_dir = "{data_dir.as_posix()}"\n',
        encoding="utf-8",
    )
    registry = _build_registry(server_toml)

    # No foreign_keys pragma here on purpose: deletion must not rely on cascades.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    install_error_handlers(app)
    for router in (dashboard_router, items_router, relationships_router, work_sessions_router):
        app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield {
            "client": client,
            "registry": registry,
            "Session": Session,
            "tmp": tmp_path,
            "server_toml": server_toml,
            "projects_dir": projects_dir,
            "data_dir": data_dir,
        }
    await engine.dispose()


async def _populate(env, key):
    """Create items, tags, links, a relationship, events, a session and rows by hand."""
    client = env["client"]
    ids = []
    for title in ("one", "two"):
        r = await client.post(
            f"/api/v1/projects/{key}/items",
            json={
                "kind": "feature",
                "title": title,
                "tags": ["x"],
                "external_links": [{"url": f"https://github.com/example/repo/issues/{title}"}],
            },
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["local_id"])
    r = await client.post(
        f"/api/v1/projects/{key}/items/{ids[0]}/relationships",
        json={"to_local_id": ids[1], "relation_type": "blocks"},
    )
    assert r.status_code == 201, r.text
    r = await client.patch(f"/api/v1/projects/{key}/items/{ids[0]}", json={"title": "one!"})
    assert r.status_code == 200, r.text
    r = await client.post(
        f"/api/v1/projects/{key}/work-sessions",
        json={"local_id": ids[0], "agent_name": "agent", "goal": "work"},
    )
    assert r.status_code == 201, r.text
    session_id = r.json()["id"]

    async with env["Session"]() as session:
        item_pk = (await session.execute(
            select(Item.pk).where(Item.project_key == key, Item.local_id == ids[0])
        )).scalar_one()
        record = ShipRecord(
            item_pk=item_pk, branch_key="main", version="1.0", shipped_at="2026-01-01",
        )
        session.add(record)
        await session.flush()
        session.add(ShipCommit(ship_record_id=record.id, sha="abc", position=0))
        session.add(ImportBatch(
            project_key=key, batch_tag="t", source_type="csv", created_at="2026-01-01",
        ))
        await session.commit()
    return ids, session_id


async def _finish(env, key, session_id):
    r = await env["client"].post(
        f"/api/v1/projects/{key}/work-sessions/{session_id}/finish", json={},
    )
    assert r.status_code == 200, r.text


async def _count(env, model, **where):
    async with env["Session"]() as session:
        stmt = select(func.count()).select_from(model)
        for column, value in where.items():
            stmt = stmt.where(getattr(model, column) == value)
        return (await session.execute(stmt)).scalar_one()


async def _total_rows(env):
    return {
        model.__name__: await _count(env, model) for model in (Item, *CHILD_MODELS)
    }


# --- confirmation page ---------------------------------------------------


async def test_overview_links_to_the_delete_page(env):
    page = await env["client"].get("/dashboard/a")

    assert 'href="/dashboard/a/delete"' in page.text


async def test_delete_page_shows_what_will_be_removed(env):
    await _populate(env, "a")

    page = await env["client"].get("/dashboard/a/delete")

    assert page.status_code == 200
    assert "Delete project" in page.text
    assert "Type the project key a to confirm" in page.text
    assert "/dashboard/a/exports/audit-bundle" in page.text
    assert "active or paused work session(s) block deletion" in page.text


async def test_delete_page_for_unknown_project_is_404(env):
    assert (await env["client"].get("/dashboard/nope/delete")).status_code == 404


# --- refusals change nothing ---------------------------------------------


@pytest.mark.parametrize("typed", ["", "wrong", "A", "a b"])
async def test_wrong_confirmation_deletes_nothing(env, typed):
    ids, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)
    before = await _total_rows(env)

    r = await env["client"].post("/dashboard/a/delete", data={"confirm_key": typed})

    assert r.status_code == 422
    assert "does not match the project key" in r.text
    assert await _total_rows(env) == before
    assert (env["projects_dir"] / "a.toml").exists()
    env["registry"].project("a")


async def test_active_work_session_blocks_deletion(env):
    await _populate(env, "a")
    before = await _total_rows(env)

    r = await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert r.status_code == 409
    assert "Nothing was deleted" in r.text
    assert await _total_rows(env) == before
    assert (env["projects_dir"] / "a.toml").exists()
    assert not (env["data_dir"] / "deleted-projects").exists()


async def test_deleting_an_unknown_project_is_404(env):
    r = await env["client"].post("/dashboard/nope/delete", data={"confirm_key": "nope"})

    assert r.status_code == 404


# --- successful deletion -------------------------------------------------


async def test_confirmed_deletion_removes_all_project_data_only(env):
    _, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)
    await _populate(env, "b")
    only_b = {}
    # Rows that belong to project b only, to compare after deleting a.
    async with env["Session"]() as session:
        b_pks = select(Item.pk).where(Item.project_key == "b")
        only_b["items"] = (await session.execute(
            select(func.count()).select_from(Item).where(Item.project_key == "b")
        )).scalar_one()
        only_b["tags"] = (await session.execute(
            select(func.count()).select_from(ItemTag).where(ItemTag.item_pk.in_(b_pks))
        )).scalar_one()
        only_b["events"] = (await session.execute(
            select(func.count()).select_from(ItemEvent).where(ItemEvent.item_pk.in_(b_pks))
        )).scalar_one()
        # A relationship is stored as a mirrored pair of rows.
        only_b["relationships"] = (await session.execute(
            select(func.count()).select_from(ItemRelationship).where(
                ItemRelationship.from_item_pk.in_(b_pks)
            )
        )).scalar_one()
        assert only_b["relationships"] == 2

    r = await env["client"].post(
        "/dashboard/a/delete", data={"confirm_key": "a"}, follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == "/dashboard/"
    # Project a is gone everywhere.
    assert await _count(env, Item, project_key="a") == 0
    assert await _count(env, WorkSession, project_key="a") == 0
    assert await _count(env, ImportBatch, project_key="a") == 0
    with pytest.raises(ProjectNotFound):
        env["registry"].project("a")
    # Every child table only holds project b's rows now.
    assert await _count(env, Item) == only_b["items"]
    assert await _count(env, ItemTag) == only_b["tags"]
    assert await _count(env, ItemEvent) == only_b["events"]
    assert await _count(env, ItemRelationship) == only_b["relationships"]
    assert await _count(env, ShipRecord) == 1
    assert await _count(env, ShipCommit) == 1
    assert await _count(env, WorkSession) == 1
    assert await _count(env, WorkSessionUpdate) == 1
    assert await _count(env, ImportBatch) == 1
    env["registry"].project("b")


async def test_deletion_includes_soft_deleted_items(env):
    ids, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)
    assert (await env["client"].delete(f"/api/v1/projects/a/items/{ids[1]}")).status_code == 204

    r = await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert r.status_code == 303
    assert await _count(env, Item, project_key="a") == 0


async def test_config_is_archived_and_backup_is_written_before_deletion(env):
    ids, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)

    await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert not (env["projects_dir"] / "a.toml").exists()
    archived = list((env["projects_dir"] / ".deleted").glob("a-*.toml"))
    assert len(archived) == 1
    assert 'key = "a"' in archived[0].read_text(encoding="utf-8")
    assert (env["projects_dir"] / "b.toml").exists()

    backups = list((env["data_dir"] / "deleted-projects").glob("a-*-audit-bundle.zip"))
    assert len(backups) == 1
    with zipfile.ZipFile(backups[0]) as bundle:
        exported = json.loads(bundle.read("items.json"))
    assert {item["local_id"] for item in exported} == set(ids)


async def test_saved_filters_of_the_project_are_removed(env):
    data_dir = env["data_dir"]
    save_dashboard_filter(data_dir, "a", "Mine", {"view": "active"})
    save_dashboard_filter(data_dir, "b", "Other", {"view": "active"})
    _, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)

    await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert list_saved_dashboard_filters(data_dir, "a") == []
    assert [f.name for f in list_saved_dashboard_filters(data_dir, "b")] == ["Other"]


async def test_server_still_starts_after_a_project_is_deleted(env):
    """Startup refuses items whose project config is missing; deletion must not cause that."""
    _, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)
    await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    fresh_registry = _build_registry(env["server_toml"])

    assert {p.key for p in fresh_registry.all_projects()} == {"b"}
    await _validate_db_against_registry(env["Session"], fresh_registry)


async def test_project_without_a_config_file_can_still_be_deleted(env):
    (env["projects_dir"] / "a.toml").unlink()

    r = await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert r.status_code == 303
    assert not (env["projects_dir"] / ".deleted").exists()


async def test_deleted_project_page_is_gone(env):
    await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert (await env["client"].get("/dashboard/a")).status_code == 404


async def test_backup_failure_aborts_the_deletion(env, monkeypatch):
    _, session_id = await _populate(env, "a")
    await _finish(env, "a", session_id)
    before = await _total_rows(env)

    async def boom(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("issuedeck.features.projects.service.export_audit_bundle", boom)

    with pytest.raises(OSError):
        await env["client"].post("/dashboard/a/delete", data={"confirm_key": "a"})

    assert await _total_rows(env) == before
    assert (env["projects_dir"] / "a.toml").exists()
    env["registry"].project("a")


# --- small units ---------------------------------------------------------


def test_unregister_project(env):
    registry = env["registry"]

    removed = registry.unregister_project("a")

    assert isinstance(removed, ProjectConfig)
    with pytest.raises(ProjectNotFound):
        registry.project("a")
    with pytest.raises(ProjectNotFound):
        registry.unregister_project("a")


def test_delete_project_filters_reports_how_many_were_removed(tmp_path):
    save_dashboard_filter(tmp_path, "a", "One", {"view": "active"})
    save_dashboard_filter(tmp_path, "a", "Two", {"view": "backlog"})

    assert delete_project_filters(tmp_path, "a") == 2
    assert delete_project_filters(tmp_path, "a") == 0
    assert delete_project_filters(tmp_path / "missing", "a") == 0
