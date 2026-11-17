"""Build the standalone MyIssueDesk installer (FEA-0009).

    python scripts/build_installer.py                  full installer with the offline libraries
    python scripts/build_installer.py --no-wheelhouse  small installer that needs --online

Result in dist/: ``myissuedeck-installer-<version>-win64.zip`` (``-online`` for the small one)
and a ``.sha256`` file. The version is read from pyproject.toml and must equal the one in
``issuedeck/__init__.py`` and in the wheel; the build fails otherwise. The installer never
contains data, ``server.toml``, tokens, or a database; the build fails if it would.

The full installer needs the network at build time only: the dependency wheels are the
ones recorded in ``uv.lock`` (URL and SHA-256), downloaded for Windows 64-bit and for each
Python in ``PYTHON_TAGS`` and verified against the lock. The environment markers of
``uv export`` are evaluated here for the target, not for the machine that builds (so
``pywin32`` is bundled when building on Linux, and ``uvloop`` is not).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_TAGS = {"cp311": "3.11", "cp312": "3.12", "cp313": "3.13"}
PLATFORM = "win_amd64"
ZIP_DATE = (2020, 1, 1, 0, 0, 0)  # fixed, so two builds give the same bytes
FORBIDDEN_NAMES = (
    re.compile(r"(^|/)server\.toml$"),
    re.compile(r"(^|/)\.mcp\.json$"),
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"\.(db|db-wal|db-shm|sqlite|sqlite3)$"),
    re.compile(r"\.(pem|key|pfx|p12)$"),
    re.compile(r"(^|/)(logs|data|backups)/"),
    re.compile(r"(^|/)projects/[^/]+\.toml$"),
)
# the text files of the installer must hold no secret: GitHub tokens, private keys, and an
# api_token that is not an obvious placeholder
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r'(?m)^\s*(?:api_)?token\s*=\s*"(?!change-me|replace-with|replace-me|your-)[^"]{16,}"'),
)


class BuildError(Exception):
    pass


# --------------------------------------------------------------------------- versions


def project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def package_version(root: Path) -> str:
    text = (root / "src" / "issuedeck" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'(?m)^__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise BuildError("src/issuedeck/__init__.py has no __version__")
    return match.group(1)


def wheel_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if not names:
            raise BuildError(f"{wheel.name} has no METADATA")
        for line in archive.read(names[0]).decode("utf-8").splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    raise BuildError(f"{wheel.name}: no Version in METADATA")


def check_versions(root: Path, wheel: Path) -> str:
    versions = {
        "pyproject.toml": project_version(root),
        "issuedeck.__version__": package_version(root),
        f"wheel {wheel.name}": wheel_version(wheel),
    }
    if len(set(versions.values())) != 1:
        listing = ", ".join(f"{k}={v}" for k, v in versions.items())
        raise BuildError(f"the versions differ: {listing}")
    return next(iter(versions.values()))


# --------------------------------------------------------------------------- wheelhouse


def find_uv() -> list[str]:
    found = shutil.which("uv")
    if found:
        return [found]
    sibling = Path(sys.executable).parent / ("uv.exe" if sys.platform == "win32" else "uv")
    if sibling.exists():
        return [str(sibling)]
    raise BuildError("uv was not found (it is needed for 'uv export' and 'uv build')")


def build_wheel(root: Path, out_dir: Path) -> Path:
    command = [*find_uv(), "build", "--wheel", "--out-dir", str(out_dir)]
    subprocess.run(command, cwd=root, check=True)
    wheels = sorted(out_dir.glob("myissuedeck-*.whl"))
    if not wheels:
        raise BuildError("uv build produced no wheel")
    return wheels[-1]


def exported_requirements(root: Path) -> str:
    result = subprocess.run(
        [*find_uv(), "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project"],
        cwd=root, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise BuildError(f"uv export failed: {result.stderr.strip()[-300:]}")
    return result.stdout


def requirements_for(exported: str, python_version: str) -> list[str]:
    """The pinned requirements that apply to Windows 64-bit with this Python."""
    try:
        from packaging.markers import Marker
    except ImportError as exc:  # pragma: no cover
        raise BuildError("the 'packaging' library is needed (it comes with pytest)") from exc
    environment = {
        "python_version": python_version,
        "python_full_version": f"{python_version}.0",
        "sys_platform": "win32",
        "platform_system": "Windows",
        "os_name": "nt",
        "platform_machine": "AMD64",
        "platform_python_implementation": "CPython",
        "implementation_name": "cpython",
        "platform_release": "10",
        "platform_version": "",
        "extra": "",
    }
    wanted: list[str] = []
    for raw in exported.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        requirement, _, marker = line.partition(";")
        if marker.strip() and not Marker(marker.strip()).evaluate(environment):
            continue
        wanted.append(requirement.strip())
    return wanted


def is_pure(name: str) -> bool:
    return name.endswith("-none-any.whl")


def locked_wheels(lock_path: Path) -> dict[str, list[dict]]:
    """name (normalised) -> the wheel entries of uv.lock (url, hash, size)."""
    from packaging.utils import canonicalize_name

    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    return {canonicalize_name(p["name"]): p.get("wheels", []) for p in lock["package"]}


def supported_tags(python_version: str, tag: str) -> list:
    """The wheel tags of CPython <version> on Windows 64-bit, best first."""
    from packaging.tags import compatible_tags, cpython_tags

    version = tuple(int(part) for part in python_version.split("."))
    platforms = [PLATFORM]
    return [
        *cpython_tags(python_version=version, abis=[tag, "abi3"], platforms=platforms),
        *compatible_tags(python_version=version, interpreter=tag, platforms=platforms),
    ]


def select_wheel(entries: list[dict], tags: list) -> dict | None:
    """The entry of the locked wheels that fits the tags best, or None."""
    from packaging.utils import InvalidWheelFilename, parse_wheel_filename

    rank = {tag: position for position, tag in enumerate(tags)}
    best: tuple[int, dict] | None = None
    for entry in entries:
        filename = entry["url"].rsplit("/", 1)[-1]
        try:
            _, _, _, wheel_tags = parse_wheel_filename(filename)
        except InvalidWheelFilename:
            continue
        positions = [rank[t] for t in wheel_tags if t in rank]
        if positions and (best is None or min(positions) < best[0]):
            best = (min(positions), entry)
    return best[1] if best else None


def fetch_wheel(entry: dict, destination: Path, cache: Path | None = None) -> None:
    """Download a locked wheel and check size and SHA-256 against uv.lock."""
    expected = entry["hash"].split(":", 1)[1]
    if cache is not None:
        cached = cache / f"{expected}.whl"
        if cached.is_file() and sha256_of(cached) == expected:
            shutil.copy2(cached, destination)
            return
    context = ssl.create_default_context()  # the operating system's certificate store
    last: Exception | None = None
    for _ in range(3):
        try:
            request = urllib.request.Request(
                entry["url"], headers={"User-Agent": "myissuedesk-build"})
            with urllib.request.urlopen(request, timeout=120, context=context) as response:  # noqa: S310
                data = response.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise BuildError(f"checksum mismatch for {entry['url'].rsplit('/', 1)[-1]}")
            if "size" in entry and len(data) != entry["size"]:
                raise BuildError(f"size mismatch for {entry['url'].rsplit('/', 1)[-1]}")
            destination.write_bytes(data)
            if cache is not None:
                cache.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, cache / f"{expected}.whl")
            return
        except (OSError, BuildError) as exc:  # a broken or altered download is tried again
            last = exc
    raise BuildError(f"could not download {entry['url']}: {last}")


def download_wheelhouse(exported: str, wheelhouse: Path, lock_path: Path,
                        cache: Path | None = None) -> dict[str, int]:
    """Common (pure Python) wheels in ``common/``, compiled ones in ``<tag>/``.

    The files are exactly the ones recorded in ``uv.lock`` and are verified against its hashes.
    """
    from packaging.utils import canonicalize_name

    locked = locked_wheels(lock_path)
    common = wheelhouse / "common"
    common.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for tag, version in PYTHON_TAGS.items():
        tags = supported_tags(version, tag)
        tag_dir = wheelhouse / tag
        compiled = 0
        for requirement in requirements_for(exported, version):
            name, _, pinned = requirement.partition("==")
            entry = select_wheel(
                [e for e in locked.get(canonicalize_name(name), [])
                 if e["url"].rsplit("/", 1)[-1].split("-")[1] == pinned], tags)
            if entry is None:
                raise BuildError(f"{tag}: uv.lock has no wheel of {requirement} for Windows "
                                 f"64-bit and Python {version}")
            filename = entry["url"].rsplit("/", 1)[-1]
            folder = common if is_pure(filename) else tag_dir
            destination = folder / filename
            if not destination.exists():
                folder.mkdir(parents=True, exist_ok=True)
                fetch_wheel(entry, destination, cache)
            if not is_pure(filename):
                compiled += 1
        counts[tag] = compiled
    return counts


# --------------------------------------------------------------------------- content checks


def scan_forbidden(stage: Path) -> list[str]:
    """Names and contents that must never be in the installer."""
    problems: list[str] = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(stage).as_posix()
        if relative == "payload/server.toml.example":
            pass  # the example is allowed; its content is still scanned below
        elif any(pattern.search(relative) for pattern in FORBIDDEN_NAMES):
            problems.append(f"forbidden file: {relative}")
            continue
        if path.suffix == ".whl":
            if path.name.startswith("myissuedeck-"):
                with zipfile.ZipFile(path) as archive:
                    for member in archive.namelist():
                        if any(p.search(member) for p in FORBIDDEN_NAMES):
                            problems.append(f"forbidden file {member} inside {path.name}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"secret-like text in {relative}")
                break
    return problems


# --------------------------------------------------------------------------- assembling


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stage_content(root: Path, stage: Path, wheel: Path) -> None:
    installer = root / "installer"
    for name in ("installer.py", "install.cmd", "README-INSTALL.txt"):
        shutil.copy2(installer / name, stage / name)
    payload = stage / "payload"
    payload.mkdir()
    for item in sorted((installer / "payload").iterdir()):
        if item.is_file():
            shutil.copy2(item, payload / item.name)
    shutil.copy2(root / "server.toml.example", payload / "server.toml.example")
    shutil.copy2(installer / "USERGUIDE.md", payload / "USERGUIDE.md")
    (stage / "wheelhouse" / "common").mkdir(parents=True, exist_ok=True)
    shutil.copy2(wheel, stage / "wheelhouse" / "common" / wheel.name)


def write_manifest(stage: Path, version: str, tags: list[str]) -> None:
    files = {}
    for path in sorted(stage.rglob("*")):
        if path.is_file() and path.name != "installer-manifest.json":
            files[path.relative_to(stage).as_posix()] = sha256_of(path)
    manifest = {
        "name": "myissuedeck-installer",
        "version": version,
        "platform": PLATFORM,
        "python_tags": tags,
        "files": files,
    }
    (stage / "installer-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def make_zip(stage: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in stage.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(path.relative_to(stage).as_posix(), ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def build(root: Path, out_dir: Path, *, wheel: Path | None, wheelhouse: bool) -> Path:
    if wheel is None:
        candidate = out_dir / f"myissuedeck-{project_version(root)}-py3-none-any.whl"
        wheel = candidate if candidate.exists() else build_wheel(root, out_dir)
    version = check_versions(root, wheel)
    name = f"myissuedeck-installer-{version}-win64{'' if wheelhouse else '-online'}.zip"
    with tempfile.TemporaryDirectory(prefix="installer-stage-") as scratch:
        stage = Path(scratch) / "myissuedeck-installer"
        stage.mkdir()
        stage_content(root, stage, wheel)
        tags: list[str] = []
        if wheelhouse:
            counts = download_wheelhouse(
                exported_requirements(root), stage / "wheelhouse", root / "uv.lock",
                cache=out_dir / ".wheel-cache")
            tags = sorted(counts)
            _require_windows_libraries(stage / "wheelhouse", tags)
        problems = scan_forbidden(stage)
        if problems:
            raise BuildError("the installer would contain forbidden content:\n  "
                             + "\n  ".join(problems))
        write_manifest(stage, version, tags)
        destination = out_dir / name
        make_zip(stage, destination)
    checksum = sha256_of(destination)
    (out_dir / f"{name}.sha256").write_text(f"{checksum}  {name}\n", encoding="utf-8")
    return destination


def _require_windows_libraries(wheelhouse: Path, tags: list[str]) -> None:
    """The reason the markers are evaluated here: pywin32 must be in the bundle."""
    for tag in tags:
        names = [p.name.lower() for p in (wheelhouse / tag).glob("*.whl")]
        for needed in ("pywin32", "pydantic_core"):
            if not any(n.startswith(needed) for n in names):
                raise BuildError(f"{needed} is missing from the {tag} libraries")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the standalone MyIssueDesk installer.")
    parser.add_argument("--no-wheelhouse", action="store_true",
                        help="do not bundle the libraries (the installer then needs --online)")
    parser.add_argument("--wheel", type=Path, default=None,
                        help="use this wheel instead of dist/ (it is built when missing)")
    parser.add_argument("--out", type=Path, default=None, help="output folder (default dist/)")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        out = build(root, (args.out or root / "dist").resolve(), wheel=args.wheel,
                    wheelhouse=not args.no_wheelhouse)
    except BuildError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    size = out.stat().st_size
    print(f"[ok] {out} ({size / 2**20:.1f} MB)")
    print(f"     sha256 {sha256_of(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
