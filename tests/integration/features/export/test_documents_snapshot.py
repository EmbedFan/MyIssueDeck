"""FEA-0012 phase 4: documents in snapshots, in imports and when a project is deleted."""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.config import ConfigRegistry, ServerConfig
from issuedeck.core.errors import SnapshotInvalid
from issuedeck.features.documents.repo import DocumentStore
from issuedeck.features.documents.service import MAX_REVISIONS, DocumentService
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.export.snapshot_import import import_snapshot, read_snapshot
from issuedeck.features.items.models import WorkSession
from issuedeck.features.projects.service import ProjectService

from .test_audit_bundle import session_and_registry  # noqa: F401
from .test_images_snapshot import FULL_TOML
from .test_roundtrip import _read
from .test_snapshot_import import _new_db, _zip_without


@pytest.fixture
async def world(tmp_path, session_and_registry):  # noqa: F811
    """Project p with two documents (one with a history); its data folder is in tmp_path."""
    session, registry = session_and_registry
    (registry.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    registry.server.data_dir = tmp_path / "source-data"
    documents = DocumentService(registry.server.data_dir / "documents", registry)
    first = documents.create("p", "Feature request.md", "# Request v1\n", kind="request",
                             title="The request", actor="me")
    documents.replace("p", first["id"], "# Request v2\r\nwith CRLF é\n", revision=1, actor="you")
    documents.create("p", "Árvíztűrő notes", "plain notes", kind="other")
    return session, registry, documents


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
    return report.bundle_path


def _names(path):
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def _folder(registry) -> Path:
    return registry.server.data_dir / "documents" / "p"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


async def _import_changed(tmp_path, world, *, name, change=None, drop=(), add=None):
    """Export, change the snapshot (``change`` edits the documents) and import it as new."""
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / f"{name}-original.zip")
    add = dict(add or {})
    if change is not None:
        with zipfile.ZipFile(original) as archive:
            docs = {n: json.loads(archive.read(n)) for n in archive.namelist()
                    if n.startswith("documents/")}
        change(docs)
        for file_name, doc in docs.items():
            drop = (*drop, file_name)
            add[file_name] = _canonical(doc)
    changed = _zip_without(original, tmp_path / f"{name}.zip", drop=drop, add=add)
    target = _target(tmp_path, name)
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=changed, mode="create", apply=True)
    await engine.dispose()
    return report, target


# ------------------------------------------------------------------------------ export


async def test_a_project_without_documents_exports_no_document_file(
        tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    registry.server.data_dir = tmp_path / "data"

    path = await _export(session, registry, tmp_path / "plain.zip")

    assert not [n for n in _names(path) if "document" in n]
    manifest = json.loads(zipfile.ZipFile(path).read("manifest.json"))
    assert "documents" not in manifest["counts"]


async def test_the_export_carries_the_document_files_exactly_as_stored(tmp_path, world):
    session, registry, _documents = world

    path = await _export(session, registry, tmp_path / "with.zip")

    with zipfile.ZipFile(path) as archive:
        for number in (1, 2):
            name = f"documents/DOC-000{number}.json"
            assert archive.read(name) == (_folder(registry) / f"DOC-000{number}.json").read_bytes()
        listing = json.loads(archive.read("documents.json"))
        manifest = json.loads(archive.read("manifest.json"))
    assert listing == {"ids": ["DOC-0001", "DOC-0002"], "next_id": 3}
    assert manifest["counts"]["documents"] == 2
    assert "documents/DOC-0001.json" in manifest["files"] and "documents.json" in manifest["files"]


async def test_two_exports_of_the_same_documents_are_equal_except_the_time(tmp_path, world):
    session, registry, _documents = world

    first = await _export(session, registry, tmp_path / "one.zip")
    second = await _export(session, registry, tmp_path / "two.zip")

    assert _read(first) == _read(second)


# ------------------------------------------------------------------------------ import


async def test_import_restores_the_documents_byte_for_byte_and_exports_the_same_files(
        tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "new")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=True)

        assert (report.documents_added, report.documents_unchanged) == (2, 0)
        assert report.documents_skipped == 0 and report.warnings == []
        for name in ("DOC-0001.json", "DOC-0002.json"):
            source_bytes = (_folder(registry) / name).read_bytes()
            assert (_folder(target) / name).read_bytes() == source_bytes
        assert DocumentStore(target.server.data_dir / "documents", "p").next_id() == 3
        again = await _export(other, target, tmp_path / "again.zip")
    await engine.dispose()

    assert _read(again) == _read(original)


