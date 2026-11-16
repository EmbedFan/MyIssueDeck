"""FEA-0007: importing an audit-bundle snapshot (create a project / update a project)."""

import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import (
    ProjectNotFound,
    SnapshotConflict,
    SnapshotInvalid,
)
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.export.snapshot_import import import_snapshot, read_snapshot
from issuedeck.features.items.models import (
    ImportBatch,
    Item,
    ItemEvent,
    ItemRelationship,
    WorkSession,
)
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.items.schemas import CreateItemRequest
from issuedeck.features.items.service import ItemService

from .test_audit_bundle import _registry, session_and_registry  # noqa: F401


@pytest.fixture
async def bundle(tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    # The shared fixture writes a minimal p.toml; a real project file matches the config.
    (registry.server.projects_dir / "p.toml").write_text(
        "\n".join([
            'key = "p"',
            'name = "P"',
            "[kinds.feature]",
            'label = "Feature"',
            'prefix = "FEAT"',
            "[statuses.proposed]",
            'label = "P"',
            "[statuses.done]",
            'label = "D"',
            "terminal = true",
            "requires_ship = true",
            "[[branches]]",
            'key = "main"',
            'label = "Main"',
            "[custom_fields.priority]",
            'label = "Priority"',
            'type = "select"',
            'options = ["low", "high"]',
            "",
        ]),
        encoding="utf-8",
    )
    report = await export_audit_bundle(
        session=session, registry=registry, project_key="p",
        out_path=tmp_path / "snapshots",
    )
    return report.bundle_path


def _target_registry(tmp_path, name, *, with_project=False):
    projects_dir = tmp_path / name
    projects_dir.mkdir()
    if with_project:
        return _registry(projects_dir)
    return ConfigRegistry(
        server=ServerConfig(api_token="t", projects_dir=projects_dir), projects={},
    )


async def _new_db():
    from issuedeck.features.items.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _count(session, model):
    return int((await session.execute(select(func.count()).select_from(model))).scalar())


def _zip_without(source: Path, target: Path, *, drop=(), add=None, manifest=None):
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as out:
        for info in src.infolist():
            if info.filename in drop:
                continue
            data = src.read(info.filename)
            if info.filename == "manifest.json" and manifest is not None:
                data = json.dumps({**json.loads(data), **manifest}).encode()
            out.writestr(info.filename, data)
        for name, data in (add or {}).items():
            out.writestr(name, data)
    return target


# ---------------------------------------------------------------------------
# create a project from a snapshot
# ---------------------------------------------------------------------------

async def test_create_rebuilds_the_project_with_everything(tmp_path, bundle):
    registry = _target_registry(tmp_path, "new-projects")
    engine, Session = await _new_db()
    async with Session() as session:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="create", apply=True,
        )
        assert report.applied is True
        assert (report.items_created, report.relationships_added) == (2, 2)
        assert (report.work_sessions_added, report.import_batches_added) == (1, 1)

        items = {
            item.local_id: item
            for item in (await session.execute(select(Item))).scalars()
        }
        assert set(items) == {"FEAT-0001", "FEAT-0002"}
        first = items["FEAT-0001"]
        assert first.project_key == "p" and first.title == "First"
        assert json.loads(first.custom_fields_json)["priority"] == "high"
        assert await _count(session, ItemRelationship) == 2
        assert await _count(session, WorkSession) == 1
        assert await _count(session, ImportBatch) == 1
        assert await _count(session, ItemEvent) >= 2

        assert registry.project("p").name == "P"
        assert (registry.server.projects_dir / "p.toml").exists()
    await engine.dispose()


async def test_create_preview_changes_nothing(tmp_path, bundle):
    registry = _target_registry(tmp_path, "new-projects")
    engine, Session = await _new_db()
    async with Session() as session:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle, mode="create",
        )
        assert report.applied is False
        assert report.items_created == 2 and report.relationships_added == 2
        assert await _count(session, Item) == 0
        assert not (registry.server.projects_dir / "p.toml").exists()
        assert registry.all_projects() == []
    await engine.dispose()


