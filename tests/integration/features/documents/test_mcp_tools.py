"""FEA-0012 phase 3: the MCP tools of the document store, through the real application."""

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.core.errors import (
    DocumentConflict,
    DocumentExists,
    DocumentNotFound,
    InvalidDocument,
    Unauthorized,
)
from issuedeck.mcp import tools
from issuedeck.mcp.client import IssueDeckClient


@pytest.fixture
async def mcp(tmp_path, monkeypatch):
    """The tools talk to the real application over ASGI with the administrator token."""
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    async with app.router.lifespan_context(app):
        client = IssueDeckClient(
            "http://t", server.api_token.get_secret_value(),
            transport=httpx.ASGITransport(app=app),
        )
        monkeypatch.setattr(tools, "get_client", lambda: client)
        yield server, app, tmp_path
        await client.aclose()


# ------------------------------------------------------------------------------ create


async def test_create_document_from_text(mcp):
    server, _app, _tmp = mcp

    document = await tools.create_document(
        "example", name="Feature request.md", body="# Request\n", kind="request", title="T")

    assert document["id"] == "DOC-0001"
    assert (document["name"], document["kind"], document["title"]) == (
        "Feature request.md", "request", "T")
    assert (server.data_dir / "documents" / "example" / "DOC-0001.json").is_file()


async def test_create_document_reads_one_file_in_the_mcp_process(mcp):
    _server, _app, tmp_path = mcp
    source = tmp_path / "elsewhere" / "My prompt (final)"  # no extension, spaces
    source.parent.mkdir()
    source.write_bytes("# Prompt\n\nÁrvíztűrő\n".encode())  # bytes: no newline translation

    document = await tools.create_document("example", source_path=str(source), kind="prompt")

    assert document["name"] == "My prompt (final)"  # the file name is the default name
    fetched = await tools.get_document("example", document["id"])
    assert fetched["body"] == "# Prompt\n\nÁrvíztűrő\n"


async def test_a_name_can_be_given_with_a_file_and_any_extension_is_fine(mcp):
    _server, _app, tmp_path = mcp
    source = tmp_path / "notes.txt"
    source.write_bytes(b"\xef\xbb\xbfplain notes\r\n")

    document = await tools.create_document("example", name="Meeting notes", source_path=str(source))

    assert document["name"] == "Meeting notes"
    assert (await tools.get_document("example", document["id"]))["body"] == "plain notes\r\n"


async def test_create_document_needs_exactly_one_of_text_and_file(mcp):
    _server, _app, tmp_path = mcp
    (tmp_path / "a.md").write_text("x")

    with pytest.raises(InvalidDocument, match="exactly one"):
        await tools.create_document("example", name="a.md")
    with pytest.raises(InvalidDocument, match="exactly one"):
        await tools.create_document("example", name="a.md", body="x",
                                    source_path=str(tmp_path / "a.md"))
    with pytest.raises(InvalidDocument, match="needs a name"):
        await tools.create_document("example", body="x")


async def test_a_missing_file_and_a_binary_file_are_refused_before_anything_is_sent(mcp):
    server, _app, tmp_path = mcp
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    (tmp_path / "folder.md").mkdir()

    with pytest.raises(InvalidDocument, match="is not a file"):
        await tools.create_document("example", source_path=str(tmp_path / "missing.md"))
    with pytest.raises(InvalidDocument, match="is not a file"):
        await tools.create_document("example", source_path=str(tmp_path / "folder.md"))
    with pytest.raises(InvalidDocument, match="binary"):
        await tools.create_document("example", source_path=str(tmp_path / "photo.png"))

    assert not (server.data_dir / "documents").exists()


async def test_a_binary_text_is_refused_by_the_server(mcp):
    with pytest.raises(InvalidDocument, match="binary"):
        await tools.create_document("example", name="x.md", body="a\x00b")


async def test_a_name_that_is_used_is_an_error_naming_the_document_or_a_new_revision(mcp):
    first = await tools.create_document("example", name="a.md", body="one")

    with pytest.raises(DocumentExists) as error:
        await tools.create_document("example", name="a.md", body="two")
    assert first["id"] in str(error.value)
    assert error.value.details["existing_id"] == first["id"]

    again = await tools.create_document("example", name="a.md", body="two", replace=True)
    assert (again["id"], again["revision"], again["body"]) == (first["id"], 2, "two")


# ------------------------------------------------------------------------------ read


async def test_list_and_get(mcp):
    await tools.create_document("example", name="a.md", body="x", kind="prompt")
    await tools.create_document("example", name="b.md", body="yy", kind="report")

    everything = await tools.list_documents("example")
    assert [d["name"] for d in everything["items"]] == ["a.md", "b.md"]
    assert "body" not in everything["items"][0]
    assert [d["name"] for d in (await tools.list_documents("example", kind="report"))["items"]] \
        == ["b.md"]
    assert [d["id"] for d in (await tools.list_documents("example", name="a.md"))["items"]] \
        == ["DOC-0001"]
    assert (await tools.get_document("example", "DOC-0002"))["body"] == "yy"
    with pytest.raises(DocumentNotFound):
        await tools.get_document("example", "DOC-0099")


