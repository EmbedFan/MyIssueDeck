"""Update the installed test copy of MyIssueDeck from the current source (TASK-0005).

    python scripts/update_test_copy.py --target C:\\Utility\\MyIssueDeck_0.10.2
    python scripts/update_test_copy.py --target ... --check     show the plan, change nothing

It runs the steps a developer would run by hand, in order:

1. read the installed version (``install.json``) and the source version (``pyproject.toml``);
2. check ``dist/myissuedeck-installer-<version>-win64.zip`` against its ``.sha256`` file;
3. note the item and project counts of the running server;
4. stop the server of the target folder (``stop-server.ps1``; the installer does the same, but a
   folder cannot be renamed while its server runs) and wait until the port is closed;
5. rename ``MyIssueDeck_<old>`` to ``MyIssueDeck_<new>`` when the version changed;
6. unpack the installer into a new scratch folder and run ``installer.py --target`` from there
   (the installer backs up the database and the configuration, keeps both, rebuilds ``.venv``,
   migrates the database and starts the server);
7. wait for ``/readyz``, check the new version and that the counts are unchanged.

It only ever touches the folder given with ``--target``. The development instance (port 8766) and
any other installation are never stopped. The administrator token is never read or printed.
Build the installer first: ``uv build --wheel`` and ``python scripts/build_installer.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY_TIMEOUT = 180  # seconds; starting the server takes a while
STOP_TIMEOUT = 120


class UpdateError(Exception):
    pass


def say(text: str) -> None:
    print(text, flush=True)


def source_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def read_install(target: Path) -> dict:
    path = target / "install.json"
    if not path.is_file():
        raise UpdateError(f"{target} holds no MyIssueDeck installation (install.json is missing)")
    info = json.loads(path.read_text(encoding="utf-8"))
    if info.get("product") != "myissuedeck":
        raise UpdateError(f"{target} is not a MyIssueDeck installation")
    return info


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def check_installer(version: str) -> Path:
    zip_path = ROOT / "dist" / f"myissuedeck-installer-{version}-win64.zip"
    sha_path = Path(f"{zip_path}.sha256")
    if not zip_path.is_file() or not sha_path.is_file():
        raise UpdateError(f"installer for {version} not built: run scripts/build_installer.py")
    expected = sha_path.read_text(encoding="utf-8").split()[0].lower()
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if expected != actual:
        raise UpdateError(f"SHA-256 of {zip_path.name} does not match its .sha256 file")
    return zip_path


def http_json(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - loopback only
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def counts(target: Path, port: int) -> dict:
    """Items in the database (read only) and projects reported by the server."""
    db = target / "data" / "tracker.db"
    items = None
    if db.is_file():
        with sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True) as conn:
            items = conn.execute("select count(*) from items").fetchone()[0]
    ready = http_json(f"http://127.0.0.1:{port}/readyz") or {}
    return {"items": items, "projects": ready.get("projects")}


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def stop_server(target: Path, port: int) -> bool:
    """Stop the server of this folder. Returns True when one was running."""
    if not port_open(port):
        return False
    script = target / "stop-server.ps1"
    if not script.is_file():
        raise UpdateError(f"{script} is missing; stop the server by hand and run again")
    subprocess.run(  # noqa: S603 - fixed arguments
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        check=False, timeout=STOP_TIMEOUT,
    )
    deadline = time.monotonic() + STOP_TIMEOUT
    while port_open(port):
        if time.monotonic() > deadline:
            raise UpdateError(f"the server on port {port} did not stop; nothing was changed")
        time.sleep(1)
    return True


def wait_ready(port: int, version: str) -> dict:
    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        ready = http_json(f"http://127.0.0.1:{port}/readyz")
        if ready and ready.get("status") == "ready":
            if ready.get("version") != version:
                raise UpdateError(f"server reports {ready.get('version')}, expected {version}")
            return ready
        time.sleep(2)
    raise UpdateError(f"the server did not become ready within {READY_TIMEOUT} s; see logs\\")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", required=True, help="the installed folder to update")
    parser.add_argument("--check", action="store_true", help="show the plan, change nothing")
    parser.add_argument("--repair", action="store_true", help="reinstall the same version")
    parser.add_argument("--no-rename", action="store_true", help="keep the folder name")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    info = read_install(target)
    old, new, port = info["version"], source_version(), int(info["port"])
    if port == 8766:
        raise UpdateError("port 8766 is the development instance; it is never updated here")
    if version_key(new) <= version_key(old) and not args.repair:
        raise UpdateError(f"installed {old}, source {new}: bump the version first (or --repair)")

    zip_path = check_installer(new)
    new_dir = target.with_name(re.sub(r"\d+(\.\d+)+$", new, target.name))
    rename = new_dir != target and not args.no_rename
    before = counts(target, port)
    say(f"installed {old} -> source {new}; folder {target.name}"
        + (f" -> {new_dir.name}" if rename else " (kept)"))
    say(f"installer {zip_path.name} verified; port {port}; before: {before}")
    if args.check:
        return 0

    was_running = stop_server(target, port)
    say(f"server stopped (was running: {was_running})")
    final = target
    if rename:
        if new_dir.exists():
            raise UpdateError(f"{new_dir} already exists; nothing was renamed")
        target.rename(new_dir)
        final = new_dir
        say(f"renamed to {new_dir}")

    with tempfile.TemporaryDirectory(prefix="myissuedeck-installer-") as scratch:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(scratch)
        command = [sys.executable, "-I", str(Path(scratch) / "installer.py"),
                   "--target", str(final), "--yes", "--start"]
        if args.repair:
            command.append("--repair")
        say("running the installer ...")
        result = subprocess.run(command, cwd=scratch, check=False)  # noqa: S603
    if result.returncode != 0:
        raise UpdateError(f"the installer exited with {result.returncode}; see its output above")

    ready = wait_ready(port, new)
    after = counts(final, port)
    say(f"ready: {ready}; after: {after}")
    # a count that could not be read before (server not running) is not compared
    changed = {k: (before[k], after[k]) for k in before
               if before[k] is not None and before[k] != after[k]}
    if changed:
        raise UpdateError(f"counts changed (before, after): {changed}")
    backups = sorted((final / "backups").glob("*"))
    say(f"OK: updated {old} -> {new} in {final}; newest backup: {backups[-1] if backups else '-'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
