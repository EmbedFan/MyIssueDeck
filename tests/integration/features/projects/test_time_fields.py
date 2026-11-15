"""FEA-0001: default Estimated time / Time spent fields and their totals."""

import json

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
from issuedeck.features.items.models import Base, Item
from issuedeck.features.items.repo import ItemRepo
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


async def test_time_summary_totals_are_rounded_against_float_noise(client):
    for spent in (0.25, 0.21):
        await client.post(
            "/api/v1/projects/a/items",
            json={"kind": "feature", "title": "x", "custom_fields": {"time_spent": spent}},
        )

    r = await client.get("/api/v1/projects/a/time-summary")

    assert r.json()["time_spent"] == 0.46


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


# --- FEA-0002: time overview diagram -------------------------------------


async def test_overview_shows_time_chart_with_data(client):
    await client.post(
        "/api/v1/projects/a/items",
        json={
            "kind": "feature",
            "title": "x",
            "custom_fields": {"estimated_time": 4, "time_spent": 1.5},
        },
    )

    page = await client.get("/dashboard/a")

    assert 'id="timeChart"' in page.text
    assert "Estimated vs spent time by status" in page.text
    assert '"labels": ["Proposed"]' in page.text
    assert '"estimated": [4.0]' in page.text
    assert '"spent": [1.5]' in page.text


async def test_overview_time_chart_empty_state(client):
    page = await client.get("/dashboard/a")

    assert 'id="timeChart"' not in page.text
    assert "No time recorded yet" in page.text


async def test_overview_time_chart_uses_contrasting_colours(client):
    await client.post("/api/v1/projects/a/items", json={"kind": "feature", "title": "x"})

    page = await client.get("/dashboard/a")

    assert "backgroundColor: '#f59e0b'" in page.text  # estimated: amber
    assert "backgroundColor: '#2563eb'" in page.text  # time spent: blue


# --- IS-0001: default estimated time --------------------------------------


async def test_new_item_without_estimate_gets_default_of_half_an_hour(client):
    r = await client.post("/api/v1/projects/a/items", json={"kind": "feature", "title": "x"})

    assert r.status_code == 201
    assert r.json()["custom_fields"] == {"estimated_time": 0.5}


async def test_empty_estimate_also_gets_the_default(client):
    r = await client.post(
        "/api/v1/projects/a/items",
        json={"kind": "feature", "title": "x", "custom_fields": {"estimated_time": ""}},
    )

    assert r.json()["custom_fields"] == {"estimated_time": 0.5}


async def test_explicit_estimate_is_kept_including_zero(client):
    for value in (4, 0):
        r = await client.post(
            "/api/v1/projects/a/items",
            json={"kind": "feature", "title": "x", "custom_fields": {"estimated_time": value}},
        )
        assert r.json()["custom_fields"] == {"estimated_time": value}


async def test_default_is_not_reapplied_when_an_estimate_is_cleared(client):
    created = await client.post(
        "/api/v1/projects/a/items", json={"kind": "feature", "title": "x"},
    )
    local_id = created.json()["local_id"]

    r = await client.patch(
        f"/api/v1/projects/a/items/{local_id}",
        json={"custom_fields": {"estimated_time": ""}},
    )

    assert r.status_code == 200
    assert r.json()["custom_fields"] == {}


def test_default_must_match_the_field_type():
    with pytest.raises(ValueError):
        CustomFieldConfig(label="N", type="number", default="soon")
    with pytest.raises(ValueError):
        CustomFieldConfig(label="N", type="number", default=True)
    with pytest.raises(ValueError):
        CustomFieldConfig(label="S", type="select", options=["a"], default="b")

    assert CustomFieldConfig(label="N", type="number", default=2).default == 2
    assert CustomFieldConfig(label="C", type="checkbox", default=False).default is False


async def test_project_override_without_default_gets_no_default(client):
    registry = client._transport.app.state.registry
    registry.project("b").custom_fields["estimated_time"] = CustomFieldConfig(
        label="Estimate", type="number",
    )

    r = await client.post("/api/v1/projects/b/items", json={"kind": "feature", "title": "x"})

    assert r.json()["custom_fields"] == {}


async def test_checkbox_default_does_not_override_an_explicit_false(client):
    registry = client._transport.app.state.registry
    registry.project("b").custom_fields["flag"] = CustomFieldConfig(
        label="Flag", type="checkbox", default=True,
    )

    unset = await client.post(
        "/api/v1/projects/b/items", json={"kind": "feature", "title": "x"},
    )
    explicit = await client.post(
        "/api/v1/projects/b/items",
        json={"kind": "feature", "title": "y", "custom_fields": {"flag": False}},
    )

    assert unset.json()["custom_fields"]["flag"] is True
    assert explicit.json()["custom_fields"]["flag"] is False


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _row(local_id, kind, status, fields, deleted=None):
    return Item(
        project_key="a",
        local_id=local_id,
        kind=kind,
        status=status,
        title=local_id,
        custom_fields_json=json.dumps(fields),
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        deleted_at=deleted,
    )


async def test_sum_custom_number_by_groups_and_skips_deleted(session_factory):
    async with session_factory() as session:
        session.add_all([
            _row("F-1", "feature", "proposed", {"time_spent": 2}),
            _row("F-2", "feature", "proposed", {"time_spent": 1.5}),
            _row("B-1", "bug", "done", {"time_spent": 4}),
            _row("B-2", "bug", "done", {}),
            _row("B-3", "bug", "done", {"time_spent": 99}, deleted="2026-01-02T00:00:00+00:00"),
        ])
        await session.commit()

        repo = ItemRepo(session)
        by_status = await repo.sum_custom_number_by("a", "time_spent", "status")
        by_kind = await repo.sum_custom_number_by("a", "time_spent", "kind")

    assert by_status == {"proposed": 3.5, "done": 4.0}
    assert by_kind == {"feature": 3.5, "bug": 4.0}


async def test_sum_custom_number_by_rejects_unknown_grouping(session_factory):
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await ItemRepo(session).sum_custom_number_by("a", "time_spent", "title")
