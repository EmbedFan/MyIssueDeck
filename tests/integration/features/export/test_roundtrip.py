"""IS-0010: the files of a snapshot are stable across an import.

The same project data must give the same files, whatever database it lives in, whatever the
order it was written in and whatever the line endings of its configuration file are.
"""

import json
import zipfile

import pytest
from sqlalchemy import select

from issuedeck.features.export.md_bundle import _canonical_toml, export_audit_bundle
from issuedeck.features.export.snapshot_import import import_snapshot
from issuedeck.features.items.models import (
    ImportBatch,
    Item,
    ItemEvent,
    ItemExternalLink,
    ItemRelationship,
    ShipCommit,
    ShipRecord,
    WorkSession,
    WorkSessionUpdate,
)

from .test_audit_bundle import _registry, session_and_registry  # noqa: F401
from .test_snapshot_import import (  # noqa: F401
    _count,
    _new_db,
    _target_registry,
    _zip_without,
    bundle,
)

FIXED = "2026-05-02T10:00:00+00:00"


def _read(path):
    """The files of a snapshot; the manifest without its export time."""
    with zipfile.ZipFile(path) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(files.pop("manifest.json"))
    manifest.pop("generated_at")
    return files, manifest


async def _export(session, registry, key, path):
    report = await export_audit_bundle(
        session=session, registry=registry, project_key=key, out_path=path)
    return report.bundle_path


def _keys_named(value, name, where="$"):
    found = []
    if isinstance(value, dict):
        for key, inner in value.items():
            if key == name:
                found.append(f"{where}.{key}")
            found += _keys_named(inner, name, f"{where}.{key}")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found += _keys_named(inner, name, f"{where}[{index}]")
    return found


# ---------------------------------------------------------------- what the files contain


async def test_no_file_carries_a_database_id(bundle):  # noqa: F811
    with zipfile.ZipFile(bundle) as archive:
        for name in ("items.json", "relationships.json", "work_sessions.json",
                     "import_batches.json"):
            assert _keys_named(json.loads(archive.read(name)), "id") == [], name


