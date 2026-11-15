"""Surgical edits of ``server.toml`` for token management (IS-0003).

The file is edited as text so comments and every other setting stay exactly as
the owner wrote them. The result is validated with ``ServerConfig`` before it is
written, and the write is atomic.
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

from pydantic import ValidationError

from issuedeck.core.config import ServerConfig
from issuedeck.core.errors import InvalidSetting

_API_TOKEN = re.compile(r"^(\s*api_token\s*=\s*)(\"(?:[^\"\\]|\\.)*\"|'[^']*')(.*)$")
_TOKENS_HEADER = re.compile(r"^\s*\[\[\s*tokens\s*\]\]\s*(#.*)?$")
_ANY_HEADER = re.compile(r"^\s*\[")


def mask_token(value: str) -> str:
    """A recognisable but useless preview of a token, e.g. ``AbCd...WxYz``."""
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _field(name: str) -> re.Pattern[str]:
    return re.compile(rf"^(\s*{name}\s*=\s*)(.*?)(\s*(?:#.*)?)$")


def _token_blocks(lines: list[str]) -> list[tuple[int, int, str | None]]:
    """(start, end, name) of every ``[[tokens]]`` block; ``end`` is exclusive."""
    blocks: list[tuple[int, int, str | None]] = []
    index = 0
    while index < len(lines):
        if _TOKENS_HEADER.match(lines[index].rstrip("\r\n")):
            start = index
            index += 1
            while index < len(lines) and not _ANY_HEADER.match(lines[index]):
                index += 1
            name = None
            for line in lines[start:index]:
                match = _field("name").match(line.rstrip("\r\n"))
                if match:
                    name = match.group(2).strip().strip("\"'")
                    break
            blocks.append((start, index, name))
        else:
            index += 1
    return blocks


def _find_block(lines: list[str], name: str) -> tuple[int, int]:
    for start, end, block_name in _token_blocks(lines):
        if block_name == name:
            return start, end
    raise InvalidSetting(
        f"token '{name}' was not found in server.toml", details={"token": name},
    )


def _replace_field(lines: list[str], start: int, end: int, field: str, value: str) -> None:
    pattern = _field(field)
    for i in range(start, end):
        stripped = lines[i].rstrip("\r\n")
        match = pattern.match(stripped)
        if match:
            newline = lines[i][len(stripped):]
            lines[i] = f"{match.group(1)}{value}{match.group(3)}{newline}"
            return
    raise InvalidSetting(f"server.toml has no '{field}' for this token", details={"field": field})


def set_api_token(text: str, new_value: str) -> str:
    """Replace the top-level ``api_token`` (the administrator token)."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if _ANY_HEADER.match(line):
            break
        stripped = line.rstrip("\r\n")
        match = _API_TOKEN.match(stripped)
        if match:
            newline = line[len(stripped):]
            lines[i] = f"{match.group(1)}{_quote(new_value)}{match.group(3)}{newline}"
            return "".join(lines)
    raise InvalidSetting("api_token was not found in server.toml")


def set_token_value(text: str, name: str, new_value: str) -> str:
    lines = text.splitlines(keepends=True)
    start, end = _find_block(lines, name)
    _replace_field(lines, start, end, "token", _quote(new_value))
    return "".join(lines)


def update_token(text: str, name: str, new_name: str, scopes: list[str]) -> str:
    lines = text.splitlines(keepends=True)
    start, end = _find_block(lines, name)
    _replace_field(lines, start, end, "name", _quote(new_name))
    _replace_field(lines, start, end, "scopes", json.dumps(scopes))
    return "".join(lines)


def validate_server_text(text: str) -> ServerConfig:
    try:
        return ServerConfig.model_validate(tomllib.loads(text))
    except (tomllib.TOMLDecodeError, ValidationError, ValueError) as exc:
        raise InvalidSetting(
            f"the change would make server.toml invalid and was not saved: {exc}",
        ) from exc


def read_server_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_server_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)
