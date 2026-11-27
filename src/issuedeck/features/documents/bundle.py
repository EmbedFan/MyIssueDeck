"""Documents in project snapshots: names of the files and the import plan (FEA-0012, phase 4).

A snapshot (audit bundle ZIP, also the files of the GitHub export) carries the document store
of a project as the files it is made of, only when the project has documents:

* ``documents.json``          ``ids`` (the documents that exist) and ``next_id``, the next free
                              number. Only the listed documents are imported: a document that was
                              deleted in the project may still have a file in a repository folder,
                              because an export only adds and changes files;
* ``documents/DOC-0001.json`` ... one file per document, exactly as the store wrote it;
* ``item_documents.json``     the links between items and documents (``local_id``,
                              ``document_id``).

On import every document is checked on its own: the JSON must be valid, the id must be the one in
the file name, the name must be a clean name, the text must be text and not binary, the SHA-256 of
the text and of every kept revision must match, and at most 50 revisions may be present. A
document that fails is skipped and named in a warning; the rest of the import goes on. Documents
are matched by id: the same id with the same name and text is unchanged, the same id with other
content is skipped (the project's own document is kept), a name that another document of the
project already uses is skipped, and a free id and name is added. The file written is the
canonical form of the checked document, so a snapshot made by this software is restored byte for
byte.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from issuedeck.core.errors import InvalidDocument
from issuedeck.features.documents.repo import DOCUMENT_ID, REGISTRY_NAME, DocumentStore, id_number
from issuedeck.features.documents.service import KINDS, MAX_REVISIONS, _lock
from issuedeck.features.documents.text import check_body, clean_name

DOCUMENTS_REGISTRY_FILE = REGISTRY_NAME
ITEM_DOCUMENTS_FILE = "item_documents.json"
DOCUMENT_FILE = re.compile(r"^documents/(DOC-\d{4,})\.json$")
LISTED_PROBLEMS = 10


def is_document_file(name: str) -> bool:
    """True for ``documents/DOC-0001.json`` (not for ``documents.json``)."""
    return bool(DOCUMENT_FILE.fullmatch(name))


def is_snapshot_document_name(name: str) -> bool:
    return name in (DOCUMENTS_REGISTRY_FILE, ITEM_DOCUMENTS_FILE) or is_document_file(name)


@dataclass
class DocumentPlan:
    """What an import does with the documents; nothing is written while it is only a plan."""

    add: list[dict[str, Any]] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)  # "DOC-0002 (reason)"
    next_id: int = 1
    known_ids: set[str] = field(default_factory=set)  # ids a link may point to afterwards

    @property
    def warnings(self) -> list[str]:
        if not self.skipped:
            return []
        listed = ", ".join(self.skipped[:LISTED_PROBLEMS])
        more = len(self.skipped) - LISTED_PROBLEMS
        suffix = f" and {more} more" if more > 0 else ""
        return [f"{len(self.skipped)} document(s) were not imported: {listed}{suffix}"]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _text(value: Any) -> bool:
    """A document text that is exactly what the store would have kept."""
    if not isinstance(value, str):
        return False
    try:
        return check_body(value) == value
    except InvalidDocument:
        return False


def _checked(raw: Any, file_id: str) -> tuple[dict[str, Any] | None, str]:
    """The document in canonical shape, or (None, the reason it is refused)."""
    if not isinstance(raw, dict):
        return None, "it is not a JSON object"
    if raw.get("id") != file_id:
        return None, "its id does not match its file name"
    name = raw.get("name")
    try:
        if not isinstance(name, str) or clean_name(name) != name:
            return None, "its name is not a clean name"
    except InvalidDocument:
        return None, "its name is not a clean name"
    if raw.get("kind") not in KINDS:
        return None, "its kind is unknown"
    if not isinstance(raw.get("title"), str):
        return None, "its title is not text"
    if not _is_int(raw.get("revision")):
        return None, "its revision is not a number"
    if not _text(raw.get("body")):
        return None, "its text is not text (a binary, or not valid)"
    if raw.get("sha256") != _sha(raw["body"]):
        return None, "its text does not match its checksum"
    for key in ("created_at", "updated_at", "actor"):
        if not isinstance(raw.get(key), str):
            return None, f"its {key} is missing"
    history = raw.get("revisions")
    if not isinstance(history, list):
        return None, "its revisions are missing"
    if len(history) > MAX_REVISIONS - 1:
        return None, f"it holds more than {MAX_REVISIONS} revisions"
    kept: list[dict[str, Any]] = []
    previous = 0
    for entry in history:
        if not isinstance(entry, dict) or not _is_int(entry.get("revision")):
            return None, "a revision is malformed"
        if not (previous < entry["revision"] < raw["revision"]):
            return None, "the revisions are not in order"
        if not _text(entry.get("body")) or entry.get("sha256") != _sha(entry["body"]):
            return None, f"revision {entry['revision']} does not match its checksum"
        if not isinstance(entry.get("time"), str) or not isinstance(entry.get("actor"), str):
            return None, "a revision is malformed"
        previous = entry["revision"]
        kept.append({k: entry[k] for k in ("revision", "body", "sha256", "time", "actor")})
    document = {k: raw[k] for k in (
        "id", "name", "kind", "title", "revision", "body", "sha256",
        "created_at", "updated_at", "actor")}
    document["revisions"] = kept
    return document, ""


def plan_document_import(
    store: DocumentStore, registry_doc: dict[str, Any] | None, files: dict[str, bytes],
) -> DocumentPlan:
    """Check the documents of a snapshot against the document store of the target project."""
    plan = DocumentPlan(next_id=store.next_id())
    existing = {}
    for document_id in store.ids():
        document = store.read(document_id)
        if document is not None:
            existing[document_id] = document
    names = {document["name"]: document_id for document_id, document in existing.items()}
    listed: set[str] | None = None
    if registry_doc:
        if _is_int(registry_doc.get("next_id")):
            plan.next_id = max(plan.next_id, registry_doc["next_id"])
        if isinstance(registry_doc.get("ids"), list):
            listed = {i for i in registry_doc["ids"] if isinstance(i, str)}
            absent = sorted(
                i for i in listed
                if DOCUMENT_ID.fullmatch(i) and f"documents/{i}.json" not in files
            )
            plan.skipped.extend(f"{missing} (the file is missing)" for missing in absent)

    for file_name in sorted(files):
        match = DOCUMENT_FILE.fullmatch(file_name)
        if match is None or not DOCUMENT_ID.fullmatch(match.group(1)):
            continue
        document_id = match.group(1)
        if listed is not None and document_id not in listed:
            continue  # not in the list: a document that was deleted, its file is a leftover
        try:
            raw = json.loads(files[file_name].decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            plan.skipped.append(f"{document_id} (the file is not valid JSON)")
            continue
        document, reason = _checked(raw, document_id)
        if document is None:
            plan.skipped.append(f"{document_id} ({reason})")
            continue
        current = existing.get(document_id)
        if current is not None:
            if current["name"] == document["name"] and current["sha256"] == document["sha256"]:
                plan.unchanged += 1
                plan.known_ids.add(document_id)
            else:
                plan.skipped.append(f"{document_id} (the project has another document with "
                                    "this id)")
            continue
        owner = names.get(document["name"])
        if owner is not None:
            plan.skipped.append(f"{document_id} (the name is used by {owner})")
            continue
        names[document["name"]] = document_id
        plan.add.append(document)
        plan.known_ids.add(document_id)
        plan.next_id = max(plan.next_id, id_number(document_id) + 1)
    return plan


def apply_document_plan(
    store: DocumentStore, project_key: str, plan: DocumentPlan,
) -> Callable[[], None]:
    """Write the planned documents. Returns a function that takes the writes back again."""
    if not plan.add:
        return lambda: None

    created: list[str] = []
    before = store.registry_path.read_bytes() if store.registry_path.is_file() else None

    def undo() -> None:
        for document_id in created:
            store.delete(document_id)
        if before is None:
            store.registry_path.unlink(missing_ok=True)
            try:
                store.dir.rmdir()
            except OSError:
                pass  # not empty, or already gone
        else:
            store.registry_path.write_bytes(before)

    try:
        with _lock(project_key):
            for document in plan.add:
                store.write(document)
                created.append(document["id"])
            store.set_next_id(max(plan.next_id, store.next_id()))
    except BaseException:
        undo()
        raise
    return undo
