"""Import of audit-bundle snapshots into a new or an existing project (FEA-0007).

A snapshot is the ZIP written by ``export_audit_bundle``. This module reads it back:

* **create** mode builds a new project (config file, items, relationships, work sessions,
  import history) and keeps the item ids of the snapshot;
* **update** mode adds what an existing project lacks and, depending on the conflict policy,
  replaces items that exist in both.

The import is all or nothing: it runs in one database transaction, and a preview runs the same
code and rolls it back, so the preview counts are exact. The ZIP is never extracted; only the
known file names are read, with a size limit.
"""

from __future__ import annotations

import json
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from issuedeck.core import events as live_events
from issuedeck.core.config import ConfigRegistry, ProjectConfig, load_project_config
from issuedeck.core.errors import ProjectNotFound, SnapshotConflict, SnapshotInvalid
from issuedeck.features.items.models import (
    ImportBatch,
    Item,
    ItemApplyTo,
    ItemEvent,
    ItemExternalLink,
    ItemRelationship,
    ItemTag,
    ShipCommit,
    ShipRecord,
    WorkSession,
    WorkSessionUpdate,
)

BUNDLE_FORMAT = "issuedeck.audit_bundle.v1"
PROJECT_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,62}$")
MODES = ("create", "update")
CONFLICT_POLICIES = ("keep", "newer", "overwrite")
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024

_REQUIRED = (
    "manifest.json",
    "project.json",
    "items.json",
    "relationships.json",
    "work_sessions.json",
    "import_batches.json",
)
_ALLOWED = (*_REQUIRED, "project.toml")
_MAX_LISTED_PROBLEMS = 10


@dataclass
class Snapshot:
    manifest: dict[str, Any]
    project: dict[str, Any]
    project_toml: str | None
    items: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    work_sessions: list[dict[str, Any]]
    import_batches: list[dict[str, Any]]

    @property
    def project_key(self) -> str:
        return str(self.manifest["project_key"])


@dataclass
class ImportReport:
    mode: str
    project_key: str
    source_project_key: str
    conflict: str
    applied: bool = False
    items_created: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    events_added: int = 0
    relationships_added: int = 0
    work_sessions_added: int = 0
    import_batches_added: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_snapshot(path: Path) -> Snapshot:
    """Read and check a snapshot ZIP. Raises SnapshotInvalid; touches nothing on disk."""
    try:
        bundle = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise SnapshotInvalid("the file is not a readable ZIP snapshot") from exc

    with bundle:
        infos = {info.filename: info for info in bundle.infolist()}
        unexpected = sorted(set(infos) - set(_ALLOWED))
        if unexpected:
            raise SnapshotInvalid(
                "the snapshot contains unexpected files: " + ", ".join(unexpected[:5]),
            )
        missing = [name for name in _REQUIRED if name not in infos]
        if missing:
            raise SnapshotInvalid("the snapshot lacks: " + ", ".join(missing))
        if sum(info.file_size for info in infos.values()) > MAX_UNCOMPRESSED_BYTES:
            raise SnapshotInvalid("the snapshot is larger than the allowed size")

        def raw(name: str) -> bytes:
            with bundle.open(name) as handle:
                data = handle.read(MAX_UNCOMPRESSED_BYTES + 1)
            if len(data) > MAX_UNCOMPRESSED_BYTES:
                raise SnapshotInvalid(f"{name} is larger than the allowed size")
            return data

        def load(name: str, kind: type) -> Any:
            try:
                value = json.loads(raw(name).decode("utf-8"))
            except ValueError as exc:
                raise SnapshotInvalid(f"{name} is not valid JSON") from exc
            if not isinstance(value, kind):
                raise SnapshotInvalid(f"{name} has an unexpected structure")
            return value

        manifest = load("manifest.json", dict)
        if manifest.get("format") != BUNDLE_FORMAT:
            raise SnapshotInvalid(
                f"unsupported snapshot format '{manifest.get('format')}'",
                details={"expected": BUNDLE_FORMAT},
            )
        key = manifest.get("project_key")
        if not isinstance(key, str) or not PROJECT_KEY_RE.fullmatch(key):
            raise SnapshotInvalid("the snapshot has no valid project key")

        project_toml = None
        if "project.toml" in infos:
            try:
                project_toml = raw("project.toml").decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise SnapshotInvalid("project.toml is not valid text") from exc

        snapshot = Snapshot(
            manifest=manifest,
            project=load("project.json", dict),
            project_toml=project_toml,
            items=load("items.json", list),
            relationships=load("relationships.json", list),
            work_sessions=load("work_sessions.json", list),
            import_batches=load("import_batches.json", list),
        )

    counts = manifest.get("counts") or {}
    for name, rows in (
        ("items", snapshot.items),
        ("relationships", snapshot.relationships),
        ("work_sessions", snapshot.work_sessions),
        ("import_batches", snapshot.import_batches),
    ):
        if counts.get(name, len(rows)) != len(rows):
            raise SnapshotInvalid(f"the manifest count for {name} does not match the file")
    _check_shapes(snapshot)
    return snapshot


