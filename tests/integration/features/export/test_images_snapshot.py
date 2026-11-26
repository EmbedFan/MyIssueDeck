"""FEA-0013 phase 5: images and image links in snapshots, and when a project is deleted."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.config import ConfigRegistry, ImagesConfig, ServerConfig
from issuedeck.core.errors import SnapshotInvalid
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.export.snapshot_import import import_snapshot, read_snapshot
from issuedeck.features.images.link_repo import ItemImageRepo
from issuedeck.features.images.link_service import ItemImageService
from issuedeck.features.images.repo import ImageStore
from issuedeck.features.images.service import ImageService
from issuedeck.features.items.models import Item, ItemImage, WorkSession
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.projects.service import ProjectService

from .test_audit_bundle import _registry, session_and_registry  # noqa: F401
from .test_roundtrip import _read
from .test_snapshot_import import _new_db, _zip_without

NS = 'xmlns="http://www.w3.org/2000/svg"'
SVG_A = f'<svg {NS}><rect width="1" height="1"/></svg>'.encode()
SVG_B = f'<svg {NS}><circle r="2"/></svg>'.encode()
SVG_C = f'<svg {NS}><path d="M0 0L9 9"/></svg>'.encode()
FULL_TOML = "\n".join([
    'key = "p"', 'name = "P"',
    "[kinds.feature]", 'label = "Feature"', 'prefix = "FEAT"',
    "[statuses.proposed]", 'label = "P"',
    "[statuses.done]", 'label = "D"', "terminal = true", "requires_ship = true",
    "[[branches]]", 'key = "main"', 'label = "Main"',
    "[custom_fields.priority]", 'label = "Priority"', 'type = "select"',
    'options = ["low", "high"]', "",
])


@pytest.fixture
async def world(tmp_path, session_and_registry):  # noqa: F811
    """Project p with two items, two images and three links; its data folder is in tmp_path."""
    session, registry = session_and_registry
    (registry.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    registry.server.data_dir = tmp_path / "source-data"
    images = ImageService(registry.server.data_dir / "images", ImagesConfig(), registry)
    images.upload("p", "pump.svg", SVG_A)
    images.upload("p", "valve.svg", SVG_B)
    links = ItemImageService(
        images, ItemRepo(session), ItemImageRepo(session), registry, session,
    )
    await links.link("p", "FEAT-0001", "IMG-0001")
    await links.link("p", "FEAT-0002", "IMG-0001")
    await links.link("p", "FEAT-0002", "IMG-0002")
    return session, registry, images


def _target(tmp_path: Path, name: str) -> ConfigRegistry:
    projects_dir = tmp_path / f"{name}-projects"
    projects_dir.mkdir()
    return ConfigRegistry(
        server=ServerConfig(
            api_token="t", projects_dir=projects_dir, data_dir=tmp_path / f"{name}-data",
        ),
        projects={},
    )


async def _export(session, registry, path, key="p"):
    report = await export_audit_bundle(
        session=session, registry=registry, project_key=key, out_path=path)
    return report.bundle_path


def _names(path):
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def _store(registry, key="p") -> Path:
    return registry.server.data_dir / "images" / key


# ------------------------------------------------------------------------------ export


async def test_a_project_without_images_exports_exactly_the_old_files(
        tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    registry.server.data_dir = tmp_path / "data"

    path = await _export(session, registry, tmp_path / "plain.zip")

    assert sorted(_names(path)) == [
        "import_batches.json", "items.json", "manifest.json", "project.json",
        "project.toml", "relationships.json", "work_sessions.json",
    ]
    manifest = json.loads(zipfile.ZipFile(path).read("manifest.json"))
    assert "images" not in manifest["counts"] and "item_images" not in manifest["counts"]


async def test_the_export_carries_the_images_the_registry_and_the_links(tmp_path, world):
    session, registry, _images = world

    path = await _export(session, registry, tmp_path / "with.zip")

    assert {"images.json", "item_images.json", "images/IMG-0001.svg", "images/IMG-0002.svg"} \
        <= set(_names(path))
    with zipfile.ZipFile(path) as archive:
        assert archive.read("images/IMG-0001.svg") == SVG_A
        assert archive.read("images/IMG-0002.svg") == SVG_B
        # the registry is the store's own file, byte for byte
        assert archive.read("images.json") == (_store(registry) / "images.json").read_bytes()
        links = json.loads(archive.read("item_images.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert [(row["local_id"], row["image_id"]) for row in links] == [
        ("FEAT-0001", "IMG-0001"), ("FEAT-0002", "IMG-0001"), ("FEAT-0002", "IMG-0002"),
    ]
    assert manifest["counts"]["images"] == 2 and manifest["counts"]["item_images"] == 3
    assert "images/IMG-0001.svg" in manifest["files"] and "item_images.json" in manifest["files"]


async def test_two_exports_of_the_same_images_are_equal_except_the_time(tmp_path, world):
    session, registry, _images = world

    first = await _export(session, registry, tmp_path / "one.zip")
    second = await _export(session, registry, tmp_path / "two.zip")

    assert _read(first) == _read(second)


# ------------------------------------------------------------------------------ import


async def test_import_creates_the_images_and_the_links_and_exports_the_same_files(
        tmp_path, world):
    session, registry, _images = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "new")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=True)

        assert (report.images_added, report.item_images_added) == (2, 3)
        assert report.images_skipped == 0 and report.warnings == []
        store = _store(target)
        assert (store / "IMG-0001.svg").read_bytes() == SVG_A
        assert (store / "IMG-0002.svg").read_bytes() == SVG_B
        source_registry = (_store(registry) / "images.json").read_bytes()
        assert (store / "images.json").read_bytes() == source_registry
        rows = (await other.execute(
            select(Item.local_id, ItemImage.image_id).join(ItemImage, ItemImage.item_pk == Item.pk)
        )).all()
        assert sorted(rows) == [
            ("FEAT-0001", "IMG-0001"), ("FEAT-0002", "IMG-0001"), ("FEAT-0002", "IMG-0002"),
        ]
        again = await _export(other, target, tmp_path / "again.zip")
    await engine.dispose()

    assert _read(again) == _read(original)


async def test_a_preview_counts_the_images_and_writes_nothing(tmp_path, world):
    session, registry, _images = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "preview")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=False)
        assert (report.images_added, report.item_images_added) == (2, 3)
        assert report.applied is False
        assert not (target.server.data_dir / "images").exists()
        assert (await other.execute(select(ItemImage))).first() is None
    await engine.dispose()


async def test_an_update_from_its_own_snapshot_changes_no_image(tmp_path, world):
    session, registry, _images = world
    before = await _export(session, registry, tmp_path / "before.zip")

    report = await import_snapshot(
        session=session, registry=registry, bundle_path=before, mode="update", apply=True)

    assert (report.images_added, report.images_unchanged) == (0, 2)
    assert (report.images_skipped, report.item_images_added) == (0, 0)
    assert _read(await _export(session, registry, tmp_path / "after.zip")) == _read(before)


async def test_an_older_snapshot_without_images_imports_as_before(
        tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    (registry.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    registry.server.data_dir = tmp_path / "data"
    old = await _export(session, registry, tmp_path / "old.zip")
    target = _target(tmp_path, "old")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=old, mode="create", apply=True)
    await engine.dispose()

    assert report.items_created == 2
    assert (report.images_added, report.item_images_added, report.warnings) == (0, 0, [])
    assert not (target.server.data_dir / "images").exists()


async def _import_changed(tmp_path, world, *, name, drop=(), add=None, edit_registry=None):
    session, registry, _images = world
    original = await _export(session, registry, tmp_path / f"{name}-original.zip")
    add = dict(add or {})
    if edit_registry is not None:
        doc = json.loads(zipfile.ZipFile(original).read("images.json"))
        edit_registry(doc)
        drop = (*drop, "images.json")
        add["images.json"] = json.dumps(doc)
    changed = _zip_without(original, tmp_path / f"{name}.zip", drop=drop, add=add)
    target = _target(tmp_path, name)
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=changed, mode="create", apply=True)
        links = (await other.execute(select(ItemImage.image_id))).scalars().all()
    await engine.dispose()
    return report, target, sorted(links)


async def test_an_image_that_does_not_match_its_checksum_is_skipped_with_its_links(
        tmp_path, world):
    report, target, links = await _import_changed(
        tmp_path, world, name="tampered",
        drop=("images/IMG-0002.svg",), add={"images/IMG-0002.svg": SVG_C})

    assert report.items_created == 2
    assert (report.images_added, report.images_skipped) == (1, 1)
    assert any("IMG-0002" in w and "checksum" in w for w in report.warnings)
    assert any("1 image link(s) were skipped" in w for w in report.warnings)
    assert sorted(p.name for p in _store(target).iterdir()) == ["IMG-0001.svg", "images.json"]
    assert links == ["IMG-0001", "IMG-0001"]


async def test_an_unsafe_svg_in_a_snapshot_is_refused_like_an_upload(tmp_path, world):
    evil = f'<svg {NS}><script>alert(1)</script></svg>'.encode()

    def edit(doc):
        doc["images"][0]["sha256"] = hashlib.sha256(evil).hexdigest()
        doc["images"][0]["size"] = len(evil)

    report, target, links = await _import_changed(
        tmp_path, world, name="evil", drop=("images/IMG-0001.svg",),
        add={"images/IMG-0001.svg": evil}, edit_registry=edit)

    assert (report.images_added, report.images_skipped) == (1, 1)
    assert any("IMG-0001" in w and "SVG refused" in w for w in report.warnings)
    assert not (_store(target) / "IMG-0001.svg").exists()
    assert links == ["IMG-0002"]


async def test_an_image_whose_file_is_missing_is_skipped(tmp_path, world):
    report, target, links = await _import_changed(
        tmp_path, world, name="missing", drop=("images/IMG-0001.svg",))

    assert (report.images_added, report.images_skipped) == (1, 1)
    assert any("IMG-0001" in w and "file is missing" in w for w in report.warnings)
    assert links == ["IMG-0002"]


async def test_a_registry_entry_with_a_bad_id_or_a_listed_twice_is_skipped(tmp_path, world):
    def edit(doc):
        doc["images"].append({**doc["images"][0], "id": "../../evil"})
        doc["images"].append(dict(doc["images"][0]))

    report, _target_registry, _links = await _import_changed(
        tmp_path, world, name="odd", edit_registry=edit)

    assert report.images_added == 2 and report.images_skipped == 2
    assert any("without a valid id" in w and "listed twice" in w for w in report.warnings)


async def test_a_snapshot_with_a_stray_file_in_images_is_refused(tmp_path, world):
    session, registry, _images = world
    original = await _export(session, registry, tmp_path / "original.zip")
    strays = ("images/evil.svg", "images/IMG-1.svg", "images/../x.svg", "images/sub/IMG-0003.svg")
    for stray in strays:
        changed = _zip_without(original, tmp_path / "stray.zip", add={stray: SVG_A})
        with pytest.raises(SnapshotInvalid, match="unexpected files"):
            read_snapshot(changed)


async def test_a_manifest_count_that_does_not_match_is_refused(tmp_path, world):
    session, registry, _images = world
    original = await _export(session, registry, tmp_path / "original.zip")
    manifest = json.loads(zipfile.ZipFile(original).read("manifest.json"))
    manifest["counts"]["item_images"] = 9
    changed = _zip_without(original, tmp_path / "count.zip", manifest=manifest)

    with pytest.raises(SnapshotInvalid, match="item_images"):
        read_snapshot(changed)


async def test_an_update_keeps_an_image_that_has_the_same_id_with_other_content(
        tmp_path, world):
    session, registry, images = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "busy")
    ImageService(target.server.data_dir / "images", ImagesConfig(), target)  # same layout
    target.register_project(registry.project("p"))
    (target.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    other_images = ImageService(target.server.data_dir / "images", ImagesConfig(), target)
    other_images.upload("p", "mine.svg", SVG_C)  # IMG-0001 here is another picture
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="update",
            project_key="p", apply=True)
    await engine.dispose()

    assert (_store(target) / "IMG-0001.svg").read_bytes() == SVG_C  # untouched
    assert (_store(target) / "IMG-0002.svg").read_bytes() == SVG_B  # the free id is added
    assert (report.images_added, report.images_skipped) == (1, 1)
    assert any("IMG-0001" in w and "another image with this id" in w for w in report.warnings)
    registry_doc = json.loads((_store(target) / "images.json").read_text(encoding="utf-8"))
    assert registry_doc["next_id"] == 3


async def test_a_failed_commit_takes_the_written_images_back(tmp_path, world, monkeypatch):
    session, registry, _images = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "failing")
    engine, Session = await _new_db()
    async with Session() as other:
        async def refuse(self):
            raise RuntimeError("disk full")

        monkeypatch.setattr(AsyncSession, "commit", refuse)
        with pytest.raises(RuntimeError, match="disk full"):
            await import_snapshot(
                session=other, registry=target, bundle_path=original, mode="create", apply=True)
    await engine.dispose()

    assert not (target.server.data_dir / "images" / "p").exists()
    assert target.all_projects() == []
    assert not (target.server.projects_dir / "p.toml").exists()


# ------------------------------------------------------------------------------ deleting a project


async def test_deleting_a_project_keeps_its_images_in_the_backup_and_removes_the_folder(
        tmp_path, world):
    session, registry, _images = world
    await session.execute(update(WorkSession).values(status="completed"))
    await session.commit()
    assert _store(registry).is_dir()

    result = await ProjectService(registry, session).delete_project("p", confirm_key="p")

    assert not _store(registry).exists()
    assert (await session.execute(select(ItemImage))).first() is None
    with zipfile.ZipFile(result.backup_path) as archive:
        assert archive.read("images/IMG-0001.svg") == SVG_A
        assert archive.read("images/IMG-0002.svg") == SVG_B
        assert len(json.loads(archive.read("item_images.json"))) == 3

    engine, Session = await _new_db()  # the backup restores the project with its images
    target = _target(tmp_path, "restored")
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=result.backup_path,
            mode="create", apply=True)
    await engine.dispose()
    assert (report.images_added, report.item_images_added) == (2, 3)
    assert (_store(target) / "IMG-0001.svg").read_bytes() == SVG_A


async def test_a_project_created_later_under_the_same_key_does_not_find_old_images(
        tmp_path, world):
    session, registry, _images = world
    await session.execute(update(WorkSession).values(status="completed"))
    await session.commit()

    await ProjectService(registry, session).delete_project("p", confirm_key="p")

    fresh = ImageStore(registry.server.data_dir / "images", "p")
    assert fresh.load() == {"next_id": 1, "images": []}
