"""Updating an installed copy: data is kept, failures restore the old version."""

from __future__ import annotations

import json

import pytest

from .conftest import (
    NEW_VERSION,
    installed_version,
    make_installation,
    read_items,
    read_revision,
)


@pytest.fixture()
def installed(tmp_path):
    target = tmp_path / "target"
    before = make_installation(target, "1.0.0")
    return target, before


def test_an_update_installs_the_new_version_and_keeps_every_piece_of_data(mod, make, installed):
    target, before = installed
    installer, _, _ = make(target)

    report = installer.run()

    assert report.mode == "update" and report.old_version == "1.0.0"
    assert installed_version(target) == NEW_VERSION
    assert read_items(target) == ["item 0", "item 1", "item 2"]
    assert read_revision(target) == "r3"
    assert report.migrations == ["r2", "r3"]
    # configuration, settings and projects are byte for byte what they were
    assert (target / "server.toml").read_bytes() == before["server.toml"]
    assert (target / "projects" / "mine.toml").read_bytes() == before["projects/mine.toml"]
    assert (target / "data" / "settings.json").read_bytes() == before["data/settings.json"]
    marker = json.loads((target / mod.MARKER).read_text(encoding="utf-8"))
    assert marker["version"] == NEW_VERSION and marker["mode"] == "update"
    assert not (target / ".venv.old").exists()


def test_the_database_of_the_checkout_is_never_copied_over_the_installed_one(mod, make, installed):
    """The old installer replaced the installed database; the new one has no such step."""
    target, _ = installed
    installer, runner, _ = make(target)

    installer.run()

    assert read_items(target) == ["item 0", "item 1", "item 2"]
    assert not any("tracker.db" in part for call in runner.calls for part in call)


def test_the_backup_holds_the_old_state_before_anything_was_changed(mod, make, installed):
    target, before = installed
    installer, _, _ = make(target)

    report = installer.run()

    backup = report.backup
    assert backup.parent == target / "backups" and backup.name.endswith("-1.0.0")
    assert (backup / "server.toml").read_bytes() == before["server.toml"]
    assert (backup / "projects" / "mine.toml").read_bytes() == before["projects/mine.toml"]
    assert (backup / "data" / "settings.json").read_bytes() == before["data/settings.json"]
    import sqlite3

    saved = sqlite3.connect(backup / "data" / "tracker.db")
    assert saved.execute("select v from rev").fetchone() == ("r1",)  # before the migrations
    assert saved.execute("select count(*) from items").fetchone() == (3,)
    saved.close()


def test_only_the_server_of_this_installation_is_stopped_and_it_is_restarted(mod, make, installed):
    target, _ = installed
    installer, _, control = make(target, running=True)

    report = installer.run()

    assert control.events == ["stop", "start"]
    assert control.running is True and report.server_running is True


def test_a_server_that_was_not_running_stays_stopped(mod, make, installed):
    target, _ = installed
    installer, _, control = make(target, running=False)

    report = installer.run()

    assert control.events == ["stop"] and report.server_running is False


def test_a_foreign_program_on_the_port_stops_the_update_before_any_change(mod, make, installed):
    target, before = installed
    installer, runner, control = make(target)
    control.foreign_ports.add(8800)

    with pytest.raises(mod.InstallError, match="another program"):
        installer.run()

    assert installed_version(target) == "1.0.0"
    assert not (target / ".venv.old").exists() and list((target / "backups").iterdir()) == []
    assert runner.calls == []
    assert (target / "server.toml").read_bytes() == before["server.toml"]


def test_the_same_version_needs_repair_and_then_reinstalls(mod, make, tmp_path):
    target = tmp_path / "same"
    make_installation(target, NEW_VERSION)
    with pytest.raises(mod.InstallError, match="--repair"):
        make(target)[0].run()

    report = make(target, repair=True)[0].run()

    assert report.mode == "repair" and read_items(target) == ["item 0", "item 1", "item 2"]