def _check_shapes(snapshot: Snapshot) -> None:
    problems: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(snapshot.items):
        if not isinstance(item, dict):
            problems.append(f"item #{index + 1} is not an object")
            continue
        for name in ("local_id", "kind", "status", "title", "created_at", "updated_at"):
            if not isinstance(item.get(name), str) or not item.get(name):
                problems.append(f"item #{index + 1} lacks '{name}'")
        local_id = item.get("local_id")
        if isinstance(local_id, str):
            if local_id in seen:
                problems.append(f"item id {local_id} appears twice")
            seen.add(local_id)
    for name, rows in (
        ("relationships", snapshot.relationships),
        ("work_sessions", snapshot.work_sessions),
        ("import_batches", snapshot.import_batches),
    ):
        if any(not isinstance(row, dict) for row in rows):
            problems.append(f"{name} contains an entry that is not an object")
    if problems:
        raise SnapshotInvalid(
            "the snapshot is malformed: " + "; ".join(problems[:_MAX_LISTED_PROBLEMS]),
            details={"problems": problems[:_MAX_LISTED_PROBLEMS]},
        )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

async def import_snapshot(
    *,
    session: AsyncSession,
    registry: ConfigRegistry,
    bundle_path: Path,
    mode: str,
    project_key: str | None = None,
    conflict: str = "keep",
    apply: bool = False,
) -> ImportReport:
    """Import a snapshot. With ``apply=False`` nothing is written (exact preview)."""
    if mode not in MODES:
        raise SnapshotInvalid(f"mode must be one of {', '.join(MODES)}")
    if conflict not in CONFLICT_POLICIES:
        raise SnapshotInvalid(f"conflict policy must be one of {', '.join(CONFLICT_POLICIES)}")

    snapshot = read_snapshot(bundle_path)
    target = project_key or snapshot.project_key
    if not PROJECT_KEY_RE.fullmatch(target):
        raise SnapshotInvalid(f"'{target}' is not a valid project key")

    config_path = registry.server.projects_dir / f"{target}.toml"
    existing_keys = {project.key for project in registry.all_projects()}
    config_text: str | None = None

    if mode == "create":
        if target in existing_keys or config_path.exists():
            raise SnapshotConflict(
                f"project '{target}' already exists; choose another key or use update mode",
                details={"project_key": target},
            )
        config_text = _config_text_for(snapshot, target)
        config = _parse_config(config_text, target)
    else:
        if target not in existing_keys:
            raise ProjectNotFound(
                f"project '{target}' not found", details={"project_key": target},
            )
        config = registry.project(target)

    _check_items_against_config(snapshot.items, config)

    report = ImportReport(
        mode=mode, project_key=target, source_project_key=snapshot.project_key,
        conflict=conflict,
    )

    wrote_config = False
    try:
        if mode == "create" and apply:
            assert config_text is not None
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(config_text, encoding="utf-8")
            wrote_config = True
            registry.register_project(load_project_config(config_path))
        await _write_rows(session, snapshot, target, mode, conflict, report)
        if apply:
            await session.commit()
            report.applied = True
        else:
            await session.rollback()
    except BaseException:
        await session.rollback()
        if wrote_config:
            try:
                registry.unregister_project(target)
            except Exception:  # pragma: no cover - defensive
                pass
            config_path.unlink(missing_ok=True)
        raise

    if report.applied:
        live_events.publish("project.changed", target)
    return report


