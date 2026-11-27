"""FEA-0010 phase 3: the advanced search dialog and its results in the dashboard."""

import json
import shutil
import subprocess
from html import unescape
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.features.dashboard import routes as dashboard_routes
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE

PAGE = "/dashboard/example/search"
API = "/api/v1/projects/example"
STATIC = Path(dashboard_routes.__file__).parent / "static" / "js"


def text(value, mode="simple", **extra):
    return {"type": "text", "mode": mode, "value": value, **extra}


def kind(*values):
    return {"type": "kind", "values": list(values)}


def status(*values):
    return {"type": "status", "values": list(values)}


def url(*items, **params):
    query = quote(json.dumps({"items": list(items)}))
    extra = "".join(f"&{k}={v}" for k, v in params.items())
    return f"{PAGE}?query={query}{extra}"


@pytest.fixture
async def world(tmp_path):
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
            admin = {"Authorization": f"Bearer {token}"}
            for kind_, title, body in [
                ("feature", "Import of CSV files", "The importer reads CSV files."),
                ("bug", "Import fails on an empty file", "Stack trace of the failure."),
                ("bug", "Search is slow", "The regular expression search takes long."),
                ("improvement", "Release notes", "Write them. Importing is done."),
            ]:
                r = await client.post(f"{API}/items", headers=admin, json={
                    "kind": kind_, "title": title, "body": body})
                assert r.status_code == 201, r.text
            yield client, admin


def titles_in(html):
    """The item titles that are in the page, in the order of the page."""
    known = ("Import of CSV files", "Import fails on an empty file", "Search is slow",
             "Release notes")
    return sorted((t for t in known if t in html), key=html.index)


async def test_the_page_offers_the_dialog_with_the_kinds_and_statuses_of_the_project(world):
    client, _admin = world

    response = await client.get(PAGE)

    html = response.text
    assert response.status_code == 200
    assert "data-advanced-search-open" in html
    assert "/dashboard/static/js/search_builder.js" in html
    assert 'name="query"' in html
    # the builder gets the project's own kinds and statuses, with their labels
    assert '"key": "bug"' in html or '"key":"bug"' in html
    assert "Bug" in html and "Proposed" in html
    assert "data-advanced-search-summary" not in html  # nothing searched yet


async def test_an_advanced_search_lists_what_matches_and_says_what_was_searched(world):
    client, _admin = world

    response = await client.get(url(text("import"), {"op": "and", **kind("bug")}))

    html = response.text
    assert response.status_code == 200
    assert titles_in(html) == ["Import fails on an empty file"]
    assert "data-advanced-search-summary" in html
    assert 'title+body match words "import" AND kind is bug' in unescape(html)
    assert 'role="alert"' not in html


async def test_the_dialog_is_filled_with_the_search_that_was_run(world):
    client, _admin = world

    response = await client.get(url(text("import"), {"op": "and", **kind("bug")}))

    html = response.text
    # the search comes back as the start value of the builder (HTML-escaped by tojson)
    assert "searchBuilder(" in html
    assert "\\u0022type\\u0022" in html or '"type"' in html
    assert "import" in html


async def test_groups_and_or_are_evaluated_by_the_page(world):
    client, _admin = world

    response = await client.get(url(
        {"group": [kind("feature"), {"op": "or", **kind("improvement")}]},
        {"op": "and", **text("import")},
    ))

    assert titles_in(response.text) == ["Release notes", "Import of CSV files"]


async def test_nothing_found_says_so(world):
    client, _admin = world

    response = await client.get(url(text("zebra")))

    assert response.status_code == 200
    assert "Nothing matches this search" in response.text
    assert titles_in(response.text) == []


async def test_a_refused_search_shows_the_fault_and_not_an_error_page(world):
    client, _admin = world

    response = await client.get(url(kind("epic")))

    assert response.status_code == 200
    assert 'role="alert"' in response.text
    assert "items[0]" in response.text


async def test_a_query_that_is_not_json_is_reported(world):
    client, _admin = world

    response = await client.get(f"{PAGE}?query=%7Bnot-json")

    assert response.status_code == 200
    assert 'role="alert"' in response.text
    assert "not valid JSON" in response.text


async def test_a_regular_expression_that_cannot_finish_shows_an_incomplete_result(
    world, monkeypatch,
):
    import issuedeck.features.search.evaluator as evaluator

    client, admin = world
    await client.post(f"{API}/items", headers=admin, json={
        "kind": "feature", "title": "Long text", "body": "a" * 3000})
    monkeypatch.setattr(evaluator, "REGEX_SECONDS", 1.0)

    response = await client.get(url(text("a*a*a*a*a*a*a*b", "regex", fields=["body"])))

    assert response.status_code == 200
    assert 'role="status"' in response.text
    assert "The result is incomplete" in response.text
    assert "did not finish in 1 s" in response.text


