"""FEA-0012 phase 2: the dashboard pages of the project document store.

They run against the real application (login, session cookie), because the cookie routes
and the pages together are what the browser uses.
"""

import json
import re

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config

PAGE = "/dashboard/example/documents"
API = "/api/v1/projects/example/documents"


@pytest.fixture
async def shell(tmp_path):
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    token = server.api_token.get_secret_value()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            await client.post("/dashboard/login", data={"token": token})
            yield client, app, server


def _files(*items):
    return [("files", (name, data, "text/markdown")) for name, data in items]


async def _upload(client, *items, **form):
    return await client.post(PAGE, files=_files(*items), data=form)


def _embedded_text(page):
    """The Markdown source the view page hands to the renderer (as the browser reads it)."""
    raw = re.search(r'<script type="application/json" id="md-source">(.*?)</script>',
                    page.text, re.S).group(1)
    return json.loads(raw)


async def test_the_sidebar_links_to_the_documents_page(shell):
    client, _app, _server = shell

    page = await client.get("/dashboard/example/list")

    assert 'href="/dashboard/example/documents"' in page.text


async def test_the_page_is_empty_at_first(shell):
    client, _app, _server = shell

    page = await client.get(PAGE)

    assert page.status_code == 200
    assert "data-documents-empty" in page.text and "data-documents-table" not in page.text
    assert 'enctype="multipart/form-data"' in page.text
    assert "0 document(s)" in page.text


async def test_several_markdown_files_are_uploaded_with_any_names(shell):
    client, _app, server = shell

    page = await _upload(
        client, ("feature_request.md", b"# Request\n"), ("Árvíztűrő terv", b"# Terv\n"),
        ("notes.txt", b"plain notes"), kind="request",
    )

    assert page.status_code == 200
    assert "data-documents-stored" in page.text and "data-documents-errors" not in page.text
    for name in ("feature_request.md", "Árvíztűrő terv", "notes.txt"):
        assert name in page.text
    assert "3 document(s)" in page.text
    folder = server.data_dir / "documents" / "example"
    assert sorted(p.name for p in folder.iterdir()) == [
        "DOC-0001.json", "DOC-0002.json", "DOC-0003.json", "documents.json"]
    stored = json.loads((folder / "DOC-0001.json").read_text(encoding="utf-8"))
    assert (stored["kind"], stored["actor"], stored["body"]) == (
        "request", "dashboard", "# Request\n")


async def test_a_binary_file_is_refused_and_the_other_files_are_stored(shell):
    client, _app, _server = shell

    page = await _upload(
        client, ("good.md", b"# ok"), ("photo.png", b"\x89PNG\r\n\x1a\n\x00\x00"))

    assert page.status_code == 200
    assert "good.md" in page.text
    assert "data-documents-errors" in page.text
    assert "photo.png" in page.text and "binary" in page.text
    assert "1 document(s)" in page.text  # only the text file was stored


async def test_when_every_file_is_refused_the_page_answers_422(shell):
    client, _app, _server = shell

    page = await _upload(client, ("photo.png", b"\x00\x01\x02"))

    assert page.status_code == 422
    assert "data-documents-errors" in page.text and "data-documents-stored" not in page.text


async def test_a_submit_without_a_file_asks_to_choose_one(shell):
    client, _app, _server = shell

    page = await client.post(PAGE, files=[("files", ("", b"", "application/octet-stream"))])

    assert page.status_code == 422
    assert "Choose at least one file." in page.text


async def test_a_name_that_exists_is_not_replaced_without_the_confirmation(shell):
    client, _app, server = shell
    await _upload(client, ("a.md", b"first"))

    refused = await _upload(client, ("a.md", b"second"))

    assert refused.status_code == 422
    assert "a document with this name exists" in refused.text
    stored = json.loads((server.data_dir / "documents" / "example" / "DOC-0001.json")
                        .read_text(encoding="utf-8"))
    assert (stored["body"], stored["revision"]) == ("first", 1)

    replaced = await _upload(client, ("a.md", b"second"), replace="1")

    assert replaced.status_code == 200 and "DOC-0001 a.md (r2)" in replaced.text
    stored = json.loads((server.data_dir / "documents" / "example" / "DOC-0001.json")
                        .read_text(encoding="utf-8"))
    assert (stored["body"], stored["revision"]) == ("second", 2)
    assert [r["body"] for r in stored["revisions"]] == ["first"]


