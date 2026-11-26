"""File storage and registry of the project images (FEA-0013).

One folder per project: ``<images_dir>/<project_key>/`` holds ``IMG-0001.svg`` ... and the
registry ``images.json``. The registry is written atomically and always in the same form
(sorted keys, two-space indent, LF), so an export of an unchanged store is byte-identical.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

REGISTRY_NAME = "images.json"
KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
STORED = re.compile(r"^IMG-\d{4,}\.svg$")


def registry_text(registry: dict[str, Any]) -> str:
    """The registry in its one stable form: sorted images and keys, two-space indent, LF."""
    ordered = {**registry, "images": sorted(registry["images"], key=lambda entry: entry["id"])}
    return json.dumps(ordered, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


class ImageStore:
    def __init__(self, images_dir: Path, project_key: str):
        if not KEY.match(project_key):
            raise ValueError(f"unsafe project key {project_key!r}")
        self.dir = Path(images_dir) / project_key

    @property
    def registry_path(self) -> Path:
        return self.dir / REGISTRY_NAME

    def load(self) -> dict[str, Any]:
        if not self.registry_path.is_file():
            return {"next_id": 1, "images": []}
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        data.setdefault("next_id", 1)
        data.setdefault("images", [])
        return data

    def save(self, registry: dict[str, Any]) -> None:
        registry["images"] = sorted(registry["images"], key=lambda entry: entry["id"])
        text = json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        self._write_atomic(self.registry_path, text.encode("utf-8"))

    def write_file(self, stored: str, data: bytes) -> None:
        self._write_atomic(self._path(stored), data)

    def read_file(self, stored: str) -> bytes:
        return self._path(stored).read_bytes()

    def delete_file(self, stored: str) -> None:
        self._path(stored).unlink(missing_ok=True)

    def _path(self, stored: str) -> Path:
        if not STORED.match(stored):
            raise ValueError(f"unsafe stored name {stored!r}")
        return self.dir / stored

    def _write_atomic(self, path: Path, data: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