def _config_text_for(snapshot: Snapshot, target: str) -> str:
    if snapshot.project_toml is None:
        raise SnapshotInvalid(
            "the snapshot has no project.toml, so a project cannot be created from it; "
            "use update mode for an existing project",
        )
    text = snapshot.project_toml
    if target != snapshot.project_key:
        text, count = re.subn(
            r'(?m)^key\s*=\s*(".*?"|\'.*?\')\s*$', f'key = "{target}"', text, count=1,
        )
        if count != 1:
            raise SnapshotInvalid("project.toml has no top-level key line to change")
    return text


def _parse_config(text: str, target: str) -> ProjectConfig:
    try:
        config = ProjectConfig.model_validate(tomllib.loads(text))
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        raise SnapshotInvalid(
            f"the project configuration in the snapshot is invalid: {exc}",
        ) from exc
    if config.key != target:
        raise SnapshotInvalid(
            f"project.toml declares key '{config.key}', not '{target}'",
        )
    return config


def _check_items_against_config(items: list[dict[str, Any]], config: ProjectConfig) -> None:
    branches = {branch.key for branch in config.branches}
    problems: list[str] = []
    for item in items:
        local_id = item["local_id"]
        if item["kind"] not in config.kinds:
            problems.append(f"{local_id}: unknown kind '{item['kind']}'")
        if item["status"] not in config.statuses:
            problems.append(f"{local_id}: unknown status '{item['status']}'")
        for branch in item.get("applies_to") or []:
            if branch not in branches:
                problems.append(f"{local_id}: unknown branch '{branch}'")
        for record in item.get("ship_records") or []:
            if not isinstance(record, dict) or record.get("branch_key") not in branches:
                problems.append(f"{local_id}: ship record for an unknown branch")
    if problems:
        shown = problems[:_MAX_LISTED_PROBLEMS]
        extra = len(problems) - len(shown)
        message = (
            f"the snapshot does not fit project '{config.key}': " + "; ".join(shown)
            + (f" (and {extra} more)" if extra else "")
        )
        raise SnapshotInvalid(message, details={"problems": problems})


async def _write_rows(
    session: AsyncSession,
    snapshot: Snapshot,
    target: str,
    mode: str,
    conflict: str,
    report: ImportReport,
) -> None:
    existing = {
        item.local_id: item
        for item in (await session.execute(
            select(Item)
            .where(Item.project_key == target)
            .options(
                selectinload(Item.tags),
                selectinload(Item.applies_to),
                selectinload(Item.external_links),
                selectinload(Item.events),
                selectinload(Item.ship_records).selectinload(ShipRecord.commits),
            )
        )).scalars().all()
    }
    if mode == "create" and existing:
        raise SnapshotConflict(
            f"the database already holds items for '{target}'",
            details={"project_key": target},
        )

    by_local: dict[str, Item] = dict(existing)

    for data in snapshot.items:
        current = existing.get(data["local_id"])
        if current is None:
            item = _new_item(target, data)
            session.add(item)
            by_local[data["local_id"]] = item
            report.items_created += 1
            report.events_added += len(data.get("events") or [])
            continue
        if not _snapshot_wins(conflict, data, current):
            report.items_unchanged += 1
            continue
        await _overwrite_item(session, current, data, report)
        report.items_updated += 1
    await session.flush()

    pk_by_local = {local_id: item.pk for local_id, item in by_local.items()}
    await _add_relationships(session, snapshot, pk_by_local, report)
    await _add_work_sessions(session, snapshot, target, pk_by_local, report)
    await _add_import_batches(session, snapshot, target, report)
    await session.flush()


