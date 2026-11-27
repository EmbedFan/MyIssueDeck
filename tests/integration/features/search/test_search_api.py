"""FEA-0010 phase 2: the advanced search through the API and the MCP tool (real application)."""

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.core.errors import InvalidSearch
from issuedeck.mcp import tools
from issuedeck.mcp.client import IssueDeckClient

BASE = "/api/v1/projects/example"
TOKENS = """
[[tokens]]
name = "reader"
token = "reader-token-0123456789"
scopes = ["read"]

[[tokens]]
name = "writer"
token = "writer-token-0123456789"
scopes = ["agent"]
"""
READER = {"Authorization": "Bearer reader-token-0123456789"}
WRITER = {"Authorization": "Bearer writer-token-0123456789"}


def text(value, mode="simple", **extra):
    return {"type": "text", "mode": mode, "value": value, **extra}


def kind(*values):
    return {"type": "kind", "values": list(values)}


def status(*values):
    return {"type": "status", "values": list(values)}


def search(*items, **extra):
    return {"query": {"items": list(items)}, **extra}


@pytest.fixture
async def world(tmp_path, monkeypatch):
    """The real application with five items, an administrator, a reader and an agent token."""
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    config.write_text(config.read_text(encoding="utf-8") + TOKENS, encoding="utf-8")
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    admin = {"Authorization": f"Bearer {server.api_token.get_secret_value()}"}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            ids = {}
            for name, kind_, title, body in [
                ("A", "feature", "Import of CSV files", "The importer reads CSV files."),
                ("B", "feature", "Export to GitHub", "Import and export of snapshots."),
                ("C", "bug", "Import fails on an empty file", "Stack trace of the failure."),
                ("D", "bug", "Search is slow", "The regular expression search takes long."),
                ("E", "improvement", "Release notes", "Write them. Importing is done."),
            ]:
                r = await client.post(f"{BASE}/items", headers=admin, json={
                    "kind": kind_, "title": title, "body": body})
                assert r.status_code == 201, r.text
                ids[name] = r.json()["local_id"]
            await client.patch(f"{BASE}/items/{ids['B']}", headers=admin,
                               json={"status": "in_progress"})
            await client.patch(f"{BASE}/items/{ids['D']}", headers=admin,
                               json={"status": "wontfix"})
            yield client, app, ids, admin


async def post(client, body, headers=READER):
    return await client.post(f"{BASE}/search", json=body, headers=headers)


def found(response):
    assert response.status_code == 200, response.text
    return [item["local_id"] for item in response.json()["items"]]


# ------------------------------------------------------------------------------ the API


async def test_a_search_answers_with_items_and_a_description(world):
    client, _app, ids, _admin = world

    response = await post(client, search(text("import")))

    assert response.status_code == 200
    body = response.json()
    assert set(found(response)) == {ids["A"], ids["B"], ids["C"], ids["E"]}  # words match by stem
    assert body["next_cursor"] is None and body["limit"] == 50
    assert body["partial"] is False and body["notes"] == []
    assert body["description"] == 'title+body match words "import"'
    first = body["items"][0]
    assert {"local_id", "kind", "status", "title", "body_preview", "tags"} <= set(first)
    assert "updated_at" in first
    stamps = [item["updated_at"] for item in body["items"]]
    assert stamps == sorted(stamps, reverse=True)  # newest first


async def test_kinds_statuses_and_or_and_groups(world):
    client, _app, ids, _admin = world

    assert set(found(await post(client, search(kind("bug"))))) == {ids["C"], ids["D"]}
    assert set(found(await post(client, search(status("in_progress"))))) == {ids["B"]}
    both = search(text("import"), {"op": "and", **kind("bug")})
    assert found(await post(client, both)) == [ids["C"]]
    # the example of the request: text AND bug AND (proposed OR in_progress)
    example = search(
        text("import"), {"op": "and", **kind("bug")},
        {"op": "and", "group": [status("proposed"), {"op": "or", **status("in_progress")}]},
    )
    assert found(await post(client, example)) == [ids["C"]]
    # AND binds tighter than OR: feature OR bug AND wontfix = feature OR (bug AND wontfix)
    mixed = search(kind("feature"), {"op": "or", **kind("bug")}, {"op": "and", **status("wontfix")})
    assert set(found(await post(client, mixed))) == {ids["A"], ids["B"], ids["D"]}
    grouped = search({"group": [kind("feature"), {"op": "or", **kind("bug")}]},
                     {"op": "and", **status("wontfix")})
    assert found(await post(client, grouped)) == [ids["D"]]


async def test_a_regular_expression_search(world):
    client, _app, ids, _admin = world

    response = await post(client, search(text(r"^import", "regex", fields=["title"])))

    assert set(found(response)) == {ids["A"], ids["C"]}
    assert response.json()["description"] == 'title match regex "^import"'
    sensitive = search(text(r"^import", "regex", fields=["title"], case_sensitive=True))
    assert found(await post(client, sensitive)) == []


async def test_a_regular_expression_that_cannot_finish_is_reported_as_partial(world, monkeypatch):
    import issuedeck.features.search.evaluator as evaluator

    client, _app, _ids, admin = world
    await client.post(f"{BASE}/items", headers=admin, json={
        "kind": "feature", "title": "Long text", "body": "a" * 3000})
    monkeypatch.setattr(evaluator, "REGEX_SECONDS", 1.0)

    response = await post(client, search(text("a*a*a*a*a*a*a*b", "regex", fields=["body"])))

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [] and body["partial"] is True
    assert any("did not finish in 1 s" in note for note in body["notes"])


