"""Running a search query against the items of a project (FEA-0010, phase 1).

Every block is evaluated on its own into the set of the items it matches, and the sets are combined
as the query says (``and`` is an intersection, ``or`` a union, ``and`` binds tighter than ``or``).
The blocks use bound parameters only; no text of the user is ever put into an SQL string.

* ``text`` in mode ``simple``: the words are quoted one by one and given to the full-text index
  (all words must occur, in any order, in the chosen fields). This is not the raw FTS5 syntax of the
  older ``q`` search, so a word such as ``OR`` or ``*`` is just a word.
* ``text`` in mode ``regex``: run in a process that is killed when the time is up
  (``regex_worker``); the result then says it is partial and which expressions did not finish.
* ``kind`` and ``status``: compared with the items.

The result is the pks of the matching items, newest first, like the lists of the dashboard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.errors import InvalidSearch
from issuedeck.features.items.models import Item
from issuedeck.features.search.query import FIELDS, Group, Kind, Query, Status, Text, terms
from issuedeck.features.search.regex_worker import Job, Row, run_regex_jobs

#: How long the regular expressions of one search may run, in seconds.
REGEX_SECONDS = 2.0
#: How many items (the newest) the regular expressions look at.
REGEX_MAX_ROWS = 50_000


@dataclass
class SearchResult:
    pks: list[int]  # newest first
    partial: bool = False
    notes: list[str] = field(default_factory=list)


def fts_match(words: str, fields: tuple[str, ...]) -> str:
    """The FTS5 MATCH text for plain words: every word quoted, all of them required."""
    quoted = " ".join('"' + word.replace('"', '""') + '"' for word in words.split())
    if set(fields) == set(FIELDS):
        return quoted
    return "{" + " ".join(fields) + "} : (" + quoted + ")"


def _blocks(items) -> list[Text | Kind | Status]:
    found: list[Text | Kind | Status] = []
    for item in items:
        if isinstance(item.node, Group):
            found.extend(_blocks(item.node.items))
        else:
            found.append(item.node)
    return found


async def run_query(
    session: AsyncSession, project_key: str, query: Query, *,
    seconds: float = REGEX_SECONDS, max_rows: int = REGEX_MAX_ROWS,
) -> SearchResult:
    blocks = _blocks(query.items)
    regex_blocks = [b for b in blocks if isinstance(b, Text) and b.mode == "regex"]

    columns = [Item.pk, Item.kind, Item.status]
    if regex_blocks:
        columns += [Item.title, Item.body]
    rows = (await session.execute(
        select(*columns)
        .where(Item.project_key == project_key, Item.deleted_at.is_(None))
        .order_by(Item.updated_at.desc(), Item.pk.desc())
    )).all()
    order = [row[0] for row in rows]
    universe = set(order)
    result = SearchResult(pks=[])

    sets: dict[int, set[int]] = {}
    for block in blocks:
        if isinstance(block, Kind):
            sets[id(block)] = {row[0] for row in rows if row[1] in block.values}
        elif isinstance(block, Status):
            sets[id(block)] = {row[0] for row in rows if row[2] in block.values}
        elif block.mode == "simple":
            sets[id(block)] = await _full_text(session, block) & universe

    if regex_blocks:
        jobs: list[Job] = [
            (index, block.value, 0 if block.case_sensitive else re.IGNORECASE, block.fields)
            for index, block in enumerate(regex_blocks)
        ]
        candidates: list[Row] = [(r[0], r[3], r[4]) for r in rows[:max_rows]]
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