def _snapshot_wins(conflict: str, data: dict[str, Any], current: Item) -> bool:
    if conflict == "overwrite":
        return True
    if conflict == "newer":
        return str(data["updated_at"]) > str(current.updated_at)
    return False


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _new_item(project_key: str, data: dict[str, Any]) -> Item:
    item = Item(
        project_key=project_key,
        local_id=data["local_id"],
        kind=data["kind"],
        status=data["status"],
        title=data["title"],
        body=data.get("body") or "",
        custom_fields_json=_json(data.get("custom_fields")),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        deleted_at=data.get("deleted_at"),
    )
    item.tags = [ItemTag(tag=tag) for tag in sorted(set(data.get("tags") or []))]
    item.applies_to = [
        ItemApplyTo(branch_key=branch) for branch in sorted(set(data.get("applies_to") or []))
    ]
    item.external_links = [_new_link(link) for link in data.get("external_links") or []]
    item.ship_records = [_new_ship_record(record) for record in data.get("ship_records") or []]
    item.events = [_new_event(event) for event in _sorted_events(data)]
    return item


def _sorted_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (event for event in data.get("events") or [] if isinstance(event, dict)),
        key=lambda event: (str(event.get("created_at", "")), event.get("id") or 0),
    )


def _new_link(link: dict[str, Any]) -> ItemExternalLink:
    return ItemExternalLink(
        link_type=link.get("link_type") or "other",
        label=link.get("label"),
        url=link["url"],
        created_at=link.get("created_at") or "",
    )


def _new_ship_record(record: dict[str, Any]) -> ShipRecord:
    ship = ShipRecord(
        branch_key=record["branch_key"],
        version=record.get("version") or "",
        shipped_at=record.get("shipped_at") or "",
    )
    ship.commits = [
        ShipCommit(sha=sha, position=position)
        for position, sha in enumerate(record.get("commits") or [])
    ]
    return ship


def _new_event(event: dict[str, Any]) -> ItemEvent:
    return ItemEvent(
        event_type=event.get("event_type") or "comment",
        actor_type=event.get("actor_type") or "system",
        actor_name=event.get("actor_name") or "",
        body=event.get("body") or "",
        metadata_json=_json(event.get("metadata")),
        created_at=event.get("created_at") or "",
    )


def _event_key(event_type: str, actor_type: str, actor_name: str, body: str, created_at: str):
    return (event_type, actor_type, actor_name, body, created_at)


async def _overwrite_item(
    session: AsyncSession, item: Item, data: dict[str, Any], report: ImportReport,
) -> None:
    item.kind = data["kind"]
    item.status = data["status"]
    item.title = data["title"]
    item.body = data.get("body") or ""
    item.custom_fields_json = _json(data.get("custom_fields"))
    item.updated_at = data["updated_at"]
    item.deleted_at = data.get("deleted_at")

    wanted_tags = set(data.get("tags") or [])
    for tag in [t for t in item.tags if t.tag not in wanted_tags]:
        item.tags.remove(tag)
    have_tags = {t.tag for t in item.tags}
    item.tags.extend(ItemTag(tag=tag) for tag in sorted(wanted_tags - have_tags))

    wanted_branches = set(data.get("applies_to") or [])
    for branch in [b for b in item.applies_to if b.branch_key not in wanted_branches]:
        item.applies_to.remove(branch)
    have_branches = {b.branch_key for b in item.applies_to}
    item.applies_to.extend(
        ItemApplyTo(branch_key=key) for key in sorted(wanted_branches - have_branches)
    )

    # Links and ship records get new rows; the old ones must be gone before the new insert
    # (a ship record is unique per item and branch).
    item.external_links.clear()
    item.ship_records.clear()
    await session.flush()
    item.external_links.extend(_new_link(link) for link in data.get("external_links") or [])
    item.ship_records.extend(
        _new_ship_record(record) for record in data.get("ship_records") or []
    )

    present = {
        _event_key(e.event_type, e.actor_type, e.actor_name, e.body, e.created_at)
        for e in item.events
    }
    for event in _sorted_events(data):
        new_event = _new_event(event)
        key = _event_key(
            new_event.event_type, new_event.actor_type, new_event.actor_name,
            new_event.body, new_event.created_at,
        )
        if key not in present:
            item.events.append(new_event)
            present.add(key)
            report.events_added += 1


