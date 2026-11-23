"""IS-0011: a snapshot whose project.toml has other line endings (CR CR LF from earlier Windows
exports, CR LF, a lone CR, a byte order mark) is imported; a really invalid file is refused with
the file and the line named."""

import tomllib
import zipfile

import pytest
from sqlalchemy import select

from issuedeck.core.errors import SnapshotInvalid
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.export.snapshot_import import (
    _toml_problem,
    canonical_config_text,
    import_snapshot,
)
from issuedeck.features.items.models import Item

from .test_audit_bundle import session_and_registry  # noqa: F401
from .test_roundtrip import _read
from .test_snapshot_import import (  # noqa: F401
    _count,
    _new_db,
    _target_registry,
    _zip_without,
    bundle,
)

NORMALISED = "the line endings of project.toml were normalised"


def _config(bundle_path):
    with zipfile.ZipFile(bundle_path) as archive:
        return archive.read("project.toml").replace(b"\r\n", b"\n")


def _with_config(tmp_path, bundle_path, raw):
    return _zip_without(
        bundle_path, tmp_path / "snapshot.zip", drop={"project.toml"}, add={"project.toml": raw})


ENDINGS = [
    pytest.param(lambda lf: lf, False, id="LF"),
    pytest.param(lambda lf: lf.replace(b"\n", b"\r\n"), True, id="CR LF"),
    pytest.param(
        lambda lf: lf.replace(b"\n", b"\r\r\n"), True, id="CR CR LF, earlier Windows exports"),
    pytest.param(lambda lf: lf.replace(b"\n", b"\r"), True, id="lone CR"),
    pytest.param(lambda lf: b"\xef\xbb\xbf" + lf, True, id="BOM and LF"),
    pytest.param(
        lambda lf: b"\xef\xbb\xbf" + lf.replace(b"\n", b"\r\r\n"), True, id="BOM and CR CR LF"),
]


# ------------------------------------------------------------------ the helper


@pytest.mark.parametrize(("raw", "expected"), [
    ('key = "p"\nname = "P"\n', 'key = "p"\nname = "P"\n'),
    ('key = "p"\r\nname = "P"\r\n', 'key = "p"\nname = "P"\n'),
    ('key = "p"\r\r\nname = "P"\r\r\n', 'key = "p"\nname = "P"\n'),
    ('key = "p"\rname = "P"\r', 'key = "p"\nname = "P"\n'),
    (chr(0xFEFF) + 'key = "p"\r\n', 'key = "p"\n'),
])
def test_the_canonical_text_has_one_line_ending_and_no_bom(raw, expected):
    assert canonical_config_text(raw) == expected


def test_the_reported_case_is_fixed_the_text_with_key_myissuedesk_and_cr_cr_lf():
    """The statement key = "myissuedesk" has 19 characters: the parser stopped at column 20."""
    broken = 'key = "myissuedesk"\r\r\nname = "X"\r\r\n'
    with pytest.raises(tomllib.TOMLDecodeError, match=r"line 1, column 20"):
        tomllib.loads(broken)

    assert tomllib.loads(canonical_config_text(broken)) == {"key": "myissuedesk", "name": "X"}


# ------------------------------------------------------------------ the import


@pytest.mark.parametrize(("make", "changed"), ENDINGS)
async def test_every_line_ending_is_imported_as_a_new_project_and_written_with_lf(
        tmp_path, bundle, make, changed):  # noqa: F811
    snapshot = _with_config(tmp_path, bundle, make(_config(bundle)))
    registry = _target_registry(tmp_path, "t")
    engine, Session = await _new_db()
    async with Session() as session:
        preview = await import_snapshot(
            session=session, registry=registry, bundle_path=snapshot, mode="create")
        assert preview.applied is False and (await _count(session, Item)) == 0
        assert not (registry.server.projects_dir / "p.toml").exists()   # nothing before the apply

        report = await import_snapshot(
            session=session, registry=registry, bundle_path=snapshot, mode="create", apply=True)
        assert report.applied is True and report.items_created == 2
    await engine.dispose()

    written = (registry.server.projects_dir / "p.toml").read_bytes()
    assert written == _config(bundle)                  # the canonical text, whatever the source was
    assert b"\r" not in written and not written.startswith(b"\xef\xbb\xbf")
    assert registry.project("p").key == "p"
    assert any(NORMALISED in warning for warning in report.warnings) is changed
    assert any(NORMALISED in warning for warning in preview.warnings) is changed


