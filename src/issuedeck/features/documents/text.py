"""What a document may contain and what it may be called (FEA-0012).

The owner's rules: no distinction between files by name or extension, and one content rule:
the file is Markdown text, not a binary. Text is UTF-8 without a NUL byte; anything else is
refused as binary. Nothing else about the content is checked (any text is valid Markdown) and
there is no size limit.
"""

from __future__ import annotations

import re

from issuedeck.core.errors import InvalidDocument

BOM = "\ufeff"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FOLDERS = re.compile(r"[\\/]")


def _binary(reason: str) -> InvalidDocument:
    return InvalidDocument(
        f"the file is a binary, not a Markdown text file ({reason})",
        details={"reason": "binary"},
    )


def decode_upload(data: bytes) -> str:
    """The text of an uploaded file; raises InvalidDocument for a binary file."""
    if b"\x00" in data:
        raise _binary("it contains a NUL byte")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _binary("it is not valid UTF-8") from exc
    return text.removeprefix(BOM)


def check_body(text: str) -> str:
    """The text of a document given as a string (API, MCP); same rules as an upload."""
    if not isinstance(text, str):
        raise InvalidDocument("the text of a document must be a string",
                              details={"reason": "type"})
    if "\x00" in text:
        raise _binary("it contains a NUL character")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _binary("it is not valid UTF-8 text") from exc
    return text.removeprefix(BOM)


def clean_name(name: str | None) -> str:
    """The name of a document: free text, only made safe, never used as a path.

    A folder part is dropped (an uploaded file may arrive as ``C:\\docs\\a.md``), control
    characters and the spaces at both ends are removed. There is no rule about the characters or
    the extension; the name only must not be empty.
    """
    last = _FOLDERS.split(name or "")[-1]
    cleaned = _CONTROL.sub("", last).strip()
    if not cleaned:
        raise InvalidDocument("a document needs a name", details={"reason": "name"})
    return cleaned
