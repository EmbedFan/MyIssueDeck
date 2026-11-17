"""A new installation."""

from __future__ import annotations

import json
import tomllib

import pytest

from .conftest import NEW_VERSION, installed_version, read_revision


def _config(target):
    return tomllib.loads((target / "server.toml").read_text(encoding="utf-8"))


def test_a_new_installation_creates_a_working_layout(mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, runner, control = make(target)

    report = installer.run()

    assert report.mode == "new"
    for name in ("data", "projects", "project-templates", "logs", "run", "backups", ".venv"):
        assert (target / name).is_dir(), name
    for name in mod.SCRIPTS:
        assert (target / name).is_file(), name
    assert installed_version(target) == NEW_VERSION
    assert read_revision(target) == "r3"  # migrations were applied
    marker = json.loads((target / mod.MARKER).read_text(encoding="utf-8"))
    assert marker["version"] == NEW_VERSION and marker["port"] == 8800
    assert not (target / mod.PARTIAL).exists()
    assert report.log_file and report.log_file.is_file()


def test_the_libraries_come_from_the_installer_and_nothing_is_downloaded(mod, make, tmp_path):
    installer, runner, _ = make(tmp_path / "fresh")

    installer.run()

    pip = next(c for c in runner.calls if "pip" in c)
    assert "--no-index" in pip
    assert pip[-1] == f"myissuedeck=={NEW_VERSION}"
    assert str(installer.wheelhouse / "common") in pip
    assert str(installer.wheelhouse / installer.python_tag) in pip


def test_online_mode_installs_the_wheel_and_lets_pip_fetch_the_rest(mod, make, tmp_path):
    installer, runner, _ = make(tmp_path / "fresh", online=True)

    installer.run()

    pip = next(c for c in runner.calls if "pip" in c)
    assert "--no-index" not in pip
    assert pip[-1].endswith(f"myissuedeck-{NEW_VERSION}-py3-none-any.whl")


def test_server_toml_gets_the_chosen_address_and_a_fresh_token(mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, _, _ = make(target)

    report = installer.run()

    config = _config(target)
    assert config["host"] == "127.0.0.1"          # not the 0.0.0.0 of the example
    assert config["port"] == 8800
    assert config["api_token"] == report.admin_token
    assert len(report.admin_token) >= 32
    assert config["api_token"] != "change-me-in-production"


def test_two_installations_get_different_tokens(mod, make, tmp_path):
    first = make(tmp_path / "a")[0].run().admin_token
    second = make(tmp_path / "b")[0].run().admin_token

    assert first != second


def test_the_token_is_never_logged_and_never_on_a_command_line(mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, runner, _ = make(target)

    report = installer.run()

    token = report.admin_token
    assert token not in report.log_file.read_text(encoding="utf-8")
    assert all(token not in part for call in runner.calls for part in call)
    assert token in (target / "server.toml").read_text(encoding="utf-8")  # only here


def test_the_log_redacts_a_secret_even_if_a_message_contains_it(mod):
    log = mod.Log(quiet=True)
    log.add_secret("s3cr3t-value")

    assert log.redact("token=s3cr3t-value;") == "token=***;"


def test_the_server_is_stopped_after_the_check_unless_asked_to_stay_up(mod, make, tmp_path):
    installer, _, control = make(tmp_path / "a")
    installer.run()
    assert control.running is False and control.events == ["start", "stop"]

    installer2, _, control2 = make(tmp_path / "b", start=True)
    report = installer2.run()
    assert control2.running is True and report.server_running is True


def test_a_port_in_use_stops_the_installation_before_anything_is_created(mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, runner, control = make(target)
    control.foreign_ports.add(8800)

    with pytest.raises(mod.InstallError, match="port 8800 is already in use"):
        installer.run()

    assert not target.exists() and runner.calls == []


def test_a_folder_with_other_content_is_not_installed_into(mod, make, tmp_path):
    target = tmp_path / "documents"
    target.mkdir()
    (target / "letter.txt").write_text("mine", encoding="utf-8")
    installer, _, _ = make(target)

    with pytest.raises(mod.InstallError, match="not empty"):
        installer.run()

    assert (target / "letter.txt").read_text(encoding="utf-8") == "mine"


def test_missing_libraries_for_this_python_point_to_the_online_option(mod, make, source, tmp_path):
    import shutil

    from .conftest import write_manifest

    shutil.rmtree(source / "wheelhouse" / mod.python_tag())
    write_manifest(source)  # an installer built without libraries for this Python
    installer, runner, _ = make(tmp_path / "fresh")

    with pytest.raises(mod.InstallError, match="--online"):
        installer.run()

    assert runner.calls == []


def test_a_failed_new_installation_says_it_can_be_repeated_and_the_repeat_works(
        mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, runner, _ = make(target)
    runner.fail_pip = True

    with pytest.raises(mod.InstallError, match="run the installer again") as error:
        installer.run()

    assert error.value.code == mod.EXIT_FAILED
    assert (target / mod.PARTIAL).exists() and not (target / mod.MARKER).exists()

    again, _, _ = make(target)
    report = again.run()  # the interrupted installation is repeated

    assert report.mode == "new"
    assert installed_version(target) == NEW_VERSION
    assert not (target / mod.PARTIAL).exists()


def test_check_changes_nothing_and_runs_nothing(mod, make, tmp_path):
    target = tmp_path / "fresh"
    installer, runner, control = make(target, check=True)

    report = installer.run()

    assert report.mode == "new"
    assert not target.exists()
    assert runner.calls == [] and control.events == []


def test_import_of_a_snapshot_zip_runs_the_import_command(mod, make, tmp_path):
    snapshot = tmp_path / "project-audit-bundle.zip"
    snapshot.write_bytes(b"zip")
    installer, runner, _ = make(tmp_path / "fresh", import_data=snapshot)

    installer.run()

    command = next(c for c in runner.calls if "import-audit-bundle" in c)
    assert command[-1] == str(snapshot) and "create" in command


def test_import_of_a_data_folder_copies_the_database_and_the_settings(mod, make, tmp_path):
    from .conftest import make_installation, read_items

    other = tmp_path / "other"
    make_installation(other, "1.0.0")
    target = tmp_path / "fresh"
    installer, _, _ = make(target, import_data=other / "data")

    installer.run()

    assert read_items(target) == ["item 0", "item 1", "item 2"]
    assert (target / "data" / "settings.json").read_text(encoding="utf-8") == '{"theme": "mine"}'
    assert read_revision(target) == "r3"  # then brought up to date


def test_import_is_refused_for_an_update(mod, make, tmp_path):
    from .conftest import make_installation

    target = tmp_path / "target"
    make_installation(target, "1.0.0")
    snapshot = tmp_path / "s.zip"
    snapshot.write_bytes(b"zip")
    installer, _, _ = make(target, import_data=snapshot)

    with pytest.raises(mod.InstallError, match="only for a new installation"):
        installer.run()


def test_an_existing_server_toml_is_kept_in_a_new_installation(mod, make, tmp_path):
    target = tmp_path / "fresh"
    target.mkdir()
    (target / mod.PARTIAL).write_text("x", encoding="utf-8")
    (target / "server.toml").write_text('host = "127.0.0.1"\nport = 8801\napi_token = "mine"\n',
                                        encoding="utf-8")
    installer, _, _ = make(target)

    report = installer.run()

    assert _config(target)["api_token"] == "mine"
    assert report.admin_token is None
    assert any("kept" in w for w in report.warnings)
