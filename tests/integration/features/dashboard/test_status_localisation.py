"""IS-0002: Kanban headers and Overview diagrams show Hungarian status names."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import install_error_handlers
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.items.models import Base
from issuedeck.features.items.routes import router as items_router


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    project = ProjectConfig(
        key="a",
        name="A",
        kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
        statuses={
            "proposed": StatusConfig(label="Proposed"),
            "in_progress": StatusConfig(label="In Progress"),
            "done": StatusConfig(label="Done", terminal=True, requires_ship=True),
            "review": StatusConfig(label="Review by QA"),
        },
        branches=[BranchConfig(key="main", label="Main")],
    )
    app = FastAPI()
    app.state.registry = ConfigRegistry(
        server=ServerConfig(api_token="t"), projects={"a": project},
    )
    app.state.session_factory = Session
    install_error_handlers(app)
    app.include_router(dashboard_router)
    app.include_router(items_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def test_kanban_headers_are_hungarian(client):
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    page = await client.get("/dashboard/a/kanban")

    assert page.status_code == 200
    assert "Javasolt" in page.text
    assert "Folyamatban" in page.text
    assert "Kész" in page.text
    assert "Review by QA" in page.text  # custom status keeps its label


async def test_kanban_headers_stay_english_by_default(client):
    page = await client.get("/dashboard/a/kanban")

    assert "In Progress" in page.text
    assert "Folyamatban" not in page.text


async def test_overview_chart_labels_are_hungarian(client):
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    page = await client.get("/dashboard/a")

    # json.dumps escapes non-ASCII characters, so check the labels one by one.
    assert '"Javasolt"' in page.text
    assert '"Folyamatban"' in page.text
    assert "Review by QA" in page.text
    assert 'K\\u00e9sz' in page.text  # "Kész" as JSON-escaped text


async def test_overview_chart_labels_stay_english_by_default(client):
    page = await client.get("/dashboard/a")

    assert '"labels": ["Proposed", "In Progress", "Done", "Review by QA"]' in page.text


async def test_item_edit_status_selector_is_hungarian(client):
    created = await client.post(
        "/api/v1/projects/a/items", json={"kind": "feature", "title": "x"},
    )
    assert created.status_code == 201, created.text
    local_id = created.json()["local_id"]
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    page = await client.get(f"/dashboard/a/items/{local_id}/edit")

    assert page.status_code == 200
    assert "Folyamatban" in page.text
    assert "Javasolt" in page.text
