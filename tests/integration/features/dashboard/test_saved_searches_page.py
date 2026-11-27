"""FEA-0010 phase 4: saved searches in the dashboard (save, run, rename, delete, restore)."""

import json
from html import unescape
from urllib.parse import parse_qs, quote, urlsplit

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE
from issuedeck.features.search.saved import SavedSearchStore

PAGE = "/dashboard/example/search"
API = "/api/v1/projects/example"


def text(value, mode="simple", **extra):
    return {"type": "text", "mode": mode, "value": value, **extra}


def kind(*values):
    return {"type": "kind", "values": list(values)}


def query(*items):
    return {"items": list(items)}


def run_url(data, **params):
    extra = "".join(f"&{k}={quote(str(v))}" for k, v in params.items())
    return f"{PAGE}?query={quote(json.dumps(data))}{extra}"


@pytest.fixture
async def world(tmp_path):
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _ensure_demo_project_config(server.projects_dir, "second")
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
            ]:
                r = await client.post(f"{API}/items", headers=admin, json={
                    "kind": kind_, "title": title, "body": body})
                assert r.status_code == 201, r.text
            store = SavedSearchStore(server.data_dir, "example")
            yield client, store, app


def location(response):
    assert response.status_code == 303, response.text
    parts = urlsplit(response.headers["location"])
    return parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}


# ------------------------------------------------------------------ the latest search is kept


async def test_a_search_that_was_run_becomes_the_latest_one(world):
    client, store, _app = world
    assert store.is_empty()

    await client.get(run_url(query(text("import"), {"op": "and", **kind("bug")})))

    assert store.read()["active"] == {
        "name": None, "query": query(text("import"), {"op": "and", **kind("bug")})}


async def test_a_refused_search_and_a_second_page_do_not_change_the_latest_one(world):
    client, store, _app = world
    first = query(text("import"))
    await client.get(run_url(first))

    await client.get(run_url(query(kind("epic"))))  # refused: not a kind of the project
    await client.get(run_url(query(text("search")), after="MTIzfDE"))  # a later page

    assert store.read()["active"]["query"] == first


async def test_the_text_search_does_not_touch_the_saved_searches(world):
    client, store, _app = world

    await client.get(PAGE, params={"q": "import"})

    assert store.is_empty()


async def test_opening_the_page_restores_the_latest_search_in_the_dialog(world):
    client, store, _app = world
    data = query(text("importer"), {"op": "and", **kind("bug")})
    store.set_active(data)

    response = await client.get(PAGE)

    html = response.text
    assert response.status_code == 200
    assert "importer" in html and "searchBuilder(" in html  # the builder starts with it
    assert "data-latest-search" in html
    assert 'title+body match words "importer" AND kind is bug' in unescape(html)
    # nothing was run by itself: no results header
    assert "data-advanced-search-summary" not in html


async def test_the_latest_search_link_runs_it(world):
    client, store, _app = world
    store.set_active(query(text("import")))
    html = (await client.get(PAGE)).text
    link = unescape(html.split('data-latest-search')[0].rsplit('href="', 1)[1].split('"')[0])

    response = await client.get(link)

    assert "Import of CSV files" in response.text
    assert "data-advanced-search-summary" in response.text


async def test_each_project_has_its_own_searches(world):
    client, store, _app = world
    store.save("Only in example", query(text("import")))

    other = await client.get("/dashboard/second/search")

    assert "Only in example" not in other.text
    assert "data-latest-search" not in other.text
    mine = await client.get(PAGE)
    assert "Only in example" in mine.text


# ------------------------------------------------------------------ saving


async def test_a_search_is_saved_under_a_name_and_listed_in_the_dialog(world):
    client, store, _app = world
    data = query(text("import"), {"op": "and", **kind("bug")})

    response = await client.post(f"{PAGE}/saved", data={
        "name": "Import bugs", "query": json.dumps(data)})

    path, params = location(response)
    assert path == PAGE and params["notice"] == "saved" and params["notice_name"] == "Import bugs"
    assert json.loads(params["query"]) == data  # the page shows the search that was saved
    assert store.get("import bugs")["query"] == data
    page = await client.get(response.headers["location"])
    assert "Saved as Import bugs." in page.text
    assert "data-saved-searches" in page.text
    assert f'search?saved={quote("Import bugs")}' in page.text


async def test_a_saved_search_is_run_by_its_name_and_becomes_the_latest_with_that_name(world):
    client, store, _app = world
    store.save("Bugs", query(kind("bug")))
    store.set_active(query(text("something else")))

    response = await client.get(PAGE, params={"saved": "bugs"})

    assert "Import fails on an empty file" in response.text
    assert "Import of CSV files" not in response.text
    assert store.read()["active"] == {"name": "Bugs", "query": query(kind("bug"))}
    assert "kind is bug" in unescape(response.text)


