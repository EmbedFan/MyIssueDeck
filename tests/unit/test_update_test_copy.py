"""TASK-0005: the helper that updates the installed test copy."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "update_test_copy.py"
spec = importlib.util.spec_from_file_location("update_test_copy", SCRIPT)
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


def test_version_key_orders_numerically():
    assert update.version_key("0.10.3") > update.version_key("0.10.2")
    assert update.version_key("0.10.0") > update.version_key("0.9.9")


def test_read_install_refuses_a_folder_without_an_installation(tmp_path):
    with pytest.raises(update.UpdateError, match="install.json"):
        update.read_install(tmp_path)


def test_read_install_refuses_another_product(tmp_path):
    (tmp_path / "install.json").write_text(json.dumps({"product": "other"}), encoding="utf-8")
    with pytest.raises(update.UpdateError, match="not a MyIssueDeck"):
        update.read_install(tmp_path)


def test_read_install_returns_the_recorded_version_and_port(tmp_path):
    info = {"product": "myissuedeck", "version": "0.10.2", "port": 8765}
    (tmp_path / "install.json").write_text(json.dumps(info), encoding="utf-8")
    assert update.read_install(tmp_path) == info


def test_counts_without_database_or_server(tmp_path):
    assert update.counts(tmp_path, 1) == {"items": None, "projects": None}


def test_main_refuses_the_development_port(tmp_path, monkeypatch):
    info = {"product": "myissuedeck", "version": "0.1.0", "port": 8766}
    (tmp_path / "install.json").write_text(json.dumps(info), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["x", "--target", str(tmp_path), "--check"])
    with pytest.raises(update.UpdateError, match="8766"):
        update.main()


def _update_world(tmp_path, monkeypatch, *, rename):
    """Everything outside the folder rename is replaced, so that main() runs without a server."""
    import zipfile
    from types import SimpleNamespace

    target = tmp_path / "MyIssueDeck_0.10.2"
    target.mkdir()
    info = {"product": "myissuedeck", "version": "0.10.2", "port": 8765}
    (target / "install.json").write_text(json.dumps(info), encoding="utf-8")
    installer = tmp_path / "installer.zip"
    with zipfile.ZipFile(installer, "w") as archive:
        archive.writestr("installer.py", "")
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(update, "source_version", lambda: "0.10.3")
    monkeypatch.setattr(update, "check_installer", lambda version: installer)
    monkeypatch.setattr(update, "stop_server", lambda folder, port: True)
    monkeypatch.setattr(update, "counts", lambda folder, port: {"items": 3, "projects": 1})
    monkeypatch.setattr(update, "wait_ready", lambda port, version: {"status": "ready"})
    monkeypatch.setattr(update.subprocess, "run", fake_run)
    if rename is not None:
        monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr("sys.argv", ["x", "--target", str(target)])
    return target, seen


def test_a_folder_that_cannot_be_renamed_is_updated_in_place(tmp_path, monkeypatch, capsys):
    def refuse(self, new):
        raise PermissionError(13, "Access denied")  # another program has the folder open

    target, seen = _update_world(tmp_path, monkeypatch, rename=refuse)

    assert update.main() == 0

    command = seen["command"]
    assert command[command.index("--target") + 1] == str(target)  # the old folder, not the new
    assert "cannot rename MyIssueDeck_0.10.2 (Access denied); updating in place" in (
        capsys.readouterr().out)
    assert target.is_dir() and not (tmp_path / "MyIssueDeck_0.10.3").exists()


def test_a_folder_that_can_be_renamed_is_updated_under_its_new_name(
        tmp_path, monkeypatch, capsys):
    target, seen = _update_world(tmp_path, monkeypatch, rename=None)

    assert update.main() == 0

    command = seen["command"]
    renamed = tmp_path / "MyIssueDeck_0.10.3"
    assert command[command.index("--target") + 1] == str(renamed)
    assert renamed.is_dir() and not target.exists()
    assert "renamed to" in capsys.readouterr().out