async def test_get_document_can_return_an_older_revision(mcp):
    await tools.create_document("example", name="a.md", body="v1")
    await tools.update_document("example", "DOC-0001", revision=1, body="v2")

    document = await tools.get_document("example", "DOC-0001", revision=1)

    assert document["body"] == "v2" and document["revision"] == 2  # the current one
    assert document["requested_revision"]["body"] == "v1"
    assert document["requested_revision"]["current"] is False
    with pytest.raises(DocumentNotFound, match="not kept"):
        await tools.get_document("example", "DOC-0001", revision=9)


# ------------------------------------------------------------------------------ change


async def test_update_document_replaces_with_the_revision_that_was_read(mcp):
    await tools.create_document("example", name="a.md", body="one")

    changed = await tools.update_document("example", "DOC-0001", revision=1, body="two",
                                          title="New title", kind="prompt")

    assert (changed["revision"], changed["body"], changed["title"], changed["kind"]) == (
        2, "two", "New title", "prompt")


async def test_a_stale_revision_is_a_conflict_that_names_the_current_one(mcp):
    await tools.create_document("example", name="a.md", body="one")
    await tools.update_document("example", "DOC-0001", revision=1, body="two")

    with pytest.raises(DocumentConflict) as error:
        await tools.update_document("example", "DOC-0001", revision=1, body="mine")

    assert error.value.details["current_revision"] == 2
    assert "revision 2" in str(error.value)
    assert (await tools.get_document("example", "DOC-0001"))["body"] == "two"


async def test_update_document_can_change_only_the_title_and_kind(mcp):
    await tools.create_document("example", name="a.md", body="keep this text")

    changed = await tools.update_document("example", "DOC-0001", revision=1, title="Only a title")

    assert (changed["revision"], changed["body"], changed["title"]) == (
        1, "keep this text", "Only a title")


async def test_append_needs_no_revision(mcp):
    await tools.create_document("example", name="log.md", body="# Log")

    appended =await tools.update_document("example", "DOC-0001", append_body="entry one")
    again = await tools.update_document("example", "DOC-0001", append_body="entry two")

    assert appended["body"] == "# Log\nentry one"
    assert again["body"] == "# Log\nentry one\nentry two" and again["revision"] == 3


async def test_update_document_refuses_unclear_calls(mcp):
    await tools.create_document("example", name="a.md", body="x")

    with pytest.raises(InvalidDocument, match="revision"):
        await tools.update_document("example", "DOC-0001", body="y")
    with pytest.raises(InvalidDocument, match="cannot be combined"):
        await tools.update_document("example", "DOC-0001", revision=1, body="y", append_body="z")
    with pytest.raises(InvalidDocument, match="cannot be combined"):
        await tools.update_document("example", "DOC-0001", append_body="z", title="t")
    with pytest.raises(DocumentNotFound):
        await tools.update_document("example", "DOC-0099", append_body="z")


# ------------------------------------------------------------------------------ delete, history


async def test_revisions_are_listed_and_delete_removes_the_document(mcp):
    server, _app, _tmp = mcp
    await tools.create_document("example", name="a.md", body="v1")
    await tools.update_document("example", "DOC-0001", revision=1, body="v2")

    rows = (await tools.list_document_revisions("example", "DOC-0001"))["items"]
    assert [(r["revision"], r["current"]) for r in rows] == [(2, True), (1, False)]

    assert await tools.delete_document("example", "DOC-0001") == {"deleted": "DOC-0001"}

    assert (await tools.list_documents("example"))["items"] == []
    assert not (server.data_dir / "documents" / "example" / "DOC-0001.json").exists()
    with pytest.raises(DocumentNotFound):
        await tools.delete_document("example", "DOC-0001")


async def test_a_wrong_token_is_reported_as_unauthorized(mcp, monkeypatch):
    _server, app, _tmp = mcp
    bad = IssueDeckClient("http://t", "wrong", transport=httpx.ASGITransport(app=app))
    monkeypatch.setattr(tools, "get_client", lambda: bad)

    with pytest.raises(Unauthorized):
        await tools.list_documents("example")
    await bad.aclose()


async def test_the_document_tools_are_registered_in_the_mcp_server():
    from issuedeck.mcp import __main__ as entry

    server = entry.mcp_server
    found = await (server.get_tools() if hasattr(server, "get_tools") else server.list_tools())
    names = set(found) if isinstance(found, dict) else {tool.name for tool in found}

    assert {"create_document", "get_document", "list_documents", "update_document",
            "delete_document", "list_document_revisions"} <= names
