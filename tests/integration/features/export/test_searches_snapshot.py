"""FEA-0010 phase 4: saved searches in snapshots, in imports, in GitHub files and when a project
is deleted."""

import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import update

from issuedeck.core.config import ConfigRegistry, ServerConfig
from issuedeck.core.errors import SnapshotInvalid
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.export.snapshot_import import import_snapshot, read_snapshot
from issuedeck.features.github_sync.service import _optional_file
from issuedeck.features.items.models import WorkSession
from issuedeck.features.projects.service import ProjectService
from issuedeck.features.search.saved import SEARCHES_FILE, SavedSearchStore

from .test_audit_bundle import session_and_registry  # noqa: F401
from .test_images_snapshot import FULL_TOML
from .test_snapshot_import import _new_db, _zip_without


def q(word):
    return {"items": [{"type": "text", "mode": "simple", "value": word}]}


@pytest.fixture
async def world(tmp_path, session_and_registry):  # noqa: F811
    """Project p with two saved searches and a latest search; its data folder is in tmp_path."""
    session, registry = session_and_registry
    (registry.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    registry.server.data_dir = tmp_path / "source-data"
    store = SavedSearchStore(registry.server.data_dir, "p")
    store.save("Open bugs", q("bug"))
    store.save("Keresés – árvíztűrő", q("tükör"))
    store.set_active(q("latest"))
    return session, registry, store


def _target(tmp_path: Path, name: str) -> ConfigRegistry:
    projects_dir = tmp_path / f"{name}-projects"
    projects_dir.mkdir()
    return ConfigRegistry(
        server=ServerConfig(
            api_token="t", projects_dir=projects_dir, data_dir=tmp_path / f"{name}-data",
        ),
        projects={},
    )


async def _export(session, registry, path):
    report = await export_audit_bundle(
        session=session, registry=registry, project_key="p", out_path=path)
    return report


async def _import(tmp_path, bundle, name, *, mode="create", target=None, apply=True):
    target = target or _target(tmp_path, name)
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=bundle, mode=mode, apply=apply)
    await engine.dispose()
    return report, target


# ------------------------------------------------------------------------------ export


