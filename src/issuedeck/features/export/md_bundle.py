"""Project export helpers."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from issuedeck.core.config import ConfigRegistry
from issuedeck.features.documents.bundle import DOCUMENTS_REGISTRY_FILE, ITEM_DOCUMENTS_FILE
from issuedeck.features.documents.repo import DocumentStore, json_text
from issuedeck.features.images.bundle import IMAGE_REGISTRY_FILE, ITEM_IMAGES_FILE
from issuedeck.features.images.repo import ImageStore, registry_text
from issuedeck.features.items.models import (
    ImportBatch,
    Item,
    ItemDocument,
    ItemImage,
    ItemRelationship,
    ShipRecord,
    WorkSession,
)
from issuedeck.features.search.saved import SEARCHES_FILE, SavedSearchStore


@dataclass
class ExportReport:
    items_written: int


@dataclass
class AuditBundleReport:
    bundle_path: Path
    items_written: int
    relationships_written: int
    work_sessions_written: int
    import_batches_written: int
    images_written: int = 0
    item_images_written: int = 0
    documents_written: int = 0
    searches_written: int = 0
    item_documents_written: int = 0


async def export_md_bundle(
    *, session: AsyncSession, registry: ConfigRegistry,
    project_key: str, out_dir: Path,
) -> ExportReport:
    registry.project(project_key)  # raises ProjectNotFound if missing

    items = (await session.execute(
        select(Item)
        .where(Item.project_key == project_key, Item.deleted_at.is_(None))
        .order_by(Item.local_id)
        .options(
            selectinload(Item.tags),
            selectinload(Item.applies_to),
            selectinload(Item.ship_records).selectinload(ShipRecord.commits),
        )
    )).scalars().all()

    items_dir = out_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    for item in items:
        (items_dir / f"{item.local_id}.md").write_text(
            _render_item_md(item), encoding="utf-8",
        )

    return ExportReport(items_written=len(items))


async def export_audit_bundle(
    *,
    session: AsyncSession,
    registry: ConfigRegistry,
    project_key: str,
    out_path: Path,
) -> AuditBundleReport:
    project = registry.project(project_key)

    items = (await session.execute(
        select(Item)
        .where(Item.project_key == project_key)
        .order_by(Item.local_id)
        .options(
            selectinload(Item.tags),
            selectinload(Item.applies_to),
            selectinload(Item.external_links),
            selectinload(Item.events),
            selectinload(Item.ship_records).selectinload(ShipRecord.commits),
        )
    )).scalars().all()
    item_pk_to_local_id = {item.pk: item.local_id for item in items}
    item_pks = list(item_pk_to_local_id)

    relationships = []
    if item_pks:
        relationships = list((await session.execute(
            select(ItemRelationship)
            .where(
                ItemRelationship.from_item_pk.in_(item_pks),
                ItemRelationship.to_item_pk.in_(item_pks),
            )
            .order_by(ItemRelationship.id)
        )).scalars().all())

    work_sessions = list((await session.execute(
        select(WorkSession)
        .where(WorkSession.project_key == project_key)
        .order_by(WorkSession.updated_at.desc(), WorkSession.id.desc())
        .options(
            selectinload(WorkSession.item),
            selectinload(WorkSession.updates),
        )
    )).scalars().all())

    import_batches = list((await session.execute(
        select(ImportBatch)
        .where(ImportBatch.project_key == project_key)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    )).scalars().all())

    # FEA-0013: the image store of the project and the links to its items, when there are any
    image_doc, image_files = _images_of_project(registry, project_key)
    item_links: list[dict[str, str]] = []
    if item_pks:
        rows = (await session.execute(
            select(ItemImage.item_pk, ItemImage.image_id, ItemImage.created_at)
            .where(ItemImage.item_pk.in_(item_pks))
        )).all()
        item_links = sorted(
            ({"image_id": image_id, "local_id": item_pk_to_local_id[pk], "created_at": created}
             for pk, image_id, created in rows),
            key=lambda row: (row["local_id"], row["image_id"]),
        )
    has_images = bool(image_doc["images"] or item_links or int(image_doc["next_id"]) > 1)
    # FEA-0012: the document store of the project, when there are documents
    document_next_id, document_files = _documents_of_project(registry, project_key)
    document_links: list[dict[str, str]] = []
    if item_pks:
        link_rows = (await session.execute(
            select(ItemDocument.item_pk, ItemDocument.document_id, ItemDocument.created_at)
            .where(ItemDocument.item_pk.in_(item_pks))
        )).all()
        document_links = sorted(
            ({"document_id": document_id, "local_id": item_pk_to_local_id[pk],
              "created_at": created} for pk, document_id, created in link_rows),
            key=lambda row: (row["local_id"], row["document_id"]),
        )
    has_documents = bool(document_files or document_links) or document_next_id > 1
    # FEA-0010: the saved searches of the project, when there are any
    search_store = SavedSearchStore(registry.server.data_dir, project_key)
    search_bytes = search_store.read_bytes()

    bundle_path = _audit_bundle_path(out_path, project_key)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "format": "issuedeck.audit_bundle.v1",
        "project_key": project_key,
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": {
            "items": len(items),
            "relationships": len(relationships),
            "work_sessions": len(work_sessions),
            "import_batches": len(import_batches),
        },
        "files": [
            "manifest.json",
            "project.json",
            "items.json",
            "relationships.json",
            "work_sessions.json",
            "import_batches.json",
        ],
    }

    if has_images:
        manifest["counts"]["images"] = len(image_doc["images"])
        manifest["counts"]["item_images"] = len(item_links)
        manifest["files"].extend([IMAGE_REGISTRY_FILE, *sorted(image_files), ITEM_IMAGES_FILE])

    if has_documents:
        manifest["counts"]["documents"] = len(document_files)
        manifest["counts"]["item_documents"] = len(document_links)
        manifest["files"].extend(
            [DOCUMENTS_REGISTRY_FILE, *sorted(document_files), ITEM_DOCUMENTS_FILE])

    if search_bytes is not None:
        manifest["counts"]["searches"] = len(search_store.read()["searches"])
        manifest["files"].append(SEARCHES_FILE)

    project_toml = registry.server.projects_dir / f"{project_key}.toml"
    if project_toml.exists():
        manifest["files"].append("project.toml")

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        _write_json(bundle, "manifest.json", manifest)
        _write_json(bundle, "project.json", project.model_dump(mode="json"))
        if project_toml.exists():
            bundle.writestr("project.toml", _canonical_toml(project_toml))
        _write_json(bundle, "items.json", [_item_to_dict(item) for item in items])
        _write_json(
            bundle,
            "relationships.json",
            sorted(
                (
                    _relationship_to_dict(relationship, item_pk_to_local_id)
                    for relationship in relationships
                ),
                key=_relationship_key,
            ),
        )
        _write_json(
            bundle,
            "work_sessions.json",
            sorted(
                (_work_session_to_dict(session) for session in work_sessions),
                key=_work_session_key,
                reverse=True,
            ),
        )
        _write_json(
            bundle,
            "import_batches.json",
            sorted(
                (_import_batch_to_dict(batch) for batch in import_batches),
                key=_import_batch_key,
                reverse=True,
            ),
        )
        if has_images:
            bundle.writestr(IMAGE_REGISTRY_FILE, registry_text(image_doc))
            for name in sorted(image_files):
                bundle.writestr(name, image_files[name])  # the file, byte for byte
            _write_json(bundle, ITEM_IMAGES_FILE, item_links)
        if has_documents:
            listing = {
                "ids": sorted(name[len("documents/"):-len(".json")] for name in document_files),
                "next_id": document_next_id,
            }
            bundle.writestr(DOCUMENTS_REGISTRY_FILE, json_text(listing))
            for name in sorted(document_files):
                bundle.writestr(name, document_files[name])  # the file, byte for byte
            _write_json(bundle, ITEM_DOCUMENTS_FILE, document_links)
        if search_bytes is not None:
            bundle.writestr(SEARCHES_FILE, search_bytes)  # the file, byte for byte

    return AuditBundleReport(
        bundle_path=bundle_path,
        items_written=len(items),
        relationships_written=len(relationships),
        work_sessions_written=len(work_sessions),
        import_batches_written=len(import_batches),
        images_written=len(image_files),
        item_images_written=len(item_links),
        documents_written=len(document_files),
        searches_written=len(search_store.read()["searches"]) if search_bytes else 0,
        item_documents_written=len(document_links),
    )


def _documents_of_project(
    registry: ConfigRegistry, project_key: str,
) -> tuple[int, dict[str, bytes]]:
    """The next free document number and the document files (by snapshot name), as stored."""
    store = DocumentStore(registry.server.data_dir / "documents", project_key)
    files: dict[str, bytes] = {}
    for document_id in store.ids():
        data = store.read_bytes(document_id)
        if data is not None:
            files[f"documents/{document_id}.json"] = data
    return store.next_id(), files


def _images_of_project(
    registry: ConfigRegistry, project_key: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """The registry of the project's image store and the files it lists (by snapshot name)."""
    store = ImageStore(registry.server.data_dir / "images", project_key)
    doc = store.load()
    files: dict[str, bytes] = {}
    for entry in doc["images"]:
        try:
            files[f"images/{entry['stored']}"] = store.read_file(entry["stored"])
        except (FileNotFoundError, ValueError):
            continue  # the import names an image whose file is missing and skips it
    return doc, files


