"""FEA-0012 phase 5: documents linked to items (API, dashboard, events, deleting a document)."""

import re

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config

API = "/api/v1/projects/example"
DASH = "/dashboard/example"


@pytest.fixture
async def world(tmp_path):
    """The real application: an API client (bearer token) and a dashboard client (cookie)."""
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    token = server.api_token.get_secret_value()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as dash, \
                httpx.AsyncClient(transport=transport, base_url="http://t",
                                  headers={"Authorization": f"Bearer {token}"}) as api:
            await dash.post("/dashboard/login", data={"token": token})
            yield api, dash, server


async def _item(api, title="An item"):
    r = await api.post(f"{API}/items", json={"kind": "feature", "title": title})
    assert r.status_code == 201, r.text
    return r.json()["local_id"]


async def _document(api, name="plan.md", body="# Plan\n", **extra):
    r = await api.post(f"{API}/documents", json={"name": name, "body": body, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _events(api, local_id):
    detail = (await api.get(f"{API}/items/{local_id}")).json()
    return detail["events"]


async def test_link_list_and_unlink_through_the_api(world):
    api, _dash, _server = world
    local_id = await _item(api)
    first = await _document(api, "a.md")
    second = await _document(api, "b.md", kind="report")

    linked = await api.post(f"{API}/items/{local_id}/documents", json={"document_id": first})
    await api.post(f"{API}/items/{local_id}/documents", json={"document_id": second})

    assert linked.status_code == 201 and linked.json()["id"] == first
    assert "body" not in linked.json()
    listing = (await api.get(f"{API}/items/{local_id}/documents")).json()["items"]
    assert [(d["id"], d["kind"]) for d in listing] == [(first, "other"), (second, "report")]

    removed = await api.delete(f"{API}/items/{local_id}/documents/{first}")

    assert removed.status_code == 204
    after = (await api.get(f"{API}/items/{local_id}/documents")).json()["items"]
    assert [d["id"] for d in after] == [second]
    assert (await api.get(f"{API}/documents/{first}")).status_code == 200  # the document stays


async def test_linking_twice_is_harmless_and_writes_one_event(world):
    api, _dash, _server = world
    local_id = await _item(api)
    document = await _document(api)

    for _ in range(2):
        r = await api.post(f"{API}/items/{local_id}/documents", json={"document_id": document})
        assert r.status_code == 201

    assert len((await api.get(f"{API}/items/{local_id}/documents")).json()["items"]) == 1
    assert [e["event_type"] for e in await _events(api, local_id)].count("document_linked") == 1


async def test_link_changes_are_written_to_the_activity(world):
    api, _dash, _server = world
    local_id = await _item(api)
    document = await _document(api, "Feature request.md")

    await api.post(f"{API}/items/{local_id}/documents", json={"document_id": document})
    await api.delete(f"{API}/items/{local_id}/documents/{document}")

    events = [e for e in await _events(api, local_id) if e["event_type"].startswith("document_")]
    assert sorted(e["event_type"] for e in events) == ["document_linked", "document_unlinked"]
    assert all(e["metadata"]["document_id"] == document for e in events)
    assert f"Linked document {document} (Feature request.md)." in [e["body"] for e in events]


async def test_unknown_item_document_or_link_is_a_404(world):
    api, _dash, _server = world
    local_id = await _item(api)
    document = await _document(api)

    no_item = await api.post(f"{API}/items/FEAT-9999/documents", json={"document_id": document})
    no_document = await api.post(f"{API}/items/{local_id}/documents",
                                 json={"document_id": "DOC-0099"})
    not_linked = await api.delete(f"{API}/items/{local_id}/documents/{document}")

    assert no_item.status_code == 404 and no_item.json()["error"]["code"] == "item_not_found"
    assert no_document.status_code == 404
    assert no_document.json()["error"]["code"] == "document_not_found"
    assert not_linked.status_code == 404


async def test_deleting_a_document_removes_its_links_and_says_so_on_the_items(world):
    api, _dash, server = world
    one, two = await _item(api, "one"), await _item(api, "two")
    document = await _document(api, "gone.md")
    other = await _document(api, "kept.md")
    for local_id in (one, two):
        await api.post(f"{API}/items/{local_id}/documents", json={"document_id": document})
    await api.post(f"{API}/items/{one}/documents", json={"document_id": other})

    assert (await api.delete(f"{API}/documents/{document}")).status_code == 204

    assert [d["id"] for d in (await api.get(f"{API}/items/{one}/documents")).json()["items"]] \
        == [other]
    assert (await api.get(f"{API}/items/{two}/documents")).json()["items"] == []
    last = [e for e in await _events(api, two) if e["event_type"] == "document_unlinked"]
    assert "was deleted; its link was removed" in last[0]["body"]
    assert not (server.data_dir / "documents" / "example" / f"{document}.json").exists()


async def test_deleting_an_unknown_document_changes_no_links(world):
    api, _dash, _server = world
    local_id = await _item(api)
    document = await _document(api)
    await api.post(f"{API}/items/{local_id}/documents", json={"document_id": document})

    assert (await api.delete(f"{API}/documents/DOC-0099")).status_code == 404

    assert len((await api.get(f"{API}/items/{local_id}/documents")).json()["items"]) == 1


async def test_the_item_page_shows_linked_documents_and_offers_the_others(world):
    api, dash, _server = world
    local_id = await _item(api)
    first = await _document(api, "Linked one.md", kind="request", title="A title")
    second = await _document(api, "Free one.md")
    await api.post(f"{API}/items/{local_id}/documents", json={"document_id": first})

    page = await dash.get(f"{DASH}/items/{local_id}")

    assert page.status_code == 200
    assert f'data-linked-document="{first}"' in page.text
    assert f'href="{DASH}/documents/{first}"' in page.text and "A title" in page.text
    assert f'action="{DASH}/items/{local_id}/documents/{first}/unlink"' in page.text
    select = page.text.split('id="link_document_id"')[1].split("</select>")[0]
    assert second in select and first not in select


async def test_the_item_page_links_and_unlinks_documents(world):
    api, dash, _server = world
    local_id = await _item(api)
    document = await _document(api)

    linked = await dash.post(f"{DASH}/items/{local_id}/documents",
                             data={"document_id": document}, follow_redirects=False)

    assert linked.status_code == 303 and linked.headers["location"] == f"{DASH}/items/{local_id}"
    assert f'data-linked-document="{document}"' in (await dash.get(f"{DASH}/items/{local_id}")).text

    unlinked = await dash.post(f"{DASH}/items/{local_id}/documents/{document}/unlink",
                               follow_redirects=False)

    assert unlinked.status_code == 303
    page = await dash.get(f"{DASH}/items/{local_id}")
    assert "data-linked-document" not in page.text and "data-no-linked-documents" in page.text


async def test_an_item_in_a_project_without_documents_says_so(world):
    api, dash, _server = world
    local_id = await _item(api)

    page = await dash.get(f"{DASH}/items/{local_id}")

    assert "The project has no documents yet." in page.text
    assert 'id="link_document_id"' not in page.text


async def test_the_documents_page_counts_the_links_and_warns_before_deleting(world):
    api, dash, _server = world
    one, two = await _item(api, "one"), await _item(api, "two")
    document = await _document(api, "Shared.md")
    for local_id in (one, two):
        await api.post(f"{API}/items/{local_id}/documents", json={"document_id": document})

    page = await dash.get(f"{DASH}/documents")

    assert 'data-linked-count="2"' in page.text and "Linked to 2 item(s)" in page.text
    assert "Its links to 2 item(s) are removed" in page.text

    deleted = await dash.post(f"{DASH}/documents/{document}/delete", follow_redirects=False)

    assert deleted.status_code == 303
    assert (await api.get(f"{API}/items/{one}/documents")).json()["items"] == []


async def test_the_page_of_a_document_names_the_items_that_link_it(world):
    api, dash, _server = world
    local_id = await _item(api, "The linking item")
    document = await _document(api)

    before = await dash.get(f"{DASH}/documents/{document}")
    assert "No item links this document." in before.text

    await api.post(f"{API}/items/{local_id}/documents", json={"document_id": document})
    after = await dash.get(f"{DASH}/documents/{document}")

    assert f'href="{DASH}/items/{local_id}"' in after.text and "The linking item" in after.text
    assert re.search(r"data-linked-items", after.text)


async def test_linking_needs_a_token_or_a_session(world):
    api, _dash, _server = world
    local_id = await _item(api)
    document = await _document(api)
    async with httpx.AsyncClient(transport=api._transport, base_url="http://t") as anonymous:
        by_api = await anonymous.post(f"{API}/items/{local_id}/documents",
                                      json={"document_id": document})
        by_page = await anonymous.post(f"{DASH}/items/{local_id}/documents",
                                       data={"document_id": document})

    assert by_api.status_code == 401 and by_page.status_code == 401