async def test_a_project_without_saved_searches_exports_no_file(tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    registry.server.data_dir = tmp_path / "data"

    report = await _export(session, registry, tmp_path / "plain.zip")

    with zipfile.ZipFile(report.bundle_path) as archive:
        assert SEARCHES_FILE not in archive.namelist()
        assert "searches" not in json.loads(archive.read("manifest.json"))["counts"]
    assert report.searches_written == 0


async def test_the_export_carries_the_file_exactly_as_stored_and_lists_it(tmp_path, world):
    session, registry, store = world

    report = await _export(session, registry, tmp_path / "with.zip")

    with zipfile.ZipFile(report.bundle_path) as archive:
        assert archive.read(SEARCHES_FILE) == store.path.read_bytes()
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["counts"]["searches"] == 2  # the named ones; the latest is not counted
    assert SEARCHES_FILE in manifest["files"]
    assert report.searches_written == 2


async def test_two_exports_of_the_same_state_are_the_same_bytes(tmp_path, world):
    session, registry, _store = world

    first = await _export(session, registry, tmp_path / "one.zip")
    second = await _export(session, registry, tmp_path / "two.zip")

    with zipfile.ZipFile(first.bundle_path) as a, zipfile.ZipFile(second.bundle_path) as b:
        assert a.read(SEARCHES_FILE) == b.read(SEARCHES_FILE)


async def test_only_a_latest_search_is_exported_too(tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    registry.server.data_dir = tmp_path / "data"
    SavedSearchStore(registry.server.data_dir, "p").set_active(q("only"))

    report = await _export(session, registry, tmp_path / "latest.zip")

    with zipfile.ZipFile(report.bundle_path) as archive:
        saved = json.loads(archive.read(SEARCHES_FILE))
    assert saved["active"]["query"] == q("only") and saved["searches"] == []


# ------------------------------------------------------------------------------ import


async def test_the_searches_survive_a_round_trip_into_a_new_project(tmp_path, world):
    session, registry, store = world
    exported = await _export(session, registry, tmp_path / "rt.zip")

    report, target = await _import(tmp_path, exported.bundle_path, "restored")

    assert report.applied and report.searches_added == 2
    restored = SavedSearchStore(target.server.data_dir, "p")
    assert restored.read() == store.read()  # names, queries, times and the latest search
    assert restored.path.read_bytes() == store.path.read_bytes()


async def test_a_dry_run_writes_nothing(tmp_path, world):
    session, registry, _store = world
    exported = await _export(session, registry, tmp_path / "dry.zip")

    report, target = await _import(tmp_path, exported.bundle_path, "dry", apply=False)

    assert not report.applied and report.searches_added == 2  # what it would do
    assert not (target.server.data_dir / "searches").exists()


async def test_an_update_keeps_the_searches_of_the_project_and_adds_new_ones(tmp_path, world):
    session, registry, _store = world
    exported = await _export(session, registry, tmp_path / "up.zip")
    _first, target = await _import(tmp_path, exported.bundle_path, "up")
    mine = SavedSearchStore(target.server.data_dir, "p")
    mine.save("Open bugs", q("my own bug search"), overwrite=True)  # differs from the snapshot
    mine.save("Mine only", q("mine"))
    mine.set_active(q("my latest"))

    report, _same = await _import(
        tmp_path, exported.bundle_path, "up", mode="update", target=target)

    assert report.searches_added == 0 and report.searches_unchanged == 1  # the Keresés one
    assert report.searches_skipped == 1
    assert any("Open bugs" in warning for warning in report.warnings)
    after = mine.read()
    names = [s["name"] for s in after["searches"]]
    assert names == ["Keresés – árvíztűrő", "Mine only", "Open bugs"]
    assert mine.get("Open bugs")["query"] == q("my own bug search")  # not replaced
    assert after["active"]["query"] == q("my latest")  # the latest search of the project stays


async def test_a_snapshot_of_an_older_version_without_the_file_still_imports(tmp_path, world):
    session, registry, _store = world
    exported = await _export(session, registry, tmp_path / "old.zip")
    old = _zip_without(
        exported.bundle_path, tmp_path / "old-version.zip", drop=(SEARCHES_FILE,),
        manifest={"counts": {}})

    report, target = await _import(tmp_path, old, "old")

    assert report.applied and report.searches_added == 0
    assert not (target.server.data_dir / "searches").exists()


async def test_a_manifest_count_that_does_not_match_is_refused(tmp_path, world):
    session, registry, _store = world
    exported = await _export(session, registry, tmp_path / "count.zip")
    manifest = json.loads(zipfile.ZipFile(exported.bundle_path).read("manifest.json"))
    manifest["counts"]["searches"] = 7
    bad = _zip_without(exported.bundle_path, tmp_path / "bad-count.zip",
                       manifest={"counts": manifest["counts"]})

    with pytest.raises(SnapshotInvalid, match="searches"):
        read_snapshot(bad)


async def test_a_searches_file_that_is_not_an_object_is_refused(tmp_path, world):
    session, registry, _store = world
    exported = await _export(session, registry, tmp_path / "shape.zip")
    bad = _zip_without(exported.bundle_path, tmp_path / "bad-shape.zip",
                       drop=(SEARCHES_FILE,), add={SEARCHES_FILE: "[1, 2]"})

    with pytest.raises(SnapshotInvalid):
        read_snapshot(bad)


async def test_damaged_entries_in_the_file_are_left_out_not_fatal(tmp_path, world):
    session, registry, _store = world
    exported = await _export(session, registry, tmp_path / "damaged.zip")
    content = json.dumps({"searches": [
        {"name": "Good", "query": q("good")}, {"name": "", "query": q("x")}, "junk",
        {"name": "No query"}]})
    changed = _zip_without(exported.bundle_path, tmp_path / "damaged-entries.zip",
                           drop=(SEARCHES_FILE,), add={SEARCHES_FILE: content},
                           manifest={"counts": {"searches": 4}})

    report, target = await _import(tmp_path, changed, "damaged")

    assert report.searches_added == 1
    assert [s["name"] for s in SavedSearchStore(target.server.data_dir, "p").read()["searches"]
            ] == ["Good"]


# ------------------------------------------------------------------------------ GitHub, deletion


def test_the_github_export_lets_the_file_travel_with_the_other_optional_files():
    assert _optional_file("searches.json")
    assert _optional_file("documents/DOC-0001.json")
    assert not _optional_file("searches/other.json")
    assert not _optional_file("secrets.json")


async def test_deleting_a_project_removes_its_searches_but_the_backup_holds_them(
        tmp_path, world):
    session, registry, store = world
    await session.execute(update(WorkSession).values(status="completed"))
    await session.commit()
    other = SavedSearchStore(registry.server.data_dir, "other")
    other.save("Stays", q("stays"))
    assert store.path.is_file()

    result = await ProjectService(registry, session).delete_project("p", confirm_key="p")

    assert not store.path.exists()
    assert other.path.is_file()  # another project's file is not touched
    with zipfile.ZipFile(result.backup_path) as archive:
        assert SEARCHES_FILE in archive.namelist()
    report, target = await _import(tmp_path, result.backup_path, "from-backup")
    assert report.searches_added == 2
    assert SavedSearchStore(target.server.data_dir, "p").get("open bugs")["query"] == q("bug")
