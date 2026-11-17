"""MyIssueDesk installer: a new installation, or an update of an installed copy.

Standard library only. It runs from the installer ZIP built by ``scripts/build_installer.py``
(``installer.py``, ``wheelhouse/``, ``payload/`` and ``installer-manifest.json`` side by side)
and, for development, from the ``installer`` folder of the source tree.

    python installer.py --target C:\\Utility\\MyIssueDesk            install or update
    python installer.py --check                                      show what would be done

Exit codes: 0 done, 1 failed and rolled back, 2 stopped before anything was changed,
3 the installer itself is damaged.

Secrets: a generated administrator token is written only to ``server.toml`` and shown once at
the end. It is never logged and never put on a command line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRODUCT = "myissuedeck"
MARKER = "install.json"
PARTIAL = "install.partial"
MANIFEST = "installer-manifest.json"
DEFAULT_TARGET = r"C:\Utility\MyIssueDesk"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_KEEP_BACKUPS = 5
MIN_PYTHON = (3, 11)
SCRIPTS = (
    "start-myissuedesk.vbs",
    "stop-myissuedesk.vbs",
    "start-server.ps1",
    "stop-server.ps1",
)
EXIT_OK, EXIT_FAILED, EXIT_STOPPED, EXIT_DAMAGED = 0, 1, 2, 3


class InstallError(Exception):
    """A step failed; ``code`` is the exit code of the installer."""

    def __init__(self, message: str, code: int = EXIT_STOPPED) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- helpers


def parse_version(text: str) -> tuple[int, ...]:
    """'0.10.0' -> (0, 10, 0). Suffixes such as 'rc1' or '.dev3' are ignored."""
    parts = re.match(r"^\s*v?(\d+(?:\.\d+)*)", text)
    if not parts:
        raise ValueError(f"not a version: {text!r}")
    return tuple(int(p) for p in parts.group(1).split("."))


def compare_versions(a: str, b: str) -> int:
    """-1, 0 or 1."""
    x, y = parse_version(a), parse_version(b)
    width = max(len(x), len(y))
    x += (0,) * (width - len(x))
    y += (0,) * (width - len(y))
    return (x > y) - (x < y)


def python_tag(version: tuple[int, int] | None = None) -> str:
    major, minor = version or sys.version_info[:2]
    return f"cp{major}{minor}"


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clear_readonly(path: Path) -> None:
    """Make a whole tree writable. Old package files can be read-only, which makes a plain
    removal fail with "access denied" (this is what stopped an upgrade half-way before)."""
    if not path.exists():
        return
    for root, dirs, files in os.walk(path):
        for name in [*dirs, *files]:
            try:
                os.chmod(Path(root) / name, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            except OSError:
                pass
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except OSError:
        pass


def remove_tree(path: Path, attempts: int = 3) -> None:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            clear_readonly(path)
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError as exc:  # a scanner or an indexer can hold a file for a moment
            last = exc
            time.sleep(0.5 * (attempt + 1))
    raise InstallError(f"could not remove {path}: {last}", EXIT_FAILED)


def rename_with_retry(source: Path, destination: Path, attempts: int = 5) -> None:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            os.rename(source, destination)
            return
        except OSError as exc:
            last = exc
            time.sleep(0.5 * (attempt + 1))
    raise InstallError(f"could not rename {source} to {destination}: {last}", EXIT_STOPPED)


def top_level_keys(text: str) -> set[str]:
    """Active keys and table names of a TOML text (comments are ignored)."""
    keys: set[str] = set()
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        header = re.match(r"^\[\[?([A-Za-z0-9_.-]+)\]\]?", stripped)
        if header:
            keys.add(f"[{header.group(1)}]")
            in_table = True
            continue
        if not in_table:
            key = re.match(r"^([A-Za-z0-9_.-]+)\s*=", stripped)
            if key:
                keys.add(key.group(1))
    return keys


def backup_sqlite(source: Path, destination: Path) -> None:
    """Consistent copy of a SQLite database that may be in use (WAL mode)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destination)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


# --------------------------------------------------------------------------- collaborators