async def test_a_restored_document_keeps_its_text_history_and_ids(tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "new")
    engine, Session = await _new_db()
    async with Session() as other:
        await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=True)
    await engine.dispose()

    restored = DocumentService(target.server.data_dir / "documents", target)
    document = restored.get("p", "DOC-0001")

    assert document["name"] == "Feature request.md" and document["revision"] == 2
    assert document["body"] == "# Request v2\r\nwith CRLF é\n"
    assert [r["body"] for r in document["revisions"]] == ["# Request v1\n"]
    assert restored.create("p", "new.md", "x")["id"] == "DOC-0003"  # ids go on


async def test_a_preview_counts_the_documents_and_writes_nothing(tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "preview")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=False)
    await engine.dispose()

    assert (report.documents_added, report.applied) == (2, False)
    assert not (target.server.data_dir / "documents").exists()


async def test_an_update_from_its_own_snapshot_changes_no_document(tmp_path, world):
    session, registry, _documents = world
    before = await _export(session, registry, tmp_path / "before.zip")

    report = await import_snapshot(
        session=session, registry=registry, bundle_path=before, mode="update", apply=True)

    assert (report.documents_added, report.documents_unchanged, report.documents_skipped) \
        == (0, 2, 0)
    assert _read(await _export(session, registry, tmp_path / "after.zip")) == _read(before)


async def test_an_older_snapshot_without_documents_imports_as_before(
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
    assert (report.documents_added, report.warnings) == (0, [])
    assert not (target.server.data_dir / "documents").exists()


async def test_only_the_listed_documents_are_imported(tmp_path, world):
    """A deleted document may leave a file in a repository folder; it must not come back."""
    session, registry, documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    leftover = json.loads(zipfile.ZipFile(original).read("documents/DOC-0002.json"))
    leftover.update(id="DOC-0009", name="deleted long ago.md")
    changed = _zip_without(original, tmp_path / "left.zip",
                           add={"documents/DOC-0009.json": _canonical(leftover)})
    target = _target(tmp_path, "left")
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=changed, mode="create", apply=True)
    await engine.dispose()

    assert (report.documents_added, report.documents_skipped, report.warnings) == (2, 0, [])
    assert sorted(p.name for p in _folder(target).iterdir()) == [
        "DOC-0001.json", "DOC-0002.json", "documents.json"]
    assert documents is not None


# ------------------------------------------------------------------------------ checks


async def test_a_text_that_does_not_match_its_checksum_is_skipped(tmp_path, world):
    def change(docs):
        docs["documents/DOC-0002.json"]["body"] = "tampered"  # sha256 stays the old one

    report, target = await _import_changed(tmp_path, world, name="tampered", change=change)

    assert report.items_created == 2
    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0002" in w and "checksum" in w for w in report.warnings)
    assert sorted(p.name for p in _folder(target).iterdir()) == ["DOC-0001.json", "documents.json"]


async def test_a_revision_that_does_not_match_its_checksum_skips_the_document(tmp_path, world):
    def change(docs):
        docs["documents/DOC-0001.json"]["revisions"][0]["body"] = "changed history"

    report, _target_registry = await _import_changed(tmp_path, world, name="history", change=change)

    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0001" in w and "revision 1" in w for w in report.warnings)


async def test_a_binary_text_with_a_matching_checksum_is_still_refused(tmp_path, world):
    def change(docs):
        doc = docs["documents/DOC-0002.json"]
        doc["body"] = "bin\u0000ary"
        doc["sha256"] = _sha(doc["body"])

    report, _t = await _import_changed(tmp_path, world, name="binary", change=change)

    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0002" in w and "not text" in w for w in report.warnings)


@pytest.mark.parametrize(("label", "mutate", "reason"), [
    ("id", lambda d: d.update(id="DOC-0077"), "does not match its file name"),
    ("name", lambda d: d.update(name="../evil.md"), "not a clean name"),
    ("empty-name", lambda d: d.update(name=""), "not a clean name"),
    ("kind", lambda d: d.update(kind="essay"), "kind is unknown"),
    ("revision", lambda d: d.update(revision="two"), "revision is not a number"),
    ("title", lambda d: d.update(title=5), "title is not text"),
    ("actor", lambda d: d.pop("actor"), "actor is missing"),
    ("history-order", lambda d: d["revisions"].append(dict(d["revisions"][0])),
     "not in order"),
    ("history-ahead", lambda d: d["revisions"][0].update(revision=9), "not in order"),
    ("too-many", lambda d: d.update(revisions=[
        {"revision": n, "body": "x", "sha256": _sha("x"), "time": "t", "actor": "a"}
        for n in range(1, 60)], revision=100), "more than 50 revisions"),
], ids=lambda v: v if isinstance(v, str) and v.isidentifier() or "-" in str(v) else "")
async def test_a_malformed_document_is_skipped_and_named(tmp_path, world, label, mutate, reason):
    def change(docs):
        mutate(docs["documents/DOC-0001.json"])

    report, _t = await _import_changed(tmp_path, world, name=f"bad-{label}", change=change)

    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0001" in w and reason in w for w in report.warnings)