def test_a_downgrade_is_refused_unless_explicitly_allowed(mod, make, tmp_path):
    target = tmp_path / "newer"
    make_installation(target, "1.2.0")
    older = tmp_path / "older_src"
    # an installer for 1.1.0
    import shutil

    shutil.copytree(make(target)[0].opt.source, older)
    (older / "wheelhouse" / "common" / "myissuedeck-1.2.0-py3-none-any.whl").rename(
        older / "wheelhouse" / "common" / "myissuedeck-1.1.0-py3-none-any.whl")
    from .conftest import write_manifest

    write_manifest(older, "1.1.0")
    options = mod.Options(target=target, silent=True, assume_yes=True, source=older, port=8800)

    with pytest.raises(mod.InstallError, match="--allow-downgrade"):
        mod.Installer(options, log=mod.Log(quiet=True)).run()

    assert installed_version(target) == "1.2.0"


def test_an_allowed_downgrade_leaves_the_database_alone_and_says_so(mod, make, tmp_path):
    import shutil

    from .conftest import FakeControl, FakeRunner, write_manifest

    target = tmp_path / "newer"
    make_installation(target, "1.2.0")
    older = tmp_path / "older_src"
    shutil.copytree(make(target)[0].opt.source, older)
    (older / "wheelhouse" / "common" / "myissuedeck-1.2.0-py3-none-any.whl").rename(
        older / "wheelhouse" / "common" / "myissuedeck-1.1.0-py3-none-any.whl")
    write_manifest(older, "1.1.0")
    options = mod.Options(target=target, silent=True, assume_yes=True, source=older,
                          port=8800, allow_downgrade=True)
    runner = FakeRunner()

    report = mod.Installer(options, runner=runner, control=FakeControl(target),
                           log=mod.Log(quiet=True)).run()

    assert report.mode == "downgrade" and installed_version(target) == "1.1.0"
    assert read_revision(target) == "r3"  # untouched
    assert any("downgrade" in w for w in report.warnings)
    assert not any("db-upgrade" in c for c in runner.calls)


def test_an_installation_from_the_old_installer_is_recognised_and_updated(mod, make, tmp_path):
    target = tmp_path / "legacy"
    make_installation(target, "1.0.0", marker=False)
    installer, _, _ = make(target)

    existing = installer.detect()
    assert existing is not None and existing.origin == "legacy" and existing.version == "1.0.0"

    report = installer.run()

    assert report.mode == "update" and installed_version(target) == NEW_VERSION
    assert (target / mod.MARKER).is_file()  # from now on it has a marker


def test_new_options_of_the_example_configuration_are_reported_not_written(mod, make, installed):
    target, before = installed
    installer, _, _ = make(target)

    report = installer.run()

    assert "[tokens]" in report.new_options or "log_level" in report.new_options
    assert (target / "server.toml").read_bytes() == before["server.toml"]


def test_only_the_newest_backups_are_kept(mod, make, installed):
    target, _ = installed
    for name in ("20250101T000000-0.1.0", "20250102T000000-0.2.0", "20250103T000000-0.3.0"):
        (target / "backups" / name).mkdir()
    installer, _, _ = make(target, keep_backups=2)

    report = installer.run()

    names = sorted(p.name for p in (target / "backups").iterdir())
    assert len(names) == 2 and names[-1] == report.backup.name
    assert "20250101T000000-0.1.0" not in names


def test_an_old_environment_left_by_a_crashed_run_is_put_back_first(mod, make, installed):
    target, _ = installed
    (target / ".venv").rename(target / ".venv.old")  # crashed after moving it aside
    installer, _, _ = make(target)

    report = installer.run()

    assert report.mode == "update" and installed_version(target) == NEW_VERSION
    assert read_items(target) == ["item 0", "item 1", "item 2"]


def test_check_reports_the_update_and_changes_nothing(mod, make, installed):
    target, before = installed
    installer, runner, control = make(target, check=True, running=True)

    report = installer.run()

    assert report.mode == "update"
    assert installed_version(target) == "1.0.0" and control.running is True
    assert control.events == []
    assert not any("venv" in c or "pip" in c for c in runner.calls)
    assert list((target / "backups").iterdir()) == []


# ---------------------------------------------- failures restore the old version


