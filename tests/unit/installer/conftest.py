"""Test doubles for the installer: no pip, no PowerShell, no real server, no network."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
INSTALLER_DIR = ROOT / "installer"

REVISIONS = ["r1", "r2", "r3"]
HEADS = {"1.0.0": "r1", "1.1.0": "r2", "1.2.0": "r3"}
NEW_VERSION = "1.2.0"


def _load():
    spec = importlib.util.spec_from_file_location(
        "myissuedesk_installer", INSTALLER_DIR / "installer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["myissuedesk_installer"] = module
    spec.loader.exec_module(module)
    return module


inst = _load()


@pytest.fixture(scope="session")
def mod():
    return inst


class FakeRunner:
    """Pretends to be python -m venv, pip, the issuedeck command and icacls."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fail_pip = False
        self.fail_migration = False
        self.wrong_version_after_install: str | None = None
        self.fail_check = False
        self.no_db_upgrade = False

    @staticmethod
    def _done(command, code=0, out="", err=""):
        return subprocess.CompletedProcess(command, code, out, err)

    def run(self, command, cwd=None, timeout=None, capture=True):
        self.calls.append(list(command))
        if command[0] == "icacls":
            return self._done(command)
        if len(command) < 3 or command[1] != "-m":
            return self._done(command, 1, "", f"unexpected command {command}")
        module = command[2]
        if module == "venv":
            venv = Path(command[3])
            python = inst.venv_python(venv)
            python.parent.mkdir(parents=True)
            python.write_text("fake python", encoding="utf-8")
            return self._done(command)
        venv = Path(command[0]).parent.parent
        version_file = venv / "installed_version.txt"
        if module == "pip":
            if self.fail_pip:
                return self._done(command, 1, "", "ERROR: pip boom")
            spec = command[-1]
            version = spec.split("==")[1] if "==" in spec else Path(spec).name.split("-")[1]
            version_file.write_text(self.wrong_version_after_install or version, encoding="utf-8")
            return self._done(command)
        if module == "issuedeck":
            return self._issuedeck(command, venv, version_file, Path(cwd) if cwd else Path.cwd())
        return self._done(command, 1, "", "unknown module")

    def _issuedeck(self, command, venv, version_file, cwd):
        sub = command[3]
        if not version_file.exists():
            return self._done(command, 1, "", "no such environment")
        version = version_file.read_text(encoding="utf-8")
        if sub == "--version":
            return self._done(command, 0, f"issuedeck {version}\n")
        if sub == "db-upgrade":
            if self.no_db_upgrade:  # a version from before the command existed
                return self._done(
                    command, 2, "",
                    "issuedeck: error: argument cmd: invalid choice: 'db-upgrade' "
                    "(choose from 'demo', 'serve')")
            database = cwd / "data" / "tracker.db"
            current = None
            if database.exists():
                conn = sqlite3.connect(database)
                try:
                    row = conn.execute("select v from rev").fetchone()
                    current = row[0] if row else None
                except sqlite3.OperationalError:
                    current = None
                conn.close()
            head = HEADS[version]
            start = REVISIONS.index(current) + 1 if current else 0
            pending = REVISIONS[start: REVISIONS.index(head) + 1]
            text = f"pending migrations: {len(pending)}" + (
                f" ({', '.join(pending)})" if pending else "")
            if "--check" in command:
                return self._done(command, 0, text + "\n")
            if pending:
                database.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(database)
                conn.execute("create table if not exists rev (v text)")
                conn.execute(
                    "create table if not exists items (id integer primary key, title text)")
                conn.execute("delete from rev")
                if self.fail_migration:
                    conn.execute("insert into rev values (?)", (pending[0],))  # half applied
                    conn.commit()
                    conn.close()
                    return self._done(command, 1, text, "migration boom")
                conn.execute("insert into rev values (?)", (head,))
                conn.commit()
                conn.close()
            return self._done(command, 0, text + "\n")
        if sub == "import-audit-bundle":
            return self._done(command, 0, "[ok] imported\n")
        return self._done(command, 1, "", "unknown subcommand")


class FakeControl:
    """The server of the installation: running or not, can fail to start, can be foreign."""

    def __init__(self, target: Path, *, running: bool = False, own_port: int = 8800) -> None:
        self.target = target
        self.running = running
        self.own_port = own_port
        self.foreign_ports: set[int] = set()
        self.fail_start = False
        self.never_ready = False
        self.on_start = None
        self.events: list[str] = []

    def stop(self, target):
        was = self.running
        self.running = False
        self.events.append("stop")
        return was

    def start(self, target):
        self.events.append("start")
        if self.fail_start:
            raise inst.InstallError("the server did not start", inst.EXIT_FAILED)
        self.running = True
        if self.on_start:
            self.on_start()

    def ready(self, host, port, timeout=0):
        if not self.running or self.never_ready:
            return None
        version_file = self.target / ".venv" / "installed_version.txt"
        return {"status": "ready", "version": version_file.read_text(encoding="utf-8")}

    def port_in_use(self, host, port):
        return port in self.foreign_ports or (self.running and port == self.own_port)