async def test_the_upload_form_knows_the_existing_names_for_its_confirmation(shell):
    client, _app, _server = shell
    # (a double quote in a file name would arrive as %22: browsers write it so in the upload)
    await _upload(client, ("a.md", b"x"), ("it's a <name> & more.md", b"y"))

    page = await client.get(PAGE)

    raw = re.search(r"data-existing='(.*?)'\n", page.text, re.S).group(1)
    assert "'" not in raw  # escaped, so it cannot end the attribute
    assert json.loads(raw) == ["a.md", "it's a <name> & more.md"]
    assert "onsubmit=\"return confirmReplace(this)\"" in page.text
    assert "Replace it with a new revision?" in page.text


async def test_the_view_page_hands_the_text_to_the_safe_renderer(shell):
    client, _app, _server = shell
    text = "# Title\n\n</script><script>alert(1)</script>\n\n`a >= b` \"q\" 'q' é 日本語\n"
    await _upload(client, ("plan.md", text.encode()))

    page = await client.get(f"{PAGE}/DOC-0001")

    assert page.status_code == 200
    assert _embedded_text(page) == text  # exactly the text, and it cannot close the script
    assert page.text.count("<script>alert(1)</script>") == 0
    assert 'id="md-rendered" class="md-content"' in page.text
    assert 'window.renderMarkdown(JSON.parse(sourceEl.textContent), "example")' in page.text
    assert "plan.md" in page.text and "DOC-0001" in page.text


async def test_an_empty_document_shows_the_empty_text(shell):
    client, _app, _server = shell
    await _upload(client, ("empty.md", b""))

    page = await client.get(f"{PAGE}/DOC-0001")

    assert "data-document-empty" in page.text and 'id="md-source"' not in page.text


async def test_the_edit_page_saves_a_new_revision(shell):
    client, _app, server = shell
    await _upload(client, ("a.md", b"one"))

    form = await client.get(f"{PAGE}/DOC-0001/edit")
    assert 'name="revision" value="1"' in form.text and "one" in form.text

    saved = await client.post(f"{PAGE}/DOC-0001/edit", follow_redirects=False,
                              data={"body": "two", "revision": "1", "title": "A title",
                                    "kind": "report"})

    assert saved.status_code == 303 and saved.headers["location"] == f"{PAGE}/DOC-0001"
    stored = json.loads((server.data_dir / "documents" / "example" / "DOC-0001.json")
                        .read_text(encoding="utf-8"))
    assert (stored["body"], stored["revision"], stored["title"], stored["kind"]) == (
        "two", 2, "A title", "report")


async def test_a_stale_save_gets_409_keeps_the_typed_text_and_names_the_new_revision(shell):
    client, _app, server = shell
    await _upload(client, ("a.md", b"one"))
    await client.post(f"{PAGE}/DOC-0001/edit", follow_redirects=False,
                      data={"body": "two by someone else", "revision": "1", "title": "",
                            "kind": "other"})

    stale = await client.post(f"{PAGE}/DOC-0001/edit",
                              data={"body": "MY TEXT", "revision": "1", "title": "",
                                    "kind": "other"})

    assert stale.status_code == 409
    assert "data-document-conflict" in stale.text
    assert "now revision 2" in stale.text
    assert "MY TEXT" in stale.text  # what was typed is not lost
    assert 'name="revision" value="2"' in stale.text  # saving again is a conscious replace
    stored = json.loads((server.data_dir / "documents" / "example" / "DOC-0001.json")
                        .read_text(encoding="utf-8"))
    assert stored["body"] == "two by someone else"


async def test_the_edit_page_refuses_a_bad_kind_and_keeps_the_text(shell):
    client, _app, _server = shell
    await _upload(client, ("a.md", b"one"))

    bad = await client.post(f"{PAGE}/DOC-0001/edit",
                            data={"body": "typed", "revision": "1", "title": "", "kind": "essay"})

    assert bad.status_code == 422 and "data-document-error" in bad.text and "typed" in bad.text


