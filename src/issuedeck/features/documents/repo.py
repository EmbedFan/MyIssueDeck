"""File storage of the project documents (FEA-0012).

One folder per project: ``<documents_dir>/<project_key>/`` holds one JSON file per document
(``DOC-0001.json``, ...) and ``documents.json`` with only ``next_id``. The file name comes from
the id, never from the name of the document, so any name is possible. Every file is written
atomically and always in one stable form (sorted keys, two-space indent, LF), so an export of
unchanged documents is byte-identical (IS-0010).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

REGISTRY_NAME = "documents.json"
KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DOCUMENT_ID = re.compile(r"^DOC-\d{4,}$")


def json_text(value: Any) -> str:
    """A document or the registry in its one stable form."""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def id_number(document_id: str) -> int:
    return int(document_id.split("-", 1)[1])


class DocumentStore:
    def __init__(self, documents_dir: Path, project_key: str):
        if not KEY.match(project_key):
            raise ValueError(f"unsafe project key {project_key!r}")
        self.dir = Path(documents_dir) / project_key

    @property
    def registry_path(self) -> Path:
        return self.dir / REGISTRY_NAME

    def _path(self, document_id: str) -> Path:
        if not DOCUMENT_ID.match(document_id):
            raise ValueError(f"unsafe document id {document_id!r}")
        return self.dir / f"{document_id}.json"

    def ids(self) -> list[str]:
        if not self.dir.is_dir():
            return []
        found = (path.stem for path in self.dir.glob("DOC-*.json"))
        return sorted((name for name in found if DOCUMENT_ID.match(name)), key=id_number)

    def next_id(self) -> int:
        """The next free number; never lower than any id that exists."""
        stored = 1
        if self.registry_path.is_file():
            stored = int(json.loads(self.registry_path.read_text(encoding="utf-8"))["next_id"])
        highest = max((id_number(i) for i in self.ids()), default=0)
        return max(stored, highest + 1)

    def set_next_id(self, number: int) -> None:
        self._write_atomic(self.registry_path, json_text({"next_id": number}).encode("utf-8"))

    def read(self, document_id: str) -> dict[str, Any] | None:
        path = self._path(document_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def read_bytes(self, document_id: str) -> bytes | None:
        """The file exactly as it is on disk (for an export)."""
        path = self._path(document_id)
        return path.read_bytes() if path.is_file() else None

    def write(self, document: dict[str, Any]) -> None:
        self._write_atomic(self._path(document["id"]), json_text(document).encode("utf-8"))

    def delete(self, document_id: str) -> None:
        self._path(document_id).unlink(missing_ok=True)

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