async def test_create_can_use_another_key(tmp_path, bundle):
    registry = _target_registry(tmp_path, "new-projects")
    engine, Session = await _new_db()
    async with Session() as session:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle, mode="create",
            project_key="copy", apply=True,
        )
        assert report.project_key == "copy" and report.source_project_key == "p"
        assert registry.project("copy").key == "copy"
        keys = {i.project_key for i in (await session.execute(select(Item))).scalars()}
        assert keys == {"copy"}
        text = (registry.server.projects_dir / "copy.toml").read_text(encoding="utf-8")
        assert 'key = "copy"' in text
    await engine.dispose()


async def test_create_refuses_an_existing_project(tmp_path, bundle, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    with pytest.raises(SnapshotConflict):
        await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="create", apply=True,
        )


async def test_create_needs_the_project_config(tmp_path, bundle):
    without = _zip_without(bundle, tmp_path / "no-toml.zip", drop={"project.toml"})
    registry = _target_registry(tmp_path, "new-projects")
    engine, Session = await _new_db()
    async with Session() as session:
        with pytest.raises(SnapshotInvalid, match="project.toml"):
            await import_snapshot(
                session=session, registry=registry, bundle_path=without, mode="create",
            )
    await engine.dispose()


async def test_failed_create_leaves_no_config_behind(tmp_path, bundle):
    """Rows for the key already exist (no config): the import stops and cleans up."""
    registry = _target_registry(tmp_path, "new-projects")
    engine, Session = await _new_db()
    async with Session() as session:
        session.add(Item(
            project_key="p", local_id="FEAT-0001", kind="feature", status="proposed",
            title="orphan", created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ))
        await session.commit()
        with pytest.raises(SnapshotConflict):
            await import_snapshot(
                session=session, registry=registry, bundle_path=bundle,
                mode="create", apply=True,
            )
        assert not (registry.server.projects_dir / "p.toml").exists()
        assert registry.all_projects() == []
        assert await _count(session, Item) == 1
    await engine.dispose()


# ---------------------------------------------------------------------------
# update a project from a snapshot
# ---------------------------------------------------------------------------

async def _target_with_local_item(tmp_path, name="target"):
    registry = _target_registry(tmp_path, name, with_project=True)
    engine, Session = await _new_db()
    session = Session()
    await ItemService(ItemRepo(session), registry, session).create(
        "p", CreateItemRequest(kind="feature", title="Local", body="local body"),
    )
    return engine, session, registry


async def test_update_keep_adds_missing_and_leaves_existing(tmp_path, bundle):
    engine, session, registry = await _target_with_local_item(tmp_path)
    try:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="keep", apply=True,
        )
        assert (report.items_created, report.items_updated, report.items_unchanged) == (1, 0, 1)
        assert report.relationships_added == 2 and report.work_sessions_added == 1
        titles = {
            i.local_id: i.title for i in (await session.execute(select(Item))).scalars()
        }
        assert titles == {"FEAT-0001": "Local", "FEAT-0002": "Second"}
    finally:
        await session.close()
        await engine.dispose()


async def test_update_overwrite_takes_the_snapshot_version(tmp_path, bundle):
    engine, session, registry = await _target_with_local_item(tmp_path)
    try:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="overwrite", apply=True,
        )
        assert report.items_updated == 1 and report.items_created == 1
        first = (await session.execute(
            select(Item).where(Item.local_id == "FEAT-0001")
        )).scalar_one()
        assert first.title == "First" and first.body == "Body one"
        await session.refresh(first, ["tags", "events"])
        assert [t.tag for t in first.tags] == ["hot"]
        assert len(first.events) >= 2  # the local event and the one of the snapshot
    finally:
        await session.close()
        await engine.dispose()


async def test_update_newer_compares_the_timestamps(tmp_path, bundle):
    engine, session, registry = await _target_with_local_item(tmp_path)
    try:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="newer",
        )
        assert report.items_updated == 0  # the local item is newer than the snapshot

        local = (await session.execute(
            select(Item).where(Item.local_id == "FEAT-0001")
        )).scalar_one()
        local.updated_at = "2000-01-01T00:00:00+00:00"
        await session.commit()
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="newer", apply=True,
        )
        assert report.items_updated == 1
        await session.refresh(local)
        assert local.title == "First"
    finally:
        await session.close()
        await engine.dispose()


async def test_update_preview_writes_nothing(tmp_path, bundle):
    engine, session, registry = await _target_with_local_item(tmp_path)
    try:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="overwrite",
        )
        assert report.applied is False and report.items_created == 1
        assert await _count(session, Item) == 1
        assert await _count(session, ItemRelationship) == 0
    finally:
        await session.close()
        await engine.dispose()


