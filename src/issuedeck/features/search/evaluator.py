"""Running a search query against the items of a project (FEA-0010, phase 1).

Every block is evaluated on its own into the set of the items it matches, and the sets are combined
as the query says (``and`` is an intersection, ``or`` a union, ``and`` binds tighter than ``or``).
The blocks use bound parameters only; no text of the user is ever put into an SQL string.

* ``text`` in mode ``simple``: the words are quoted one by one and given to the full-text index
  (all words must occur, in any order, in the chosen fields). This is not the raw FTS5 syntax of the
  older ``q`` search, so a word such as ``OR`` or ``*`` is just a word.
* ``text`` in mode ``regex``: run in a process that is killed when the time is up
  (``regex_worker``); the result then says it is partial and which expressions did not finish.
* ``document`` (phase 5): the documents of the project are files without an index, so they are
  read and matched here (plain words: all of them, ignoring case, as written, no stemming;
  regular expressions in the killable process, with a budget of their own); the result is the items
  that have a matching document linked (``item_documents``).
* ``kind`` and ``status``: compared with the items.

The result is the pks of the matching items, newest first, like the lists of the dashboard.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.errors import InvalidSearch
from issuedeck.features.documents.repo import DocumentStore
from issuedeck.features.items.models import Item, ItemDocument
from issuedeck.features.search.query import (
    FIELDS,
    Document,
    Group,
    Kind,
    Query,
    Status,
    Text,
    terms,
)
from issuedeck.features.search.regex_worker import Job, Row, run_regex_jobs

#: How long the regular expressions of one search may run, in seconds.
REGEX_SECONDS = 2.0
#: How many items (the newest) the regular expressions look at.
REGEX_MAX_ROWS = 50_000
#: How many documents (the first by id) a document block looks at.
MAX_DOCUMENTS = 5_000


@dataclass
class SearchResult:
    pks: list[int]  # newest first
    partial: bool = False
    notes: list[str] = field(default_factory=list)
    updated: dict[int, str] = field(default_factory=dict)  # pk -> updated_at of every match


def fts_match(words: str, fields: tuple[str, ...]) -> str:
    """The FTS5 MATCH text for plain words: every word quoted, all of them required."""
    quoted = " ".join('"' + word.replace('"', '""') + '"' for word in words.split())
    if set(fields) == set(FIELDS):
        return quoted
    return "{" + " ".join(fields) + "} : (" + quoted + ")"


def _blocks(items) -> list[Text | Document | Kind | Status]:
    found: list[Text | Document | Kind | Status] = []
    for item in items:
        if isinstance(item.node, Group):
            found.extend(_blocks(item.node.items))
        else:
            found.append(item.node)
    return found


async def run_query(
    session: AsyncSession, project_key: str, query: Query, *,
    seconds: float | None = None, max_rows: int | None = None,
    documents_dir: Path | None = None,
) -> SearchResult:
    # read at the call, so that a test or a setting can change them
    seconds = REGEX_SECONDS if seconds is None else seconds
    max_rows = REGEX_MAX_ROWS if max_rows is None else max_rows
    blocks = _blocks(query.items)
    regex_blocks = [b for b in blocks if isinstance(b, Text) and b.mode == "regex"]
    document_blocks = [b for b in blocks if isinstance(b, Document)]

    columns = [Item.pk, Item.kind, Item.status, Item.updated_at]
    if regex_blocks:
        columns += [Item.title, Item.body]
    rows = (await session.execute(
        select(*columns)
        .where(Item.project_key == project_key, Item.deleted_at.is_(None))
        .order_by(Item.updated_at.desc(), Item.pk.desc())
    )).all()
    order = [row.pk for row in rows]
    updated = {row.pk: row.updated_at for row in rows}
    universe = set(order)
    result = SearchResult(pks=[])

    sets: dict[int, set[int]] = {}
    for block in blocks:
        if isinstance(block, Kind):
            sets[id(block)] = {row.pk for row in rows if row.kind in block.values}
        elif isinstance(block, Status):
            sets[id(block)] = {row.pk for row in rows if row.status in block.values}
        elif isinstance(block, Document):
            continue  # below, with the documents
        elif block.mode == "simple":
            sets[id(block)] = await _full_text(session, block) & universe

    if document_blocks:
        await _documents(session, project_key, document_blocks, documents_dir, universe,
                         sets, result, seconds)

    if regex_blocks:
        jobs: list[Job] = [
            (index, block.value, 0 if block.case_sensitive else re.IGNORECASE, block.fields)
            for index, block in enumerate(regex_blocks)
        ]
        candidates: list[Row] = [(r.pk, r.title, r.body) for r in rows[:max_rows]]
        if len(rows) > max_rows:
            result.partial = True
            result.notes.append(
                f"a regular expression looked only at the newest {max_rows} of {len(rows)} items")
        done, unfinished = await run_regex_jobs(jobs, candidates, seconds)
        for index, block in enumerate(regex_blocks):
            sets[id(block)] = done.get(index, set()) & universe
        if unfinished:
            result.partial = True
            for index in unfinished:
                result.notes.append(
                    f'the regular expression "{regex_blocks[index].value}" did not finish in '
                    f"{seconds:g} s and matched nothing; the result is incomplete")

    def evaluate(items) -> set[int]:
        matched: set[int] = set()
        for chain in terms(items):
            current: set[int] | None = None
            for item in chain:
                node = item.node
                value = evaluate(node.items) if isinstance(node, Group) else sets[id(node)]
                current = value if current is None else current & value
            matched |= current or set()
        return matched

    matching = evaluate(query.items)
    result.pks = [pk for pk in order if pk in matching]
    result.updated = {pk: updated[pk] for pk in result.pks}
    return result


async def _full_text(session: AsyncSession, block: Text) -> set[int]:
    try:
        rows = await session.execute(
            text("SELECT rowid FROM items_fts WHERE items_fts MATCH :q"),
            {"q": fts_match(block.value, block.fields)},
        )
    except OperationalError as exc:
        raise InvalidSearch(
            f'the words "{block.value}" cannot be searched: {exc.orig}',
            details={"value": block.value},
        ) from exc
    return {row[0] for row in rows.all()}


def _read_documents(documents_dir: Path, project_key: str) -> tuple[list[dict[str, Any]], int]:
    """The documents of the project as ``{id, kind, title, body}``; ``title`` is the name and the
    title together. Returns them (at most ``MAX_DOCUMENTS``) and how many there are."""
    store = DocumentStore(documents_dir, project_key)
    ids = store.ids()
    found: list[dict[str, Any]] = []
    for document_id in ids[:MAX_DOCUMENTS]:
        document = store.read(document_id)
        if document is None:
            continue
        found.append({
            "id": document_id, "kind": document.get("kind"),
            "title": f"{document.get('name') or ''}\n{document.get('title') or ''}",
            "body": document.get("body") or "",
        })
    return found, len(ids)


def _words_in(document: dict[str, Any], block: Document) -> bool:
    """All the words occur (ignoring case, as written) in the chosen fields together."""
    haystack = "\n".join(document[f] for f in block.fields).casefold()
    return all(word.casefold() in haystack for word in block.value.split())


async def _documents(
    session: AsyncSession, project_key: str, blocks: list[Document], documents_dir: Path | None,
    universe: set[int], sets: dict[int, set[int]], result: SearchResult, seconds: float,
) -> None:
    """The items with a linked document that matches, for every document block."""
    if documents_dir is None:
        raise InvalidSearch("the documents cannot be searched here",
                            details={"path": ""})
    documents, total = await asyncio.to_thread(_read_documents, documents_dir, project_key)
    if total > len(documents):
        result.partial = True
        result.notes.append(
            f"a document block looked only at the first {len(documents)} of {total} documents")

    links: dict[str, set[int]] = {}
    for pk, document_id in (await session.execute(
        select(ItemDocument.item_pk, ItemDocument.document_id)
        .join(Item, Item.pk == ItemDocument.item_pk)
        .where(Item.project_key == project_key, Item.deleted_at.is_(None))
    )).all():
        links.setdefault(document_id, set()).add(pk)

    def candidates(block: Document) -> list[dict[str, Any]]:
        return [d for d in documents if not block.kinds or d["kind"] in block.kinds]

    matched: dict[int, set[str]] = {}
    regex = [b for b in blocks if b.mode == "regex"]
    for block in blocks:
        if block.mode == "simple":
            matched[id(block)] = {d["id"] for d in candidates(block) if _words_in(d, block)}
    if regex:
        numbered = {number: d["id"] for number, d in enumerate(documents, start=1)}
        rows: list[Row] = [(n, d["title"], d["body"]) for n, d in enumerate(documents, start=1)]
        jobs: list[Job] = [
            (index, block.value, 0 if block.case_sensitive else re.IGNORECASE, block.fields)
            for index, block in enumerate(regex)
        ]
        done, unfinished = await run_regex_jobs(jobs, rows, seconds)
        for index, block in enumerate(regex):
            allowed = {d["id"] for d in candidates(block)}
            matched[id(block)] = {numbered[n] for n in done.get(index, set())} & allowed
        for index in unfinished:
            result.partial = True
            result.notes.append(
                f'the regular expression "{regex[index].value}" of a document block did not '
                f"finish in {seconds:g} s and matched nothing; the result is incomplete")

    for block in blocks:
        items: set[int] = set()
        for document_id in matched[id(block)]:
            items |= links.get(document_id, set())
        sets[id(block)] = items & universe
