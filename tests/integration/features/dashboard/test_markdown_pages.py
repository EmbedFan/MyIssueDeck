"""IS-0004: the item page and the form preview hand Markdown to the renderer intact."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import install_error_handlers
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.items.models import Base
from issuedeck.features.items.routes import router as items_router

DASHBOARD = Path(__file__).resolve().parents[4] / "src" / "issuedeck" / "features" / "dashboard"

NASTY_BODY = (
    "# Heading\n\n> quote with <angle> & ampersand \"double\" 'single'\n\n"
    "</script><script>alert(1)</script>\n\n<!-- comment -->\n\n"
    "`a >= b` and routes -> service, árvíztűrő, 日本語, \\u0041 and \\n literal\n"
)


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    project = ProjectConfig(
        key="a",
        name="A",
        kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
        statuses={"proposed": StatusConfig(label="Proposed")},
        branches=[BranchConfig(key="main", label="Main")],
    )
    app = FastAPI()
    app.state.registry = ConfigRegistry(
        server=ServerConfig(api_token="t"), projects={"a": project},
    )
    app.state.session_factory = Session
    install_error_handlers(app)
    app.include_router(dashboard_router)
    app.include_router(items_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await engine.dispose()


async def _item(client, body):
    r = await client.post(
        "/api/v1/projects/a/items", json={"kind": "feature", "title": "md", "body": body},
    )
    assert r.status_code == 201, r.text
    return r.json()["local_id"]


def _source(page_text: str):
    match = re.search(
        r'<script type="application/json" id="md-source">(.*?)</script>', page_text, re.S,
    )
    assert match, "the Markdown source script is missing"
    return json.loads(match.group(1))


async def test_the_body_reaches_the_page_unchanged(client):
    local_id = await _item(client, NASTY_BODY)

    page = await client.get(f"/dashboard/a/items/{local_id}")

    assert page.status_code == 200
    assert _source(page.text) == NASTY_BODY


async def test_a_body_cannot_close_the_script_element(client):
    local_id = await _item(client, "</script><script>alert(1)</script>")

    page = await client.get(f"/dashboard/a/items/{local_id}")

    assert "</script><script>alert(1)" not in page.text
    assert _source(page.text) == "</script><script>alert(1)</script>"


async def test_the_item_page_uses_the_safe_renderer_and_the_md_content_class(client):
    local_id = await _item(client, "# Hi")

    page = await client.get(f"/dashboard/a/items/{local_id}")

    assert 'id="md-rendered" class="md-content"' in page.text
    assert "window.renderMarkdown(JSON.parse(" in page.text
    assert "marked.parse" not in page.text
    assert "prose" not in page.text
    assert "/dashboard/static/js/markdown.js" in page.text


async def test_an_item_without_a_body_shows_the_empty_text(client):
    local_id = await _item(client, "")

    page = await client.get(f"/dashboard/a/items/{local_id}")

    assert 'id="md-source"' not in page.text
    assert 'id="md-rendered"' not in page.text
    assert "No content" in page.text


async def test_the_form_preview_uses_the_same_renderer_and_class(client):
    local_id = await _item(client, "## Preview me")

    page = await client.get(f"/dashboard/a/items/{local_id}/edit")

    assert page.status_code == 200
    assert "window.renderMarkdown(this.bodyText, \"a\")" in page.text
    assert 'x-html="renderedBody" class="md-content"' in page.text
    assert "marked.parse" not in page.text
    assert "prose" not in page.text


class _FormAttrs(HTMLParser):
    """Collects the attributes of the item form as a browser would parse them."""

    def __init__(self):
        super().__init__()
        self.x_data = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form" and "x-data" in values and self.x_data is None:
            self.x_data = values["x-data"]


@pytest.mark.parametrize("body", [NASTY_BODY, "", 'only "double" quotes', "it's 'single'"])
async def test_the_form_x_data_survives_any_body(client, body):
    """A body with quotes must not cut the Alpine expression short (preview needs it)."""
    local_id = await _item(client, body)

    page = await client.get(f"/dashboard/a/items/{local_id}/edit")

    parser = _FormAttrs()
    parser.feed(page.text)
    assert parser.x_data is not None
    assert "get renderedBody()" in parser.x_data  # the attribute was not cut off
    assert "previewMode: false" in parser.x_data
    match = re.search(r"bodyText: (.*?),\n\s+get renderedBody", parser.x_data, re.S)
    assert match, parser.x_data
    assert json.loads(match.group(1)) == body


def test_the_renderer_script_exists_and_is_loaded_after_marked():
    base = (DASHBOARD / "templates" / "base.html").read_text(encoding="utf-8")

    assert (DASHBOARD / "static" / "js" / "markdown.js").is_file()
    assert base.index("marked.min.js") < base.index("markdown.js")


@pytest.mark.parametrize("rule", [
    ".md-content h1", ".md-content h2", ".md-content ul", ".md-content ol",
    ".md-content pre", ".md-content code", ".md-content blockquote",
    ".md-content table", ".md-content th", ".md-content a", ".md-content img",
])
def test_the_stylesheet_formats_every_markdown_element(rule):
    css = (DASHBOARD / "static" / "css" / "dashboard.css").read_text(encoding="utf-8")

    assert rule in css


def test_list_markers_and_table_borders_come_back_after_the_reset():
    css = (DASHBOARD / "static" / "css" / "dashboard.css").read_text(encoding="utf-8")

    # The minifier writes "list-style: disc" as the equivalent "list-style:outside".
    assert re.search(r"\.md-content ul\{[^}]*list-style:(disc|outside)", css)
    assert re.search(r"\.md-content ol\{[^}]*list-style:decimal", css)
    assert re.search(r"\.md-content (th,\.md-content td|td)\{[^}]*border:", css)
