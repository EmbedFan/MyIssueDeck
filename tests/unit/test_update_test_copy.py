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