def _write_wheel_content(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def source(tmp_path):
    """A small installer image: manifest, wheelhouse for this Python, payload."""
    src = tmp_path / "installer_src"
    tag = inst.python_tag()
    app = f"myissuedeck-{NEW_VERSION}-py3-none-any.whl"
    _write_wheel_content(src / "wheelhouse" / "common" / app, "app wheel")
    _write_wheel_content(src / "wheelhouse" / "common" / "pure-1.0-py3-none-any.whl", "pure")
    _write_wheel_content(src / "wheelhouse" / tag / "compiled-1.0-cp-win_amd64.whl", "compiled")
    for name in inst.SCRIPTS:
        _write_wheel_content(src / "payload" / name, (INSTALLER_DIR / "payload" / name).read_text(
            encoding="utf-8"))
    _write_wheel_content(src / "payload" / inst.GUIDE, "the guide of the installer")
    _write_wheel_content(src / "payload" / "server.toml.example",
                         (ROOT / "server.toml.example").read_text(encoding="utf-8"))
    write_manifest(src)
    return src


def write_manifest(src: Path, version: str = NEW_VERSION) -> None:
    files = {}
    for path in sorted(src.rglob("*")):
        if path.is_file() and path.name != inst.MANIFEST:
            files[path.relative_to(src).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (src / inst.MANIFEST).write_text(json.dumps({
        "name": "myissuedeck-installer", "version": version, "files": files}, indent=2),
        encoding="utf-8")


LEGACY_FILES = (*inst.LEGACY_SCRIPT_NAMES, "start-server.ps1", "stop-server.ps1")


def make_installation(target: Path, version: str, *, marker: bool = True, rows: int = 3,
                      port: int = 8800) -> dict[str, bytes]:
    """An installed copy with data worth keeping; returns the bytes of the files to compare."""
    venv = target / ".venv"
    python = inst.venv_python(venv)
    python.parent.mkdir(parents=True)
    python.write_text("fake python", encoding="utf-8")
    (venv / "installed_version.txt").write_text(version, encoding="utf-8")
    (target / "data").mkdir()
    conn = sqlite3.connect(target / "data" / "tracker.db")
    conn.execute("create table rev (v text)")
    conn.execute("create table items (id integer primary key, title text)")
    conn.execute("insert into rev values (?)", (HEADS[version],))
    for number in range(rows):
        conn.execute("insert into items (title) values (?)", (f"item {number}",))
    conn.commit()
    conn.close()
    (target / "data" / "settings.json").write_text('{"theme": "mine"}', encoding="utf-8")
    (target / "projects").mkdir()
    (target / "projects" / "mine.toml").write_text('key = "mine"\n', encoding="utf-8")
    (target / "project-templates").mkdir()
    for name in ("logs", "run", "backups"):
        (target / name).mkdir()
    (target / "server.toml").write_text(
        f'host = "127.0.0.1"\nport = {port}\napi_token = "OLD-SECRET-TOKEN-0123456789"\n'
        'data_dir = "./data"\nprojects_dir = "./projects"\n', encoding="utf-8")
    for name in LEGACY_FILES:  # the names the first installer used; it installed no guide
        (target / name).write_text(f"old {name}", encoding="utf-8")
    if marker:
        (target / inst.MARKER).write_text(json.dumps({"version": version}), encoding="utf-8")
    return {
        "server.toml": (target / "server.toml").read_bytes(),
        "projects/mine.toml": (target / "projects" / "mine.toml").read_bytes(),
        "data/settings.json": (target / "data" / "settings.json").read_bytes(),
    }


def read_items(target: Path) -> list[str]:
    conn = sqlite3.connect(target / "data" / "tracker.db")
    try:
        return [row[0] for row in conn.execute("select title from items order by id")]
    finally:
        conn.close()


def read_revision(target: Path) -> str:
    conn = sqlite3.connect(target / "data" / "tracker.db")
    try:
        return conn.execute("select v from rev").fetchone()[0]
    finally:
        conn.close()


def installed_version(target: Path) -> str:
    return (target / ".venv" / "installed_version.txt").read_text(encoding="utf-8")


@pytest.fixture()
def make(mod, source, tmp_path):
    """Build an Installer for a target folder with all doubles wired in."""
    def factory(target: Path | None = None, *, running: bool = False, **overrides):
        target = target or tmp_path / "target"
        options = mod.Options(
            target=target, silent=True, assume_yes=True, source=source, port=8800,
            **overrides)
        runner = FakeRunner()
        control = FakeControl(target, running=running, own_port=8800)
        installer = mod.Installer(options, runner=runner, control=control, log=mod.Log(quiet=True))
        return installer, runner, control
    return factory
