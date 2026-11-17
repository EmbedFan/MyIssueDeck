"""FEA-0008: the GitHub commands of the command line (local GitHub test double)."""

import asyncio
import sqlite3

import pytest

from issuedeck import cli
from issuedeck.cli import (
    _cmd_github_export,
    _cmd_github_import,
    _cmd_github_list,
    _cmd_github_test,
    _cmd_seed_demo,
    _ensure_demo_config,
    _ensure_demo_project_config,
)
from issuedeck.core.config import load_server_config
from issuedeck.core.runtime_settings import RuntimeSettings

from .fake_github import TOKEN, FakeGitHub


def _installation(tmp_path, name, *, seeded=False):
    root = tmp_path / name
    root.mkdir()
    config = root / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    RuntimeSettings(server.data_dir).update_settings(
        {"github": {"repository": "octo/exports"}},
    )
    if seeded:
        _ensure_demo_project_config(server.projects_dir, "example")
        assert asyncio.run(_cmd_seed_demo(config, "example", force_reset=False)) == 0
    return root, config


def _items(root, key):
    with sqlite3.connect(root / "data" / "tracker.db") as conn:
        return conn.execute(
            "select count(*) from items where project_key = ?", (key,),
        ).fetchone()[0]


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setenv("GITHUB_PAT", TOKEN)
    monkeypatch.setattr(cli, "_github_transport", lambda: fake.transport)
    return fake


def test_the_commands_are_listed_in_the_help():
    import subprocess
    import sys

    out = subprocess.run(
        [sys.executable, "-m", "issuedeck", "--help"], capture_output=True, text=True,
    )
    for name in ("github-test", "github-list", "github-export", "github-import"):
        assert name in out.stdout + out.stderr


def test_github_test_reports_every_check(tmp_path, fake, capsys):
    _, config = _installation(tmp_path, "src")
    assert asyncio.run(_cmd_github_test(config)) == 0
    out = capsys.readouterr().out
    for name in ("token", "repository", "write access", "privacy", "branch"):
        assert f"[ok] {name}" in out
    assert TOKEN not in out


def test_a_missing_token_is_explained(tmp_path, fake, capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_PAT")
    root, config = _installation(tmp_path, "src", seeded=True)
    assert asyncio.run(_cmd_github_export(config, "example", False)) == 2
    assert "GITHUB_PAT is not set" in capsys.readouterr().err
    assert fake.requests == []


def test_export_preview_export_list_and_repeat(tmp_path, fake, capsys):
    root, config = _installation(tmp_path, "src", seeded=True)

    assert asyncio.run(_cmd_github_export(config, "example", True)) == 0
    assert "(dry run)" in capsys.readouterr().err and len(fake.history()) == 1

    assert asyncio.run(_cmd_github_export(config, "example", False)) == 0
    assert "as commit" in capsys.readouterr().err and len(fake.history()) == 2

    assert asyncio.run(_cmd_github_list(config, None)) == 0
    assert "example\t8 items" in capsys.readouterr().out

    assert asyncio.run(_cmd_github_export(config, "example", False)) == 0
    assert "up to date" in capsys.readouterr().err and len(fake.history()) == 2

    audit = RuntimeSettings(load_server_config(config).data_dir).audit_log()
    assert [e["action"] for e in audit if e["action"].startswith("github.")] == ["github.export"]
    assert TOKEN not in str(audit)


def test_import_creates_the_project_in_another_installation(tmp_path, fake, capsys):
    _, source = _installation(tmp_path, "src", seeded=True)
    assert asyncio.run(_cmd_github_export(source, "example", False)) == 0
    capsys.readouterr()
    target_root, target = _installation(tmp_path, "dst")

    preview = asyncio.run(_cmd_github_import(
        target, "example", "create", "restored", None, "keep", True,
    ))
    assert preview == 0 and "would import (dry run)" in capsys.readouterr().err
    assert not (target_root / "projects" / "restored.toml").exists()

    assert asyncio.run(_cmd_github_import(
        target, "example", "create", "restored", None, "keep", False,
    )) == 0
    assert "restart a running server" in capsys.readouterr().err
    assert _items(target_root, "restored") == 8

    again = asyncio.run(_cmd_github_import(
        target, "example", "update", "restored", None, "keep", False,
    ))
    assert again == 0 and "created=0" in capsys.readouterr().err
    assert _items(target_root, "restored") == 8


def test_import_of_a_missing_project_is_reported(tmp_path, fake, capsys):
    _, target = _installation(tmp_path, "dst")
    rc = asyncio.run(_cmd_github_import(target, "nothing", "create", None, None, "keep", False))
    assert rc == 2 and "snapshot_invalid" in capsys.readouterr().err
