"""IS-0006: drag and drop on the Kanban board must survive live updates.

A live update replaces the board (``data-live-region="board"``) with new columns. SortableJS is
attached per column, so the page must prepare the new columns again, never attach twice, and
tell live.js when a move is over so that updates held back during the drag are applied.
The real behaviour (handlers present after repeated refreshes) was checked with the page and
its scripts in jsdom; these tests keep the structure that behaviour depends on.
"""

import re
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
from issuedeck.features.dashboard import routes as dashboard_routes
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.items.models import Base
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.items.schemas import CreateItemRequest
from issuedeck.features.items.service import ItemService

LIVE_JS = (
    Path(dashboard_routes.__file__).parent / "static" / "js" / "live.js"
).read_text(encoding="utf-8")


@pytest.fixture
async def kanban_page(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    registry = ConfigRegistry(
        server=ServerConfig(api_token="t", projects_dir=tmp_path),
        projects={"test": ProjectConfig(
            key="test", name="Test",
            kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
            statuses={
                "proposed": StatusConfig(label="Proposed"),
                "done": StatusConfig(label="Done", terminal=True),
            },
            branches=[BranchConfig(key="main", label="Main")],
        )},
    )
    async with Session() as session:
        await ItemService(ItemRepo(session), registry, session).create(
            "test", CreateItemRequest(kind="feature", title="Card", body=""),
        )
    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    install_error_handlers(app)
    app.include_router(dashboard_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/dashboard/test/kanban")
        assert response.status_code == 200
        yield response.text
    await engine.dispose()


def _page_script(html: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    return next(s for s in scripts if "new Sortable" in s)


async def test_the_board_is_a_live_region(kanban_page):
    # The premise of the defect: live updates replace the whole board, columns included.
    assert 'id="kanban-board" data-live-region="board"' in kanban_page


async def test_the_board_is_prepared_on_load_and_after_every_replacement(kanban_page):
    script = _page_script(kanban_page)
    assert "document.addEventListener('DOMContentLoaded', prepareBoard)" in script
    handler = re.search(
        r"document\.addEventListener\('live:applied'.*?\}\);", script, re.S,
    )
    assert handler, "the page does not react to a replaced board"
    assert "'board'" in handler.group(0) and "prepareBoard()" in handler.group(0)


async def test_a_column_never_gets_two_handlers(kanban_page):
    script = _page_script(kanban_page)
    prepare = re.search(r"function prepareBoard\(\) \{(.*?)\n  \}\n", script, re.S).group(1)
    assert "if (Sortable.get(col)) return;" in prepare
    assert prepare.index("Sortable.get(col)") < prepare.index("new Sortable(col")


async def test_columns_are_looked_up_when_needed_not_kept_from_page_load(kanban_page):
    script = _page_script(kanban_page)
    # a list taken once at page load would point at columns that live updates have replaced
    assert not re.search(r"const columns\s*=\s*document\.querySelectorAll", script)
    counts = re.search(r"function updateColumnCounts\(\) \{(.*?)\n  \}\n", script, re.S).group(1)
    assert "columnsNow()" in counts


async def test_a_replaced_card_is_not_put_back(kanban_page):
    script = _page_script(kanban_page)
    put_back = re.search(r"function putBack\(evt\) \{(.*?)\n  \}\n", script, re.S).group(1)
    assert "evt.item.isConnected" in put_back and "evt.from.isConnected" in put_back


async def test_every_move_ends_with_the_idle_event(kanban_page):
    script = _page_script(kanban_page)
    assert "new CustomEvent('live:idle')" in script
    # a move inside one column ends at once; a status change ends after the request settled,
    # whether it was saved, refused or failed
    assert re.search(r"if \(newStatus === oldStatus\) \{\s*moveEnded\(\);\s*return;", script)
    assert re.search(r"\.catch\(function\(\) \{.*?\}\)\s*\.then\(moveEnded\);", script, re.S)


def test_live_js_applies_held_back_updates_when_a_move_ends():
    listener = re.search(
        r"addEventListener\('live:idle', function \(\) \{(.*?)\n  \}\);", LIVE_JS, re.S,
    )
    assert listener, "live.js does not listen for the end of a move"
    body = listener.group(1)
    assert "Object.keys(blocked).length" in body
    assert "refresh(false)" in body


def test_live_js_still_holds_updates_while_a_card_is_dragged():
    assert ".sortable-chosen, .sortable-ghost, .sortable-drag" in LIVE_JS
