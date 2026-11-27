"""Business rules of the project document store (FEA-0012, phase 1)."""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import (
    DocumentConflict,
    DocumentExists,
    DocumentNotFound,
    InvalidDocument,
)
from issuedeck.features.documents.repo import DOCUMENT_ID, DocumentStore
from issuedeck.features.documents.text import check_body, clean_name

KINDS = ("prompt", "description", "request", "report", "other")
#: Revisions kept per document, the current one included: the oldest are dropped.
MAX_REVISIONS = 50

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(project_key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(project_key, threading.Lock())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def _kind(kind: str | None) -> str | None:
    if kind is not None and kind not in KINDS:
        raise InvalidDocument(f"the kind must be one of: {', '.join(KINDS)}",
                              details={"reason": "kind", "kinds": list(KINDS)})
    return kind


def summary(document: dict[str, Any]) -> dict[str, Any]:
    """The document without its text and history."""
    return {
        "id": document["id"], "name": document["name"], "kind": document["kind"],
        "title": document["title"], "revision": document["revision"],
        "sha256": document["sha256"], "size": _size(document["body"]),
        "created_at": document["created_at"], "updated_at": document["updated_at"],
        "actor": document["actor"],
    }


def detail(document: dict[str, Any]) -> dict[str, Any]:
    return {**summary(document), "body": document["body"]}


class DocumentService:
    def __init__(self, documents_dir: Path, registry: ConfigRegistry):
        self._dir = Path(documents_dir)
        self._registry = registry

    def _store(self, project_key: str) -> DocumentStore:
        self._registry.project(project_key)  # raises ProjectNotFound
        return DocumentStore(self._dir, project_key)

    @staticmethod
    def _not_found(project_key: str, document_id: str) -> DocumentNotFound:
        return DocumentNotFound(
            f"document {document_id} not found in project {project_key}",
            details={"project_key": project_key, "document_id": document_id},
        )

    def _load(self, store: DocumentStore, project_key: str, document_id: str) -> dict[str, Any]:
        document = store.read(document_id) if DOCUMENT_ID.match(document_id) else None
        if document is None:
            raise self._not_found(project_key, document_id)
        return document

    @staticmethod
    def _new_revision(document: dict[str, Any], body: str, actor: str) -> None:
        """Make ``body`` the current text; the text it replaces goes to the history."""
        history = [*document["revisions"], {
            "revision": document["revision"], "body": document["body"],
            "sha256": document["sha256"], "time": document["updated_at"],
            "actor": document["actor"],
        }]
        document["revisions"] = history[-(MAX_REVISIONS - 1):]
        document["revision"] += 1
        document["body"] = body
        document["sha256"] = _sha(body)
        document["updated_at"] = _now()
        document["actor"] = actor

    # ------------------------------------------------------------------ create and read

    def create(self, project_key: str, name: str, body: str, *, kind: str = "other",
               title: str = "", replace: bool = False, actor: str = "api") -> dict[str, Any]:
        """A new document; a name that is used gives DocumentExists, or with ``replace`` a
        new revision of that document."""
        store = self._store(project_key)
        name = clean_name(name)
        body = check_body(body)
        kind = _kind(kind) or "other"
        with _lock(project_key):
            for document_id in store.ids():
                current = store.read(document_id)
                if current is None or current["name"] != name:
                    continue
                if not replace:
                    raise DocumentExists(
                        f"a document named '{name}' already exists as {document_id}",
                        details={"existing_id": document_id, "name": name},
                    )
                if body != current["body"]:
                    self._new_revision(current, body, actor)
                current["kind"] = kind if kind != "other" else current["kind"]
                current["title"] = title or current["title"]
                store.write(current)
                return current
            number = store.next_id()
            store.set_next_id(number + 1)  # first, so a crash never lets an id be used twice
            now = _now()
            document = {
                "id": f"DOC-{number:04d}", "name": name, "kind": kind, "title": title,
                "revision": 1, "body": body, "sha256": _sha(body),
                "created_at": now, "updated_at": now, "actor": actor, "revisions": [],
            }
            store.write(document)
        return document

    def list(self, project_key: str, *, kind: str | None = None,
             name: str | None = None) -> list[dict[str, Any]]:
        store = self._store(project_key)
        found = []
        for document_id in store.ids():
            document = store.read(document_id)
            if document is None:
                continue
            if kind is not None and document["kind"] != kind:
                continue
            if name is not None and document["name"] != name:
                continue
            found.append(summary(document))
        return found

    def get(self, project_key: str, document_id: str) -> dict[str, Any]:
        return self._load(self._store(project_key), project_key, document_id)

    # ------------------------------------------------------------------ change

    def replace(self, project_key: str, document_id: str, body: str, *, revision: int,
                title: str | None = None, kind: str | None = None,
                actor: str = "api") -> dict[str, Any]:
        """Replace the text; ``revision`` must be the one the caller read, else 409."""
        store = self._store(project_key)
        body = check_body(body)
        kind = _kind(kind)
        with _lock(project_key):
            document = self._load(store, project_key, document_id)
            self._check_revision(document, revision)
            if body != document["body"]:
                self._new_revision(document, body, actor)
            if title is not None:
                document["title"] = title
            if kind is not None:
                document["kind"] = kind
            store.write(document)
        return document

    def append(self, project_key: str, document_id: str, text: str,
               actor: str = "api") -> dict[str, Any]:
        """Add text at the end; no revision is needed, so agents can add notes at any time."""
        store = self._store(project_key)
        text = check_body(text)
        with _lock(project_key):
            document = self._load(store, project_key, document_id)
            body = document["body"]
            glue = "\n" if body and not body.endswith("\n") and not text.startswith("\n") else ""
            self._new_revision(document, body + glue + text, actor)
            store.write(document)
        return document

    def delete(self, project_key: str, document_id: str) -> None:
        store = self._store(project_key)
        with _lock(project_key):
            self._load(store, project_key, document_id)
            store.delete(document_id)

    @staticmethod
    def _check_revision(document: dict[str, Any], revision: int) -> None:
        if revision != document["revision"]:
            raise DocumentConflict(
                f"{document['id']} is at revision {document['revision']}, not {revision}; "
                "read it again before changing it",
                details={"document_id": document["id"],
                         "current_revision": document["revision"]},
            )

    # ------------------------------------------------------------------ revisions

    def revisions(self, project_key: str, document_id: str) -> list[dict[str, Any]]:
        """The kept revisions, newest first (the current one included)."""
        document = self.get(project_key, document_id)
        rows = [{
            "revision": document["revision"], "sha256": document["sha256"],
            "size": _size(document["body"]), "time": document["updated_at"],
            "actor": document["actor"], "current": True,
        }]
        for old in reversed(document["revisions"]):
            rows.append({
                "revision": old["revision"], "sha256": old["sha256"],
                "size": _size(old["body"]), "time": old["time"], "actor": old["actor"],
                "current": False,
            })
        return rows

    def revision(self, project_key: str, document_id: str, number: int) -> dict[str, Any]:
        document = self.get(project_key, document_id)
        if number == document["revision"]:
            return {"revision": number, "sha256": document["sha256"],
                    "size": _size(document["body"]), "time": document["updated_at"],
                    "actor": document["actor"], "current": True, "body": document["body"]}
        for old in document["revisions"]:
            if old["revision"] == number:
                return {"revision": number, "sha256": old["sha256"],
                        "size": _size(old["body"]), "time": old["time"],
                        "actor": old["actor"], "current": False, "body": old["body"]}
        raise DocumentNotFound(
            f"revision {number} of {document_id} is not kept (the last {MAX_REVISIONS} are)",
            details={"document_id": document_id, "revision": number},
        )

    def restore(self, project_key: str, document_id: str, number: int,
                actor: str = "api") -> dict[str, Any]:
        """Make the text of an older revision the current one, as a new revision."""
        store = self._store(project_key)
        with _lock(project_key):
            document = self._load(store, project_key, document_id)
            wanted = self.revision(project_key, document_id, number)["body"]
            if wanted != document["body"]:
                self._new_revision(document, wanted, actor)
                store.write(document)
        return document
