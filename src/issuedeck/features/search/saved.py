"""Saved searches of a project (FEA-0010, phase 4).

One JSON file per project: ``<data_dir>/searches/<project_key>.json``::

    {"active":   {"name": "Open bugs" | null, "query": {...}},     # the latest search that was run
     "searches": [{"name": "Open bugs", "query": {...}, "saved_at": "..."}, ...]}

* ``active`` is saved automatically every time a search is run, under no name (the dashboard shows
  it under a default name); when it was started from a saved search, ``name`` says which.
* ``searches`` are the named ones, sorted by name. A name is unique in a project, ignoring case.
* The file is written atomically in one stable form (sorted keys, two-space indent), so the same
  content is the same bytes: the snapshot and the GitHub export carry it as ``searches.json``.

This module does not check a query against the kinds and statuses of the project: the project
configuration may change after a search was saved. A saved search is checked by ``parse_query``
when it is run (and when it is saved, by the caller).
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from issuedeck.core.errors import InvalidSearch, IssueDeckError

SEARCHES_FILE = "searches.json"  # the name inside a snapshot
MAX_SEARCHES = 50
MAX_NAME = 80
_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_locks: dict[str, threading.Lock] = {}


class SavedSearchExists(IssueDeckError):
    """Saving under a name that is taken, without permission to replace it."""

    code = "saved_search_exists"
    http_status = 409


class SavedSearchNotFound(IssueDeckError):
    code = "saved_search_not_found"
    http_status = 404


def clean_name(name: object) -> str:
    """The name as it is kept: spaces collapsed; never empty, at most ``MAX_NAME`` characters."""
    if not isinstance(name, str):
        raise InvalidSearch("name: a name is required", details={"path": "name"})
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidSearch("name: a name is required", details={"path": "name"})
    if len(cleaned) > MAX_NAME:
        raise InvalidSearch(
            f"name: at most {MAX_NAME} characters", details={"path": "name"})
    return cleaned


def json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def is_snapshot_searches_name(name: str) -> bool:
    return name == SEARCHES_FILE


def _shape_of_query(query: object) -> bool:
    return isinstance(query, dict) and isinstance(query.get("items"), list)


def normalise(raw: object) -> dict[str, Any]:
    """A stored or imported file as ``{"active": ... | None, "searches": [...]}``.

    Anything that is not of the right shape is left out instead of failing: a damaged file must
    not stop the search page.
    """
    out: dict[str, Any] = {"active": None, "searches": []}
    if not isinstance(raw, dict):
        return out
    active = raw.get("active")
    if isinstance(active, dict) and _shape_of_query(active.get("query")):
        name = active.get("name")
        out["active"] = {
            "name": name if isinstance(name, str) and name else None,
            "query": active["query"],
        }
    seen: set[str] = set()
    listed = raw.get("searches")
    for entry in listed if isinstance(listed, list) else []:
        if not isinstance(entry, dict) or not _shape_of_query(entry.get("query")):
            continue
        try:
            name = clean_name(entry.get("name"))
        except InvalidSearch:
            continue
        if name.casefold() in seen:
            continue
        seen.add(name.casefold())
        saved_at = entry.get("saved_at")
        out["searches"].append({
            "name": name, "query": entry["query"],
            "saved_at": saved_at if isinstance(saved_at, str) else "",
        })
    out["searches"].sort(key=lambda s: (s["name"].casefold(), s["name"]))
    out["searches"] = out["searches"][:MAX_SEARCHES]
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class SavedSearchStore:
    def __init__(self, data_dir: Path, project_key: str):
        if not _KEY.fullmatch(project_key):  # the key becomes a file name
            raise ValueError(f"not a valid project key: {project_key!r}")
        self.project_key = project_key
        self.path = Path(data_dir) / "searches" / f"{project_key}.json"

    # -- reading -------------------------------------------------------------------------

    def read(self) -> dict[str, Any]:
        try:
            return normalise(json.loads(self.path.read_text(encoding="utf-8")))
        except (FileNotFoundError, ValueError, OSError):
            return normalise(None)

    def get(self, name: str) -> dict[str, Any]:
        wanted = " ".join(str(name).split()).casefold()
        for entry in self.read()["searches"]:
            if entry["name"].casefold() == wanted:
                return entry
        raise SavedSearchNotFound(
            f"no saved search named {name!r}", details={"name": name})

    def is_empty(self) -> bool:
        data = self.read()
        return data["active"] is None and not data["searches"]

    def read_bytes(self) -> bytes | None:
        """The file as stored, for the snapshot; None when there is nothing to keep."""
        if self.is_empty():
            return None
        return json_text(self.read()).encode("utf-8")

    # -- writing -------------------------------------------------------------------------

    def _lock(self) -> threading.Lock:
        return _locks.setdefault(self.project_key, threading.Lock())

    def _write(self, data: dict[str, Any]) -> None:
        if data["active"] is None and not data["searches"]:
            self.path.unlink(missing_ok=True)
            self._remove_empty_dir()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json_text(data), encoding="utf-8", newline="\n")
        os.replace(temporary, self.path)

    def _remove_empty_dir(self) -> None:
        try:
            self.path.parent.rmdir()
        except OSError:
            pass  # not empty (other projects), or already gone

    def set_active(self, query: dict[str, Any], name: str | None = None) -> None:
        """Remember the latest search that was run (the automatic save)."""
        with self._lock():
            data = self.read()
            data["active"] = {"name": name, "query": query}
            self._write(data)

    def save(self, name: str, query: dict[str, Any], *, overwrite: bool = False) -> dict[str, Any]:
        cleaned = clean_name(name)
        with self._lock():
            data = self.read()
            same = [s for s in data["searches"] if s["name"].casefold() == cleaned.casefold()]
            if same and not overwrite:
                raise SavedSearchExists(
                    f"a saved search named {same[0]['name']!r} exists",
                    details={"name": same[0]["name"]})
            if not same and len(data["searches"]) >= MAX_SEARCHES:
                raise InvalidSearch(
                    f"at most {MAX_SEARCHES} saved searches in a project",
                    details={"path": "name"})
            entry = {"name": cleaned, "query": query, "saved_at": _now()}
            data["searches"] = [s for s in data["searches"] if s not in same] + [entry]
            data["active"] = {"name": cleaned, "query": query}
            self._write(normalise(data))
            return entry

    def rename(self, old: str, new: str, *, overwrite: bool = False) -> dict[str, Any]:
        cleaned = clean_name(new)
        with self._lock():
            data = self.read()
            wanted = " ".join(str(old).split()).casefold()
            entry = next((s for s in data["searches"] if s["name"].casefold() == wanted), None)
            if entry is None:
                raise SavedSearchNotFound(f"no saved search named {old!r}", details={"name": old})
            clash = [s for s in data["searches"]
                     if s is not entry and s["name"].casefold() == cleaned.casefold()]
            if clash and not overwrite:
                raise SavedSearchExists(
                    f"a saved search named {clash[0]['name']!r} exists",
                    details={"name": clash[0]["name"]})
            data["searches"] = [s for s in data["searches"] if s not in clash and s is not entry]
            entry = {**entry, "name": cleaned}
            data["searches"].append(entry)
            active = data["active"]
            if active and active["name"] and active["name"].casefold() == wanted:
                active["name"] = cleaned
            self._write(normalise(data))
            return entry

    def delete(self, name: str) -> None:
        with self._lock():
            data = self.read()
            wanted = " ".join(str(name).split()).casefold()
            kept = [s for s in data["searches"] if s["name"].casefold() != wanted]
            if len(kept) == len(data["searches"]):
                raise SavedSearchNotFound(f"no saved search named {name!r}", details={"name": name})
            data["searches"] = kept
            active = data["active"]
            if active and active["name"] and active["name"].casefold() == wanted:
                active["name"] = None  # the search stays the latest one, but has no name now
            self._write(data)

    def delete_all(self) -> None:
        with self._lock():
            self.path.unlink(missing_ok=True)
            self._remove_empty_dir()


# ---------------------------------------------------------------------------------------
# The snapshot: export is ``SavedSearchStore.read_bytes()``; import is planned, then applied
# ---------------------------------------------------------------------------------------


@dataclass
class SearchPlan:
    """What an import does with the saved searches; nothing is written while it is a plan."""

    add: list[dict[str, Any]] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)  # "name (reason)"
    active: dict[str, Any] | None = None  # taken only when the project has none yet
    warnings: list[str] = field(default_factory=list)


def check_snapshot_file(raw: object) -> None:
    """Refuse a ``searches.json`` that is not an object (the rest is cleaned by ``normalise``)."""
    if not isinstance(raw, dict):
        raise InvalidSearch("searches.json has an unexpected structure")


def plan_search_import(store: SavedSearchStore, raw: dict[str, Any] | None) -> SearchPlan:
    plan = SearchPlan()
    if raw is None:
        return plan
    incoming = normalise(raw)
    have = store.read()
    by_name = {s["name"].casefold(): s for s in have["searches"]}
    room = MAX_SEARCHES - len(have["searches"])
    for entry in incoming["searches"]:
        existing = by_name.get(entry["name"].casefold())
        if existing is None:
            if room <= 0:
                plan.skipped.append(f"{entry['name']} (the project already has {MAX_SEARCHES})")
                continue
            room -= 1
            plan.add.append(entry)
        elif existing["query"] == entry["query"]:
            plan.unchanged += 1
        else:
            plan.skipped.append(f"{entry['name']} (a different search has this name)")
    if plan.skipped:
        plan.warnings.append(
            "saved searches not imported: " + "; ".join(plan.skipped[:10]))
    if have["active"] is None and incoming["active"] is not None:
        plan.active = incoming["active"]
    return plan


def apply_search_plan(store: SavedSearchStore, plan: SearchPlan) -> Callable[[], None]:
    """Write the planned searches. Returns a function that takes the write back again."""
    if not plan.add and plan.active is None:
        return lambda: None
    before = store.path.read_bytes() if store.path.is_file() else None

    def undo() -> None:
        if before is None:
            store.delete_all()
        else:
            store.path.parent.mkdir(parents=True, exist_ok=True)
            store.path.write_bytes(before)

    try:
        with store._lock():
            data = store.read()
            data["searches"] = data["searches"] + plan.add
            if plan.active is not None:
                data["active"] = plan.active
            store._write(normalise(data))
    except BaseException:
        undo()
        raise
    return undo