def _render_item_md(item: Item) -> str:
    lines: list[str] = ["---"]
    lines.append(f"id: {item.local_id}")
    lines.append(f"kind: {item.kind}")
    lines.append(f"status: {item.status}")
    lines.append(f"title: {_yaml_quote(item.title)}")
    if item.tags:
        lines.append("tags:")
        for t in item.tags:
            lines.append(f"  - {t.tag}")
    if item.applies_to:
        applies = ", ".join(a.branch_key for a in item.applies_to)
        lines.append(f"applies_to: [{applies}]")
    custom_fields = _metadata(item.custom_fields_json)
    if custom_fields:
        lines.append("custom_fields:")
        for key, value in sorted(custom_fields.items()):
            lines.append(f"  {key}: {_yaml_value(value)}")
    for sr in item.ship_records:
        lines.append(f"shipped_in_{sr.branch_key}: {sr.version}")
        if sr.commits:
            lines.append(f"commits_{sr.branch_key}:")
            for c in sr.commits:
                lines.append(f"  - {c.sha}")
    lines.append(f"created_at: {item.created_at}")
    lines.append(f"updated_at: {item.updated_at}")
    lines.append("---")
    lines.append("")
    lines.append(item.body or "")
    return "\n".join(lines) + "\n"


def _yaml_quote(s: str) -> str:
    if any(c in s for c in ":#\"'\n"):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return _yaml_quote(str(value))


