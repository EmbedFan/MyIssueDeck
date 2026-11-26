"""FEA-0013 phase 2: the dashboard page of the project image store.

These run against the real application (login, session cookie, static files), because the
cookie-authenticated routes are what an <img> tag in the browser uses.
"""

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.features.dashboard.image_routes import human_size

NS = 'xmlns="http://www.w3.org/2000/svg"'
SVG_A = f'<svg {NS}><rect width="1" height="1"/></svg>'.encode()
SVG_B = f'<svg {NS}><circle r="2"/></svg>'.encode()
SVG_EVIL = f'<svg {NS}><script>alert(1)</script></svg>'.encode()
PAGE = "/dashboard/example/images"


@pytest.fixture
async def shell(tmp_path):
    """The real application with one project, and a signed-in client."""
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    admin = server.api_token.get_secret_value()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            await client.post("/dashboard/login", data={"token": admin})
            yield client, app, server


def _files(*items):
    return [("files", (name, data, "image/svg+xml")) for name, data in items]


async def test_the_sidebar_links_to_the_images_page(shell):
    client, _app, _server = shell

    page = await client.get("/dashboard/example/list")

    assert 'href="/dashboard/example/images"' in page.text


async def test_the_page_is_empty_at_first(shell):
    client, _app, _server = shell

    page = await client.get(PAGE)

    assert page.status_code == 200
    assert "data-images-empty" in page.text
    assert "data-images-grid" not in page.text
    assert 'enctype="multipart/form-data"' in page.text
    assert "0 images" in page.text


async def test_several_files_are_uploaded_at_once_and_shown(shell):
    client, _app, server = shell

    page = await client.post(PAGE, files=_files(("a.svg", SVG_A), ("b.svg", SVG_B)))

    assert page.status_code == 200
    assert "data-images-uploaded" in page.text
    assert "IMG-0001 (a.svg)" in page.text and "IMG-0002 (b.svg)" in page.text
    assert "data-images-errors" not in page.text
    assert 'src="/dashboard/example/images/IMG-0001/file"' in page.text
    assert "2 images" in page.text
    folder = server.data_dir / "images" / "example"
    assert (folder / "IMG-0001.svg").read_bytes() == SVG_A
    assert '"actor": "dashboard"' in (folder / "images.json").read_text(encoding="utf-8")


async def test_a_refused_file_is_reported_and_the_others_are_kept(shell):
    client, _app, server = shell

    page = await client.post(
        PAGE, files=_files(("good.svg", SVG_A), ("evil.svg", SVG_EVIL), ("photo.png", b"\x89PNG")),
    )

    assert page.status_code == 200
    assert "IMG-0001 (good.svg)" in page.text
    assert "evil.svg" in page.text and "SVG refused" in page.text
    assert "photo.png" in page.text
    assert sorted(p.name for p in (server.data_dir / "images" / "example").iterdir()) == [
        "IMG-0001.svg", "images.json"]


async def test_when_every_file_is_refused_the_page_answers_422(shell):
    client, _app, _server = shell

    page = await client.post(PAGE, files=_files(("evil.svg", SVG_EVIL)))

    assert page.status_code == 422
    assert "data-images-errors" in page.text
    assert "data-images-uploaded" not in page.text


async def test_a_submit_without_a_file_asks_to_choose_one(shell):
    client, _app, _server = shell

    page = await client.post(PAGE, files=[("files", ("", b"", "application/octet-stream"))])

    assert page.status_code == 422
    assert "Choose at least one SVG file." in page.text


async def test_the_file_is_served_to_the_browser_with_the_safe_headers(shell):
    client, _app, _server = shell
    await client.post(PAGE, files=_files(("Wiring.svg", SVG_A)))

    shown = await client.get(f"{PAGE}/IMG-0001/file")
    saved = await client.get(f"{PAGE}/IMG-0001/file?download=true")

    assert shown.status_code == 200 and shown.content == SVG_A
    assert shown.headers["content-type"].startswith("image/svg+xml")
    assert shown.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in shown.headers["content-security-policy"]
    assert "content-disposition" not in shown.headers
    assert saved.headers["content-disposition"].startswith('attachment; filename="IMG-0001.svg"')


async def test_the_page_and_the_file_need_a_session(shell):
    client, app, _server = shell
    await client.post(PAGE, files=_files(("a.svg", SVG_A)))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://t") as anonymous:
        page = await anonymous.get(PAGE)
        file = await anonymous.get(f"{PAGE}/IMG-0001/file")
        upload = await anonymous.post(PAGE, files=_files(("b.svg", SVG_B)))
        delete = await anonymous.post(f"{PAGE}/IMG-0001/delete")

    assert page.status_code == 303 and "/dashboard/login" in page.headers["location"]
    assert file.status_code == 303 and "/dashboard/login" in file.headers["location"]
    assert upload.status_code == 401
    assert delete.status_code == 401


async def test_delete_removes_the_image_and_says_so(shell):
    client, _app, server = shell
    await client.post(PAGE, files=_files(("a.svg", SVG_A)))

    response = await client.post(f"{PAGE}/IMG-0001/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"{PAGE}?deleted=IMG-0001"
    page = await client.get(response.headers["location"])
    assert "Deleted IMG-0001." in page.text
    assert "data-images-empty" in page.text
    assert not (server.data_dir / "images" / "example" / "IMG-0001.svg").exists()


async def test_each_image_has_open_download_and_confirmed_delete(shell):
    client, _app, _server = shell
    page = await client.post(PAGE, files=_files(("a.svg", SVG_A)))

    assert 'target="_blank" rel="noopener"' in page.text
    assert f"{PAGE}/IMG-0001/file?download=true" in page.text
    assert f'action="{PAGE}/IMG-0001/delete"' in page.text
    assert "Delete this image? This cannot be undone." in page.text
    assert "confirm(this.dataset.confirm)" in page.text


async def test_an_unknown_image_is_a_404(shell):
    client, _app, _server = shell

    assert (await client.get(f"{PAGE}/IMG-0009/file")).status_code == 404
    assert (await client.post(f"{PAGE}/IMG-0009/delete")).status_code == 404
    assert (await client.get("/dashboard/nope/images")).status_code == 404


@pytest.mark.parametrize(("lang", "title"), [("hu", "Képek"), ("zh-CN", "图片"), ("en", "Images")])
async def test_the_page_is_translated(shell, lang, title):
    client, _app, _server = shell
    client.cookies.set("issuedeck_lang", lang)

    page = await client.get(PAGE)

    assert "<h1" in page.text and title in page.text.split("</h1>")[0]


@pytest.mark.parametrize(("size", "text"), [
    (0, "0 B"), (999, "999 B"), (1000, "1.0 KB"), (3400, "3.4 KB"),
    (2_000_000, "2.0 MB"), (100_000_000, "100.0 MB"),
])
def test_human_size(size, text):
    assert human_size(size) == text
