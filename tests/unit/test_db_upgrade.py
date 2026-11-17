"""The ``db-upgrade`` command: apply or list pending database migrations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from issuedeck.cli import _migration_state


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "server.toml"
    cfg.write_text(
        'host = "127.0.0.1"\nport = 8799\napi_token = "test-token-for-db-upgrade"\n'
        'data_dir = "./data"\nprojects_dir = "./projects"\n',
        encoding="utf-8",
    )
    return cfg


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "issuedeck", "db-upgrade", "--config", "server.toml", *args],
        cwd=tmp_path, capture_output=True, text=True,
    )


def _downgrade_one(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    import issuedeck.cli as cli

    cfg = Config()
    cfg.set_main_option(
        "script_location", (Path(cli.__file__).resolve().parent / "migrations").as_posix()
    )
    cfg.set_main_option(
        "sqlalchemy.url", f"sqlite:///{(tmp_path / 'data' / 'tracker.db').resolve().as_posix()}"
    )
    command.downgrade(cfg, "-1")


def test_check_on_a_new_installation_reports_everything_pending_and_creates_nothing(tmp_path):
    _config(tmp_path)

    r = _run(tmp_path, "--check")

    assert r.returncode == 0, r.stderr
    assert "current revision: none" in r.stdout
    assert "pending migrations:" in r.stdout and "pending migrations: 0" not in r.stdout
    assert not (tmp_path / "data").exists()  # --check never creates the database


def test_apply_creates_the_database_at_the_head_revision(tmp_path):
    _config(tmp_path)

    r = _run(tmp_path)

    assert r.returncode == 0, r.stderr
    assert "[ok] applied" in r.stdout
    current, pending, head = _migration_state(tmp_path / "data" / "tracker.db")
    assert current == head and pending == []
    assert f"revision now: {head}" in r.stdout


def test_a_second_run_changes_nothing(tmp_path):
    _config(tmp_path)
    assert _run(tmp_path).returncode == 0
    before = (tmp_path / "data" / "tracker.db").read_bytes()

    r = _run(tmp_path)

    assert r.returncode == 0, r.stderr
    assert "pending migrations: 0" in r.stdout
    assert "The database is up to date." in r.stdout
    assert (tmp_path / "data" / "tracker.db").read_bytes() == before


def test_a_database_one_revision_behind_is_brought_up_and_check_does_not_change_it(tmp_path):
    _config(tmp_path)
    assert _run(tmp_path).returncode == 0
    _downgrade_one(tmp_path)
    behind = (tmp_path / "data" / "tracker.db").read_bytes()

    checked = _run(tmp_path, "--check")
    assert checked.returncode == 0, checked.stderr
    assert "pending migrations: 1" in checked.stdout
    assert (tmp_path / "data" / "tracker.db").read_bytes() == behind

    applied = _run(tmp_path)
    assert applied.returncode == 0, applied.stderr
    assert "applied 1 migration(s)" in applied.stdout
    current, pending, head = _migration_state(tmp_path / "data" / "tracker.db")
    assert current == head and pending == []


def test_a_missing_config_is_reported_not_a_traceback(tmp_path):
    r = _run(tmp_path, "--check")

    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "[error] config file not found" in r.stderr
    assert not (tmp_path / "data").exists()


def test_the_command_and_its_check_flag_are_in_the_help():
    r = subprocess.run(
        [sys.executable, "-m", "issuedeck", "db-upgrade", "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "--check" in r.stdout
