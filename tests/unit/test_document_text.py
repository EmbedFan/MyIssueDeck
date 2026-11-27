"""FEA-0012: what a document may contain and what it may be called."""

import pytest

from issuedeck.core.errors import InvalidDocument
from issuedeck.features.documents.text import check_body, clean_name, decode_upload


def test_a_markdown_file_is_decoded_and_a_byte_order_mark_is_removed():
    assert decode_upload("# Title\n\ntext é ő 日本語\n".encode()) == "# Title\n\ntext é ő 日本語\n"
    assert decode_upload(b"\xef\xbb\xbf# Title") == "# Title"


def test_line_endings_are_kept_as_they_are():
    assert decode_upload(b"a\r\nb\r\n") == "a\r\nb\r\n"


def test_an_empty_file_is_a_valid_document():
    assert decode_upload(b"") == ""


@pytest.mark.parametrize("data", [
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    b"PK\x03\x04\x14\x00\x00\x00\x08\x00",
    b"text with a NUL \x00 byte",
    b"\xff\xfe#\x00 \x00t\x00",
    b"caf\xe9 in latin-1",
], ids=["png", "zip", "nul", "utf16", "latin1"])
def test_a_binary_file_is_refused(data):
    with pytest.raises(InvalidDocument) as error:
        decode_upload(data)
    assert error.value.details["reason"] == "binary"
    assert "binary" in error.value.message


def test_a_text_given_as_a_string_follows_the_same_rules():
    assert check_body("# ok\n") == "# ok\n"
    assert check_body("\ufeff# bom") == "# bom"
    with pytest.raises(InvalidDocument):
        check_body("a\x00b")
    with pytest.raises(InvalidDocument):
        check_body("lone surrogate \ud800")
    with pytest.raises(InvalidDocument):
        check_body(123)  # type: ignore[arg-type]


@pytest.mark.parametrize(("given", "cleaned"), [
    ("feature_request.md", "feature_request.md"),
    ("My Prompt (final) v2.markdown", "My Prompt (final) v2.markdown"),
    ("no extension at all", "no extension at all"),
    ("notes.txt", "notes.txt"),
    ("árvíztűrő tükörfúrógép.MD", "árvíztűrő tükörfúrógép.MD"),
    ("日本語のメモ", "日本語のメモ"),
    ("  spaced  .md  ", "spaced  .md"),
    ("C:\\Users\\me\\docs\\a.md", "a.md"),
    ("../../etc/passwd", "passwd"),
    ("folder/sub/b.md", "b.md"),
    ("tab\tand\nnewline.md", "tabandnewline.md"),
    ("..", ".."),
], ids=str)
def test_any_name_is_accepted_and_only_made_safe(given, cleaned):
    assert clean_name(given) == cleaned


@pytest.mark.parametrize("given", ["", "   ", None, "\x00\x01", "folder/", "C:\\dir\\"])
def test_a_name_must_not_be_empty(given):
    with pytest.raises(InvalidDocument) as error:
        clean_name(given)
    assert error.value.details["reason"] == "name"