class Log:
    """Console and file log; known secrets are replaced before anything is written."""

    def __init__(self, quiet: bool = False) -> None:
        self.quiet = quiet
        self._secrets: set[str] = set()
        self._buffer: list[str] = []
        self._file: Path | None = None

    def add_secret(self, value: str) -> None:
        if value:
            self._secrets.add(value)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def attach(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path
        with path.open("a", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in self._buffer))
        self._buffer.clear()

    def write(self, message: str, *, console: bool = True) -> None:
        message = self.redact(message)
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        line = f"{stamp} {message}"
        if self._file is not None:
            with self._file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        else:
            self._buffer.append(line)
        if console and not self.quiet:
            print(message, flush=True)


class Runner:
    """Runs external commands. Tests replace it."""

    def run(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """``capture=False`` is for commands that start a long-running program (the server):
        its children inherit the output pipes, so waiting for the pipes to close would block
        until the server exits, and not even the timeout could free the call."""
        if not capture:
            return subprocess.run(
                command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=timeout,
            )
        return subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )


class ServerControl:
    """Stops, starts and probes the server of one installation (through the shipped scripts)."""

    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def _script(self, target: Path, name: str) -> subprocess.CompletedProcess[str]:
        return self.runner.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(target / name)],
            cwd=target, timeout=120, capture=False,
        )

    def stop(self, target: Path) -> bool:
        """True when a server of this installation was running and is now stopped."""
        result = self._script(target, "stop-server.ps1")
        if result.returncode == 0:
            return True
        if result.returncode == 4:
            return False
        raise InstallError("the server of this installation could not be stopped "
                           "(see logs\\start.log)", EXIT_STOPPED)

    def start(self, target: Path) -> None:
        result = self._script(target, "start-server.ps1")
        if result.returncode == 2:
            raise InstallError("the port is already in use, the server was not started",
                               EXIT_FAILED)
        if result.returncode != 0:
            raise InstallError("the server did not start (see logs\\server.err.log)",
                               EXIT_FAILED)

    def ready(self, host: str, port: int, timeout: float = 20.0) -> dict | None:
        """The /readyz answer, or None when the server does not become ready in time."""
        url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}/readyz"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:  # noqa: S310
                    return json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(0.5)
        return None

    def port_in_use(self, host: str, port: int) -> bool:
        probe = "127.0.0.1" if host in ("0.0.0.0", "") else host
        try:
            with socket.create_connection((probe, port), timeout=1):
                return True
        except OSError:
            return False


# --------------------------------------------------------------------------- model


@dataclass
class Options:
    target: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    port_given: bool = False
    online: bool = False
    check: bool = False
    repair: bool = False
    allow_downgrade: bool = False
    keep_backups: int = DEFAULT_KEEP_BACKUPS
    start: bool | None = None
    import_data: Path | None = None
    silent: bool = False
    assume_yes: bool = False
    source: Path = HERE


@dataclass
class Installation:
    version: str
    origin: str  # "marker" or "legacy"
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT


@dataclass
class Report:
    mode: str = ""
    old_version: str | None = None
    new_version: str = ""
    target: Path | None = None
    backup: Path | None = None
    migrations: list[str] = field(default_factory=list)
    new_options: list[str] = field(default_factory=list)
    server_running: bool = False
    url: str = ""
    admin_token: str | None = None
    warnings: list[str] = field(default_factory=list)
    log_file: Path | None = None


# --------------------------------------------------------------------------- installer