async def _add_relationships(
    session: AsyncSession,
    snapshot: Snapshot,
    pk_by_local: dict[str, int],
    report: ImportReport,
) -> None:
    pks = list(pk_by_local.values())
    present: set[tuple[int, int, str]] = set()
    if pks:
        present = {
            (row.from_item_pk, row.to_item_pk, row.relation_type)
            for row in (await session.execute(
                select(ItemRelationship).where(ItemRelationship.from_item_pk.in_(pks))
            )).scalars()
        }
    skipped = 0
    for row in snapshot.relationships:
        source = pk_by_local.get(str(row.get("from_local_id")))
        destination = pk_by_local.get(str(row.get("to_local_id")))
        relation_type = row.get("relation_type")
        if source is None or destination is None or not relation_type:
            skipped += 1
            continue
        key = (source, destination, str(relation_type))
        if key in present:
            continue
        session.add(ItemRelationship(
            from_item_pk=source, to_item_pk=destination, relation_type=str(relation_type),
            created_at=row.get("created_at") or "",
        ))
        present.add(key)
        report.relationships_added += 1
    if skipped:
        report.warnings.append(
            f"{skipped} relationship(s) were skipped because an item is not in the project",
        )


async def _add_work_sessions(
    session: AsyncSession,
    snapshot: Snapshot,
    target: str,
    pk_by_local: dict[str, int],
    report: ImportReport,
) -> None:
    present = {
        (row.item_pk, row.agent_name, row.started_at)
        for row in (await session.execute(
            select(WorkSession).where(WorkSession.project_key == target)
        )).scalars()
    }
    for row in snapshot.work_sessions:
        local_id = row.get("local_id")
        item_pk = pk_by_local.get(str(local_id)) if local_id else None
        if local_id and item_pk is None:
            report.warnings.append(
                f"a work session for {local_id} was skipped because the item is not in the project",
            )
            continue
        key = (item_pk, row.get("agent_name") or "", row.get("started_at") or "")
        if key in present:
            continue
        work = WorkSession(
            project_key=target,
            item_pk=item_pk,
            agent_name=row.get("agent_name") or "",
            status=row.get("status") or "completed",
            goal=row.get("goal") or "",
            summary=row.get("summary") or "",
            branch=row.get("branch"),
            started_at=row.get("started_at") or "",
            updated_at=row.get("updated_at") or row.get("started_at") or "",
            ended_at=row.get("ended_at"),
            metadata_json=_json(row.get("metadata")),
        )
        work.updates = [
            WorkSessionUpdate(
                update_type=update.get("update_type") or "progress",
                message=update.get("message") or "",
                metadata_json=_json(update.get("metadata")),
                created_at=update.get("created_at") or "",
            )
            for update in sorted(
                (u for u in row.get("updates") or [] if isinstance(u, dict)),
                key=lambda u: (str(u.get("created_at", "")), u.get("id") or 0),
            )
        ]
        session.add(work)
        present.add(key)
        report.work_sessions_added += 1


async def _add_import_batches(
    session: AsyncSession, snapshot: Snapshot, target: str, report: ImportReport,
) -> None:
    present = {
        (row.batch_tag, row.source_type, row.created_at)
        for row in (await session.execute(
            select(ImportBatch).where(ImportBatch.project_key == target)
        )).scalars()
    }
    for row in snapshot.import_batches:
        key = (
            row.get("batch_tag") or "",
            row.get("source_type") or "",
            row.get("created_at") or "",
        )
        if key in present:
            continue
        session.add(ImportBatch(
            project_key=target,
            batch_tag=key[0],
            source_type=key[1],
            source_name=row.get("source_name") or "",
            items_planned=int(row.get("items_planned") or 0),
            items_written=int(row.get("items_written") or 0),
            skipped_count=int(row.get("skipped_count") or 0),
            status_mapped=int(row.get("status_mapped") or 0),
            external_links=int(row.get("external_links") or 0),
            created_at=key[2],
            metadata_json=_json(row.get("metadata")),
        ))
        present.add(key)
        report.import_batches_added += 1

