"""The installer generator (scripts/build_installer.py). No network: the small variant only."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location(
        "build_installer_module", ROOT / "scripts" / "build_installer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_installer_module"] = module
    spec.loader.exec_module(module)
    return module


bi = _load()


def _make_wheel(path: Path, version: str, extra: dict[str, str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"issuedeck-{version}.dist-info/METADATA",
                         f"Metadata-Version: 2.4\nName: myissuedeck\nVersion: {version}\n")
        archive.writestr("issuedeck/__init__.py", "")
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return path


@pytest.fixture()
def wheel(tmp_path):
    version = bi.project_version(ROOT)
    return _make_wheel(tmp_path / "wheels" / f"myissuedeck-{version}-py3-none-any.whl", version)


def _build(tmp_path, wheel, name="out"):
    out = tmp_path / name
    code = bi.main(["--no-wheelhouse", "--wheel", str(wheel), "--out", str(out)])
    assert code == 0
    return next(out.glob("*.zip"))


def test_the_version_comes_from_pyproject_and_matches_the_package():
    assert bi.project_version(ROOT) == bi.package_version(ROOT)


def test_the_small_installer_is_named_with_the_version_and_has_a_checksum(tmp_path, wheel):
    archive = _build(tmp_path, wheel)

    version = bi.project_version(ROOT)
    assert archive.name == f"myissuedeck-installer-{version}-win64-online.zip"
    recorded = (archive.parent / f"{archive.name}.sha256").read_text(encoding="utf-8").split()
    assert recorded == [bi.sha256_of(archive), archive.name]


def test_the_installer_contains_what_it_needs_and_nothing_else(tmp_path, wheel):
    archive = _build(tmp_path, wheel)

    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
    version = bi.project_version(ROOT)
    assert names == {
        "install.cmd", "installer.py", "README-INSTALL.txt", "installer-manifest.json",
        "payload/server.toml.example", "payload/USERGUIDE.md",
        "payload/start-myissuedesk.vbs", "payload/stop-myissuedesk.vbs",
        "payload/start-server.ps1", "payload/stop-server.ps1",
        f"wheelhouse/common/myissuedeck-{version}-py3-none-any.whl",
    }


def test_the_manifest_lists_every_file_with_its_real_checksum(tmp_path, wheel):
    archive = _build(tmp_path, wheel)

    import hashlib

    with zipfile.ZipFile(archive) as z:
        manifest = json.loads(z.read("installer-manifest.json"))
        assert manifest["version"] == bi.project_version(ROOT)
        others = set(z.namelist()) - {"installer-manifest.json"}
        assert set(manifest["files"]) == others
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == expected, name


def test_two_builds_give_the_same_bytes(tmp_path, wheel):
    first = _build(tmp_path, wheel, "one")
    second = _build(tmp_path, wheel, "two")

    assert first.read_bytes() == second.read_bytes()


def test_the_installer_ships_the_current_example_configuration_not_a_copy(tmp_path, wheel):
    archive = _build(tmp_path, wheel)

    with zipfile.ZipFile(archive) as z:
        assert z.read("payload/server.toml.example") == (ROOT / "server.toml.example").read_bytes()
        assert z.read("installer.py") == (ROOT / "installer" / "installer.py").read_bytes()


def test_a_wheel_with_another_version_stops_the_build(tmp_path, capsys):
    stale = _make_wheel(tmp_path / "w" / "myissuedeck-0.0.1-py3-none-any.whl", "0.0.1")

    code = bi.main(["--no-wheelhouse", "--wheel", str(stale), "--out", str(tmp_path / "out")])

    assert code == 1
    assert "the versions differ" in capsys.readouterr().err
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("*.zip"))


def test_a_wheel_that_contains_a_database_stops_the_build(tmp_path, capsys):
    version = bi.project_version(ROOT)
    bad = _make_wheel(tmp_path / "w" / f"myissuedeck-{version}-py3-none-any.whl", version,
                      {"issuedeck/tracker.db": "sqlite"})

    code = bi.main(["--no-wheelhouse", "--wheel", str(bad), "--out", str(tmp_path / "out")])

    assert code == 1
    assert "forbidden" in capsys.readouterr().err


@pytest.mark.parametrize("relative", [
    "data/tracker.db", "payload/server.toml", ".mcp.json", "payload/.env", "projects/mine.toml",
    "logs/server.out.log", "backups/x/tracker.db", "payload/secret.pem", "tracker.db-wal",
])
def test_forbidden_files_are_found(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")

    problems = bi.scan_forbidden(tmp_path)

    assert any(relative in p for p in problems), problems


@pytest.mark.parametrize("text", [
    "token = ghp_" + "a" * 36,
    "pat = github_pat_" + "b" * 40,
    "-----BEGIN RSA PRIVATE KEY-----",
    'api_token = "' + "k" * 40 + '"',
])
def test_secret_like_text_is_found(tmp_path, text):
    (tmp_path / "notes.txt").write_text(text + "\n", encoding="utf-8")

    assert bi.scan_forbidden(tmp_path) == ["secret-like text in notes.txt"]


def test_the_example_configuration_with_its_placeholder_token_is_allowed(tmp_path):
    (tmp_path / "payload").mkdir()
    (tmp_path / "payload" / "server.toml.example").write_text(
        (ROOT / "server.toml.example").read_text(encoding="utf-8"), encoding="utf-8")

    assert bi.scan_forbidden(tmp_path) == []


def test_the_real_installer_folder_passes_the_content_scan(tmp_path):
    """Names the file if a secret or a data file ever gets into installer/."""
    import shutil

    copy = tmp_path / "installer"
    shutil.copytree(ROOT / "installer", copy, ignore=shutil.ignore_patterns("__pycache__"))

    assert bi.scan_forbidden(copy) == []


EXPORTED = """\
# autogenerated
aiosqlite==0.22.1
    # via myissuedeck
