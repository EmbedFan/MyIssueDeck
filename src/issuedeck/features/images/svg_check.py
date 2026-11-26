"""Safety check for SVG images (FEA-0013).

SVG is the only image type the store accepts. An SVG file is XML that a browser can run
script in, so a file is accepted only when it is well-formed, has the SVG root element, and
holds nothing that can run script or load another resource. A file that fails is refused with
the reason; it is never rewritten.

The check needs no extra library: any ``<!`` declaration other than a comment or a CDATA
section is refused before parsing (so there is no DOCTYPE and no entity, and the parser has
nothing to expand or fetch), and the standard library parser reads the rest.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from issuedeck.core.errors import InvalidImage

SVG_NS = "http://www.w3.org/2000/svg"
MIME_TYPE = "image/svg+xml"

# Elements that run script, embed another document, or load or configure outside resources.
FORBIDDEN_ELEMENTS = frozenset({
    "script", "foreignobject", "iframe", "embed", "object", "audio", "video", "canvas",
    "link", "meta", "base", "handler", "listener",
})
ANIMATION_ELEMENTS = frozenset({"animate", "set", "animatemotion", "animatetransform"})
SCRIPT_URL = re.compile(r"(?:javascript|vbscript|livescript|data)\s*:", re.IGNORECASE)
DECLARATION = re.compile(r"<!(?!--|\[CDATA\[)")
PROCESSING = re.compile(r"<\?")
XML_DECL = re.compile(r"^<\?xml\s[^>]*\?>")
ENCODING = re.compile(r"""encoding\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
CSS_URL = re.compile(r"""url\(\s*["']?\s*(?!#)""", re.IGNORECASE)
CSS_DANGER = re.compile(r"@import|expression\s*\(|behaviou?r\s*:|-moz-binding", re.IGNORECASE)


def _refuse(reason: str, code: str) -> InvalidImage:
    return InvalidImage(f"SVG refused: {reason}", details={"reason": code})


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _check_css(css: str) -> None:
    if CSS_DANGER.search(css) or CSS_URL.search(css) or SCRIPT_URL.search(css):
        raise _refuse("a style refers to an outside resource or runs code", "style")


def _decode(data: bytes) -> str:
    if not data.strip():
        raise _refuse("the file is empty", "empty")
    if b"\x00" in data:
        raise _refuse("the file is not UTF-8 text", "encoding")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _refuse("the file is not valid UTF-8", "encoding") from exc


def validate_svg(data: bytes) -> None:
    """Raise InvalidImage unless ``data`` is a safe, well-formed SVG file."""
    text = _decode(data).lstrip()

    declaration = XML_DECL.match(text)
    if declaration:
        encoding = ENCODING.search(declaration.group(0))
        if encoding and encoding.group(1).lower().replace("_", "-") not in {"utf-8", "utf8"}:
            raise _refuse("the XML declaration names an encoding other than UTF-8", "encoding")
    body = text[declaration.end():] if declaration else text
    if PROCESSING.search(body):
        raise _refuse("a processing instruction (for example a style sheet) is not allowed",
                      "processing_instruction")
    if DECLARATION.search(text):
        raise _refuse("a DOCTYPE or entity declaration is not allowed", "doctype")

    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise _refuse(f"the file is not well-formed XML ({exc})", "xml") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise _refuse(f'the root element must be <svg xmlns="{SVG_NS}">', "root")

    for element in root.iter():
        name = _local(element.tag) if isinstance(element.tag, str) else ""
        if name in FORBIDDEN_ELEMENTS:
            raise _refuse(f"the <{name}> element is not allowed", "element")
        if name == "style":
            _check_css(element.text or "")
        for attribute, value in element.attrib.items():
            attribute_name = _local(attribute)
            compact = re.sub(r"[\s\x00-\x1f]+", "", value)
            if attribute_name.startswith("on"):
                raise _refuse(f"the event attribute '{attribute_name}' is not allowed", "event")
            if attribute_name == "href" and not compact.startswith("#"):
                raise _refuse("a link or image refers to an outside resource "
                              "(only #fragment references are allowed)", "external")
            if SCRIPT_URL.search(compact):
                raise _refuse("an attribute holds a javascript: or data: address", "script_url")
            if attribute_name == "style":
                _check_css(value)
            if (name in ANIMATION_ELEMENTS and attribute_name == "attributename"
                    and value.rsplit(":", 1)[-1].strip().lower() == "href"):
                raise _refuse("an animation changes a link address", "animation")