class Installer:
    def __init__(
        self,
        options: Options,
        runner: Runner | None = None,
        control: ServerControl | None = None,
        log: Log | None = None,
    ) -> None:
        self.opt = options
        self.runner = runner or Runner()
        self.control = control or ServerControl(self.runner)
        self.log = log or Log(quiet=options.silent)
        self.report = Report(target=options.target)
        self.migrations_at_start = False
        self.manifest = self._load_manifest()
        self.version = self._product_version()
        self.report.new_version = self.version
        self.python_tag = python_tag()

    # ---- the installer's own content -------------------------------------------------

    @property
    def wheelhouse(self) -> Path:
        return self.opt.source / "wheelhouse"

    @property
    def payload(self) -> Path:
        return self.opt.source / "payload"

    def _load_manifest(self) -> dict | None:
        path = self.opt.source / MANIFEST
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InstallError(
                f"the installer manifest is unreadable: {exc}", EXIT_DAMAGED) from exc

    def _product_version(self) -> str:
        if self.manifest:
            return str(self.manifest["version"])
        wheels = sorted((self.wheelhouse / "common").glob(f"{PRODUCT}-*.whl")) if (
            self.wheelhouse / "common").exists() else []
        if not wheels:
            raise InstallError(
                "no installer manifest and no myissuedeck wheel found next to the installer",
                EXIT_DAMAGED)
        return wheels[-1].name.split("-")[1]

    def verify_content(self) -> None:
        """Every file of the manifest is present and has the recorded SHA-256."""
        if not self.manifest:
            self.log.write("No manifest: development run, content not verified.")
            return
        bad: list[str] = []
        for relative, expected in self.manifest.get("files", {}).items():
            path = self.opt.source / relative
            if not path.is_file() or sha256_of(path) != expected:
                bad.append(relative)
        if bad:
            raise InstallError(
                "the installer is damaged or was changed (checksum mismatch): "
                + ", ".join(sorted(bad)[:5]) + (" ..." if len(bad) > 5 else ""), EXIT_DAMAGED)
        self.log.write(f"Installer content verified ({len(self.manifest['files'])} files).")

    def _app_wheel(self) -> Path:
        found = sorted((self.wheelhouse / "common").glob(f"{PRODUCT}-{self.version}-*.whl"))
        if not found:
            raise InstallError(
                f"the wheel for version {self.version} is missing from the installer", EXIT_DAMAGED)
        return found[0]

    def _example_text(self) -> str:
        for candidate in (self.payload / "server.toml.example",
                          self.opt.source.parent / "server.toml.example"):
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        raise InstallError("server.toml.example is missing from the installer", EXIT_DAMAGED)

    # ---- detection ---------------------------------------------------------------------

    def detect(self) -> Installation | None:
        target = self.opt.target
        if not target.exists():
            return None
        marker = target / MARKER
        host, port = self._configured_endpoint()
        if marker.is_file():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                return Installation(str(data["version"]), "marker", host, port)
            except (OSError, ValueError, KeyError):
                self.log.write("install.json is unreadable; trying the installed command.")
        py = venv_python(target / ".venv")
        if py.exists():
            result = self.runner.run([str(py), "-m", "issuedeck", "--version"], cwd=target)
            match = re.search(r"(\d+(?:\.\d+)+)", result.stdout or "")
            if result.returncode == 0 and match:
                return Installation(match.group(1), "legacy", host, port)
        return None

    def _configured_endpoint(self) -> tuple[str, int]:
        config = self.opt.target / "server.toml"
        try:
            data = tomllib.loads(config.read_text(encoding="utf-8-sig"))
            return str(data.get("host", DEFAULT_HOST)), int(data.get("port", DEFAULT_PORT))
        except (OSError, ValueError):
            return DEFAULT_HOST, DEFAULT_PORT

    def decide_mode(self, existing: Installation | None) -> str:
        target = self.opt.target
        if existing is None:
            if (target / PARTIAL).exists():
                return "new"  # an interrupted installation is repeated
            if target.exists() and any(target.iterdir()):
                raise InstallError(
                    f"{target} is not empty and holds no MyIssueDesk installation; "
                    "choose another folder with --target")
            return "new"
        order = compare_versions(self.version, existing.version)
        if order > 0:
            return "update"
        if order == 0:
            if self.opt.repair:
                return "repair"
            raise InstallError(
                f"version {existing.version} is already installed; use --repair to reinstall it")
        if not self.opt.allow_downgrade:
            raise InstallError(
                f"the installed version {existing.version} is newer than this installer "
                f"({self.version}); use --allow-downgrade only if you accept that the "
                "database may be newer than the old software understands")
        return "downgrade"

    # ---- prerequisites ---------------------------------------------------------------

    def check_prerequisites(self, mode: str, existing: Installation | None) -> None:
        if sys.version_info[:2] < MIN_PYTHON:
            raise InstallError(
                f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required, "
                f"this is {platform.python_version()}")
        if not self.opt.online:
            tag_dir = self.wheelhouse / self.python_tag
            if not (self.wheelhouse / "common").is_dir() or not tag_dir.is_dir():
                available = sorted(p.name for p in self.wheelhouse.glob("cp*")) if (
                    self.wheelhouse.exists()) else []
                raise InstallError(
                    f"this installer carries no libraries for Python {self.python_tag} "
                    f"(it has: {', '.join(available) or 'none'}). Use a supported Python, or "
                    "run it with --online to download the libraries from the package index")
        anchor = self.opt.target
        while not anchor.exists() and anchor.parent != anchor:
            anchor = anchor.parent
        if not os.access(anchor, os.W_OK):
            raise InstallError(f"no permission to write in {anchor}")
        needed = self._needed_bytes()
        free = shutil.disk_usage(anchor).free
        if free < needed:
            raise InstallError(
                f"not enough free disk space on {anchor.drive or anchor}: "
                f"{free // 2**20} MB free, about {needed // 2**20} MB needed")
        if mode in ("new",) and self.control.port_in_use(self.opt.host, self.opt.port):
            raise InstallError(
                f"port {self.opt.port} is already in use by another program. "
                "Stop it, or choose another port with --port")
        if mode != "new" and self.opt.import_data is not None:
            raise InstallError("--import-data is only for a new installation")
        if self.opt.import_data is not None and not self.opt.import_data.exists():
            raise InstallError(f"--import-data: {self.opt.import_data} does not exist")

    def _needed_bytes(self) -> int:
        size = 0
        if self.wheelhouse.exists():
            size = sum(p.stat().st_size for p in self.wheelhouse.rglob("*") if p.is_file())
        return max(300 * 2**20, 3 * size + 100 * 2**20)

    # ---- the plan --------------------------------------------------------------------

    def describe_plan(self, mode: str, existing: Installation | None) -> list[str]:
        libraries = "downloaded from the package index" if self.opt.online else "from the installer"
        lines = [f"MyIssueDesk {self.version} installer",
                 f"  target:   {self.opt.target}",
                 f"  Python:   {platform.python_version()} ({self.python_tag})",
                 f"  libraries: {libraries}"]
        if mode == "new":
            lines += [f"  mode:     new installation (address {self.opt.host}:{self.opt.port})",
                      "  steps:    create folders and environment, install, write server.toml "
                      "with a new administrator token, create the database, check the server"]
        else:
            assert existing is not None
            origin = " (made by the old installer)" if existing.origin == "legacy" else ""
            lines += [f"  mode:     {mode} of version {existing.version}{origin} to {self.version}",
                      "  steps:    stop this installation's server, back up the data, build the "
                      "new environment beside the old one, apply the database migrations, "
                      "start the server again; any failure restores the old version"]
        return lines

    # ---- running ---------------------------------------------------------------------

    def run(self) -> Report:
        self.verify_content()  # also for --check: a damaged installer is reported first
        existing = self.detect()
        mode = self.decide_mode(existing)
        self.report.mode = mode
        self.report.old_version = existing.version if existing else None
        self.check_prerequisites(mode, existing)
        for line in self.describe_plan(mode, existing):
            self.log.write(line)
        if self.opt.check:
            self.log.write("Check only: nothing was changed.")
            return self.report
        if not (self.opt.silent or self.opt.assume_yes) and sys.stdin.isatty():
            answer = input("Continue? [Y/n] ").strip().lower()
            if answer not in ("", "y", "yes"):
                raise InstallError("stopped by the user")
        self._open_log()
        if mode == "new":
            try:
                self._install_new()
            except InstallError as exc:
                raise InstallError(
                    f"{exc} -- the installation is incomplete; run the installer again "
                    "to repeat it",
                    exc.code) from exc
        else:
            assert existing is not None
            self._update(mode, existing)
        return self.report

    def _open_log(self) -> None:
        logs = self.opt.target / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        path = logs / f"install-{datetime.now().strftime('%Y%m%dT%H%M%S')}.log"
        self.log.attach(path)
        self.report.log_file = path

    def _run(self, command: list[str], cwd: Path | None = None, what: str = "") -> str:
        self.log.write("$ " + " ".join(command), console=False)
        result = self.runner.run(command, cwd=cwd)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if output:
            self.log.write(output, console=False)
        if result.returncode != 0:
            tail = " | ".join(output.splitlines()[-3:]) if output else "no output"
            raise InstallError(f"{what or command[0]} failed (exit {result.returncode}): {tail}",
                               EXIT_FAILED)
        return output

    # ---- shared steps ------------------------------------------------------------------

    def _build_environment(self, venv: Path) -> None:
        self.log.write("Creating the Python environment ...")
        self._run([sys.executable, "-m", "venv", str(venv)], what="creating the environment")
        py = str(venv_python(venv))
        self.log.write("Installing MyIssueDesk and its libraries ...")
        if self.opt.online:
            command = [py, "-m", "pip", "install", "--disable-pip-version-check",
                       str(self._app_wheel())]
        else:
            command = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-index",
                       "--find-links", str(self.wheelhouse / "common"),
                       "--find-links", str(self.wheelhouse / self.python_tag),
                       f"{PRODUCT}=={self.version}"]
        self._run(command, what="installing the software")
        output = self._run([py, "-m", "issuedeck", "--version"], cwd=self.opt.target,
                           what="checking the installed command")
        if self.version not in output:
            raise InstallError(
                f"the installed command reports {output!r}, expected version {self.version}",
                EXIT_FAILED)

    def _install_scripts(self) -> None:
        for name in SCRIPTS:
            source = self.payload / name
            if not source.is_file():
                raise InstallError(f"{name} is missing from the installer", EXIT_DAMAGED)
            shutil.copy2(source, self.opt.target / name)

    def _write_marker(self, mode: str, host: str, port: int) -> None:
        data = {
            "product": PRODUCT,
            "version": self.version,
            "installer_version": self.version,
            "mode": mode,
            "python": platform.python_version(),
            "python_tag": self.python_tag,
            "wheel_sha256": sha256_of(self._app_wheel()),
            "host": host,
            "port": port,
            "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        (self.opt.target / MARKER).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def _db_upgrade(self, check: bool) -> tuple[list[str], str]:
        py = str(venv_python(self.opt.target / ".venv"))
        command = [py, "-m", "issuedeck", "db-upgrade", "--config", "server.toml"]
        if check:
            command.append("--check")
        self.log.write("$ " + " ".join(command), console=False)
        result = self.runner.run(command, cwd=self.opt.target)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        if output:
            self.log.write(output, console=False)
        if result.returncode == 2 and "invalid choice" in output and "db-upgrade" in output:
            # a version from before the command existed: the server applies the migrations
            # when it starts, so the database may change at the first start
            self.log.write("This version has no db-upgrade command; the migrations are applied "
                           "when the server starts.")
            self.migrations_at_start = True
            return [], output
        if result.returncode != 0:
            tail = " | ".join(output.splitlines()[-3:]) if output else "no output"
            raise InstallError(
                f"the database migration failed (exit {result.returncode}): {tail}", EXIT_FAILED)
        pending: list[str] = []
        match = re.search(r"pending migrations: \d+(?: \(([^)]*)\))?", output)
        if match and match.group(1):
            pending = [item.strip() for item in match.group(1).split(",")]
        return pending, output

    def _verify_running(self, host: str, port: int) -> None:
        ready = self.control.ready(host, port)
        if not ready or str(ready.get("version")) != self.version:
            raise InstallError(
                f"the server did not become ready with version {self.version} "
                f"(answer: {ready})", EXIT_FAILED)

    # ---- new installation -------------------------------------------------------------

    def _make_config(self) -> str:
        """Write server.toml from the example with this installation's address and a fresh
        administrator token. Returns the token."""
        token = secrets.token_urlsafe(32)
        self.log.add_secret(token)
        text = self._example_text()

        def replace(key: str, value: str, body: str) -> str:
            pattern = re.compile(rf"(?m)^{key}\s*=.*$")
            if not pattern.search(body):
                return f"{key} = {value}\n" + body
            return pattern.sub(lambda _m: f"{key} = {value}", body, count=1)

        text = replace("host", json.dumps(self.opt.host), text)
        text = replace("port", str(self.opt.port), text)
        text = replace("api_token", json.dumps(token), text)
        config = self.opt.target / "server.toml"
        config.write_text(text, encoding="utf-8")
        tomllib.loads(text)  # must stay valid TOML
        if os.name == "nt":  # the file holds the token: only the current user may read it
            user = os.environ.get("USERNAME", "")
            if user:
                result = self.runner.run(
                    ["icacls", str(config), "/inheritance:r", "/grant:r", f"{user}:(F)"])
                if result.returncode != 0:
                    self.report.warnings.append(
                        "could not restrict the permissions of server.toml")
        return token

    def _install_new(self) -> None:
        target = self.opt.target
        self.log.write(f"New installation in {target}")
        target.mkdir(parents=True, exist_ok=True)
        (target / PARTIAL).write_text("installation in progress\n", encoding="utf-8")
        for name in ("data", "projects", "project-templates", "logs", "run", "backups"):
            (target / name).mkdir(exist_ok=True)
        venv = target / ".venv"
        if venv.exists():  # left by an interrupted run
            remove_tree(venv)
        self._build_environment(venv)
        self._install_scripts()
        if (target / "server.toml").exists():
            self.report.warnings.append("an existing server.toml was kept")
            host, port = self._configured_endpoint()
        else:
            self.report.admin_token = self._make_config()
            host, port = self.opt.host, self.opt.port
        if self.opt.import_data is not None:
            self._import_data(self.opt.import_data)
        self._db_upgrade(check=False)
        self.log.write("Checking that the server starts ...")
        self.control.start(target)
        try:
            self._verify_running(host, port)
        finally:
            keep = bool(self.opt.start)
            if not keep:
                self.control.stop(target)
        self.report.server_running = bool(self.opt.start)
        self._write_marker("new", host, port)
        (target / PARTIAL).unlink(missing_ok=True)
        self.report.url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}/dashboard"
        self.log.write("Installation finished.")

    def _import_data(self, source: Path) -> None:
        target = self.opt.target
        if source.is_file() and source.suffix.lower() == ".zip":
            self.log.write(f"Importing the project snapshot {source.name} ...")
            py = str(venv_python(target / ".venv"))
            self._run([py, "-m", "issuedeck", "import-audit-bundle", "--config", "server.toml",
                       "--mode", "create", str(source)], cwd=target, what="the snapshot import")
            return
        database = source / "tracker.db"
        if not database.is_file():
            raise InstallError(f"--import-data: {source} has no tracker.db and is not a ZIP")
        self.log.write(f"Copying the data folder {source} ...")
        backup_sqlite(database, target / "data" / "tracker.db")
        for item in source.iterdir():
            if item.name.startswith("tracker.db") or item.name.startswith("backup-"):
                continue
            destination = target / "data" / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)

    # ---- update, repair, downgrade ------------------------------------------------------

    def _backup(self, old_version: str) -> Path:
        target = self.opt.target
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        folder = target / "backups" / f"{stamp}-{old_version}"
        folder.mkdir(parents=True)
        database = target / "data" / "tracker.db"
        if database.is_file():
            backup_sqlite(database, folder / "data" / "tracker.db")
        data = target / "data"
        if data.is_dir():
            for item in data.iterdir():
                if item.name.startswith("tracker.db"):
                    continue
                destination = folder / "data" / item.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                if item.is_dir():
                    shutil.copytree(item, destination, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, destination)
        for name in ("server.toml", MARKER):
            if (target / name).is_file():
                shutil.copy2(target / name, folder / name)
        for name in ("projects", "project-templates"):
            if (target / name).is_dir():
                shutil.copytree(target / name, folder / name, dirs_exist_ok=True)
        return folder

    def _prune_backups(self) -> None:
        root = self.opt.target / "backups"
        if not root.is_dir() or self.opt.keep_backups < 1:
            return
        folders = sorted(p for p in root.iterdir() if p.is_dir())
        for old in folders[: max(0, len(folders) - self.opt.keep_backups)]:
            try:
                remove_tree(old)
            except InstallError as exc:
                self.report.warnings.append(str(exc))

    def _restore_database(self, backup: Path) -> None:
        saved = backup / "data" / "tracker.db"
        live = self.opt.target / "data" / "tracker.db"
        if not saved.is_file():
            return
        for suffix in ("", "-wal", "-shm"):
            (live.parent / f"tracker.db{suffix}").unlink(missing_ok=True)
        backup_sqlite(saved, live)

    def _update(self, mode: str, existing: Installation) -> None:
        target = self.opt.target
        host, port = existing.host, existing.port
        self.log.write(f"{mode.capitalize()} of {existing.version} to {self.version} in {target}")
        was_running = False
        backup: Path | None = None
        old_venv = target / ".venv.old"
        venv = target / ".venv"
        state = {"renamed": False, "built": False, "migrated": False, "started": False}
        try:
            if not venv.exists() and old_venv.exists():
                # an earlier run was interrupted after the old environment was moved aside
                self.log.write("Restoring the environment left aside by an earlier run ...")
                rename_with_retry(old_venv, venv)
            was_running = self.control.stop(target)
            self.log.write("The server of this installation was "
                           + ("running and is stopped." if was_running else "not running."))
            if self.control.port_in_use(host, port):
                raise InstallError(
                    f"port {port} is used by another program (not this installation); "
                    "it was not touched. Stop it and run the installer again")
            backup = self._backup(existing.version)
            self.report.backup = backup
            self.log.write(f"Backup written to {backup}")
            if venv.exists():
                if old_venv.exists():  # left by an earlier run that was not cleaned up
                    remove_tree(old_venv)
                rename_with_retry(venv, old_venv)
                state["renamed"] = True
            self._build_environment(venv)
            state["built"] = True
            if mode != "downgrade":
                pending, _ = self._db_upgrade(check=True)
                self.report.migrations = pending
                # a half-applied migration is restored too
                state["migrated"] = bool(pending) or self.migrations_at_start
                self._db_upgrade(check=False)
                if self.migrations_at_start:
                    state["migrated"] = True
                    self.report.warnings.append(
                        "this version has no db-upgrade command; the migrations are applied "
                        "when the server starts")
            else:
                self.report.warnings.append(
                    "downgrade: the database was not changed; if the old version does not "
                    f"start, restore the backup {backup}")
            self._install_scripts()
            self._report_new_options()
            self._write_marker(mode, host, port)
            if was_running or self.opt.start:
                self.control.start(target)
                state["started"] = True
                self._verify_running(host, port)
                self.report.server_running = True
        except InstallError as exc:
            self._rollback(exc, state, backup, existing, was_running)
            raise InstallError(
                f"{exc} -- the previous version {existing.version} was restored"
                + (f"; backup: {backup}" if backup else ""), EXIT_FAILED) from exc
        except Exception as exc:  # any unexpected failure restores as well
            self._rollback(exc, state, backup, existing, was_running)
            raise InstallError(
                f"unexpected error: {exc} -- the previous version {existing.version} "
                "was restored" + (f"; backup: {backup}" if backup else ""),
                EXIT_FAILED) from exc
        try:
            remove_tree(old_venv)
        except InstallError as exc:
            self.report.warnings.append(f"the old environment could not be removed: {exc}")
        self._prune_backups()
        self.report.url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{port}/dashboard"
        self.log.write("Update finished.")

    def _report_new_options(self) -> None:
        config = self.opt.target / "server.toml"
        try:
            installed = top_level_keys(config.read_text(encoding="utf-8-sig"))
        except OSError:
            return
        self.report.new_options = sorted(top_level_keys(self._example_text()) - installed)

    def _rollback(self, error: Exception, state: dict[str, bool], backup: Path | None,
                  existing: Installation, was_running: bool) -> None:
        target = self.opt.target
        self.log.write(f"FAILED: {error}. Restoring version {existing.version} ...")
        venv, old_venv = target / ".venv", target / ".venv.old"
        problems: list[str] = []
        try:
            if state["started"] or self.control.port_in_use(existing.host, existing.port):
                self.control.stop(target)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"stopping the new server: {exc}")
        try:
            if state["renamed"]:
                if venv.exists():
                    remove_tree(venv)
                rename_with_retry(old_venv, venv)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"restoring the old environment: {exc}")
        try:
            if state["migrated"] and backup is not None:
                self._restore_database(backup)
            if backup is not None and (backup / MARKER).is_file():
                shutil.copy2(backup / MARKER, target / MARKER)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"restoring the data: {exc}")
        try:
            if was_running:
                self.control.start(target)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"starting the old server: {exc}")
        for problem in problems:
            self.log.write(f"Rollback problem: {problem}")
            self.report.warnings.append(f"rollback problem: {problem}")


