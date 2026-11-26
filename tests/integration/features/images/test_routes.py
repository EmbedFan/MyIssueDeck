"""FEA-0013 phase 1: the project image store and its API."""

import hashlib
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    ImagesConfig,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import install_error_handlers
from issuedeck.features.images.routes import item_router
from issuedeck.features.images.routes import router as images_router
from issuedeck.features.items.models import Base

NS = 'xmlns="http://www.w3.org/2000/svg"'
SVG_A = f'<svg {NS}><rect width="1" height="1"/></svg>'.encode()
SVG_B = f'<svg {NS}><circle r="2"/></svg>'.encode()
BASE = "/api/v1/projects/test/images"


def _registry():
    return ConfigRegistry(
        server=ServerConfig(api_token="t"),
        projects={"test": ProjectConfig(
            key="test", name="Test",
            kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
            statuses={"proposed": StatusConfig(label="P")},
            branches=[BranchConfig(key="main", label="Main")],
        )},
    )


async def _app(tmp_path, config=None):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = FastAPI()
    app.state.registry = _registry()
    app.state.engine = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.images_dir = tmp_path / "images"
    app.state.images_config = config or ImagesConfig()
    install_error_handlers(app)
    app.include_router(images_router)
    app.include_router(item_router)
    return app


@pytest.fixture
async def client(tmp_path):
    app = await _app(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await app.state.engine.dispose()


async def _upload(client, data=SVG_A, name="diagram.svg", url=BASE):
    return await client.post(url, files={"file": (name, data, "image/svg+xml")})


async def test_upload_stores_the_file_and_the_registry(client, tmp_path):
    r = await _upload(client, name="Wiring diagram.svg")

    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "IMG-0001"
    assert body["name"] == "Wiring diagram.svg"
    assert body["mime"] == "image/svg+xml"
    assert body["size"] == len(SVG_A)
    assert body["sha256"] == hashlib.sha256(SVG_A).hexdigest()
    folder = tmp_path / "images" / "test"
    assert (folder / "IMG-0001.svg").read_bytes() == SVG_A
    registry = json.loads((folder / "images.json").read_text(encoding="utf-8"))
    assert registry["next_id"] == 2
    assert [e["id"] for e in registry["images"]] == ["IMG-0001"]


async def test_the_registry_is_written_in_one_stable_form(client, tmp_path):
    await _upload(client)
    await _upload(client, SVG_B, "b.svg")

    raw = (tmp_path / "images" / "test" / "images.json").read_bytes()

    assert raw.endswith(b"\n") and b"\r" not in raw
    assert raw == (json.dumps(json.loads(raw), indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n").encode("utf-8")


async def test_list_and_get_metadata(client):
    await _upload(client)
    await _upload(client, SVG_B, "b.svg")

    listing = (await client.get(BASE)).json()

    assert [i["id"] for i in listing["items"]] == ["IMG-0001", "IMG-0002"]
    assert listing["total_bytes"] == len(SVG_A) + len(SVG_B)
    one = await client.get(f"{BASE}/IMG-0002")
    assert one.status_code == 200 and one.json()["name"] == "b.svg"


async def test_content_is_served_with_the_safe_headers(client):
    await _upload(client)

    r = await client.get(f"{BASE}/IMG-0001/content")

    assert r.status_code == 200
    assert r.content == SVG_A
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"]
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "content-disposition" not in r.headers


async def test_download_asks_the_browser_to_save_the_file(client):
    await _upload(client, name="Wiring diagram.svg")

    r = await client.get(f"{BASE}/IMG-0001/content?download=true")

    assert r.headers["content-disposition"].startswith('attachment; filename="IMG-0001.svg"')
    assert "Wiring%20diagram.svg" in r.headers["content-disposition"]


async def test_content_supports_conditional_requests(client):
    await _upload(client)
    etag = (await client.get(f"{BASE}/IMG-0001/content")).headers["etag"]

    r = await client.get(f"{BASE}/IMG-0001/content", headers={"If-None-Match": etag})

    assert r.status_code == 304


async def test_delete_removes_the_file_and_the_entry_and_the_id_is_not_reused(client, tmp_path):
    await _upload(client)

    r = await client.delete(f"{BASE}/IMG-0001")

    assert r.status_code == 204
    assert not (tmp_path / "images" / "test" / "IMG-0001.svg").exists()
    assert (await client.get(f"{BASE}/IMG-0001")).status_code == 404
    assert (await client.get(BASE)).json()["items"] == []
    again = await _upload(client, SVG_B, "b.svg")
    assert again.json()["id"] == "IMG-0002"


async def test_unknown_image_and_project(client):
    assert (await client.get(f"{BASE}/IMG-0009")).status_code == 404
    assert (await client.get(f"{BASE}/IMG-0009/content")).status_code == 404
    assert (await client.delete(f"{BASE}/IMG-0009")).status_code == 404
    missing = await client.get("/api/v1/projects/nope/images")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"


@pytest.mark.parametrize(("data", "name"), [
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "photo.png"),
    (b"<html><body>hi</body></html>", "page.svg"),
    (SVG_A.replace(b"<rect", b"<script>x()</script><rect"), "evil.svg"),
], ids=["png", "html-named-svg", "script"])
async def test_a_file_that_is_not_a_safe_svg_is_refused_and_nothing_is_stored(
        client, tmp_path, data, name):
    r = await _upload(client, data, name)

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_image"
    assert not (tmp_path / "images" / "test").exists()


async def test_the_same_image_is_stored_once(client):
    await _upload(client)

    r = await _upload(client, name="copy.svg")

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "image_duplicate"
    assert r.json()["error"]["details"]["existing_id"] == "IMG-0001"
    assert len((await client.get(BASE)).json()["items"]) == 1


async def test_a_file_over_the_limit_is_refused(tmp_path):
    app = await _app(tmp_path, ImagesConfig(max_file_bytes=len(SVG_A) - 1))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await _upload(c)
    await app.state.engine.dispose()

    assert r.status_code == 413
    assert r.json()["error"]["code"] == "image_too_large"


async def test_a_project_over_its_limit_is_refused(tmp_path):
    app = await _app(tmp_path, ImagesConfig(max_project_bytes=len(SVG_A) + 1))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await _upload(c)).status_code == 201
        r = await _upload(c, SVG_B, "b.svg")
    await app.state.engine.dispose()

    assert r.status_code == 413
    assert r.json()["error"]["details"]["used_bytes"] == len(SVG_A)


@pytest.mark.parametrize("name", ["../../evil.svg", "C:\\temp\\x\\evil.svg", "a\x00b\nc.svg"])
async def test_the_file_name_is_metadata_only(client, tmp_path, name):
    r = await _upload(client, name=name)

    assert r.status_code == 201
    shown = r.json()["name"]
    assert "/" not in shown and "\\" not in shown and "\x00" not in shown
    assert r.json()["id"] == "IMG-0001"
    assert sorted(p.name for p in (tmp_path / "images" / "test").iterdir()) == [
        "IMG-0001.svg", "images.json"]


async def test_the_limits_come_from_the_server_configuration():
    config = ServerConfig(api_token="t", images={"max_file_bytes": 10, "max_project_bytes": 99})

    assert config.images.max_file_bytes == 10
    assert ServerConfig(api_token="t").images.max_file_bytes == 2_000_000


async def test_the_real_application_wires_the_store_and_the_authentication(tmp_path):
    """The router is mounted, needs a token, and keeps the files under data/images."""
    from issuedeck.app import create_app
    from issuedeck.cli import (
        _ensure_demo_config,
        _ensure_demo_project_config,
        _upgrade_database,
    )
    from issuedeck.core.config import load_server_config

    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    auth = {"Authorization": f"Bearer {server.api_token.get_secret_value()}"}
    url = "/api/v1/projects/example/images"
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            files = {"file": ("a.svg", SVG_A, "image/svg+xml")}
            assert (await c.post(url, files=files)).status_code == 401
            r = await c.post(url, files=files, headers=auth)
            assert r.status_code == 201
            assert (server.data_dir / "images" / "example" / "IMG-0001.svg").read_bytes() == SVG_A
            assert (await c.get(f"{url}/IMG-0001/content", headers=auth)).content == SVG_A
