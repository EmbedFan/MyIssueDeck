"""FEA-0012 phase 1: the document API."""

import hashlib

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.core.errors import install_error_handlers
from issuedeck.features.documents.routes import item_router as item_documents_router
from issuedeck.features.documents.routes import router as documents_router
from issuedeck.features.items.models import Base

from .test_service import _registry

BASE = "/api/v1/projects/test/documents"


@pytest.fixture
async def client(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = FastAPI()
    app.state.registry = _registry()
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.documents_dir = tmp_path / "documents"
    install_error_handlers(app)
    app.include_router(documents_router)
    app.include_router(item_documents_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def _create(client, name="a.md", body="# A\n", **extra):
    r = await client.post(BASE, json={"name": name, "body": body, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_and_read_a_document(client):
    created = await _create(client, "Feature request.md", "# Request\n", kind="request",
                            title="The request")

    assert created["id"] == "DOC-0001"
    assert created["sha256"] == hashlib.sha256(b"# Request\n").hexdigest()
    assert created["size"] == len(b"# Request\n") and created["revision"] == 1
    one = (await client.get(f"{BASE}/DOC-0001")).json()
    assert one["body"] == "# Request\n" and one["name"] == "Feature request.md"
    listing = (await client.get(BASE)).json()["items"]
    assert [d["id"] for d in listing] == ["DOC-0001"] and "body" not in listing[0]


async def test_list_filters(client):
    await _create(client, "a.md", kind="prompt")
    await _create(client, "b.md", kind="report")

    assert [d["name"] for d in (await client.get(f"{BASE}?kind=report")).json()["items"]] \
        == ["b.md"]
    assert [d["id"] for d in (await client.get(f"{BASE}?name=a.md")).json()["items"]] \
        == ["DOC-0001"]


async def test_a_name_that_is_used_gives_409_and_replace_makes_a_revision(client):
    await _create(client, "a.md", "one")

    again = await client.post(BASE, json={"name": "a.md", "body": "two"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "document_exists"
    assert again.json()["error"]["details"]["existing_id"] == "DOC-0001"

    replaced = await client.post(BASE, json={"name": "a.md", "body": "two", "replace": True})
    assert replaced.status_code == 201 and replaced.json()["revision"] == 2


async def test_replace_needs_the_current_revision(client):
    await _create(client, "a.md", "one")

    ok = await client.put(f"{BASE}/DOC-0001", json={"body": "two", "revision": 1})
    stale = await client.put(f"{BASE}/DOC-0001", json={"body": "mine", "revision": 1})

    assert ok.status_code == 200 and ok.json()["revision"] == 2
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "document_conflict"
    assert stale.json()["error"]["details"]["current_revision"] == 2
    assert (await client.get(f"{BASE}/DOC-0001")).json()["body"] == "two"


async def test_replace_without_a_revision_is_refused_by_the_schema(client):
    await _create(client)

    r = await client.put(f"{BASE}/DOC-0001", json={"body": "x"})

    assert r.status_code == 422


async def test_append_and_delete(client):
    await _create(client, "log.md", "# Log")

    appended = await client.patch(f"{BASE}/DOC-0001", json={"text": "entry"})
    assert appended.json()["body"] == "# Log\nentry" and appended.json()["revision"] == 2

    assert (await client.delete(f"{BASE}/DOC-0001")).status_code == 204
    assert (await client.get(f"{BASE}/DOC-0001")).status_code == 404
    assert (await client.delete(f"{BASE}/DOC-0001")).status_code == 404


async def test_revisions_and_restore(client):
    await _create(client, "a.md", "v1")
    await client.put(f"{BASE}/DOC-0001", json={"body": "v2", "revision": 1})

    rows = (await client.get(f"{BASE}/DOC-0001/revisions")).json()["items"]
    assert [(r["revision"], r["current"]) for r in rows] == [(2, True), (1, False)]
    old = (await client.get(f"{BASE}/DOC-0001/revisions/1")).json()
    assert old["body"] == "v1" and old["current"] is False

    restored = await client.post(f"{BASE}/DOC-0001/restore/1")

    assert restored.status_code == 200
    assert (restored.json()["revision"], restored.json()["body"]) == (3, "v1")
    assert (await client.get(f"{BASE}/DOC-0001/revisions/9")).status_code == 404
    assert (await client.post(f"{BASE}/DOC-0001/restore/9")).status_code == 404


async def test_content_is_markdown_text_with_safe_headers(client):
    await _create(client, "Wiring plan.md", "# Plan\n\n<script>alert(1)</script>\n")

    r = await client.get(f"{BASE}/DOC-0001/content")

    assert r.status_code == 200
    assert r.text == "# Plan\n\n<script>alert(1)</script>\n"  # the text, never interpreted
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    assert "content-disposition" not in r.headers


async def test_download_names_the_file_like_the_document(client):
    await _create(client, "árvíztűrő terv.md")

    r = await client.get(f"{BASE}/DOC-0001/content?download=true")

    disposition = r.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="DOC-0001.md"')
    assert "%C3%A1rv%C3%ADzt%C5%B1r%C5%91%20terv.md" in disposition


async def test_content_supports_conditional_requests(client):
    await _create(client)
    etag = (await client.get(f"{BASE}/DOC-0001/content")).headers["etag"]

    r = await client.get(f"{BASE}/DOC-0001/content", headers={"If-None-Match": etag})

    assert r.status_code == 304


@pytest.mark.parametrize("escaped", [r"a\u0000b", r"lone surrogate \ud800"])
async def test_a_binary_text_is_refused(client, escaped):
    # sent as raw JSON with an escape, the way any client can send it
    raw = '{"name": "x.md", "body": "' + escaped + '"}'

    r = await client.post(BASE, content=raw, headers={"Content-Type": "application/json"})

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_document"
    assert (await client.get(BASE)).json()["items"] == []


async def test_a_bad_kind_or_an_empty_name_is_refused(client):
    assert (await client.post(BASE, json={"name": "x.md", "body": "x", "kind": "essay"})
            ).status_code == 422
    assert (await client.post(BASE, json={"name": "  ", "body": "x"})).status_code == 422


async def test_unknown_document_and_project(client):
    assert (await client.get(f"{BASE}/DOC-0009")).status_code == 404
    assert (await client.get(f"{BASE}/DOC-0009/content")).status_code == 404
    missing = await client.get("/api/v1/projects/nope/documents")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "project_not_found"


async def test_the_real_application_wires_the_store_and_the_authentication(tmp_path):
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    auth = {"Authorization": f"Bearer {server.api_token.get_secret_value()}"}
    url = "/api/v1/projects/example/documents"
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            body = {"name": "a.md", "body": "# Hi\n"}
            assert (await c.post(url, json=body)).status_code == 401
            assert (await c.get(url)).status_code == 401
            created = await c.post(url, json=body, headers=auth)
            assert created.status_code == 201
            assert (server.data_dir / "documents" / "example" / "DOC-0001.json").is_file()
            assert (await c.get(f"{url}/DOC-0001/content", headers=auth)).text == "# Hi\n"