# --------------------------------------------------------------------------- command line


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="installer.py",
        description="Install MyIssueDesk, or update an installed copy without touching its data.",
    )
    parser.add_argument("--target", default=DEFAULT_TARGET, help="installation folder "
                        f"(default {DEFAULT_TARGET})")
    parser.add_argument("--host", default=DEFAULT_HOST, help="address of a new installation")
    parser.add_argument("--port", type=int, default=None,
                        help=f"port of a new installation (default {DEFAULT_PORT}, must be free)")
    parser.add_argument("--online", action="store_true",
                        help="download the libraries from the package index instead of using "
                             "the ones in the installer")
    parser.add_argument("--check", action="store_true",
                        help="show what would be done and change nothing")
    parser.add_argument("--repair", action="store_true",
                        help="reinstall the same version")
    parser.add_argument("--allow-downgrade", action="store_true",
                        help="allow installing an older version than the installed one")
    parser.add_argument("--keep-backups", type=int, default=DEFAULT_KEEP_BACKUPS,
                        help="how many update backups to keep (default 5)")
    start = parser.add_mutually_exclusive_group()
    start.add_argument("--start", dest="start", action="store_true", default=None,
                       help="leave the server running at the end")
    start.add_argument("--no-start", dest="start", action="store_false",
                       help="do not start the server (an updated server that was running is "
                            "still restarted)")
    parser.add_argument("--import-data", default=None,
                        help="new installation only: a project snapshot .zip or the data folder "
                             "of another installation")
    parser.add_argument("--silent", action="store_true", help="no questions, little output")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--source", default=None, help=argparse.SUPPRESS)
    return parser


