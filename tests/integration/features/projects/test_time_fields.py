"""FEA-0001: default Estimated time / Time spent fields and their totals."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    CustomFieldConfig,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import install_error_handlers
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.items.models import Base
from issuedeck.features.items.routes import router as items_router
from issuedeck.features.projects.routes import router as projects_router


def _project(key: str, **extra) -> ProjectConfig:
    return ProjectConfig(
        key=key,
        name=key.upper(),
        kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
        statuses={"proposed": StatusConfig(label="Proposed")},
        branches=[BranchConfig(key="main", label="Main")],
        **extra,
    )


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    app = FastAPI()
    app.state.registry = ConfigRegistry(
        server=ServerConfig(api_token="t"),
        projects={"a": _project("a"), "b": _project("b")},
    )
    app.state.session_factory = Session
    install_error_handlers(app)
    app.include_router(projects_router)
    app.include_router(items_router)
    app.include_router(dashboard_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


def test_default_time_fields_are_added_to_every_project():
    project = _project("p")

    assert project.custom_fields["estimated_time"].type == "number"
    assert project.custom_fields["time_spent"].type == "number"
    assert project.custom_fields["estimated_time"].required is False


def test_project_definition_overrides_the_default_time_field():
    project = _project(
        "p",
        custom_fields={"time_spent": CustomFieldConfig(label="Hours worked", type="number")},
    )

    assert project.custom_fields["time_spent"].label == "Hours worked"
    assert project.custom_fields["estimated_time"].label == "Estimated time (h)"


def test_defaults_are_not_shared_between_projects():
    first = _project("one")
    second = _project("two")

    first.custom_fields["time_spent"].label = "changed"

    assert second.custom_fields["time_spent"].label == "Time spent (h)"


async def test_items_store_time_fields(client):
    r = await client.post(
        "/api/v1/projects/a/items",
        json={
            "kind": "feature",
            "title": "x",
            "custom_fields": {"estimated_time": 4, "time_spent": 1.5},
        },
    )

    assert r.status_code == 201
    assert r.json()["custom_fields"] == {"estimated_time": 4, "time_spent": 1.5}


async def test_time_fields_reject_non_numbers(client):
    r = await client.post(
        "/api/v1/projects/a/items",
        json={"kind": "feature", "title": "x", "custom_fields": {"time_spent": "lots"}},
    )

    assert r.status_code == 422


async def test_time_summary_totals_exclude_deleted_items(client):
    for title, est, spent in [("one", 4, 1.5), ("two", 2, None), ("gone", 100, 100)]:
        fields = {"estimated_time": est}
        if spent is not None:
            fields["time_spent"] = spent
        r = await client.post(
            "/api/v1/projects/a/items",
            json={"kind": "feature", "title": title, "custom_fields": fields},
        )
        assert r.status_code == 201
    gone = (await client.get("/api/v1/projects/a/items")).json()["items"]
    gone_id = next(i["local_id"] for i in gone if i["title"] == "gone")
    assert (await client.delete(f"/api/v1/projects/a/items/{gone_id}")).status_code == 204

    r = await client.get("/api/v1/projects/a/time-summary")

    assert r.status_code == 200
    assert r.json() == {
        "project_key": "a",
        "unit": "hours",
        "estimated_time": 6.0,
        "time_spent": 1.5,
    }


async def test_time_summary_is_per_project_and_zero_when_empty(client):
    await client.post(
        "/api/v1/projects/a/items",
        json={"kind": "feature", "title": "x", "custom_fields": {"time_spent": 3}},
    )

    r = await client.get("/api/v1/projects/b/time-summary")

    assert r.json()["estimated_time"] == 0.0
    assert r.json()["time_spent"] == 0.0


async def test_time_summary_unknown_project_is_404(client):
    r = await client.get("/api/v1/projects/nope/time-summary")

    assert r.status_code == 404


async def test_overview_page_shows_time_totals(client):
    await client.post(
        "/api/v1/projects/a/items",
        json={
            "kind": "feature",
            "title": "x",
            "custom_fields": {"estimated_time": 4, "time_spent": 1.5},
        },
    )

    page = await client.get("/dashboard/a")

    assert page.status_code == 200
    assert "Estimated time (h)" in page.text
    assert "Time spent (h)" in page.text
    assert ">4<" in page.text.replace(" ", "").replace("\n", "")
    assert ">1.5<" in page.text.replace(" ", "").replace("\n", "")
