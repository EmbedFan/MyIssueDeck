"""Business rules of the project image store (FEA-0013, phase 1: SVG only)."""

from __future__ import annotations

import hashlib
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from issuedeck.core.config import ConfigRegistry, ImagesConfig
from issuedeck.core.errors import ImageDuplicate, ImageNotFound, ImageTooLarge
from issuedeck.features.images.repo import ImageStore
from issuedeck.features.images.svg_check import MIME_TYPE, validate_svg

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
NAME_LIMIT = 120


def _lock(project_key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(project_key, threading.Lock())


def clean_name(name: str | None) -> str:
    """The original file name as metadata only: no folders, no control characters."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = _CONTROL.sub("", base).strip()
    return base[:NAME_LIMIT] or "image.svg"


def _not_found(project_key: str, image_id: str) -> ImageNotFound:
    return ImageNotFound(
        f"image {image_id} not found in project {project_key}",
        details={"project_key": project_key, "image_id": image_id},
    )


class ImageService:
    def __init__(self, images_dir: Path, config: ImagesConfig, registry: ConfigRegistry):
        self._dir = Path(images_dir)
        self._config = config
        self._registry = registry

    def _store(self, project_key: str) -> ImageStore:
        self._registry.project(project_key)  # raises ProjectNotFound
        return ImageStore(self._dir, project_key)

    def upload(self, project_key: str, filename: str | None, data: bytes,
               actor: str = "api") -> dict[str, Any]:
        store = self._store(project_key)
        if len(data) > self._config.max_file_bytes:
            raise ImageTooLarge(
                f"the file is larger than {self._config.max_file_bytes} bytes",
                details={"max_file_bytes": self._config.max_file_bytes},
            )
        validate_svg(data)
        digest = hashlib.sha256(data).hexdigest()
        with _lock(project_key):
            registry = store.load()
            for entry in registry["images"]:
                if entry["sha256"] == digest:
                    raise ImageDuplicate(
                        f"the same image is already stored as {entry['id']}",
                        details={"existing_id": entry["id"]},
                    )
            used = sum(entry["size"] for entry in registry["images"])
            if used + len(data) > self._config.max_project_bytes:
                raise ImageTooLarge(
                    "the project image store would exceed "
                    f"{self._config.max_project_bytes} bytes",
                    details={"max_project_bytes": self._config.max_project_bytes,
                             "used_bytes": used},
                )
            number = int(registry["next_id"])  # never reused, so image:<id> stays unique
            image_id = f"IMG-{number:04d}"
            entry = {
                "id": image_id,
                "name": clean_name(filename),
                "stored": f"{image_id}.svg",
                "mime": MIME_TYPE,
                "size": len(data),
                "sha256": digest,
                "uploaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "actor": actor,
            }
            store.write_file(entry["stored"], data)
            registry["images"].append(entry)
            registry["next_id"] = number + 1
            store.save(registry)
        return entry

    def list(self, project_key: str) -> dict[str, Any]:
        registry = self._store(project_key).load()
        images = sorted(registry["images"], key=lambda entry: entry["id"])
        return {"items": images, "total_bytes": sum(entry["size"] for entry in images)}

    def get(self, project_key: str, image_id: str) -> dict[str, Any]:
        for entry in self._store(project_key).load()["images"]:
            if entry["id"] == image_id:
                return entry
        raise _not_found(project_key, image_id)

    def content(self, project_key: str, image_id: str) -> tuple[dict[str, Any], bytes]:
        entry = self.get(project_key, image_id)
        try:
            return entry, self._store(project_key).read_file(entry["stored"])
        except FileNotFoundError as exc:
            raise _not_found(project_key, image_id) from exc

    def delete(self, project_key: str, image_id: str) -> None:
        store = self._store(project_key)
        with _lock(project_key):
            registry = store.load()
            removed = next((e for e in registry["images"] if e["id"] == image_id), None)
            if removed is None:
                raise _not_found(project_key, image_id)
            registry["images"] = [e for e in registry["images"] if e["id"] != image_id]
            store.save(registry)
            store.delete_file(removed["stored"])