async def test_the_history_lists_the_revisions_and_restores_one(shell):
    client, _app, server = shell
    await _upload(client, ("a.md", b"v1"))
    await client.post(f"{PAGE}/DOC-0001/edit", follow_redirects=False,
                      data={"body": "v2", "revision": "1", "title": "", "kind": "other"})

    history = await client.get(f"{PAGE}/DOC-0001/history")

    assert history.status_code == 200
    assert 'data-revision="2"' in history.text and 'data-revision="1"' in history.text
    assert "The last 50 revisions are kept." in history.text
    old = await client.get(f"{PAGE}/DOC-0001/revisions/1")
    assert "data-old-revision" in old.text and _embedded_text(old) == "v1"
    assert f'action="{PAGE}/DOC-0001/restore/1"' in old.text

    restored = await client.post(f"{PAGE}/DOC-0001/restore/1", follow_redirects=False)

    assert restored.status_code == 303
    stored = json.loads((server.data_dir / "documents" / "example" / "DOC-0001.json")
                        .read_text(encoding="utf-8"))
    assert (stored["body"], stored["revision"]) == ("v1", 3)
    assert (await client.get(f"{PAGE}/DOC-0001/revisions/9")).status_code == 404


async def test_the_files_are_served_for_download_with_safe_headers(shell):
    client, _app, _server = shell
    await _upload(client, ("My plan.md", b"# Plan v1\n"))
    await client.post(f"{PAGE}/DOC-0001/edit", follow_redirects=False,
                      data={"body": "# Plan v2\n", "revision": "1", "title": "", "kind": "other"})

    shown = await client.get(f"{PAGE}/DOC-0001/file")
    saved = await client.get(f"{PAGE}/DOC-0001/file?download=true")
    old = await client.get(f"{PAGE}/DOC-0001/revisions/1/file?download=true")

    assert shown.text == "# Plan v2\n" and "content-disposition" not in shown.headers
    assert shown.headers["content-type"].startswith("text/markdown")
    assert shown.headers["x-content-type-options"] == "nosniff"
    assert saved.headers["content-disposition"].startswith('attachment; filename="DOC-0001.md"')
    assert "My%20plan.md" in saved.headers["content-disposition"]
    assert old.text == "# Plan v1\n"
    assert old.headers["etag"] != shown.headers["etag"]


async def test_delete_removes_the_document_after_the_confirmation_text(shell):
    client, _app, server = shell
    await _upload(client, ("Old notes.md", b"x"))
    page = await client.get(f"{PAGE}/DOC-0001")
    assert "Delete Old notes.md? All its revisions are deleted too." in page.text

    deleted = await client.post(f"{PAGE}/DOC-0001/delete", follow_redirects=False)

    assert deleted.status_code == 303
    after = await client.get(deleted.headers["location"])
    assert "Deleted DOC-0001 Old notes.md." in after.text
    assert "data-documents-empty" in after.text
    assert not (server.data_dir / "documents" / "example" / "DOC-0001.json").exists()


async def test_the_pages_need_a_session(shell):
    client, app, _server = shell
    await _upload(client, ("a.md", b"x"))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://t") as anonymous:
        for url in (PAGE, f"{PAGE}/DOC-0001", f"{PAGE}/DOC-0001/edit",
                    f"{PAGE}/DOC-0001/history", f"{PAGE}/DOC-0001/file"):
            response = await anonymous.get(url)
            assert response.status_code == 303
            assert "/dashboard/login" in response.headers["location"]
        assert (await anonymous.post(PAGE, files=_files(("b.md", b"y")))).status_code == 401
        assert (await anonymous.post(f"{PAGE}/DOC-0001/delete")).status_code == 401


async def test_an_unknown_document_is_a_404(shell):
    client, _app, _server = shell

    for url in (f"{PAGE}/DOC-0009", f"{PAGE}/DOC-0009/edit", f"{PAGE}/DOC-0009/history",
                f"{PAGE}/DOC-0009/file", "/dashboard/nope/documents"):
        assert (await client.get(url)).status_code == 404, url
    assert (await client.post(f"{PAGE}/DOC-0009/delete")).status_code == 404


@pytest.mark.parametrize(("lang", "title"), [("hu", "Dokumentumok"), ("zh-CN", "文档"),
                                             ("en", "Documents")])
async def test_the_page_is_translated(shell, lang, title):
    client, _app, _server = shell
    client.cookies.set("issuedeck_lang", lang)

    page = await client.get(PAGE)

    assert "<h1" in page.text and title in page.text.split("</h1>")[0]