@pytest.mark.parametrize(("make", "changed"), ENDINGS)
async def test_the_imported_project_exports_the_same_files_whatever_the_snapshot_had(
        tmp_path, bundle, make, changed):  # noqa: F811
    """The first export of the imported project repairs the repository (IS-0011, IS-0010)."""
    snapshot = _with_config(tmp_path, bundle, make(_config(bundle)))
    registry = _target_registry(tmp_path, "t")
    engine, Session = await _new_db()
    async with Session() as session:
        await import_snapshot(
            session=session, registry=registry, bundle_path=snapshot, mode="create", apply=True)
        again = await export_audit_bundle(
            session=session, registry=registry, project_key="p", out_path=tmp_path / "again.zip")
    await engine.dispose()

    assert _read(again.bundle_path) == _read(bundle)


async def test_update_mode_does_not_report_line_endings(tmp_path, session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    snapshot_path = (await export_audit_bundle(
        session=session, registry=registry, project_key="p",
        out_path=tmp_path / "s.zip")).bundle_path
    old = _with_config(tmp_path, snapshot_path, _config(snapshot_path).replace(b"\n", b"\r\r\n"))

    report = await import_snapshot(
        session=session, registry=registry, bundle_path=old, mode="update", apply=True)

    assert report.warnings == []        # nothing is written from the configuration in update mode


async def test_a_changed_key_is_applied_to_a_snapshot_with_other_line_endings(
        tmp_path, bundle):  # noqa: F811
    snapshot = _with_config(tmp_path, bundle, _config(bundle).replace(b"\n", b"\r\r\n"))
    registry = _target_registry(tmp_path, "t")
    engine, Session = await _new_db()
    async with Session() as session:
        await import_snapshot(
            session=session, registry=registry, bundle_path=snapshot, mode="create",
            project_key="copy", apply=True)
        keys = {i.project_key for i in (await session.execute(select(Item))).scalars()}
    await engine.dispose()

    assert keys == {"copy"} and registry.project("copy").key == "copy"
    written = (registry.server.projects_dir / "copy.toml").read_bytes()
    assert b"\r" not in written and b'key = "copy"' in written


# ------------------------------------------------------------------ a really invalid file


async def test_an_invalid_configuration_names_the_file_the_line_and_its_text(
        tmp_path, bundle):  # noqa: F811
    broken = b'key = "p"\nname = "P"\n[kinds.feature\nlabel = "Feature"\n'
    snapshot = _with_config(tmp_path, bundle, broken)
    registry = _target_registry(tmp_path, "t")
    engine, Session = await _new_db()
    async with Session() as session:
        with pytest.raises(SnapshotInvalid) as error:
            await import_snapshot(
                session=session, registry=registry, bundle_path=snapshot, mode="create",
                apply=True)
        assert await _count(session, Item) == 0
    await engine.dispose()

    message = str(error.value)
    assert "project.toml" in message and "line 3" in message
    assert "'[kinds.feature'" in message                      # the text of that line
    assert "line ending" not in message and "carriage" not in message.lower()
    assert not (registry.server.projects_dir / "p.toml").exists()   # nothing left behind


async def test_a_configuration_that_does_not_fit_the_model_is_still_refused(
        tmp_path, bundle):  # noqa: F811
    snapshot = _with_config(tmp_path, bundle, b'key = "p"\nname = "P"\nkinds = 3\n')
    registry = _target_registry(tmp_path, "t")
    engine, Session = await _new_db()
    async with Session() as session:
        with pytest.raises(
                SnapshotInvalid, match="project configuration in the snapshot is invalid"):
            await import_snapshot(
                session=session, registry=registry, bundle_path=snapshot, mode="create",
                apply=True)
    await engine.dispose()
    assert not (registry.server.projects_dir / "p.toml").exists()


def test_the_problem_text_without_a_position_keeps_the_parser_message():
    class Fake(tomllib.TOMLDecodeError):
        pass

    text = _toml_problem("key = ", Fake("Invalid statement (at end of document)"))

    assert text.startswith("the project configuration (project.toml) in the snapshot is invalid:")
    assert "at end of document" in text and "that line reads" not in text