async def test_a_saved_name_that_is_not_there_is_a_notice_not_an_error(world):
    client, _store, _app = world

    response = await client.get(PAGE, params={"saved": "nope"})

    assert response.status_code == 200
    assert "There is no saved search named nope." in response.text


async def test_saving_over_a_name_needs_the_overwrite_flag(world):
    client, store, _app = world
    old, new = query(text("old")), query(text("new"))
    store.save("Same", old)

    refused = await client.post(f"{PAGE}/saved", data={"name": "same", "query": json.dumps(new)})

    assert location(refused)[1]["notice"] == "exists"
    assert store.get("Same")["query"] == old

    allowed = await client.post(f"{PAGE}/saved", data={
        "name": "same", "query": json.dumps(new), "overwrite": "1"})

    assert location(allowed)[1]["notice"] == "saved"
    assert [s["name"] for s in store.read()["searches"]] == ["same"]
    assert store.get("same")["query"] == new


@pytest.mark.parametrize(("name", "data"), [
    ("", query(text("x"))),
    ("   ", query(text("x"))),
    ("Name", "not json"),
    ("Name", {"items": []}),
    ("Name", query(kind("epic"))),
    ("x" * 81, query(text("x"))),
])
async def test_what_cannot_be_saved_is_reported_and_nothing_is_written(world, name, data):
    client, store, _app = world
    raw = data if isinstance(data, str) else json.dumps(data)

    response = await client.post(f"{PAGE}/saved", data={"name": name, "query": raw})

    assert location(response)[1]["notice"] == "invalid"
    assert store.is_empty()


async def test_a_name_with_markup_is_shown_as_text(world):
    client, store, _app = world
    name = '<script>alert(1)</script>"\'&'
    store.save(name, query(text("x")))

    html = (await client.get(PAGE)).text

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ------------------------------------------------------------------ rename and delete


async def test_a_saved_search_is_renamed(world):
    client, store, _app = world
    store.save("Old", query(text("x")))

    response = await client.post(f"{PAGE}/saved/rename", data={"name": "old", "new_name": "New"})

    assert location(response)[1] == {"notice": "renamed", "notice_name": "New"}
    assert [s["name"] for s in store.read()["searches"]] == ["New"]
    assert store.read()["active"]["name"] == "New"


async def test_renaming_onto_a_taken_name_or_a_missing_one_is_a_notice(world):
    client, store, _app = world
    store.save("A", query(text("a")))
    store.save("B", query(text("b")))

    taken = await client.post(f"{PAGE}/saved/rename", data={"name": "A", "new_name": "b"})
    missing = await client.post(f"{PAGE}/saved/rename", data={"name": "zzz", "new_name": "c"})
    blank = await client.post(f"{PAGE}/saved/rename", data={"name": "A", "new_name": " "})

    assert location(taken)[1]["notice"] == "exists"
    assert location(missing)[1]["notice"] == "not_found"
    assert location(blank)[1]["notice"] == "invalid"
    assert [s["name"] for s in store.read()["searches"]] == ["A", "B"]


async def test_a_saved_search_is_deleted_but_stays_the_latest_search(world):
    client, store, _app = world
    store.save("Drop", query(text("x")))

    response = await client.post(f"{PAGE}/saved/delete", data={"name": "Drop"})

    assert location(response)[1] == {"notice": "deleted", "notice_name": "Drop"}
    assert store.read()["searches"] == []
    assert store.read()["active"] == {"name": None, "query": query(text("x"))}
    again = await client.post(f"{PAGE}/saved/delete", data={"name": "Drop"})
    assert location(again)[1]["notice"] == "not_found"


async def test_the_dialog_asks_before_replacing_or_deleting(world):
    client, store, _app = world
    store.save("Keep", query(text("x")))

    html = (await client.get(PAGE)).text

    assert "A saved search named {name} exists. Replace it?" in unescape(html)
    assert "Delete the saved search Keep?" in unescape(html)
    assert 'onclick="return confirm(this.dataset.confirm)"' in html


# ------------------------------------------------------------------ access and language


async def test_saving_needs_the_dashboard_login(world):
    _client, store, app = world
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as stranger:
        response = await stranger.post(f"{PAGE}/saved", data={
            "name": "x", "query": json.dumps(query(text("x")))})

    assert response.status_code in (303, 401, 403)
    assert response.status_code != 303 or "login" in response.headers["location"]
    assert store.is_empty()


async def test_the_new_texts_are_translated(world):
    client, store, _app = world
    store.save("X", query(text("x")))
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")
    hungarian = await client.get(PAGE)
    client.cookies.set(DASHBOARD_LANG_COOKIE, "zh-CN")
    chinese = await client.get(PAGE)

    assert "Mentett keresések" in hungarian.text and "Az utolsó keresés" in hungarian.text
    assert "已保存的搜索" in chinese.text and "运行最近一次搜索" in chinese.text