def print_report(report: Report, log: Log) -> None:
    out = log.write
    out("")
    out(f"MyIssueDesk {report.new_version}: {report.mode} finished.")
    out(f"  folder:  {report.target}")
    if report.old_version:
        out(f"  version: {report.old_version} -> {report.new_version}")
    if report.backup:
        out(f"  backup:  {report.backup}")
    if report.migrations:
        out(f"  database migrations applied: {', '.join(report.migrations)}")
    elif report.mode in ("update", "repair"):
        out("  database migrations applied: none")
    if report.new_options:
        out("  new options in the example configuration (not added to your server.toml): "
            + ", ".join(report.new_options))
    out(f"  server:  {'running' if report.server_running else 'stopped'}"
        + (f" - {report.url}" if report.url else ""))
    out(f"  start:   {report.target}\\start-myissuedesk.vbs   stop: stop-myissuedesk.vbs")
    for warning in report.warnings:
        out(f"  note:    {warning}")
    if report.log_file:
        out(f"  log:     {report.log_file}")
    if report.admin_token:
        out("")
        out("  Administrator token (shown only now; it is stored in server.toml):")
        # the one place the token is printed: not through the log
        print(f"    {report.admin_token}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    options = Options(
        target=Path(args.target),
        host=args.host,
        port=args.port if args.port is not None else DEFAULT_PORT,
        port_given=args.port is not None,
        online=args.online,
        check=args.check,
        repair=args.repair,
        allow_downgrade=args.allow_downgrade,
        keep_backups=args.keep_backups,
        start=args.start,
        import_data=Path(args.import_data) if args.import_data else None,
        silent=args.silent,
        assume_yes=args.yes,
        source=Path(args.source) if args.source else HERE,
    )
    log = Log(quiet=args.silent)
    try:
        installer = Installer(options, log=log)
        report = installer.run()
    except InstallError as exc:
        log.write(f"[error] {exc}")
        return exc.code
    except Exception as exc:  # noqa: BLE001 - the user gets a message, the log has the rest
        log.write(f"[error] unexpected: {type(exc).__name__}: {exc}")
        return EXIT_FAILED
    if not options.check:
        print_report(report, log)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
