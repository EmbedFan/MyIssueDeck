"""Images in project snapshots: names of the files and the import plan (FEA-0013, phase 5).

A snapshot (audit bundle ZIP, also the files of the GitHub export) carries the image store of
a project as plain files, only when the project has images:

* ``images.json``      the registry of ``data/images/<project>/`` in its stable form;
* ``images/IMG-0001.svg`` ... the image files, byte for byte;
* ``item_images.json`` the links between items and images (``local_id``, ``image_id``).

On import every image is checked on its own: the file must be present, its SHA-256 and size
must match the registry, and it must pass the SVG safety check, exactly as an upload does. An
image that fails is skipped and named in a warning; the rest of the import goes on. Images are
matched by id (the Markdown of the items refers to ``image:<id>``, so ids must not change): an id
that exists with the same content is unchanged, an id that exists with other content is skipped,
a free id is added.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from issuedeck.core.errors import InvalidImage
from issuedeck.features.images.repo import REGISTRY_NAME, ImageStore
from issuedeck.features.images.service import _lock, clean_name
from issuedeck.features.images.svg_check import MIME_TYPE, validate_svg

IMAGE_REGISTRY_FILE = REGISTRY_NAME
ITEM_IMAGES_FILE = "item_images.json"
IMAGE_FILE = re.compile(r"^images/IMG-\d{4,}\.svg$")
IMAGE_ID = re.compile(r"^IMG-\d{4,}$")
OPTIONAL_FILES = (IMAGE_REGISTRY_FILE, ITEM_IMAGES_FILE)
LISTED_PROBLEMS = 10


def is_image_file(name: str) -> bool:
    """True for the optional image files of a snapshot (not the two JSON files)."""
    return bool(IMAGE_FILE.fullmatch(name))


def is_snapshot_image_name(name: str) -> bool:
    return name in OPTIONAL_FILES or is_image_file(name)


@dataclass
class ImagePlan:
    """What an import does with the images; nothing is written while it is only a plan."""

    add: list[tuple[dict[str, Any], bytes]] = field(default_factory=list)
    unchanged: int = 0
    skipped: list[str] = field(default_factory=list)  # "IMG-0002 (reason)"
    known_ids: set[str] = field(default_factory=set)  # ids a link may point to afterwards
    next_id: int = 1

    @property
    def warnings(self) -> list[str]:
        if not self.skipped:
            return []
        listed = ", ".join(self.skipped[:LISTED_PROBLEMS])
        more = len(self.skipped) - LISTED_PROBLEMS
        suffix = f" and {more} more" if more > 0 else ""
        return [f"{len(self.skipped)} image(s) were not imported: {listed}{suffix}"]


def _number(image_id: str) -> int:
    return int(image_id.split("-", 1)[1])


def plan_image_import(
    store: ImageStore, registry_doc: dict[str, Any] | None, files: dict[str, bytes],
) -> ImagePlan:
    """Check the images of a snapshot against the image store of the target project."""
    plan = ImagePlan()
    existing = store.load()
    by_id = {entry["id"]: entry for entry in existing["images"]}
    plan.next_id = int(existing["next_id"])
    plan.known_ids = set(by_id)
    if not registry_doc:
        return plan

    entries = registry_doc.get("images")
    if not isinstance(entries, list):
        plan.skipped.append("images.json (the list of images is missing)")
        return plan
    try:
        plan.next_id = max(plan.next_id, int(registry_doc.get("next_id") or 1))
    except (TypeError, ValueError):
        pass

    seen: set[str] = set()
    for raw in entries:
        image_id = raw.get("id") if isinstance(raw, dict) else None
        if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
            plan.skipped.append("an entry without a valid id")
            continue
        if image_id in seen:
            plan.skipped.append(f"{image_id} (listed twice)")
            continue
        seen.add(image_id)
        data = files.get(f"images/{image_id}.svg")
        if data is None:
            plan.skipped.append(f"{image_id} (the file is missing)")
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest != raw.get("sha256") or len(data) != raw.get("size"):
            plan.skipped.append(f"{image_id} (the file does not match its checksum)")
            continue
        try:
            validate_svg(data)
        except InvalidImage as exc:
            plan.skipped.append(f"{image_id} ({exc.message})")
            continue
        current = by_id.get(image_id)
        if current is not None:
            if current["sha256"] == digest:
                plan.unchanged += 1
            else:
                plan.skipped.append(f"{image_id} (the project has another image with this id)")
            continue
        entry = {
            "id": image_id,
            "name": clean_name(raw.get("name") if isinstance(raw.get("name"), str) else None),
            "stored": f"{image_id}.svg",
            "mime": MIME_TYPE,
            "size": len(data),
            "sha256": digest,
            "uploaded_at": str(raw.get("uploaded_at") or ""),
            "actor": str(raw.get("actor") or "import"),
        }
        plan.add.append((entry, data))
        plan.known_ids.add(image_id)
        plan.next_id = max(plan.next_id, _number(image_id) + 1)
    return plan


def apply_image_plan(store: ImageStore, project_key: str, plan: ImagePlan) -> Callable[[], None]:
    """Write the planned images. Returns a function that takes the writes back again."""
    if not plan.add:
        return lambda: None

    created: list[str] = []
    before = store.registry_path.read_bytes() if store.registry_path.is_file() else None

    def undo() -> None:
        for stored in created:
            store.delete_file(stored)
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
            for entry, data in plan.add:
                store.write_file(entry["stored"], data)
                created.append(entry["stored"])
            registry = store.load()
            registry["images"] = [*registry["images"], *(entry for entry, _ in plan.add)]
            registry["next_id"] = max(int(registry["next_id"]), plan.next_id)
            store.save(registry)
    except BaseException:
        undo()
        raise
    return undo