async def test_two_exports_of_the_same_data_are_equal_except_the_time(
        tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    first = await _export(session, registry, "p", tmp_path / "one.zip")
    second = await _export(session, registry, "p", tmp_path / "two.zip")

    assert _read(first) == _read(second)


# ---------------------------------------------------------------- the round trip


async def test_import_into_an_empty_database_exports_the_same_files(tmp_path, bundle):  # noqa: F811
    registry = _target_registry(tmp_path, "empty")
    engine, Session = await _new_db()
    async with Session() as session:
        await import_snapshot(
            session=session, registry=registry, bundle_path=bundle, mode="create", apply=True)
        again = await _export(session, registry, "p", tmp_path / "again.zip")
    await engine.dispose()

    assert _read(again) == _read(bundle)


async def test_import_into_a_database_that_holds_other_data_exports_the_same_files(
        tmp_path, bundle):  # noqa: F811
    """The ids of the new rows cannot be the ones of the original: other data used them."""
    registry = _target_registry(tmp_path, "busy")
    engine, Session = await _new_db()
    async with Session() as session:
        await import_snapshot(  # another project takes the first ids of every table
            session=session, registry=registry, bundle_path=bundle, mode="create",
            project_key="other", apply=True)
        await import_snapshot(
            session=session, registry=registry, bundle_path=bundle, mode="create", apply=True)
        ids = {row.id for row in (await session.execute(select(ItemRelationship))).scalars()}
        assert ids == {1, 2, 3, 4}  # the project p has relationship ids 3 and 4 here, not 1 and 2
        again = await _export(session, registry, "p", tmp_path / "again.zip")
    await engine.dispose()

    assert _read(again) == _read(bundle)


async def test_an_update_from_its_own_snapshot_changes_nothing_in_the_next_export(
        tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    before = await _export(session, registry, "p", tmp_path / "before.zip")

    report = await import_snapshot(
        session=session, registry=registry, bundle_path=before, mode="update", apply=True)
    after = await _export(session, registry, "p", tmp_path / "after.zip")

    assert (report.items_created, report.relationships_added) == (0, 0)
    assert (report.work_sessions_added, report.import_batches_added) == (0, 0)
    assert _read(after) == _read(before)


# ---------------------------------------------------------------- the order of writing


async def _fixed_project(Session, reverse):
    """The same data written in two different orders, with timestamps that tie everywhere."""
    def ordered(rows):
        return list(reversed(rows)) if reverse else rows

    async with Session() as session:
        first = Item(
            project_key="p", local_id="FEAT-0001", kind="feature", status="proposed",
            title="Item 1", body="", custom_fields_json="{}", created_at=FIXED, updated_at=FIXED,
            events=[
                ItemEvent(event_type="comment", actor_type="human", actor_name="me", body=body,
                          metadata_json="{}", created_at=FIXED)
                for body in ordered(["first comment", "second comment"])
            ],
            external_links=[
                ItemExternalLink(link_type="other", label=None, url=url, created_at=FIXED)
                for url in ordered(["https://example.com/a", "https://example.com/b"])
            ],
            ship_records=[  # one record per branch
                ShipRecord(branch_key=branch, version="1.0", shipped_at=FIXED,
                           commits=[ShipCommit(sha="abc", position=0)])
                for branch in ordered(["main", "release"])
            ],
        )
        second = Item(
            project_key="p", local_id="FEAT-0002", kind="feature", status="proposed",
            title="Item 2", body="", custom_fields_json="{}", created_at=FIXED, updated_at=FIXED)
        session.add_all(ordered([first, second]))
        await session.flush()
        pairs = [(first.pk, second.pk, "blocks"), (second.pk, first.pk, "related_to")]
        for from_pk, to_pk, kind in ordered(pairs):
            session.add(ItemRelationship(
                from_item_pk=from_pk, to_item_pk=to_pk, relation_type=kind, created_at=FIXED))
        for agent in ordered(["codex", "claude"]):
            session.add(WorkSession(
                project_key="p", item_pk=first.pk, agent_name=agent, status="completed",
                goal="goal", summary="", branch="main", started_at=FIXED, updated_at=FIXED,
                ended_at=FIXED, metadata_json="{}",
                updates=[
                    WorkSessionUpdate(update_type="progress", message=message,
                                      metadata_json="{}", created_at=FIXED)
                    for message in ordered(["step one", "step two"])
                ]))
        for tag in ordered(["batch-a", "batch-b"]):
            session.add(ImportBatch(
                project_key="p", batch_tag=tag, source_type="csv", source_name="x.csv",
                items_planned=1, items_written=1, skipped_count=0, status_mapped=0,
                external_links=0, created_at=FIXED, metadata_json="{}"))
        await session.commit()


async def test_the_order_in_which_rows_were_written_does_not_change_the_files(tmp_path):
    exports = []
    for reverse in (False, True):
        folder = tmp_path / f"order-{reverse}"
        folder.mkdir()
        registry = _registry(folder)
        engine, Session = await _new_db()
        await _fixed_project(Session, reverse)
        async with Session() as session:
            exports.append(_read(await _export(session, registry, "p", folder / "p.zip")))
        await engine.dispose()

    assert exports[0] == exports[1]


# ---------------------------------------------------------------- project.toml


@pytest.mark.parametrize(("raw", "label"), [
    (b'key = "p"\nname = "P"\n', "LF"),
    (b'key = "p"\r\nname = "P"\r\n', "CR LF"),
    (b'key = "p"\r\r\nname = "P"\r\r\n', "CR CR LF (what the importer used to write on Windows)"),
    (b'\xef\xbb\xbfkey = "p"\r\nname = "P"\r\n', "BOM and CR LF"),
    (b'key = "p"\rname = "P"\r', "lone CR"),
])
async def test_the_exported_configuration_has_one_line_ending_whatever_the_file_had(
        tmp_path, session_and_registry, raw, label):  # noqa: F811
    session, registry = session_and_registry
    (registry.server.projects_dir / "p.toml").write_bytes(raw)

    path = await _export(session, registry, "p", tmp_path / "p.zip")

    with zipfile.ZipFile(path) as archive:
        assert archive.read("project.toml") == b'key = "p"\nname = "P"\n', label


def test_canonical_toml_keeps_the_text_and_only_changes_line_ends(tmp_path):
    source = tmp_path / "x.toml"
    source.write_bytes('name = "Árvíztűrő"\r\r\nbody = "a\\r"\r\n'.encode())

    assert _canonical_toml(source) == 'name = "Árvíztűrő"\nbody = "a\\r"\n'


def _real_toml(snapshot_zip, ending):
    """The configuration text of the fixture bundle with the given line ending."""
    with zipfile.ZipFile(snapshot_zip) as archive:
        text = archive.read("project.toml")
    return text.replace(b"\r\n", b"\n").replace(b"\n", ending)


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
async def test_the_importer_writes_the_configuration_byte_for_byte(
        tmp_path, bundle, ending):  # noqa: F811
    """Text mode turned every CR LF into CR CR LF on Windows (IS-0010)."""
    raw = _real_toml(bundle, ending)
    snapshot = _zip_without(
        bundle, tmp_path / "ends.zip", drop={"project.toml"}, add={"project.toml": raw})
    registry = _target_registry(tmp_path, "exact")
    engine, Session = await _new_db()
    async with Session() as session:
        await import_snapshot(
            session=session, registry=registry, bundle_path=snapshot, mode="create", apply=True)
    await engine.dispose()

    written = (registry.server.projects_dir / "p.toml").read_bytes()
    assert written == raw
    assert b"\r\r" not in written
    assert registry.project("p").key == "p"


async def test_a_changed_key_does_not_double_the_line_endings_either(tmp_path, bundle):  # noqa: F811
    raw = _real_toml(bundle, b"\r\n")
    snapshot = _zip_without(
        bundle, tmp_path / "ends.zip", drop={"project.toml"}, add={"project.toml": raw})
    registry = _target_registry(tmp_path, "renamed")
    engine, Session = await _new_db()
    async with Session() as session:
        await import_snapshot(
            session=session, registry=registry, bundle_path=snapshot, mode="create",
            project_key="copy", apply=True)
    await engine.dispose()

    written = (registry.server.projects_dir / "copy.toml").read_bytes()
    assert b"\r\r" not in written and b'key = "copy"' in written
    assert registry.project("copy").key == "copy"


# ---------------------------------------------------------------- old snapshots


def _with_ids(files):
    """The shape an earlier version wrote: numeric ids in events, relationships and so on."""
    counter = iter(range(100, 10_000))

    def add(rows, *nested):
        for row in rows:
            row["id"] = next(counter)
            for name in nested:
                for inner in row.get(name) or []:
                    inner["id"] = next(counter)

    items = json.loads(files["items.json"])
    add(items, "events", "external_links")
    sessions = json.loads(files["work_sessions.json"])
    add(sessions, "updates")
    relationships = json.loads(files["relationships.json"])
    add(relationships)
    batches = json.loads(files["import_batches.json"])
    add(batches)
    return {
        "items.json": json.dumps(items), "work_sessions.json": json.dumps(sessions),
        "relationships.json": json.dumps(relationships), "import_batches.json": json.dumps(batches),
    }


async def test_a_snapshot_in_the_old_shape_with_ids_is_still_imported(tmp_path, bundle):  # noqa: F811
    files, _ = _read(bundle)
    old = _zip_without(
        bundle, tmp_path / "old.zip",
        drop={"items.json", "work_sessions.json", "relationships.json", "import_batches.json"},
        add=_with_ids(files))
    assert _keys_named(json.loads(zipfile.ZipFile(old).read("items.json")), "id")  # it has ids
    registry = _target_registry(tmp_path, "from-old")
    engine, Session = await _new_db()
    async with Session() as session:
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=old, mode="create", apply=True)
        again = await _export(session, registry, "p", tmp_path / "again.zip")
        assert (report.items_created, report.relationships_added) == (2, 2)
        assert (report.work_sessions_added, report.import_batches_added) == (1, 1)
        assert await _count(session, ItemEvent) > 0
    await engine.dispose()

    assert _read(again) == _read(bundle)  # and what it exports again is the new, stable shape
