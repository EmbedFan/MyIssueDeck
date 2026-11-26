"""FEA-0013 phase 3: the MCP tools of the image store, through the real application."""

import base64

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.core.errors import (
    ImageDuplicate,
    ImageNotFound,
    ImageTooLarge,
    InvalidImage,
    Unauthorized,
)
from issuedeck.mcp import tools
from issuedeck.mcp.client import IssueDeckClient

NS = 'xmlns="http://www.w3.org/2000/svg"'
SVG_A = f'<svg {NS}><rect width="1" height="1"/></svg>'
SVG_B = f'<svg {NS}><circle r="2"/></svg>'
SVG_EVIL = f'<svg {NS}><script>alert(1)</script></svg>'


@pytest.fixture
async def mcp(tmp_path, monkeypatch):
    """The tools talk to the real application over ASGI, with the administrator token."""
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


async def test_upload_image_reads_the_file_in_the_mcp_process(mcp):
    server, _app, tmp_path = mcp
    source = tmp_path / "elsewhere" / "Pump layout.svg"
    source.parent.mkdir()
    source.write_text(SVG_A, encoding="utf-8")

    image = await tools.upload_image("example", str(source))

    assert image["id"] == "IMG-0001"
    assert image["name"] == "Pump layout.svg"
    stored = server.data_dir / "images" / "example" / "IMG-0001.svg"
    assert stored.read_text(encoding="utf-8") == SVG_A


async def test_upload_image_accepts_only_svg_files_that_exist(mcp):
    _server, _app, tmp_path = mcp
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")
    (tmp_path / "folder.svg").mkdir()

    with pytest.raises(InvalidImage, match="only .svg files"):
        await tools.upload_image("example", str(tmp_path / "photo.png"))
    with pytest.raises(InvalidImage, match="is not a file"):
        await tools.upload_image("example", str(tmp_path / "folder.svg"))
    with pytest.raises(InvalidImage, match="is not a file"):
        await tools.upload_image("example", str(tmp_path / "missing.svg"))


async def test_upload_image_refuses_a_big_local_file_without_uploading_it(mcp, monkeypatch):
    _server, _app, tmp_path = mcp
    big = tmp_path / "big.svg"
    big.write_text(SVG_A, encoding="utf-8")
    monkeypatch.setattr(tools, "MAX_LOCAL_IMAGE_BYTES", 5)

    with pytest.raises(ImageTooLarge):
        await tools.upload_image("example", str(big))


async def test_the_server_still_checks_the_content_of_an_uploaded_file(mcp):
    _server, _app, tmp_path = mcp
    evil = tmp_path / "evil.svg"
    evil.write_text(SVG_EVIL, encoding="utf-8")

    with pytest.raises(InvalidImage, match="SVG refused"):
        await tools.upload_image("example", str(evil))


async def test_upload_image_data_takes_base64_or_text(mcp):
    encoded = base64.b64encode(SVG_A.encode()).decode()

    first = await tools.upload_image_data("example", "a.svg", data_base64=encoded)
    second = await tools.upload_image_data("example", "b.svg", svg_text=SVG_B)

    assert (first["id"], second["id"]) == ("IMG-0001", "IMG-0002")
    listing = await tools.list_images("example")
    assert [i["name"] for i in listing["items"]] == ["a.svg", "b.svg"]
    assert listing["total_bytes"] == len(SVG_A) + len(SVG_B)


async def test_upload_image_data_needs_exactly_one_source_and_valid_base64(mcp):
    with pytest.raises(InvalidImage, match="exactly one"):
        await tools.upload_image_data("example", "a.svg")
    with pytest.raises(InvalidImage, match="exactly one"):
        await tools.upload_image_data("example", "a.svg", data_base64="AA==", svg_text=SVG_A)
    with pytest.raises(InvalidImage, match="not valid base64"):
        await tools.upload_image_data("example", "a.svg", data_base64="***not base64***")


async def test_a_duplicate_is_reported_with_the_existing_id(mcp):
    await tools.upload_image_data("example", "a.svg", svg_text=SVG_A)

    with pytest.raises(ImageDuplicate, match="IMG-0001"):
        await tools.upload_image_data("example", "again.svg", svg_text=SVG_A)


async def test_get_image_returns_the_metadata_and_optionally_the_svg_text(mcp):
    await tools.upload_image_data("example", "a.svg", svg_text=SVG_A)

    meta = await tools.get_image("example", "IMG-0001")
    full = await tools.get_image("example", "IMG-0001", include_content=True)

    assert meta["name"] == "a.svg" and "content" not in meta
    assert full["content"] == SVG_A
    assert {k: v for k, v in full.items() if k != "content"} == meta


async def test_delete_image_and_unknown_images(mcp):
    await tools.upload_image_data("example", "a.svg", svg_text=SVG_A)

    assert await tools.delete_image("example", "IMG-0001") == {"deleted": "IMG-0001"}

    assert (await tools.list_images("example"))["items"] == []
    with pytest.raises(ImageNotFound):
        await tools.get_image("example", "IMG-0001")
    with pytest.raises(ImageNotFound):
        await tools.delete_image("example", "IMG-0001")


async def test_a_wrong_token_is_reported_as_unauthorized(mcp, monkeypatch):
    _server, app, _tmp = mcp
    bad = IssueDeckClient("http://t", "wrong", transport=httpx.ASGITransport(app=app))
    monkeypatch.setattr(tools, "get_client", lambda: bad)

    with pytest.raises(Unauthorized):
        await tools.list_images("example")
    await bad.aclose()


async def test_the_image_tools_are_registered_in_the_mcp_server():
    from issuedeck.mcp import __main__ as entry

    server = entry.mcp_server
    found = await (server.get_tools() if hasattr(server, "get_tools") else server.list_tools())
    names = set(found) if isinstance(found, dict) else {tool.name for tool in found}

    assert {"upload_image", "upload_image_data", "list_images", "get_image",
            "delete_image"} <= names