async def test_paging_walks_the_whole_result_without_repeating_an_item(world):
    client, _app, ids, _admin = world
    everything = found(await post(client, search(text("import"), limit=500)))
    assert len(everything) == 4

    pages, after = [], None
    for _ in range(5):
        body = {**search(text("import"), limit=2), **({"after": after} if after else {})}
        response = await post(client, body)
        pages.append(found(response))
        after = response.json()["next_cursor"]
        if after is None:
            break

    assert [len(p) for p in pages] == [2, 2]
    assert [i for page in pages for i in page] == everything  # the same order, no repeats
    assert after is None


# ------------------------------------------------------------------------------ refusals


async def test_a_refused_search_names_the_fault(world):
    client, _app, _ids, _admin = world

    deep = search(kind("bug"), {"op": "and", "group": [
        status("proposed"), {"op": "or", "group": [status("done")]}]})
    response = await post(client, deep)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_search"
    assert error["details"]["path"] == "items[1].group[1]"
    assert "nested 2 levels" in error["message"]


@pytest.mark.parametrize(("body", "path"), [
    (search(kind("epic")), "items[0]"),
    (search(text("(a+)+$", "regex")), "items[0]"),
    (search(text("x", case_sensitive=True)), "items[0]"),
    ({"query": {"items": []}}, "items"),
    ({"query": {"items": [kind("bug")], "extra": 1}}, ""),
    (search(kind("bug"), after="not a cursor!"), "after"),
])
async def test_other_refusals_are_422_with_a_path(world, body, path):
    client, _app, _ids, _admin = world

    response = await post(client, body)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_search"
    assert response.json()["error"]["details"]["path"] == path


@pytest.mark.parametrize("body", [
    {}, {"query": "import"}, {"query": {"items": [kind("bug")]}, "limit": 0},
    {"query": {"items": [kind("bug")]}, "limit": 501},
])
async def test_a_request_of_the_wrong_shape_is_422(world, body):
    client, _app, _ids, _admin = world

    assert (await post(client, body)).status_code == 422


async def test_an_unknown_project_is_404(world):
    client, _app, _ids, _admin = world

    response = await client.post("/api/v1/projects/nope/search", json=search(kind("bug")),
                                 headers=READER)

    assert response.status_code == 404


# ------------------------------------------------------------------------------ who may search


async def test_a_read_token_may_search_although_it_is_a_post(world):
    client, _app, ids, _admin = world

    # D was changed last, so it is the newest bug
    assert found(await post(client, search(kind("bug"), limit=1), READER)) == [ids["D"]]
    assert (await post(client, search(kind("bug")), WRITER)).status_code == 200


async def test_a_read_token_still_cannot_write(world):
    client, _app, _ids, _admin = world

    created = await client.post(f"{BASE}/items", headers=READER, json={
        "kind": "feature", "title": "no"})

    assert created.status_code == 403


async def test_no_token_is_401(world):
    client, _app, _ids, _admin = world

    assert (await client.post(f"{BASE}/search", json=search(kind("bug")))).status_code == 401
    wrong = await client.post(f"{BASE}/search", json=search(kind("bug")),
                              headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401


async def test_the_get_search_with_q_is_unchanged(world):
    client, _app, ids, _admin = world

    response = await client.get(f"{BASE}/search", params={"q": "import"}, headers=READER)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "next_cursor", "limit"}  # no partial, no notes: as before
    assert {i["local_id"] for i in body["items"]} >= {ids["A"], ids["C"]}


# ------------------------------------------------------------------------------ the MCP tool


@pytest.fixture
async def mcp(world, monkeypatch):
    _client, app, ids, admin = world
    token = admin["Authorization"].split(" ", 1)[1]
    client = IssueDeckClient("http://t", token, transport=httpx.ASGITransport(app=app))
    monkeypatch.setattr(tools, "get_client", lambda: client)
    yield ids
    await client.aclose()


async def test_the_mcp_tool_runs_a_structured_search(mcp):
    ids = mcp

    result = await tools.search_items("example", query={"items": [
        text("import"), {"op": "and", **kind("bug")}]})

    assert [i["local_id"] for i in result["items"]] == [ids["C"]]
    assert result["partial"] is False and "description" in result


async def test_the_mcp_tool_pages_with_after(mcp):
    first = await tools.search_items("example", query={"items": [text("import")]}, limit=3)
    second = await tools.search_items("example", query={"items": [text("import")]}, limit=3,
                                      after=first["next_cursor"])

    assert len(first["items"]) == 3 and first["next_cursor"]
    assert len(second["items"]) == 1 and second["next_cursor"] is None


async def test_the_mcp_tool_with_q_works_as_before(mcp):
    ids = mcp

    result = await tools.search_items("example", q="import", limit=10)

    assert {i["local_id"] for i in result["items"]} >= {ids["A"], ids["C"]}
    assert "description" not in result


async def test_the_mcp_tool_needs_exactly_one_of_q_and_query(mcp):
    with pytest.raises(InvalidSearch, match="exactly one"):
        await tools.search_items("example")
    with pytest.raises(InvalidSearch, match="exactly one"):
        await tools.search_items("example", q="x", query={"items": [kind("bug")]})


async def test_the_mcp_tool_reports_a_refused_query_with_its_path(mcp):
    with pytest.raises(InvalidSearch) as error:
        await tools.search_items("example", query={"items": [kind("epic")]})

    assert error.value.details["path"] == "items[0]"