def _audit_bundle_path(out_path: Path, project_key: str) -> Path:
    if out_path.suffix.lower() == ".zip":
        return out_path
    return out_path / f"{project_key}-audit-bundle.zip"


def _write_json(bundle: zipfile.ZipFile, name: str, payload: Any) -> None:
    bundle.writestr(
        name,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


# IS-0010: the files of a snapshot never carry the numeric row ids of the database they come
# from (events, relationships, work sessions, their updates, import batches, external links).
# An import cannot restore them, so a project that was imported would export different files
# than the one it came from. Everything is ordered by its content instead, so the same data
# always gives the same files, whatever the database and the order of insertion.


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _event_dict(event: Any) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "actor_type": event.actor_type,
        "actor_name": event.actor_name,
        "body": event.body,
        "metadata": _metadata(event.metadata_json),
        "created_at": event.created_at,
    }


def _event_key(event: dict[str, Any]) -> tuple[str, ...]:
    return (
        _text(event["created_at"]), _text(event["event_type"]), _text(event["actor_type"]),
        _text(event["actor_name"]), _text(event["body"]), _canonical(event["metadata"]),
    )


def _item_to_dict(item: Item) -> dict[str, Any]:
    links = [
        {
            "link_type": link.link_type,
            "label": link.label,
            "url": link.url,
            "created_at": link.created_at,
        }
        for link in item.external_links
    ]
    records = [
        {
            "branch_key": record.branch_key,
            "version": record.version,
            "shipped_at": record.shipped_at,
            "commits": [commit.sha for commit in record.commits],
        }
        for record in item.ship_records
    ]
    return {
        "local_id": item.local_id,
        "project_key": item.project_key,
        "kind": item.kind,
        "status": item.status,
        "title": item.title,
        "body": item.body,
        "tags": sorted(tag.tag for tag in item.tags),
        "applies_to": sorted(branch.branch_key for branch in item.applies_to),
        "custom_fields": _metadata(item.custom_fields_json),
        "external_links": sorted(
            links,
            key=lambda link: (
                _text(link["created_at"]), _text(link["link_type"]),
                _text(link["url"]), _text(link["label"]),
            ),
        ),
        "ship_records": sorted(
            records,
            key=lambda record: (
                _text(record["shipped_at"]), _text(record["branch_key"]),
                _text(record["version"]),
            ),
        ),
        "events": sorted((_event_dict(event) for event in item.events), key=_event_key),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "deleted_at": item.deleted_at,
    }