def _assert_old_version_restored(target, before, items=("item 0", "item 1", "item 2")):
    assert installed_version(target) == "1.0.0"
    assert not (target / ".venv.old").exists()
    assert read_items(target) == list(items)
    assert read_revision(target) == "r1"
    assert (target / "server.toml").read_bytes() == before["server.toml"]
    assert (target / "projects" / "mine.toml").read_bytes() == before["projects/mine.toml"]
    assert json.loads((target / mod_marker()).read_text(encoding="utf-8"))["version"] == "1.0.0"


def mod_marker():
    return "install.json"


def test_a_failing_installation_of_the_software_restores_the_old_environment(mod, make, installed):
    target, before = installed
    installer, runner, control = make(target, running=True)
    runner.fail_pip = True

    with pytest.raises(mod.InstallError, match="1.0.0 was restored") as error:
        installer.run()

    assert error.value.code == mod.EXIT_FAILED
    _assert_old_version_restored(target, before)
    assert control.running is True  # the old server is running again


def test_a_wrong_version_after_the_install_is_a_failure_that_restores(mod, make, installed):
    target, before = installed
    installer, runner, _ = make(target)
    runner.wrong_version_after_install = "0.0.1"

    with pytest.raises(mod.InstallError, match="expected version"):
        installer.run()

    _assert_old_version_restored(target, before)


def test_a_half_applied_migration_restores_the_database_from_the_backup(mod, make, installed):
    target, before = installed
    installer, runner, control = make(target, running=True)
    runner.fail_migration = True

    with pytest.raises(mod.InstallError, match="migration"):
        installer.run()

    _assert_old_version_restored(target, before)  # revision is r1 again, not the half-applied r2
    assert control.running is True


def test_a_server_that_does_not_start_after_the_update_rolls_everything_back(mod, make, installed):
    target, before = installed
    installer, _, control = make(target, running=True)
    control.fail_start = True
    original_start = control.start
    calls = {"n": 0}

    def start_once_failing(path):
        calls["n"] += 1
        if calls["n"] == 1:
            return original_start(path)  # raises: the new server does not start
        control.fail_start = False
        return original_start(path)      # the restored old server starts

    control.start = start_once_failing

    with pytest.raises(mod.InstallError, match="did not start"):
        installer.run()

    _assert_old_version_restored(target, before)
    assert control.running is True


def test_a_server_that_never_becomes_ready_rolls_back(mod, make, installed):
    target, before = installed
    installer, _, control = make(target, running=True)
    control.never_ready = True

    with pytest.raises(mod.InstallError, match="did not become ready"):
        installer.run()

    _assert_old_version_restored(target, before)


def test_a_failure_leaves_the_backup_and_names_it(mod, make, installed):
    target, _ = installed
    installer, runner, _ = make(target)
    runner.fail_pip = True

    with pytest.raises(mod.InstallError, match="backup:"):
        installer.run()

    assert len(list((target / "backups").iterdir())) == 1


def test_data_written_by_the_user_is_not_lost_by_a_rolled_back_update(mod, make, installed):
    target, before = installed
    installer, runner, _ = make(target)
    runner.fail_migration = True

    with pytest.raises(mod.InstallError):
        installer.run()

    assert (target / "data" / "settings.json").read_bytes() == before["data/settings.json"]


def test_a_version_without_the_db_upgrade_command_is_updated_and_the_server_migrates(
        mod, make, installed):
    target, _ = installed
    installer, runner, _ = make(target, running=True)
    runner.no_db_upgrade = True

    report = installer.run()

    assert installed_version(target) == NEW_VERSION and report.mode == "update"
    assert any("no db-upgrade command" in w for w in report.warnings)
    assert read_items(target) == ["item 0", "item 1", "item 2"]


def test_when_the_server_does_the_migration_a_failed_start_still_restores_the_database(
        mod, make, installed):
    import sqlite3

    target, before = installed
    installer, runner, control = make(target, running=True)
    runner.no_db_upgrade = True
    control.never_ready = True

    def server_migrates():  # only the NEW server migrates; the old one, restarted later, does not
        control.on_start = None
        conn = sqlite3.connect(target / "data" / "tracker.db")
        conn.execute("update rev set v = 'r3'")
        conn.commit()
        conn.close()

    control.on_start = server_migrates

    with pytest.raises(mod.InstallError):
        installer.run()

    _assert_old_version_restored(target, before)  # revision is r1 again
