"""IS-0009: the scripts carry the product's spelling, the user guide is installed, and an
update replaces the old names safely (with a copy in the backup and a restore on a failure)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from .conftest import (
    INSTALLER_DIR,
    LEGACY_FILES,
    NEW_VERSION,
    ROOT,
    installed_version,
    make_installation,
    write_manifest,
)

OLD_SPELLING = re.compile(r"(start|stop)-myissuedesk")


@pytest.fixture()
def legacy(tmp_path):
    """An installation as the first installer made it: old script names, no guide."""
    target = tmp_path / "target"
    make_installation(target, "1.0.0")
    return target


def _names(target: Path) -> set[str]:
    return {p.name for p in target.iterdir() if p.is_file()}


# ------------------------------------------------------------------ new installation


def test_a_new_installation_has_the_new_script_names_and_the_guide(mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, _, _ = make(target)

    report = installer.run()

    files = _names(target)
    assert {"start-myissuedeck.vbs", "stop-myissuedeck.vbs"} <= files
    assert not files & set(mod.LEGACY_SCRIPT_NAMES)
    assert (target / "USERGUIDE.md").read_text(encoding="utf-8") == "the guide of the installer"
    assert report.guide == target / "USERGUIDE.md" and report.renamed == []


def test_the_scripts_of_the_installer_have_the_new_names(mod):
    assert mod.SCRIPTS[:2] == ("start-myissuedeck.vbs", "stop-myissuedeck.vbs")
    assert sorted(p.name for p in (INSTALLER_DIR / "payload").glob("*.vbs")) == [
        "start-myissuedeck.vbs", "stop-myissuedeck.vbs"]


def test_in_a_development_run_the_guide_beside_installer_py_is_used(mod, make, source, tmp_path):
    (source / "payload" / "USERGUIDE.md").unlink()
    (source / "USERGUIDE.md").write_text("the guide next to the script", encoding="utf-8")
    write_manifest(source)
    target = tmp_path / "fresh"
    installer, _, _ = make(target)

    installer.run()

    assert (target / "USERGUIDE.md").read_text(encoding="utf-8") == "the guide next to the script"


def test_a_guide_missing_from_the_installer_stops_it_as_damaged_before_any_change(
        mod, make, source, tmp_path):
    (source / "payload" / "USERGUIDE.md").unlink()
    write_manifest(source)  # the manifest is right: the file is simply not part of it
    target = tmp_path / "fresh"
    installer, runner, control = make(target)

    with pytest.raises(mod.InstallError, match="USERGUIDE.md is missing") as error:
        installer.run()

    assert error.value.code == mod.EXIT_DAMAGED
    assert not target.exists() and runner.calls == [] and control.events == []


def test_a_guide_missing_from_the_installer_changes_nothing_of_an_installation(
        mod, make, source, legacy):
    (source / "payload" / "USERGUIDE.md").unlink()
    write_manifest(source)
    installer, runner, _ = make(legacy)

    with pytest.raises(mod.InstallError) as error:
        installer.run()

    assert error.value.code == mod.EXIT_DAMAGED
    assert _names(legacy) >= set(LEGACY_FILES)
    assert list((legacy / "backups").iterdir()) == []


# ------------------------------------------------------------------ update and repair


def test_an_update_installs_the_new_names_and_removes_the_old_ones(mod, make, legacy):
    installer, _, _ = make(legacy)

    report = installer.run()

    files = _names(legacy)
    assert set(mod.SCRIPTS) <= files
    assert not files & set(mod.LEGACY_SCRIPT_NAMES)       # never side by side
    assert (legacy / "start-myissuedeck.vbs").read_text(encoding="utf-8") != "old"
    assert (legacy / "USERGUIDE.md").read_text(encoding="utf-8") == "the guide of the installer"
    assert report.renamed == ["start-myissuedesk.vbs to start-myissuedeck.vbs",
                              "stop-myissuedesk.vbs to stop-myissuedeck.vbs"]
    assert any("shortcut" in w for w in report.warnings)


def test_the_old_scripts_are_in_the_backup_before_they_are_removed(mod, make, legacy):
    (legacy / "start-myissuedesk.vbs").write_text("changed by hand", encoding="utf-8")
    installer, _, _ = make(legacy)

    report = installer.run()

    saved = report.backup / mod.INSTALLED_FILES
    assert (saved / "start-myissuedesk.vbs").read_text(encoding="utf-8") == "changed by hand"
    assert (saved / "stop-myissuedesk.vbs").is_file()
    assert (saved / "start-server.ps1").read_text(encoding="utf-8") == "old start-server.ps1"
    assert not (saved / "USERGUIDE.md").exists()           # there was no guide


def test_an_edited_guide_is_replaced_and_the_previous_copy_is_kept(mod, make, legacy):
    (legacy / "USERGUIDE.md").write_text("my own notes in the guide", encoding="utf-8")
    installer, _, _ = make(legacy)

    report = installer.run()

    assert (legacy / "USERGUIDE.md").read_text(encoding="utf-8") == "the guide of the installer"
    kept = report.backup / mod.INSTALLED_FILES / "USERGUIDE.md"
    assert kept.read_text(encoding="utf-8") == "my own notes in the guide"


def test_a_repair_also_renames_and_installs_the_guide(mod, make, tmp_path):
    target = tmp_path / "same"
    make_installation(target, NEW_VERSION)
    installer, _, _ = make(target, repair=True)

    report = installer.run()

    assert report.mode == "repair" and len(report.renamed) == 2
    assert not _names(target) & set(mod.LEGACY_SCRIPT_NAMES)
    assert (target / "USERGUIDE.md").is_file()


def test_an_installation_that_already_has_the_new_names_reports_no_rename(mod, make, legacy):
    for old, new in mod.LEGACY_SCRIPT_NAMES.items():
        (legacy / old).rename(legacy / new)
    installer, _, _ = make(legacy)

    report = installer.run()

    assert report.renamed == [] and not any("shortcut" in w for w in report.warnings)
    assert not _names(legacy) & set(mod.LEGACY_SCRIPT_NAMES)


def test_the_final_report_names_the_new_scripts_the_guide_and_each_rename(
        mod, make, legacy, capsys):
    installer, _, _ = make(legacy)
    report = installer.run()

    mod.print_report(report, mod.Log(quiet=False))

    out = capsys.readouterr().out
    assert "start-myissuedeck.vbs" in out and "stop: stop-myissuedeck.vbs" in out
    assert f"guide:   {legacy / 'USERGUIDE.md'}" in out
    assert "renamed: start-myissuedesk.vbs to start-myissuedeck.vbs" in out
    assert "renamed: stop-myissuedesk.vbs to stop-myissuedeck.vbs" in out
    assert "start-myissuedesk.vbs   stop" not in out


# ------------------------------------------------------------------ failures


def test_a_failure_after_the_files_were_replaced_restores_the_old_files(mod, make, legacy):
    (legacy / "USERGUIDE.md").write_text("the old guide", encoding="utf-8")
    before = {n: (legacy / n).read_bytes() for n in (*LEGACY_FILES, "USERGUIDE.md")}
    installer, _, control = make(legacy, running=True)
    control.never_ready = True                              # fails after the files were copied

    with pytest.raises(mod.InstallError, match="1.0.0 was restored"):
        installer.run()

    assert installed_version(legacy) == "1.0.0"
    for name, content in before.items():
        assert (legacy / name).read_bytes() == content, name
    files = _names(legacy)
    assert not files & {"start-myissuedeck.vbs", "stop-myissuedeck.vbs"}   # new names removed again


def test_a_failure_removes_a_guide_that_the_update_created(mod, make, legacy):
    installer, _, control = make(legacy, running=True)
    control.never_ready = True

    with pytest.raises(mod.InstallError):
        installer.run()

    assert not (legacy / "USERGUIDE.md").exists()            # there was none before
    assert _names(legacy) >= set(LEGACY_FILES)


def test_a_failure_before_the_files_are_touched_leaves_them_alone(mod, make, legacy):
    before = {n: (legacy / n).read_bytes() for n in LEGACY_FILES}
    installer, runner, _ = make(legacy)
    runner.fail_pip = True

    with pytest.raises(mod.InstallError):
        installer.run()

    for name, content in before.items():
        assert (legacy / name).read_bytes() == content
    assert not (legacy / "USERGUIDE.md").exists()
    assert not _names(legacy) & {"start-myissuedeck.vbs", "stop-myissuedeck.vbs"}


# ------------------------------------------------------------------ guards


def _shipped_texts():
    """Every file the installer ships or documents, except the history of the CHANGELOG."""
    paths = [INSTALLER_DIR / "installer.py", INSTALLER_DIR / "README-INSTALL.txt",
             INSTALLER_DIR / "USERGUIDE.md", INSTALLER_DIR / "install.cmd",
             ROOT / "docs" / "installer.md", ROOT / "scripts" / "build_installer.py",
             *sorted((INSTALLER_DIR / "payload").iterdir())]
    return paths


def test_the_old_spelling_is_not_in_any_file_the_installer_ships_or_documents():
    """Only the tagged mapping of the old names (needed to replace them) may use it."""
    found = []
    for path in _shipped_texts():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if OLD_SPELLING.search(line) and "# legacy name" not in line:
                found.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()[:80]}")
    assert found == [], "\n".join(found)


def test_the_legacy_mapping_is_the_only_place_of_the_old_names_in_the_installer():
    lines = [line for line in (INSTALLER_DIR / "installer.py").read_text(encoding="utf-8")
             .splitlines() if OLD_SPELLING.search(line)]
    assert len(lines) == 2 and all("# legacy name" in line for line in lines)


def test_the_shipped_guide_is_true_on_an_installed_machine():
    guide = (INSTALLER_DIR / "USERGUIDE.md").read_text(encoding="utf-8")
    assert "docs\\installer.md" not in guide               # that file is not installed
    assert "C:\\Utility\\MyIssueDesk\\.venv" not in guide  # one machine's folder as "the" folder
    assert "<installation folder>" in guide
    assert "README-INSTALL.txt" in guide


def test_the_docs_name_the_scripts_and_the_guide_that_are_installed():
    docs = (ROOT / "docs" / "installer.md").read_text(encoding="utf-8")
    assert "start-myissuedeck.vbs" in docs and "USERGUIDE.md" in docs
    readme = (INSTALLER_DIR / "README-INSTALL.txt").read_text(encoding="utf-8")
    assert "start-myissuedeck.vbs" in readme and "USERGUIDE.md" in readme