colorama==0.4.6 ; sys_platform == 'win32'
pywin32==311 ; sys_platform == 'win32'
uvloop==0.22.1 ; platform_python_implementation != 'PyPy' and sys_platform != 'win32'
tomli==2.0.1 ; python_version < '3.11'
exceptiongroup==1.3.0 ; python_version < '3.11'
"""


def test_markers_are_evaluated_for_windows_and_the_target_python_not_for_this_machine():
    wanted = bi.requirements_for(EXPORTED, "3.12")

    assert "pywin32==311" in wanted and "colorama==0.4.6" in wanted
    assert not any(w.startswith("uvloop") for w in wanted)
    assert not any(w.startswith("tomli") for w in wanted)
    assert wanted[0] == "aiosqlite==0.22.1"


def test_an_older_python_gets_the_backports():
    wanted = bi.requirements_for(EXPORTED, "3.10")

    assert any(w.startswith("tomli") for w in wanted)


def test_pure_python_wheels_are_recognised():
    assert bi.is_pure("jinja2-3.1.6-py3-none-any.whl")
    assert not bi.is_pure("pydantic_core-2.46.3-cp312-cp312-win_amd64.whl")


# ------------------------------------------------------------- the built installer runs


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _extract(archive: Path, where: Path) -> Path:
    with zipfile.ZipFile(archive) as z:
        z.extractall(where)
    return where


def _run_installer(folder: Path, *args: str):
    return subprocess.run([sys.executable, str(folder / "installer.py"), *args],
                          capture_output=True, text=True)


def test_the_built_installer_verifies_itself_and_reports_a_check_run(tmp_path, wheel):
    folder = _extract(_build(tmp_path, wheel), tmp_path / "unzipped")
    target = tmp_path / "target"

    run = _run_installer(folder, "--check", "--online", "--target", str(target),
                         "--port", str(_free_port()))

    assert run.returncode == 0, run.stdout + run.stderr
    assert "Installer content verified" in run.stdout
    assert "new installation" in run.stdout and "Check only" in run.stdout
    assert not target.exists()


def test_a_changed_file_in_the_built_installer_is_refused_with_the_damaged_code(tmp_path, wheel):
    folder = _extract(_build(tmp_path, wheel), tmp_path / "unzipped")
    (folder / "payload" / "start-server.ps1").write_text("changed", encoding="utf-8")

    run = _run_installer(folder, "--check", "--online", "--target", str(tmp_path / "t"),
                         "--port", str(_free_port()))

    assert run.returncode == 3
    assert "damaged" in run.stdout and "start-server.ps1" in run.stdout


def test_without_online_the_small_installer_explains_what_to_do(tmp_path, wheel):
    folder = _extract(_build(tmp_path, wheel), tmp_path / "unzipped")

    run = _run_installer(folder, "--check", "--target", str(tmp_path / "t"),
                         "--port", str(_free_port()))

    assert run.returncode == 2
    assert "--online" in run.stdout


# ------------------------------------------------------------- libraries taken from uv.lock


def _entry(folder: Path, filename: str, content: bytes | None = None, *, bad_hash=False) -> dict:
    import hashlib

    folder.mkdir(parents=True, exist_ok=True)
    data = content if content is not None else filename.encode()
    (folder / filename).write_bytes(data)
    digest = hashlib.sha256(b"other" if bad_hash else data).hexdigest()
    return {"url": (folder / filename).as_uri(), "hash": f"sha256:{digest}", "size": len(data)}


def _tags(version: str, tag: str):
    return bi.supported_tags(version, tag)


def test_the_wheel_for_the_target_python_and_windows_is_chosen(tmp_path):
    entries = [
        _entry(tmp_path, "core-1.0-cp312-cp312-win32.whl"),
        _entry(tmp_path, "core-1.0-cp312-cp312-manylinux_2_17_x86_64.whl"),
        _entry(tmp_path, "core-1.0-cp311-cp311-win_amd64.whl"),
        _entry(tmp_path, "core-1.0-cp312-cp312-win_amd64.whl"),
        _entry(tmp_path, "core-1.0-cp313-cp313-win_amd64.whl"),
    ]

    chosen = bi.select_wheel(entries, _tags("3.12", "cp312"))

    assert chosen["url"].endswith("core-1.0-cp312-cp312-win_amd64.whl")


def test_an_abi3_wheel_serves_every_newer_python(tmp_path):
    entries = [_entry(tmp_path, "crypto-1.0-cp39-abi3-win_amd64.whl")]

    for version, tag in (("3.11", "cp311"), ("3.12", "cp312"), ("3.13", "cp313")):
        assert bi.select_wheel(entries, _tags(version, tag)) is not None


def test_a_pure_python_wheel_is_chosen_when_there_is_nothing_compiled(tmp_path):
    entries = [_entry(tmp_path, "pure-1.0-py3-none-any.whl")]

    assert bi.select_wheel(entries, _tags("3.12", "cp312")) is not None


def test_no_wheel_for_windows_means_none(tmp_path):
    entries = [_entry(tmp_path, "core-1.0-cp312-cp312-manylinux_2_17_x86_64.whl"),
               _entry(tmp_path, "core-1.0-cp312-cp312-macosx_11_0_arm64.whl")]

    assert bi.select_wheel(entries, _tags("3.12", "cp312")) is None


def test_a_download_is_checked_against_the_hash_of_the_lock(tmp_path):
    good = _entry(tmp_path / "src", "pure-1.0-py3-none-any.whl")
    bad = _entry(tmp_path / "src2", "evil-1.0-py3-none-any.whl", bad_hash=True)

    bi.fetch_wheel(good, tmp_path / "ok.whl")
    assert (tmp_path / "ok.whl").read_bytes() == b"pure-1.0-py3-none-any.whl"
    with pytest.raises(bi.BuildError, match="checksum mismatch"):
        bi.fetch_wheel(bad, tmp_path / "bad.whl")
    assert not (tmp_path / "bad.whl").exists()  # an altered file is never kept


def test_a_size_that_differs_from_the_lock_is_refused(tmp_path):
    entry = _entry(tmp_path / "src", "pure-1.0-py3-none-any.whl")
    entry["size"] += 1

    with pytest.raises(bi.BuildError, match="size mismatch"):
        bi.fetch_wheel(entry, tmp_path / "x.whl")


def test_a_verified_download_is_reused_from_the_cache(tmp_path):
    entry = _entry(tmp_path / "src", "pure-1.0-py3-none-any.whl")
    cache = tmp_path / "cache"
    bi.fetch_wheel(entry, tmp_path / "first.whl", cache)
    (tmp_path / "src" / "pure-1.0-py3-none-any.whl").unlink()  # the source is gone

    bi.fetch_wheel(entry, tmp_path / "second.whl", cache)

    assert (tmp_path / "second.whl").read_bytes() == (tmp_path / "first.whl").read_bytes()


def _write_lock(path: Path, packages: dict[str, list[dict]]) -> None:
    lines = ["version = 1", ""]
    for name, wheels in packages.items():
        version = wheels[0]["url"].rsplit("/", 1)[-1].split("-")[1]
        lines += ["[[package]]", f'name = "{name}"', f'version = "{version}"', "wheels = ["]
        for w in wheels:
            lines.append(f'  {{ url = "{w["url"]}", hash = "{w["hash"]}", size = {w["size"]} }},')
        lines += ["]", ""]
    path.write_text(os.linesep.join(lines), encoding="utf-8")


def test_the_wheelhouse_is_laid_out_per_python_and_verified(tmp_path):
    src = tmp_path / "src"
    packages = {
        "pure-lib": [_entry(src, "pure_lib-1.0-py3-none-any.whl")],
        "fast-core": [_entry(src, f"fast_core-2.0-{t}-{t}-win_amd64.whl") for t in bi.PYTHON_TAGS]
        + [_entry(src, "fast_core-2.0-cp312-cp312-manylinux_2_17_x86_64.whl")],
        "pywin32": [_entry(src, f"pywin32-311-{t}-{t}-win_amd64.whl") for t in bi.PYTHON_TAGS],
    }
    lock = tmp_path / "uv.lock"
    _write_lock(lock, packages)
    exported = os.linesep.join([
        "pure-lib==1.0",
        "fast-core==2.0",
        "pywin32==311 ; sys_platform == 'win32'",
        "uvloop==1.0 ; sys_platform != 'win32'",
    ])

    counts = bi.download_wheelhouse(exported, tmp_path / "wh", lock)

    assert counts == {"cp311": 2, "cp312": 2, "cp313": 2}
    common = sorted(p.name for p in (tmp_path / "wh" / "common").iterdir())
    assert common == ["pure_lib-1.0-py3-none-any.whl"]
    for tag in bi.PYTHON_TAGS:
        names = sorted(p.name for p in (tmp_path / "wh" / tag).iterdir())
        assert names == [f"fast_core-2.0-{tag}-{tag}-win_amd64.whl",
                         f"pywin32-311-{tag}-{tag}-win_amd64.whl"]


def test_a_library_without_a_windows_wheel_stops_the_build_and_names_it(tmp_path):
    src = tmp_path / "src"
    lock = tmp_path / "uv.lock"
    wheel = _entry(src, "linux_only-1.0-cp312-cp312-manylinux_2_17_x86_64.whl")
    _write_lock(lock, {"linux-only": [wheel]})

    with pytest.raises(bi.BuildError, match="linux-only==1.0"):
        bi.download_wheelhouse("linux-only==1.0", tmp_path / "wh", lock)


def test_the_real_lock_has_a_windows_wheel_for_every_requirement_of_every_python():
    """No network: only the selection. Catches a dependency that would break the offline bundle."""
    locked = bi.locked_wheels(ROOT / "uv.lock")
    from packaging.utils import canonicalize_name

    exported = bi.exported_requirements(ROOT)
    for tag, version in bi.PYTHON_TAGS.items():
        tags = _tags(version, tag)
        for requirement in bi.requirements_for(exported, version):
            name, _, pinned = requirement.partition("==")
            candidates = [e for e in locked[canonicalize_name(name)]
                          if e["url"].rsplit("/", 1)[-1].split("-")[1] == pinned]
            assert bi.select_wheel(candidates, tags) is not None, f"{tag}: {requirement}"
