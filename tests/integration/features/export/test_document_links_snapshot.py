"""FEA-0012 phase 5: the links between documents and items in snapshots."""

import json
import zipfile

import pytest
from sqlalchemy import select, update

from issuedeck.core.errors import SnapshotInvalid
from issuedeck.features.documents.link_repo import ItemDocumentRepo
from issuedeck.features.documents.link_service import ItemDocumentService
from issuedeck.features.export.snapshot_import import import_snapshot, read_snapshot
from issuedeck.features.items.models import Item, ItemDocument, WorkSession
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.projects.service import ProjectService

from .test_audit_bundle import session_and_registry  # noqa: F401
from .test_documents_snapshot import _export, _target, world  # noqa: F401
from .test_roundtrip import _read
from .test_snapshot_import import _new_db, _zip_without


async def _link(world_tuple):
    session, registry, documents = world_tuple
    links = ItemDocumentService(
        documents, ItemRepo(session), ItemDocumentRepo(session), registry, session)
    await links.link("p", "FEAT-0001", "DOC-0001")
    await links.link("p", "FEAT-0002", "DOC-0001")
    await links.link("p", "FEAT-0002", "DOC-0002")
    return links


async def _rows(session):
    return sorted((await session.execute(
        select(Item.local_id, ItemDocument.document_id)
        .join(ItemDocument, ItemDocument.item_pk == Item.pk)
    )).all())


async def test_the_export_lists_the_links_in_a_stable_order(tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)

    path = await _export(session, registry, tmp_path / "with.zip")

    with zipfile.ZipFile(path) as archive:
        links = json.loads(archive.read("item_documents.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert [(r["local_id"], r["document_id"]) for r in links] == [
        ("FEAT-0001", "DOC-0001"), ("FEAT-0002", "DOC-0001"), ("FEAT-0002", "DOC-0002")]
    assert manifest["counts"]["item_documents"] == 3
    assert "item_documents.json" in manifest["files"]
    again = await _export(session, registry, tmp_path / "again.zip")
    assert _read(again) == _read(path)


async def test_an_export_without_links_has_an_empty_list_when_there_are_documents(
        tmp_path, world):  # noqa: F811
    session, registry, _documents = world

    path = await _export(session, registry, tmp_path / "plain.zip")

    with zipfile.ZipFile(path) as archive:
        assert json.loads(archive.read("item_documents.json")) == []
        assert json.loads(archive.read("manifest.json"))["counts"]["item_documents"] == 0


async def test_import_restores_the_links_and_exports_the_same_files(tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "new")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=True)

        assert (report.documents_added, report.item_documents_added) == (2, 3)
        assert report.warnings == []
        assert await _rows(other) == [
            ("FEAT-0001", "DOC-0001"), ("FEAT-0002", "DOC-0001"), ("FEAT-0002", "DOC-0002")]
        again = await _export(other, target, tmp_path / "again.zip")
    await engine.dispose()

    assert _read(again) == _read(original)


async def test_a_preview_counts_the_links_and_writes_nothing(tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "preview")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=False)
        assert (report.item_documents_added, report.applied) == (3, False)
        assert await _rows(other) == []
    await engine.dispose()


async def test_an_update_from_its_own_snapshot_adds_no_link(tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    before = await _export(session, registry, tmp_path / "before.zip")

    report = await import_snapshot(
        session=session, registry=registry, bundle_path=before, mode="update", apply=True)

    assert (report.item_documents_added, report.documents_unchanged) == (0, 2)
    assert _read(await _export(session, registry, tmp_path / "after.zip")) == _read(before)


async def test_links_to_a_document_that_was_not_imported_are_skipped(
        tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    original = await _export(session, registry, tmp_path / "original.zip")
    doc = json.loads(zipfile.ZipFile(original).read("documents/DOC-0002.json"))
    doc["body"] = "tampered"  # the checksum no longer matches: the document is skipped
    changed = _zip_without(original, tmp_path / "bad.zip", drop=("documents/DOC-0002.json",),
                           add={"documents/DOC-0002.json": json.dumps(doc)})
    target = _target(tmp_path, "bad")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=changed, mode="create", apply=True)
        rows = await _rows(other)
    await engine.dispose()

    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert report.item_documents_added == 2
    assert any("1 document link(s) were skipped" in w for w in report.warnings)
    assert rows == [("FEAT-0001", "DOC-0001"), ("FEAT-0002", "DOC-0001")]


async def test_a_link_to_an_unknown_item_is_skipped(tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    original = await _export(session, registry, tmp_path / "original.zip")
    links = json.loads(zipfile.ZipFile(original).read("item_documents.json"))
    links.append({"document_id": "DOC-0001", "local_id": "FEAT-0099", "created_at": ""})
    manifest = json.loads(zipfile.ZipFile(original).read("manifest.json"))
    manifest["counts"]["item_documents"] = len(links)
    changed = _zip_without(original, tmp_path / "unknown.zip", drop=("item_documents.json",),
                           add={"item_documents.json": json.dumps(links)}, manifest=manifest)
    target = _target(tmp_path, "unknown")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=changed, mode="create", apply=True)
    await engine.dispose()

    assert report.item_documents_added == 3
    assert any("1 document link(s) were skipped" in w for w in report.warnings)


async def test_a_snapshot_from_before_the_links_imports_without_them(
        tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    manifest = json.loads(zipfile.ZipFile(original).read("manifest.json"))
    manifest["counts"].pop("item_documents")
    old = _zip_without(original, tmp_path / "old.zip", drop=("item_documents.json",),
                       manifest=manifest)
    target = _target(tmp_path, "old")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=old, mode="create", apply=True)
    await engine.dispose()

    assert (report.documents_added, report.item_documents_added, report.warnings) == (2, 0, [])


async def test_a_manifest_count_of_links_that_does_not_match_is_refused(
        tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    original = await _export(session, registry, tmp_path / "original.zip")
    manifest = json.loads(zipfile.ZipFile(original).read("manifest.json"))
    manifest["counts"]["item_documents"] = 9
    changed = _zip_without(original, tmp_path / "count.zip", manifest=manifest)

    with pytest.raises(SnapshotInvalid, match="item_documents"):
        read_snapshot(changed)


async def test_deleting_a_project_removes_the_link_rows_and_the_backup_restores_them(
        tmp_path, world):  # noqa: F811
    session, registry, _documents = world
    await _link(world)
    await session.execute(update(WorkSession).values(status="completed"))
    await session.commit()

    result = await ProjectService(registry, session).delete_project("p", confirm_key="p")

    assert (await session.execute(select(ItemDocument))).first() is None
    with zipfile.ZipFile(result.backup_path) as archive:
        assert len(json.loads(archive.read("item_documents.json"))) == 3
    engine, Session = await _new_db()
    target = _target(tmp_path, "restored")
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=result.backup_path,
            mode="create", apply=True)
    await engine.dispose()
    assert (report.documents_added, report.item_documents_added) == (2, 3)
