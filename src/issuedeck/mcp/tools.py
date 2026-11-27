"""MCP tool functions. Thin wrappers calling IssueDeckClient."""
from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Any

from issuedeck.core.errors import ImageTooLarge, InvalidDocument, InvalidImage, InvalidSearch
from issuedeck.features.documents.text import decode_upload
from issuedeck.mcp.client import get_client

# The MCP process reads the file itself, so it never reads more than this from the disk. The
# server enforces its own (smaller) limit, [images] max_file_bytes in server.toml.
MAX_LOCAL_IMAGE_BYTES = 10_000_000


def _drop_none(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


async def list_projects() -> dict[str, Any]:
    """List every configured issuedeck project."""
    return await get_client().list_projects()


async def get_project_config(project_key: str) -> dict[str, Any]:
    """Return the kinds, statuses, tags and applies_to values for a project."""
    return await get_client().get_project_config(project_key)


async def create_item(
    project_key: str,
    kind: str,
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    applies_to: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    external_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new tracker item. Returns the full item with its local_id."""
    payload = _drop_none({
        "kind": kind,
        "title": title,
        "body": body,
        "tags": tags,
        "applies_to": applies_to,
        "custom_fields": custom_fields,
        "external_links": external_links,
    })
    return await get_client().create_item(project_key, payload)


async def update_item(
    project_key: str,
    local_id: str,
    title: str | None = None,
    body: str | None = None,
    append_body: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    applies_to: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    external_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Partial update of an item. Pass body OR append_body, not both."""
    payload = _drop_none({
        "title": title,
        "body": body,
        "append_body": append_body,
        "status": status,
        "tags": tags,
        "applies_to": applies_to,
        "custom_fields": custom_fields,
        "external_links": external_links,
    })
    return await get_client().update_item(project_key, local_id, payload)


async def bulk_update_items(
    project_key: str,
    local_ids: list[str],
    action: str = "update",
    kind: str | None = None,
    status: str | None = None,
    applies_to: list[str] | None = None,
    tags: list[str] | None = None,
    tag_mode: str = "add",
    custom_fields: dict[str, Any] | None = None,
    reason: str = "mcp bulk update",
) -> dict[str, Any]:
    """Update, delete, or restore multiple items by local_id."""
    payload = _drop_none({
        "local_ids": local_ids,
        "action": action,
        "kind": kind,
        "status": status,
        "applies_to": applies_to,
        "tags": tags,
        "tag_mode": tag_mode,
        "custom_fields": custom_fields,
        "reason": reason,
    })
    return await get_client().bulk_update_items(project_key, payload)


async def ship_item(
    project_key: str,
    local_id: str,
    branch: str,
    version: str,
    commits: list[str] | None = None,
) -> dict[str, Any]:
    """Mark an item as shipped on a given branch at a given version."""
    payload = _drop_none({
        "branch": branch,
        "version": version,
        "commits": commits,
    })
    return await get_client().ship_item(project_key, local_id, payload)


async def append_item_event(
    project_key: str,
    local_id: str,
    body: str,
    event_type: str = "comment",
    actor_type: str = "agent",
    actor_name: str = "agent",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append an activity timeline event or comment to an item."""
    payload = _drop_none({
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_name": actor_name,
        "body": body,
        "metadata": metadata,
    })
    return await get_client().create_item_event(project_key, local_id, payload)


async def delete_item(project_key: str, local_id: str) -> dict[str, Any]:
    """Soft-delete an item."""
    return await get_client().delete_item(project_key, local_id)


async def get_item(project_key: str, local_id: str) -> dict[str, Any]:
    """Fetch a single item with relationships and ship history."""
    return await get_client().get_item(project_key, local_id)


async def list_items(
    project_key: str,
    status: str | None = None,
    kind: str | None = None,
    tag: list[str] | None = None,
    applies_to: str | None = None,
    relation_type: str | None = None,
    custom_field: list[str] | None = None,
    shipped_in_branch: str | None = None,
    since: str | None = None,
    include_deleted: bool = False,
    only_deleted: bool = False,
    after: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List items with filters.

    custom_field entries use FIELD=VALUE, FIELD>=VALUE, or FIELD:missing syntax.
    """
    params: dict[str, Any] = _drop_none({
        "status": status,
        "kind": kind,
        "applies_to": applies_to,
        "relation_type": relation_type,
        "shipped_in_branch": shipped_in_branch,
        "since": since,
        "after": after,
    })
    params["limit"] = limit
    if include_deleted:
        params["include_deleted"] = "true"
    if only_deleted:
        params["only_deleted"] = "true"
    if tag:
        params["tag"] = tag
    if custom_field:
        params["custom_field"] = custom_field
    return await get_client().list_items(project_key, params)


async def search_items(
    project_key: str,
    q: str | None = None,
    limit: int = 20,
    query: dict[str, Any] | None = None,
    after: str | None = None,
) -> dict[str, Any]:
    """Search items: with ``q`` the text is FTS5 MATCH syntax; with ``query`` a structured search.

    Give exactly one of ``q`` and ``query``. A ``query`` is an object
    ``{"items": [block, {"op": "and"|"or", ...block}, ...]}``. A block is
    ``{"type": "text", "mode": "simple"|"regex", "value": "...", "fields": ["title", "body"]}``
    (simple: all the words must occur, matched by stem; regex: Python syntax, ``case_sensitive``
    allowed), ``{"type": "document", ...same keys..., "kinds": [document kinds]}`` (items that have
    a linked document that matches; words as written, no stemming), ``{"type": "kind", "values":
    [...]}``, ``{"type": "status", "values": [...]}``, or a ``{"group": [blocks]}`` of blocks with
    their own ``op``. ``and`` binds tighter than ``or``;
    groups nest one level. The answer has ``items``, ``next_cursor`` (pass it as ``after`` for the
    next page), ``description`` of the search in words, ``partial`` and ``notes`` (a regular
    expression that did not finish in time is reported there).
    """
    if (q is None) == (query is None):
        raise InvalidSearch("give exactly one of q and query", details={"path": ""})
    if query is None:
        return await get_client().search_items(project_key, {"q": q, "limit": limit})
    body = _drop_none({"query": query, "limit": limit, "after": after})
    return await get_client().search_items_query(project_key, body)


async def add_relationship(
    project_key: str,
    from_local_id: str,
    to_local_id: str,
    relation_type: str,
) -> dict[str, Any]:
    """Create a relationship between two items. relation_type in {blocks, related_to}."""
    return await get_client().add_relationship(
        project_key,
        from_local_id,
        {
            "to_local_id": to_local_id,
            "relation_type": relation_type,
        },
    )


async def remove_relationship(
    project_key: str,
    rel_id: int,
) -> dict[str, Any]:
    """Delete a relationship and its bidirectional inverse."""
    return await get_client().remove_relationship(project_key, rel_id)


async def start_work_session(
    project_key: str,
    local_id: str,
    agent_name: str,
    goal: str,
    branch: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start an agent work session on a tracked item."""
    payload = _drop_none({
        "local_id": local_id,
        "agent_name": agent_name,
        "goal": goal,
        "branch": branch,
        "metadata": metadata,
    })
    return await get_client().start_work_session(project_key, payload)


async def list_work_sessions(
    project_key: str,
    status: str | None = None,
    agent_name: str | None = None,
    local_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List agent work sessions, optionally filtered by status, agent, or item."""
    params = _drop_none({
        "status": status,
        "agent_name": agent_name,
        "local_id": local_id,
    })
    params["limit"] = limit
    return await get_client().list_work_sessions(project_key, params)


async def get_work_session(
    project_key: str,
    session_id: int,
) -> dict[str, Any]:
    """Fetch a single agent work session with progress updates."""
    return await get_client().get_work_session(project_key, session_id)


async def update_work_session(
    project_key: str,
    session_id: int,
    message: str,
    update_type: str = "progress",
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append progress to an active agent work session."""
    payload = _drop_none({
        "message": message,
        "update_type": update_type,
        "status": status,
        "metadata": metadata,
    })
    return await get_client().update_work_session(project_key, session_id, payload)


async def finish_work_session(
    project_key: str,
    session_id: int,
    status: str = "completed",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark an agent work session as completed or canceled."""
    payload = _drop_none({
        "status": status,
        "summary": summary,
        "metadata": metadata,
    })
    return await get_client().finish_work_session(project_key, session_id, payload)


async def upload_image(project_key: str, source_path: str) -> dict[str, Any]:
    """Store an SVG file from this machine (local folder or network share) as a project image.

    The MCP process reads ``source_path`` and uploads it, so the server needs no access to the
    path. Only ``.svg`` files are read; the server checks the content and refuses anything
    that is not a safe SVG. Returns the image with its id (for example ``IMG-0001``).
    """
    path = Path(source_path).expanduser()
    if path.suffix.lower() != ".svg":
        raise InvalidImage("only .svg files can be uploaded", details={"reason": "extension"})
    if not path.is_file():
        raise InvalidImage(f"{path} is not a file", details={"reason": "not_a_file"})
    if path.stat().st_size > MAX_LOCAL_IMAGE_BYTES:
        raise ImageTooLarge(f"{path.name} is larger than {MAX_LOCAL_IMAGE_BYTES} bytes")
    return await get_client().upload_image(project_key, path.name, path.read_bytes())


async def upload_image_data(
    project_key: str,
    name: str,
    data_base64: str | None = None,
    svg_text: str | None = None,
) -> dict[str, Any]:
    """Store an SVG given as data (base64, or the SVG text itself) as a project image.

    Use this when the SVG is not a file the MCP process can read. Give exactly one of
    ``data_base64`` and ``svg_text``. Returns the image with its id.
    """
    if (data_base64 is None) == (svg_text is None):
        raise InvalidImage("give exactly one of data_base64 and svg_text",
                           details={"reason": "data"})
    if svg_text is not None:
        data = svg_text.encode("utf-8")
    else:
        try:
            data = base64.b64decode(data_base64 or "", validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidImage("data_base64 is not valid base64",
                               details={"reason": "base64"}) from exc
    if len(data) > MAX_LOCAL_IMAGE_BYTES:
        raise ImageTooLarge(f"the data is larger than {MAX_LOCAL_IMAGE_BYTES} bytes")
    return await get_client().upload_image(project_key, name, data)


async def list_images(project_key: str) -> dict[str, Any]:
    """List the SVG images of a project (id, name, size, SHA-256, upload time)."""
    return await get_client().list_images(project_key)


async def get_image(
    project_key: str, image_id: str, include_content: bool = False,
) -> dict[str, Any]:
    """Return the metadata of an image, and with ``include_content`` its SVG text."""
    image = await get_client().get_image(project_key, image_id)
    if include_content:
        data = await get_client().get_image_content(project_key, image_id)
        image = {**image, "content": data.decode("utf-8", errors="replace")}
    return image


async def delete_image(project_key: str, image_id: str) -> dict[str, Any]:
    """Delete an image of a project."""
    await get_client().delete_image(project_key, image_id)
    return {"deleted": image_id}


async def create_document(
    project_key: str,
    name: str | None = None,
    body: str | None = None,
    source_path: str | None = None,
    kind: str = "other",
    title: str = "",
    replace: bool = False,
) -> dict[str, Any]:
    """Store a Markdown document in a project: its text, or one file read from this machine.

    Give exactly one of ``body`` (the text) and ``source_path`` (one file; the MCP process
    reads it, so a local folder or a network share works; no folders). ``name`` is free text; it
    defaults to the file name. A binary file is refused. ``kind`` is prompt, description,
    request, report or other. A name that is already used gives an error, or with
    ``replace=True`` a new revision of that document. Returns the document with its id
    (for example DOC-0001).
    """
    if (body is None) == (source_path is None):
        raise InvalidDocument("give exactly one of body and source_path",
                              details={"reason": "source"})
    if source_path is not None:
        path = Path(source_path).expanduser()
        if not path.is_file():
            raise InvalidDocument(f"{path} is not a file", details={"reason": "not_a_file"})
        body = decode_upload(path.read_bytes())  # a binary file is refused here
        name = name or path.name
    if not name:
        raise InvalidDocument("a document needs a name", details={"reason": "name"})
    return await get_client().create_document(project_key, {
        "name": name, "body": body, "kind": kind, "title": title, "replace": replace,
    })


async def list_documents(
    project_key: str, kind: str | None = None, name: str | None = None,
) -> dict[str, Any]:
    """List the documents of a project (id, name, kind, title, revision, size), without text."""
    return await get_client().list_documents(project_key, _drop_none({"kind": kind, "name": name}))


async def get_document(
    project_key: str, document_id: str, revision: int | None = None,
) -> dict[str, Any]:
    """Return a document with its text; with ``revision`` the text of that older revision."""
    if revision is None:
        return await get_client().get_document(project_key, document_id)
    document = await get_client().get_document(project_key, document_id)
    old = await get_client().get_document_revision(project_key, document_id, revision)
    return {**document, "requested_revision": old}


async def update_document(
    project_key: str,
    document_id: str,
    revision: int | None = None,
    body: str | None = None,
    append_body: str | None = None,
    title: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Change a document: append text, or replace its text, title or kind.

    ``append_body`` adds text at the end and needs no ``revision``. Replacing (``body``, ``title``
    or ``kind``) needs the ``revision`` you read; if the document has changed since, the call
    fails with a conflict that names the current revision, and nothing is written. Every change of
    the text is a new revision (the last 50 are kept).
    """
    if append_body is not None:
        if body is not None or title is not None or kind is not None:
            raise InvalidDocument("append_body cannot be combined with body, title or kind",
                                  details={"reason": "mode"})
        return await get_client().append_document(project_key, document_id, append_body)
    if revision is None:
        raise InvalidDocument("give the revision you read (to replace), or append_body",
                              details={"reason": "revision"})
    if body is None:
        body = (await get_client().get_document(project_key, document_id))["body"]
    return await get_client().replace_document(
        project_key, document_id,
        _drop_none({"body": body, "revision": revision, "title": title, "kind": kind}),
    )


async def delete_document(project_key: str, document_id: str) -> dict[str, Any]:
    """Delete a document and all its revisions."""
    await get_client().delete_document(project_key, document_id)
    return {"deleted": document_id}


async def list_document_revisions(project_key: str, document_id: str) -> dict[str, Any]:
    """List the kept revisions of a document, newest first (the last 50 are kept)."""
    return await get_client().list_document_revisions(project_key, document_id)
