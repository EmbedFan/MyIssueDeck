"""FEA-0007: the dashboard pages for importing a project snapshot."""

import re
from io import BytesIO

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import ConfigRegistry, ServerConfig, load_project_config
from issuedeck.core.errors import install_error_handlers
from issuedeck.features.dashboard import snapshot_routes
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.dashboard.snapshot_routes import router as snapshot_router
from issuedeck.features.items.models import Base, Item
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.items.schemas import CreateItemRequest
from issuedeck.features.items.service import ItemService

PROJECT_TOML = "\n".join([
    'key = "test"',
    'name = "Test"',
    "[kinds.feature]",
    'label = "Feature"',
    'prefix = "FEAT"',
    "[statuses.proposed]",
    'label = "Proposed"',
    "[statuses.done]",
    'label = "Done"',
    "terminal = true",
    "requires_ship = true",
    "[[branches]]",
    'key = "main"',
    'label = "Main"',
    "",
])


@pytest.fixture
async def app_parts(tmp_path):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "test.toml").write_text(PROJECT_TOML, encoding="utf-8")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    registry = ConfigRegistry(
        server=ServerConfig(
            api_token="t", projects_dir=projects_dir, data_dir=tmp_path / "data",
        ),
        projects={"test": load_project_config(projects_dir / "test.toml")},
    )
    async with Session() as session:
        svc = ItemService(ItemRepo(session), registry, session)
        await svc.create(
            "test", CreateItemRequest(kind="feature", title="Snapshot me", body="Body"),
        )

    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    install_error_handlers(app)
    app.include_router(snapshot_router)
    app.include_router(dashboard_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, registry, Session, tmp_path
    await engine.dispose()


async def _bundle(client) -> bytes:
    response = await client.get("/dashboard/test/exports/audit-bundle")
    assert response.status_code == 200
    return response.content


def _upload(content: bytes, name="snapshot.zip"):
    return {"snapshot_file": (name, BytesIO(content), "application/zip")}


def _token(html: str) -> str:
    match = re.search(r'name="token" value="([0-9a-f]{32})"', html)
    assert match, "the preview page has no apply form"
    return match.group(1)


async def _count_items(Session, key):
    async with Session() as session:
        return int((await session.execute(
            select(func.count(Item.pk)).where(Item.project_key == key)
        )).scalar())


async def test_pages_link_to_the_import(app_parts):
    client, *_ = app_parts
    overview = await client.get("/dashboard/test")
    assert "/dashboard/import-snapshot?project=test" in overview.text
    form_page = await client.get("/dashboard/projects-new")
    assert "/dashboard/import-snapshot" in form_page.text


async def test_form_preselects_the_project_to_update(app_parts):
    client, *_ = app_parts
    page = await client.get("/dashboard/import-snapshot?project=test")
    assert page.status_code == 200
    assert "Import a project snapshot" in page.text
    assert re.search(r'value="update"[^>]*checked', page.text)
    assert re.search(r'<option value="test" selected>', page.text)

    plain = await client.get("/dashboard/import-snapshot")
    assert re.search(r'value="create"[^>]*checked', plain.text)


async def test_preview_then_apply_creates_a_project(app_parts):
    client, registry, Session, tmp_path = app_parts
    content = await _bundle(client)

    preview = await client.post(
        "/dashboard/import-snapshot/preview",
        files=_upload(content),
        data={"mode": "create", "new_key": "copy", "target": "", "conflict": "keep"},
    )
    assert preview.status_code == 200
    assert "nothing has been written yet" in preview.text
    assert "data-snapshot-counts" in preview.text
    token = _token(preview.text)
    assert await _count_items(Session, "copy") == 0
    assert not (registry.server.projects_dir / "copy.toml").exists()
    stored = tmp_path / "data" / "snapshot-uploads" / f"{token}.zip"
    assert stored.exists()

    applied = await client.post(
        "/dashboard/import-snapshot/apply",
        data={"token": token, "mode": "create", "new_key": "copy", "target": "",
              "conflict": "keep"},
    )
    assert applied.status_code == 200
    assert "Snapshot imported" in applied.text
    assert 'href="/dashboard/copy"' in applied.text
    assert await _count_items(Session, "copy") == 1
    assert (registry.server.projects_dir / "copy.toml").exists()
    assert registry.project("copy").name == "Test"
    assert not stored.exists()
    assert (await client.get("/dashboard/copy")).status_code == 200


async def test_the_stored_upload_cannot_be_applied_twice(app_parts):
    client, *_ = app_parts
    content = await _bundle(client)
    preview = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(content),
        data={"mode": "create", "new_key": "copy", "conflict": "keep"},
    )
    token = _token(preview.text)
    data = {"token": token, "mode": "create", "new_key": "copy", "conflict": "keep"}
    first = await client.post("/dashboard/import-snapshot/apply", data=data)
    second = await client.post("/dashboard/import-snapshot/apply", data=data)
    assert first.status_code == 200
    assert second.status_code == 422
    assert "no longer available" in second.text


async def test_update_preview_reports_what_would_change(app_parts):
    client, _, Session, _ = app_parts
    content = await _bundle(client)
    preview = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(content),
        data={"mode": "update", "target": "test", "conflict": "overwrite"},
    )
    assert preview.status_code == 200
    assert "Items updated" in preview.text
    assert await _count_items(Session, "test") == 1


async def test_bad_requests_are_explained(app_parts):
    client, _, _, tmp_path = app_parts

    no_file = await client.post(
        "/dashboard/import-snapshot/preview",
        data={"mode": "create", "conflict": "keep"},
    )
    assert no_file.status_code == 422 and "Choose a snapshot file" in no_file.text

    not_zip = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(b"not a zip"),
        data={"mode": "create", "conflict": "keep"},
    )
    assert not_zip.status_code == 422 and "not a readable ZIP" in not_zip.text
    assert list((tmp_path / "data" / "snapshot-uploads").glob("*.zip")) == []

    bad_mode = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(b"x"),
        data={"mode": "delete", "conflict": "keep"},
    )
    assert bad_mode.status_code == 422 and "options are not valid" in bad_mode.text

    content = await _bundle(client)
    exists = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(content),
        data={"mode": "create", "new_key": "test", "conflict": "keep"},
    )
    assert exists.status_code == 409 and "already exists" in exists.text

    default_target = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(content),
        data={"mode": "update", "target": "", "conflict": "keep"},
    )
    # no project chosen: the project with the key of the snapshot is updated
    assert default_target.status_code == 200 and "Items updated" in default_target.text

    unknown = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(content),
        data={"mode": "update", "target": "nope", "conflict": "keep"},
    )
    assert unknown.status_code == 404

    bad_token = await client.post(
        "/dashboard/import-snapshot/apply",
        data={"token": "../../etc/passwd", "mode": "create", "conflict": "keep"},
    )
    assert bad_token.status_code == 422 and "no longer available" in bad_token.text


async def test_too_large_uploads_are_refused(app_parts, monkeypatch):
    client, *_ = app_parts
    monkeypatch.setattr(snapshot_routes, "MAX_UPLOAD_BYTES", 10)
    response = await client.post(
        "/dashboard/import-snapshot/preview", files=_upload(b"x" * 100),
        data={"mode": "create", "conflict": "keep"},
    )
    assert response.status_code == 413 and "larger than 64 MB" in response.text


async def test_the_page_follows_the_language(app_parts):
    client, *_ = app_parts
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")
    page = await client.get("/dashboard/import-snapshot")
    assert "Projekt importálása pillanatképből" in page.text
    assert "Pillanatkép ellenőrzése" in page.text