async def test_importing_twice_adds_nothing_new(tmp_path, bundle):
    engine, session, registry = await _target_with_local_item(tmp_path)
    try:
        await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="overwrite", apply=True,
        )
        before = {
            model: await _count(session, model)
            for model in (Item, ItemEvent, ItemRelationship, WorkSession, ImportBatch)
        }
        again = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle,
            mode="update", conflict="overwrite", apply=True,
        )
        assert again.items_created == 0
        assert (again.events_added, again.relationships_added) == (0, 0)
        assert (again.work_sessions_added, again.import_batches_added) == (0, 0)
        after = {model: await _count(session, model) for model in before}
        assert after == before
    finally:
        await session.close()
        await engine.dispose()


async def test_update_rejects_items_the_project_cannot_hold(tmp_path, bundle):
    registry = ConfigRegistry(
        server=ServerConfig(api_token="t", projects_dir=tmp_path),
        projects={"p": ProjectConfig(
            key="p", name="P",
            kinds={"task": KindConfig(label="Task", prefix="TASK")},
            statuses={"proposed": StatusConfig(label="P")},
            branches=[BranchConfig(key="main", label="Main")],
        )},
    )
    engine, Session = await _new_db()
    async with Session() as session:
        with pytest.raises(SnapshotInvalid, match="unknown kind 'feature'"):
            await import_snapshot(
                session=session, registry=registry, bundle_path=bundle,
                mode="update", apply=True,
            )
        assert await _count(session, Item) == 0
    await engine.dispose()


async def test_update_needs_an_existing_project(tmp_path, bundle):
    registry = _target_registry(tmp_path, "empty")
    engine, Session = await _new_db()
    async with Session() as session:
        with pytest.raises(ProjectNotFound):
            await import_snapshot(
                session=session, registry=registry, bundle_path=bundle, mode="update",
            )
    await engine.dispose()


# ---------------------------------------------------------------------------
# reading a snapshot safely
# ---------------------------------------------------------------------------

def test_a_file_that_is_not_a_zip_is_rejected(tmp_path):
    path = tmp_path / "x.zip"
    path.write_text("not a zip", encoding="utf-8")
    with pytest.raises(SnapshotInvalid, match="ZIP"):
        read_snapshot(path)


def test_unexpected_and_traversing_names_are_rejected(tmp_path, bundle):
    for name in ("../evil.txt", "extra.json"):
        bad = _zip_without(bundle, tmp_path / "bad.zip", add={name: "x"})
        with pytest.raises(SnapshotInvalid, match="unexpected files"):
            read_snapshot(bad)


def test_a_missing_file_is_rejected(tmp_path, bundle):
    bad = _zip_without(bundle, tmp_path / "bad.zip", drop={"items.json"})
    with pytest.raises(SnapshotInvalid, match="lacks"):
        read_snapshot(bad)


def test_an_unknown_format_is_rejected(tmp_path, bundle):
    bad = _zip_without(bundle, tmp_path / "bad.zip", manifest={"format": "other.v9"})
    with pytest.raises(SnapshotInvalid, match="unsupported snapshot format"):
        read_snapshot(bad)


def test_counts_must_match_the_manifest(tmp_path, bundle):
    bad = _zip_without(
        bundle, tmp_path / "bad.zip",
        manifest={"counts": {"items": 5, "relationships": 2, "work_sessions": 1,
                             "import_batches": 1}},
    )
    with pytest.raises(SnapshotInvalid, match="count for items"):
        read_snapshot(bad)


def test_an_item_without_an_id_is_rejected(tmp_path, bundle):
    bad = _zip_without(
        bundle, tmp_path / "bad.zip",
        drop={"items.json"}, add={"items.json": json.dumps([{"title": "x"}])},
        manifest={"counts": {"items": 1, "relationships": 2, "work_sessions": 1,
                             "import_batches": 1}},
    )
    with pytest.raises(SnapshotInvalid, match="malformed"):
        read_snapshot(bad)


def test_a_valid_snapshot_reads_back(bundle):
    snapshot = read_snapshot(bundle)
    assert snapshot.project_key == "p"
    assert len(snapshot.items) == 2 and snapshot.project_toml is not None
