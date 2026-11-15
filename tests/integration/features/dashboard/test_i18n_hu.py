"""FEA-0005: Hungarian is selectable, persists, and renders in the dashboard."""

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
        statuses={"proposed": StatusConfig(label="Proposed")},
        branches=[BranchConfig(key="main", label="Main")],
    )
    app = FastAPI()
    app.state.registry = ConfigRegistry(
        server=ServerConfig(api_token="t"), projects={"a": project},
    )
    app.state.session_factory = Session
    install_error_handlers(app)
    app.include_router(dashboard_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def test_language_switch_to_hungarian_sets_cookie(client):
    r = await client.post(
        "/dashboard/language",
        data={"lang": "hu", "next": "/dashboard/a"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert r.headers["location"] == "/dashboard/a"
    assert f"{DASHBOARD_LANG_COOKIE}=hu" in r.headers["set-cookie"]


async def test_unknown_language_cookie_value_is_not_stored(client):
    r = await client.post(
        "/dashboard/language", data={"lang": "de", "next": "/dashboard/a"},
        follow_redirects=False,
    )

    assert DASHBOARD_LANG_COOKIE not in r.headers.get("set-cookie", "")


async def test_overview_renders_in_hungarian_after_switch(client):
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    page = await client.get("/dashboard/a")

    assert page.status_code == 200
    assert "Áttekintés" in page.text
    assert "Becsült és ráfordított idő állapotonként" in page.text
    assert "Nyelv" in page.text  # language switcher label
    assert "Magyar" in page.text  # language switcher button


async def test_switcher_offers_all_three_languages(client):
    page = await client.get("/dashboard/a")

    assert 'value="en"' in page.text
    assert 'value="zh-CN"' in page.text
    assert 'value="hu"' in page.text


async def test_unknown_cookie_falls_back_to_english(client):
    client.cookies.set(DASHBOARD_LANG_COOKIE, "xx")

    page = await client.get("/dashboard/a")

    assert "Overview" in page.text
    assert "Áttekintés" not in page.text


async def test_login_page_offers_hungarian(client):
    page = await client.get("/dashboard/login")

    assert page.status_code == 200
    assert 'value="hu"' in page.text