async def test_a_file_that_is_not_json_is_skipped(tmp_path, world):
    report, _t = await _import_changed(
        tmp_path, world, name="notjson", drop=("documents/DOC-0001.json",),
        add={"documents/DOC-0001.json": b"{ not json"})

    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0001" in w and "not valid JSON" in w for w in report.warnings)


async def test_a_listed_document_whose_file_is_missing_is_named(tmp_path, world):
    report, _t = await _import_changed(
        tmp_path, world, name="missing", drop=("documents/DOC-0002.json",))

    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0002" in w and "file is missing" in w for w in report.warnings)


async def test_a_stray_file_under_documents_is_refused(tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    for stray in ("documents/evil.json", "documents/DOC-1.json", "documents/sub/DOC-0001.json",
                  "documents/DOC-0001.md", "documents/../x.json"):
        changed = _zip_without(original, tmp_path / "stray.zip", add={stray: "{}"})
        with pytest.raises(SnapshotInvalid, match="unexpected files"):
            read_snapshot(changed)


async def test_a_manifest_count_that_does_not_match_is_refused(tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    manifest = json.loads(zipfile.ZipFile(original).read("manifest.json"))
    manifest["counts"]["documents"] = 9
    changed = _zip_without(original, tmp_path / "count.zip", manifest=manifest)

    with pytest.raises(SnapshotInvalid, match="documents"):
        read_snapshot(changed)


# ------------------------------------------------------------------------------ merging


async def _busy_target(tmp_path, registry, files):
    target = _target(tmp_path, "busy")
    target.register_project(registry.project("p"))
    (target.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    service = DocumentService(target.server.data_dir / "documents", target)
    for name, body in files:
        service.create("p", name, body)
    return target, service


async def test_an_update_keeps_a_document_that_has_the_same_id_with_other_content(
        tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target, service = await _busy_target(tmp_path, registry, [("mine.md", "my own text")])
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="update",
            project_key="p", apply=True)
    await engine.dispose()

    assert service.get("p", "DOC-0001")["body"] == "my own text"  # untouched
    assert (report.documents_added, report.documents_skipped) == (1, 1)
    assert any("DOC-0001" in w and "another document with this id" in w for w in report.warnings)
    assert service.get("p", "DOC-0002")["name"] == "Árvíztűrő notes"


async def test_a_name_that_another_document_already_uses_is_skipped(tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target, service = await _busy_target(
        tmp_path, registry, [("other.md", "o"), ("temporary", "t"), ("Árvíztűrő notes", "mine")])
    service.delete("p", "DOC-0002")  # the id 2 is free, the name is used by DOC-0003
    engine, Session = await _new_db()
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="update",
            project_key="p", apply=True)
    await engine.dispose()

    assert any("DOC-0002" in w and "name is used by DOC-0003" in w for w in report.warnings)
    assert any("DOC-0001" in w and "another document with this id" in w for w in report.warnings)
    assert report.documents_added == 0 and report.documents_skipped == 2
    assert service.get("p", "DOC-0003")["body"] == "mine"


async def test_the_next_id_never_goes_down(tmp_path, world):
    session, registry, _documents = world
    original = await _export(session, registry, tmp_path / "original.zip")
    target = _target(tmp_path, "high")
    store = DocumentStore(target.server.data_dir / "documents", "p")
    store.set_next_id(50)
    engine, Session = await _new_db()
    async with Session() as other:
        await import_snapshot(
            session=other, registry=target, bundle_path=original, mode="create", apply=True)
    await engine.dispose()

    assert store.next_id() == 50


async def test_a_failed_commit_takes_the_written_documents_back(tmp_path, world, monkeypatch):
    session, registry, _documents = world
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

    assert not (target.server.data_dir / "documents" / "p").exists()
    assert target.all_projects() == []


# ------------------------------------------------------------------------------ deleting a project


async def test_deleting_a_project_removes_its_documents_but_the_backup_holds_them(
        tmp_path, world):
    session, registry, _documents = world
    await session.execute(update(WorkSession).values(status="completed"))
    await session.commit()
    assert _folder(registry).is_dir()

    result = await ProjectService(registry, session).delete_project("p", confirm_key="p")

    assert not _folder(registry).exists()
    with zipfile.ZipFile(result.backup_path) as archive:
        assert "documents/DOC-0001.json" in archive.namelist()
        assert json.loads(archive.read("documents/DOC-0002.json"))["name"] == "Árvíztűrő notes"
    engine, Session = await _new_db()  # the backup restores the project with its documents
    target = _target(tmp_path, "restored")
    async with Session() as other:
        report = await import_snapshot(
            session=other, registry=target, bundle_path=result.backup_path,
            mode="create", apply=True)
    await engine.dispose()
    assert report.documents_added == 2
    assert MAX_REVISIONS == 50
