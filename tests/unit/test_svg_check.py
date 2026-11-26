"""FEA-0013: the safety check of SVG images."""

import pytest

from issuedeck.core.errors import InvalidImage
from issuedeck.features.images.svg_check import validate_svg

NS = 'xmlns="http://www.w3.org/2000/svg"'
GOOD = f'<svg {NS} viewBox="0 0 10 10"><rect width="10" height="10" fill="red"/></svg>'.encode()


def svg(inner: str, attrs: str = "") -> bytes:
    return f"<svg {NS} {attrs}>{inner}</svg>".encode()


def test_a_plain_svg_is_accepted():
    validate_svg(GOOD)


def test_a_realistic_svg_is_accepted():
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- a diagram -->\n"
        f'<svg {NS} xmlns:xlink="http://www.w3.org/1999/xlink" width="100" height="50">'
        '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient>'
        '<style>.a { fill: url(#g); stroke: #000 }</style></defs>'
        '<g class="a"><path d="M0 0L10 10"/><use xlink:href="#p"/>'
        '<text>Résistance <![CDATA[<5 Ω>]]></text></g></svg>'
    ).encode()
    validate_svg(data)


def test_a_byte_order_mark_is_accepted():
    validate_svg(b"\xef\xbb\xbf" + GOOD)


@pytest.mark.parametrize(("data", "reason"), [
    (b"", "empty"),
    (b"   \n", "empty"),
    (b"\x89PNG\r\n\x1a\n\x00\x00", "encoding"),
    (b"\xff\xfe<\x00s\x00v\x00g\x00>\x00", "encoding"),
    (b"not xml at all", "xml"),
    (b"<svg", "xml"),
    (b"<html><body/></html>", "root"),
    (b"<svg><rect/></svg>", "root"),
    (b'<svg xmlns="http://example.com/x"/>', "root"),
    (f'<?xml version="1.0" encoding="ISO-8859-1"?><svg {NS}/>'.encode(), "encoding"),
], ids=["empty", "blank", "png", "utf16", "text", "truncated", "html", "no-namespace",
        "wrong-namespace", "latin1"])
def test_a_file_that_is_not_an_svg_is_refused(data, reason):
    with pytest.raises(InvalidImage) as error:
        validate_svg(data)
    assert error.value.details["reason"] == reason


@pytest.mark.parametrize(("data", "reason"), [
    (svg("<script>alert(1)</script>"), "element"),
    (svg('<SCRIPT type="x">1</SCRIPT>'), "element"),
    (svg('<foreignObject><body xmlns="http://www.w3.org/1999/xhtml"/></foreignObject>'),
     "element"),
    (svg('<iframe src="x"/>'), "element"),
    (svg('<rect onclick="alert(1)"/>'), "event"),
    (svg('<rect ONLOAD="x()"/>'), "event"),
    (svg("<rect/>", 'onload="x()"'), "event"),
    (svg('<a href="javascript:alert(1)"><rect/></a>'), "external"),
    (svg('<a xmlns:x="http://www.w3.org/1999/xlink" x:href="https://evil.test/"/>'),
     "external"),
    (svg('<image href="https://evil.test/a.png"/>'), "external"),
    (svg('<image href="data:image/png;base64,AAAA"/>'), "external"),
    (svg('<rect fill="java&#x09;script:alert(1)"/>'), "script_url"),
    (svg('<rect style="fill:url(https://evil.test/x)"/>'), "style"),
    (svg("<style>@import url(https://evil.test/a.css);</style>"), "style"),
    (svg("<style>.a { background: url('http://evil.test/x') }</style>"), "style"),
    (svg('<rect style="width: expression(alert(1))"/>'), "style"),
    (svg('<a><set attributeName="href" to="#x"/></a>'), "animation"),
    (svg('<animate attributeName="xlink:href" values="#a;#b"/>'), "animation"),
], ids=["script", "script-upper", "foreignobject", "iframe", "onclick", "onload-upper",
        "onload-root", "js-href", "xlink-https", "image-https", "image-data",
        "split-javascript", "css-url", "css-import", "css-url-quoted", "css-expression",
        "animate-set", "animate-xlink"])
def test_an_unsafe_svg_is_refused_with_the_reason(data, reason):
    with pytest.raises(InvalidImage) as error:
        validate_svg(data)
    assert error.value.details["reason"] == reason
    assert error.value.message.startswith("SVG refused: ")


@pytest.mark.parametrize("data", [
    b'<?xml version="1.0"?><!DOCTYPE svg SYSTEM "http://evil.test/x.dtd"><svg '
    + NS.encode() + b"/>",
    b'<!DOCTYPE svg [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><svg '
    + NS.encode() + b">&b;</svg>",
    b'<!doctype svg><svg ' + NS.encode() + b"/>",
    b'<!ENTITY x "y"><svg ' + NS.encode() + b"/>",
], ids=["external-dtd", "billion-laughs", "doctype-lower", "entity"])
def test_a_doctype_or_entity_is_refused(data):
    with pytest.raises(InvalidImage) as error:
        validate_svg(data)
    assert error.value.details["reason"] == "doctype"


def test_a_style_sheet_instruction_is_refused():
    data = (b'<?xml version="1.0"?><?xml-stylesheet href="https://evil.test/a.css"?>'
            + svg("<rect/>"))
    with pytest.raises(InvalidImage) as error:
        validate_svg(data)
    assert error.value.details["reason"] == "processing_instruction"