async def test_load_more_keeps_the_advanced_search(world):
    client, _admin = world

    first = await client.get(url(text("import"), limit=1))

    html = first.text
    assert len(titles_in(html)) == 1
    assert "query=" in html and "after=" in html
    # follow the link of the button: it must give the next, different item
    link = next(
        part.split('"')[0] for part in html.split('hx-get="') if "after=" in part.split('"')[0]
    ).replace("&amp;", "&")
    second = await client.get(link, headers={"HX-Request": "true"})
    assert second.status_code == 200
    # the link has no limit, so the next page is the usual size: the rest, without the first item
    rest = titles_in(second.text)
    assert rest and titles_in(html)[0] not in rest
    assert len(rest) == 2  # three items match "import" (by stem), one was on the first page


async def test_the_text_search_with_q_is_unchanged(world):
    client, _admin = world

    response = await client.get(PAGE, params={"q": "import"})

    assert response.status_code == 200
    assert "Import of CSV files" in response.text
    assert "data-advanced-search-summary" not in response.text


async def test_the_dialog_is_translated(world):
    client, _admin = world
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")

    hungarian = await client.get(PAGE)
    client.cookies.set(DASHBOARD_LANG_COOKIE, "zh-CN")
    chinese = await client.get(PAGE)

    assert "Összetett keresés" in hungarian.text
    assert "高级搜索" in chinese.text


async def test_the_script_is_served(world):
    client, _admin = world

    response = await client.get("/dashboard/static/js/search_builder.js")

    assert response.status_code == 200
    assert "function searchBuilder" in response.text


# ------------------------------------------------------------------ the builder script itself

NODE = shutil.which("node")


def run_builder(script: str):
    """Run search_builder.js under Node and return what the snippet prints as JSON."""
    code = (
        "const window = {};\n"
        + (STATIC / "search_builder.js").read_text(encoding="utf-8")
        + "\n" + script
    )
    done = subprocess.run([NODE, "-e", code], capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_the_builder_writes_the_same_json_the_api_takes():
    start = {"items": [
        {"type": "text", "mode": "regex", "value": "x+", "fields": ["title"],
         "case_sensitive": True},
        {"op": "or", "group": [
            {"type": "kind", "values": ["bug"]},
            {"op": "and", "type": "status", "values": ["done", "proposed"]},
        ]},
    ]}

    result = run_builder(
        f"const b = searchBuilder({json.dumps(start)}, [], []);"
        "console.log(JSON.stringify(JSON.parse(b.json())));"
    )

    assert result == start


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_the_builder_drops_empty_blocks_and_the_operator_of_the_new_first_block():
    result = run_builder(
        "const b = searchBuilder({}, [], []);"
        "b.items[0].value = '   ';"                       # an empty text block: dropped
        "b.addBlock(b.items, 'kind');"                     # no value chosen: dropped
        "b.addBlock(b.items, 'text'); b.items[2].value = 'import'; b.items[2].op = 'or';"
        "b.addBlock(b.items, 'group');"                    # an empty group: dropped
        "b.addBlock(b.items, 'status'); b.toggleValue(b.items[4], 'done');"
        "console.log(b.json());"
    )

    # the first block that is left has no operator, the second keeps its own
    assert result == {"items": [
        {"type": "text", "mode": "simple", "value": "import", "fields": ["title", "body"]},
        {"type": "status", "values": ["done"], "op": "and"},
    ]}


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_an_empty_builder_has_nothing_to_send_and_a_field_less_text_is_dropped():
    result = run_builder(
        "const b = searchBuilder({}, [], []);"
        "const empty = b.isEmpty();"
        "b.items[0].value = 'x'; b.items[0].title = false; b.items[0].body = false;"
        "console.log(JSON.stringify({empty, nofields: b.isEmpty()}));"
    )

    assert result == {"empty": True, "nofields": True}


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_blocks_can_be_moved_and_removed():
    result = run_builder(
        "const b = searchBuilder({items: [{type:'kind', values:['bug']},"
        " {op:'and', type:'status', values:['done']}]}, [], []);"
        "b.move(b.items, 1, -1);"
        "const moved = JSON.parse(b.json()).items.map(x => x.type);"
        "b.remove(b.items, 0);"
        "const left = JSON.parse(b.json()).items.map(x => x.type);"
        "console.log(JSON.stringify({moved, left}));"
    )

    assert result == {"moved": ["status", "kind"], "left": ["kind"]}


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_the_builder_knows_which_saved_names_are_taken():
    result = run_builder(
        "const b = searchBuilder({}, [], [], ['Open bugs', 'Árvíz']);"
        "console.log(JSON.stringify([b.taken('open   BUGS'), b.taken(' Árvíz'), b.taken('x'),"
        " b.taken(''), searchBuilder({}, [], []).taken('open bugs')]));"
    )

    assert result == [True, True, False, False, False]
