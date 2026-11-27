"""The advanced search query: its model, its validation and its description (FEA-0010).

A search is plain data (JSON), the same in the dialog, the API, MCP and the saved file::

    {"items": [
      {"type": "text", "mode": "regex", "value": "import(ing)?\\b", "fields": ["title", "body"]},
      {"op": "and", "type": "kind", "values": ["bug"]},
      {"op": "and", "type": "document", "mode": "simple", "value": "rollback",
       "kinds": ["request"]},
      {"op": "and", "group": [
        {"type": "status", "values": ["proposed"]},
        {"op": "or", "type": "status", "values": ["in_progress"]}
      ]}
    ]}

Every item after the first has the operator ``and`` or ``or`` that joins it to the one above. A
``group`` is a list of blocks of its own and counts as one block of the list above it. ``and``
binds tighter than ``or``. Lists nest at most ``MAX_DEPTH`` levels (the top list and one level of
groups), and the number is a parameter, not a constant of the code, so that deeper nesting can be
allowed later.

A ``document`` block (phase 5) has the keys of a ``text`` block and the optional ``kinds`` of the
documents; it matches the items that have a linked document whose name and title (``title``) or
text (``body``) match.

``parse_query`` checks everything a client can get wrong and raises ``InvalidSearch`` with the path
of the fault (``items[2].group[0]``). Nothing here touches the database.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from issuedeck.core.errors import InvalidSearch

MAX_DEPTH = 2
MAX_BLOCKS = 20
MAX_REGEX_LENGTH = 200
MAX_SIMPLE_LENGTH = 500
FIELDS = ("title", "body")
MODES = ("simple", "regex")
OPERATORS = ("and", "or")

_TEXT_KEYS = {"type", "op", "mode", "value", "fields", "case_sensitive"}
_DOCUMENT_KEYS = _TEXT_KEYS | {"kinds"}
_VALUES_KEYS = {"type", "op", "values"}
_GROUP_KEYS = {"group", "op"}


@dataclass(frozen=True, eq=False)
class Text:
    mode: str
    value: str
    fields: tuple[str, ...]
    case_sensitive: bool


@dataclass(frozen=True, eq=False)
class Document:
    """Items that have a linked document whose name and title (``title``) or text (``body``) match;
    ``kinds`` limits the documents (empty: every kind)."""

    mode: str
    value: str
    fields: tuple[str, ...]
    case_sensitive: bool
    kinds: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class Kind:
    values: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class Status:
    values: tuple[str, ...]


@dataclass(frozen=True, eq=False)
class Item:
    op: str | None  # how it joins the item above; None for the first item of a list
    node: Text | Document | Kind | Status | Group


@dataclass(frozen=True, eq=False)
class Group:
    items: tuple[Item, ...]


@dataclass(frozen=True, eq=False)
class Query:
    items: tuple[Item, ...]


def _fail(path: str, message: str, **details: Any) -> InvalidSearch:
    return InvalidSearch(f"{path}: {message}", details={"path": path, **details})


def _has_nested_repeat(pattern: str) -> bool:
    """True for a repeat inside a repeat that has no upper limit, such as ``(a+)+``.

    Such a pattern can take exponential time on some texts. This is a courtesy check that gives the
    user a clear message at once; the real protection is that a regular expression runs in a
    process that is killed when its time is up (see ``regex_worker``).
    """
    try:
        import re._parser as parser  # private, but present in every Python this project supports

        tree = parser.parse(pattern)
    except Exception:  # noqa: BLE001 - an unparsable pattern is reported by re.compile
        return False

    def unbounded(high: int) -> bool:
        return high > 10_000  # MAXREPEAT is a huge number

    def walk(items, inside: bool) -> bool:
        for op, arg in items:
            name = str(op)
            if name in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
                _low, high, sub = arg
                open_ended = unbounded(high)
                if inside and open_ended:
                    return True
                if walk(sub, inside or open_ended):
                    return True
            elif name == "SUBPATTERN":
                if walk(arg[-1], inside):
                    return True
            elif name == "BRANCH":
                if any(walk(branch, inside) for branch in arg[1]):
                    return True
            elif name in ("ASSERT", "ASSERT_NOT"):
                if walk(arg[1], inside):
                    return True
            elif name == "ATOMIC_GROUP":
                if walk(arg, inside):
                    return True
        return False

    return walk(tree, False)


def parse_query(
    data: Any,
    kinds: Iterable[str],
    statuses: Iterable[str],
    *,
    max_depth: int = MAX_DEPTH,
    max_blocks: int = MAX_BLOCKS,
    document_kinds: Iterable[str] | None = None,
) -> Query:
    """Check a search given as JSON data and return it as a ``Query``."""
    allowed_kinds = tuple(kinds)
    allowed_statuses = tuple(statuses)
    if document_kinds is None:
        from issuedeck.features.documents.service import KINDS as document_kinds
    allowed_document_kinds = tuple(document_kinds)
    counter = {"blocks": 0}

    def parse_values(raw: Any, allowed: tuple[str, ...], path: str, what: str) -> tuple[str, ...]:
        if not isinstance(raw, list) or not raw:
            raise _fail(path, f"'values' must be a non-empty list of {what}s")
        values: list[str] = []
        for value in raw:
            if not isinstance(value, str) or value not in allowed:
                raise _fail(path, f"unknown {what} {value!r}; the project has: "
                                  f"{', '.join(allowed)}", allowed=list(allowed))
            if value in values:
                raise _fail(path, f"the {what} {value!r} is listed twice")
            values.append(value)
        return tuple(values)

    def parse_text(raw: dict[str, Any], path: str) -> Text:
        mode = raw.get("mode", "simple")
        if mode not in MODES:
            raise _fail(path, f"'mode' must be one of: {', '.join(MODES)}")
        value = raw.get("value")
        if not isinstance(value, str) or not value.strip():
            raise _fail(path, "'value' must be a text that is not empty")
        fields = raw.get("fields", list(FIELDS))
        if (not isinstance(fields, list) or not fields or len(set(fields)) != len(fields)
                or any(f not in FIELDS for f in fields)):
            raise _fail(path, f"'fields' must be a non-empty list from: {', '.join(FIELDS)}")
        case_sensitive = raw.get("case_sensitive", False)
        if not isinstance(case_sensitive, bool):
            raise _fail(path, "'case_sensitive' must be true or false")
        if mode == "simple":
            if case_sensitive:
                raise _fail(path, "'case_sensitive' works only with mode 'regex' "
                                  "(the full-text index ignores case)")
            if len(value) > MAX_SIMPLE_LENGTH:
                raise _fail(path, f"'value' is longer than {MAX_SIMPLE_LENGTH} characters")
        else:
            if len(value) > MAX_REGEX_LENGTH:
                raise _fail(path, f"the regular expression is longer than {MAX_REGEX_LENGTH} "
                                  "characters")
            try:
                re.compile(value)
            except re.error as exc:
                raise _fail(path, f"the regular expression is not valid: {exc}") from exc
            if _has_nested_repeat(value):
                raise _fail(path, "a repeat inside a repeat, such as (a+)+, can take very long "
                                  "on some texts; write the expression another way")
        return Text(mode, value, tuple(fields), case_sensitive)

    def parse_list(raw: Any, path: str, depth: int) -> tuple[Item, ...]:
        if not isinstance(raw, list) or not raw:
            raise _fail(path, "must be a non-empty list of blocks")
        items: list[Item] = []
        for index, entry in enumerate(raw):
            here = f"{path}[{index}]"
            if not isinstance(entry, dict):
                raise _fail(here, "a block must be an object")
            op = entry.get("op")
            if index == 0 and op is not None:
                raise _fail(here, "the first block has no operator")
            if index > 0 and op not in OPERATORS:
                raise _fail(here, f"'op' must be one of: {', '.join(OPERATORS)}")
            if ("group" in entry) == ("type" in entry):
                raise _fail(here, "a block has either 'type' or 'group'")
            if "group" in entry:
                if set(entry) - _GROUP_KEYS:
                    raise _fail(here, f"unknown keys: {sorted(set(entry) - _GROUP_KEYS)}")
                if depth + 1 > max_depth:
                    raise _fail(here, f"groups can be nested {max_depth} levels at most "
                                      "(the list and one level of groups)")
                node: Text | Document | Kind | Status | Group = Group(
                    parse_list(entry["group"], f"{here}.group", depth + 1))
            else:
                counter["blocks"] += 1
                if counter["blocks"] > max_blocks:
                    raise _fail(here, f"a search has at most {max_blocks} blocks")
                kind = entry["type"]
                if kind == "text":
                    if set(entry) - _TEXT_KEYS:
                        raise _fail(here, f"unknown keys: {sorted(set(entry) - _TEXT_KEYS)}")
                    node = parse_text(entry, here)
                elif kind == "document":
                    if set(entry) - _DOCUMENT_KEYS:
                        raise _fail(here, f"unknown keys: {sorted(set(entry) - _DOCUMENT_KEYS)}")
                    text = parse_text({k: v for k, v in entry.items() if k != "kinds"}, here)
                    of_kinds = (parse_values(entry["kinds"], allowed_document_kinds, here,
                                             "document kind") if "kinds" in entry else ())
                    node = Document(text.mode, text.value, text.fields, text.case_sensitive,
                                    of_kinds)
                elif kind in ("kind", "status"):
                    if set(entry) - _VALUES_KEYS:
                        raise _fail(here, f"unknown keys: {sorted(set(entry) - _VALUES_KEYS)}")
                    if kind == "kind":
                        node = Kind(parse_values(entry.get("values"), allowed_kinds, here, "kind"))
                    else:
                        node = Status(parse_values(
                            entry.get("values"), allowed_statuses, here, "status"))
                else:
                    raise _fail(
                        here, f"unknown block type {kind!r}; use text, document, kind or status")
            items.append(Item(op, node))
        return tuple(items)

    if not isinstance(data, dict) or set(data) - {"items"}:
        raise InvalidSearch("a search is an object with one key, 'items'",
                            details={"path": ""})
    return Query(parse_list(data.get("items"), "items", 1))


# ------------------------------------------------------------------------------ meaning


def terms(items: tuple[Item, ...]) -> list[list[Item]]:
    """A list as OR-terms of AND-chains: ``A and B or C`` is ``[[A, B], [C]]``."""
    result: list[list[Item]] = []
    for item in items:
        if item.op == "or" or not result:
            result.append([])
        result[-1].append(item)
    return result


def describe(query: Query) -> str:
    """The search in words with explicit brackets, so a user sees what will be searched."""

    def node_text(node: Text | Document | Kind | Status | Group) -> str:
        if isinstance(node, Document):
            what = "+".join("name+title" if f == "title" else f for f in node.fields)
            kind = "regex" if node.mode == "regex" else "words"
            case = ", case sensitive" if node.case_sensitive else ""
            of_kinds = f" (document kind is {' or '.join(node.kinds)})" if node.kinds else ""
            return f'a linked document: {what} match {kind} "{node.value}"{case}{of_kinds}'
        if isinstance(node, Text):
            what = "+".join(node.fields)
            kind = "regex" if node.mode == "regex" else "words"
            case = ", case sensitive" if node.case_sensitive else ""
            return f'{what} match {kind} "{node.value}"{case}'
        if isinstance(node, Kind):
            return "kind is " + " or ".join(node.values)
        if isinstance(node, Status):
            return "status is " + " or ".join(node.values)
        return "(" + list_text(node.items) + ")"

    def list_text(items: tuple[Item, ...]) -> str:
        parts = []
        grouped = terms(items)
        for chain in grouped:
            text = " AND ".join(node_text(item.node) for item in chain)
            parts.append(f"({text})" if len(grouped) > 1 and len(chain) > 1 else text)
        return " OR ".join(parts)

    return list_text(query.items)