def _relationship_to_dict(
    relationship: ItemRelationship,
    item_pk_to_local_id: dict[int, str],
) -> dict[str, Any]:
    return {
        "from_local_id": item_pk_to_local_id[relationship.from_item_pk],
        "to_local_id": item_pk_to_local_id[relationship.to_item_pk],
        "relation_type": relationship.relation_type,
        "created_at": relationship.created_at,
    }


def _relationship_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _text(row["from_local_id"]), _text(row["to_local_id"]),
        _text(row["relation_type"]), _text(row["created_at"]),
    )


def _work_session_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _text(row["updated_at"]), _text(row["started_at"]), _text(row["agent_name"]),
        _text(row["local_id"]), _text(row["goal"]),
    )


def _import_batch_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _text(row["created_at"]), _text(row["batch_tag"]), _text(row["source_type"]),
        _text(row["source_name"]),
    )


def _canonical_toml(path: Path) -> str:
    """The project configuration with one fixed line ending and without a byte order mark,
    so that an export made on Windows equals one made on Linux, and a file whose lines end in
    CR CR LF (what earlier imports wrote on Windows) exports like one with LF."""
    text = path.read_bytes().decode("utf-8-sig")
    return re.sub(r"\r+\n|\r", "\n", text)


def _work_session_to_dict(session: WorkSession) -> dict[str, Any]:
    return {
        "project_key": session.project_key,
        "local_id": session.item.local_id if session.item else None,
        "agent_name": session.agent_name,
        "status": session.status,
        "goal": session.goal,
        "summary": session.summary,
        "branch": session.branch,
        "started_at": session.started_at,
        "updated_at": session.updated_at,
        "ended_at": session.ended_at,
        "metadata": _metadata(session.metadata_json),
        "updates": sorted(
            (
                {
                    "update_type": update.update_type,
                    "message": update.message,
                    "metadata": _metadata(update.metadata_json),
                    "created_at": update.created_at,
                }
                for update in session.updates
            ),
            key=lambda update: (
                _text(update["created_at"]), _text(update["update_type"]),
                _text(update["message"]), _canonical(update["metadata"]),
            ),
        ),
    }


def _import_batch_to_dict(batch: ImportBatch) -> dict[str, Any]:
    return {
        "project_key": batch.project_key,
        "batch_tag": batch.batch_tag,
        "source_type": batch.source_type,
        "source_name": batch.source_name,
        "items_planned": batch.items_planned,
        "items_written": batch.items_written,
        "skipped_count": batch.skipped_count,
        "status_mapped": batch.status_mapped,
        "external_links": batch.external_links,
        "created_at": batch.created_at,
        "metadata": _metadata(batch.metadata_json),
    }


def _metadata(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"raw": raw}
