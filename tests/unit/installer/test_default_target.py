"""The default installation folder holds one version: C:\\Utility\\MyIssueDeck_<version>."""

from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest

from .conftest import INSTALLER_DIR, NEW_VERSION, ROOT

DEFAULT = rf"C:\Utility\MyIssueDeck_{NEW_VERSION}"
OLD_DEFAULT = re.compile(r"C:\\+Utility\\+MyIssueDesk\b")


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_default_folder_is_named_after_the_version(mod):
    assert mod.default_target("0.10.1") == Path(r"C:\Utility\MyIssueDeck_0.10.1")
    assert mod.default_target("1.2.0") == Path(r"C:\Utility\MyIssueDeck_1.2.0")


def test_the_version_comes_from_the_manifest(mod, source):
    assert mod.product_version(source) == NEW_VERSION


def test_without_a_manifest_the_version_comes_from_the_wheel_name(mod, source):
    (source / mod.MANIFEST).unlink()

    assert mod.product_version(source) == NEW_VERSION


@pytest.mark.parametrize("damage", ["unreadable", "no version", "no wheel"])
def test_an_installer_without_a_version_is_damaged(mod, source, damage):
    if damage == "unreadable":
        (source / mod.MANIFEST).write_text("{ not json", encoding="utf-8")
    elif damage == "no version":
        (source / mod.MANIFEST).write_text("{}", encoding="utf-8")
    else:
        (source / mod.MANIFEST).unlink()
        for wheel in (source / "wheelhouse" / "common").glob("myissuedeck-*.whl"):
            wheel.unlink()

    with pytest.raises(mod.InstallError) as error:
        mod.product_version(source)

    assert error.value.code == mod.EXIT_DAMAGED


def test_a_run_without_target_names_the_versioned_folder_and_changes_nothing(
        mod, source, capsys):
    code = mod.main(["--check", "--source", str(source), "--port", str(_free_port())])

    out = capsys.readouterr().out
    assert code == 0
    assert f"target:   {DEFAULT}" in out
    assert "to update an installation that already exists, give its folder with --target" in out
    assert not Path(DEFAULT).exists()


def test_an_explicit_target_wins_and_has_no_hint(mod, source, tmp_path, capsys):
    target = tmp_path / "my-folder"

    code = mod.main(["--check", "--source", str(source), "--target", str(target),
                     "--port", str(_free_port())])

    out = capsys.readouterr().out
    assert code == 0
    assert f"target:   {target}" in out
    assert "MyIssueDeck_" not in out and "give its folder" not in out


def test_a_damaged_installer_without_target_is_reported_not_a_traceback(
        mod, source, capsys):
    (source / mod.MANIFEST).write_text("{ not json", encoding="utf-8")

    code = mod.main(["--check", "--source", str(source)])

    out = capsys.readouterr().out
    assert code == mod.EXIT_DAMAGED
    assert "[error] the installer manifest is unreadable" in out and "Traceback" not in out


def test_a_busy_port_with_the_default_folder_points_to_updating_an_existing_one(
        mod, make, tmp_path):
    installer, _, control = make(tmp_path / "fresh")
    installer.opt.target_is_default = True
    control.foreign_ports.add(8800)

    with pytest.raises(mod.InstallError, match="give its folder with --target"):
        installer.run()


def test_a_busy_port_with_an_explicit_folder_has_no_such_hint(mod, make, tmp_path):
    installer, _, control = make(tmp_path / "fresh")
    control.foreign_ports.add(8800)

    with pytest.raises(mod.InstallError) as error:
        installer.run()

    assert "give its folder" not in str(error.value)


def test_the_help_shows_the_pattern_and_no_fixed_folder(mod, capsys):
    with pytest.raises(SystemExit):
        mod.main(["--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert r"C:\Utility\MyIssueDeck_<version>" in text
    assert not OLD_DEFAULT.search(text)


def test_there_is_no_fixed_default_folder_left(mod):
    assert not hasattr(mod, "DEFAULT_TARGET")
    assert "{version}" in mod.DEFAULT_TARGET_TEMPLATE


def test_the_documents_describe_the_versioned_default_and_not_the_old_one():
    files = [INSTALLER_DIR / "README-INSTALL.txt", INSTALLER_DIR / "USERGUIDE.md",
             INSTALLER_DIR / "install.cmd", INSTALLER_DIR / "installer.py",
             ROOT / "docs" / "installer.md"]
    for path in files:
        assert not OLD_DEFAULT.search(path.read_text(encoding="utf-8")), path.name
    for path in (INSTALLER_DIR / "README-INSTALL.txt", ROOT / "docs" / "installer.md"):
        assert "MyIssueDeck_<version>" in path.read_text(encoding="utf-8"), path.name
