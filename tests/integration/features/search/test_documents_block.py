"""FEA-0010 phase 5: the document block of the advanced search (real application, real files)."""

import httpx
import pytest

import issuedeck.features.search.evaluator as evaluator
from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config

BASE = "/api/v1/projects/example"


def doc(value, mode="simple", **extra):
    return {"type": "document", "mode": mode, "value": value, **extra}


def kind(*values):
    return {"type": "kind", "values": list(values)}


def search(*items):
    return {"query": {"items": list(items)}}


@pytest.fixture
async def world(tmp_path):
    """Items A (feature), B (bug), C (improvement); documents linked to A and B, one to nobody."""
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    token = server.api_token.get_secret_value()
    admin = {"Authorization": f"Bearer {token}"}
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            ids = {}
            for name, kind_, title in [
                ("A", "feature", "Release plan"), ("B", "bug", "Crash on start"),
                ("C", "improvement", "Cleanup"),
            ]:
                r = await client.post(f"{BASE}/items", headers=admin, json={
                    "kind": kind_, "title": title, "body": "Nothing about it here."})
                assert r.status_code == 201, r.text
                ids[name] = r.json()["local_id"]
            docs = {}
            for name, file_name, kind_, title, body in [
                ("plan", "rollback-plan.md", "request", "How to roll back",
                 "Steps to rollback the release quickly. ROLLBACK is safe."),
                ("crash", "crash-report.md", "report", "Crash report",
                 "Stack trace: NullPointer in the loader."),
                ("orphan", "orphan.md", "other", "Loose notes", "rollback notes of nobody"),
            ]:
                r = await client.post(f"{BASE}/documents", headers=admin, json={
                    "name": file_name, "body": body, "kind": kind_, "title": title})
                assert r.status_code == 201, r.text
                docs[name] = r.json()["id"]
            for item, document in (("A", "plan"), ("B", "crash")):
                r = await client.post(f"{BASE}/items/{ids[item]}/documents", headers=admin,
                                      json={"document_id": docs[document]})
                assert r.status_code == 201, r.text
            yield client, admin, ids, docs


async def run(client, admin, *items):
    response = await client.post(f"{BASE}/search", json=search(*items), headers=admin)
    assert response.status_code == 200, response.text
    return response.json()


def found(body):
    return [item["local_id"] for item in body["items"]]


# ------------------------------------------------------------------------------ plain words


async def test_the_items_with_a_linked_document_that_has_the_words_are_found(world):
    client, admin, ids, _docs = world

    body = await run(client, admin, doc("rollback"))

    assert found(body) == [ids["A"]]  # the loose document is linked to nobody
    assert body["partial"] is False and body["notes"] == []
    assert body["description"] == (
        'a linked document: name+title+body match words "rollback"')


async def test_words_are_found_ignoring_case_in_any_order_and_as_written(world):
    client, admin, ids, _docs = world

    assert found(await run(client, admin, doc("RELEASE ROLLBACK"))) == [ids["A"]]
    assert found(await run(client, admin, doc("roll"))) == [ids["A"]]  # part of a word
    assert found(await run(client, admin, doc("rolling"))) == []  # no stemming here
    assert found(await run(client, admin, doc("rollback nullpointer"))) == []  # not in one document


async def test_special_characters_are_only_characters(world):
    client, admin, ids, _docs = world

    for text in ('" OR 1=1 --', "*", "NEAR(", "'; DROP TABLE items; --"):
        assert found(await run(client, admin, doc(text))) == []
    assert found(await run(client, admin, doc("rollback"))) == [ids["A"]]  # the data is intact


async def test_the_fields_are_the_name_and_title_or_the_text(world):
    client, admin, ids, _docs = world

    only_title = await run(client, admin, doc("rollback-plan", fields=["title"]))
    only_body = await run(client, admin, doc("rollback-plan", fields=["body"]))
    title_of = await run(client, admin, doc("Crash report", fields=["title"]))
    by_body = await run(client, admin, doc("Stack trace", fields=["body"]))

    assert found(only_title) == [ids["A"]] and found(only_body) == []  # a name is in "title"
    assert found(title_of) == [ids["B"]] and found(by_body) == [ids["B"]]


async def test_the_kind_of_the_document_limits_the_search(world):
    client, admin, ids, _docs = world

    assert found(await run(client, admin, doc("crash", kinds=["report"]))) == [ids["B"]]
    assert found(await run(client, admin, doc("crash", kinds=["request"]))) == []
    both = await run(client, admin, doc("crash", kinds=["request", "report"]))
    assert found(both) == [ids["B"]]
    assert "(document kind is request or report)" in both["description"]


# ------------------------------------------------------------------------------ expressions


async def test_a_regular_expression_is_matched_in_the_documents(world):
    client, admin, ids, _docs = world

    body = await run(client, admin, doc(r"NullPointer\b", "regex", fields=["body"]))

    assert found(body) == [ids["B"]]
    assert body["description"] == (
        'a linked document: body match regex "NullPointer\\b"')


async def test_case_sensitivity_of_a_regular_expression(world):
    client, admin, ids, _docs = world

    assert found(await run(client, admin, doc("ROLLBACK", "regex"))) == [ids["A"]]  # ignores case
    sensitive = await run(client, admin, doc("^Steps", "regex", case_sensitive=True,
                                             fields=["body"]))
    assert found(sensitive) == [ids["A"]]
    wrong_case = await run(client, admin, doc("^steps", "regex", case_sensitive=True,
                                              fields=["body"]))
    assert found(wrong_case) == []


async def test_a_regular_expression_respects_the_kind_of_the_document(world):
    client, admin, ids, _docs = world

    assert found(await run(client, admin, doc("rollback", "regex", kinds=["report"]))) == []
    assert found(await run(client, admin, doc("rollback", "regex", kinds=["request"]))) == [
        ids["A"]]


async def test_a_regular_expression_that_cannot_finish_gives_a_partial_result(world, monkeypatch):
    client, admin, ids, _docs = world
    await client.post(f"{BASE}/documents", headers=admin, json={
        "name": "long.md", "body": "a" * 3000, "kind": "other"})
    monkeypatch.setattr(evaluator, "REGEX_SECONDS", 1.0)

    body = await run(client, admin, doc("a*a*a*a*a*a*a*b", "regex", fields=["body"]),
                     {"op": "or", **kind("bug")})

    assert found(body) == [ids["B"]]  # what finished is kept
    assert body["partial"] is True
    assert any("of a document block did not finish in 1 s" in note for note in body["notes"])


# ------------------------------------------------------------------------------ combining


async def test_a_document_block_combines_with_the_other_blocks(world):
    client, admin, ids, _docs = world

    both = await run(client, admin, doc("rollback"), {"op": "and", **kind("bug")})
    either = await run(client, admin, doc("rollback"), {"op": "or", **kind("bug")})
    grouped = await run(client, admin, {"group": [doc("rollback"), {"op": "or", **doc("crash")}]},
                        {"op": "and", **kind("bug")})

    assert found(both) == []
    assert set(found(either)) == {ids["A"], ids["B"]}
    assert found(grouped) == [ids["B"]]


async def test_a_deleted_item_is_not_found_through_its_document(world):
    client, admin, ids, _docs = world

    assert (await client.delete(f"{BASE}/items/{ids['A']}", headers=admin)).status_code in (
        200, 204)

    assert found(await run(client, admin, doc("rollback"))) == []


async def test_an_unlinked_document_is_found_again_once_it_is_linked(world):
    client, admin, ids, docs = world
    assert found(await run(client, admin, doc("nobody"))) == []

    await client.post(f"{BASE}/items/{ids['C']}/documents", headers=admin,
                      json={"document_id": docs["orphan"]})

    assert found(await run(client, admin, doc("nobody"))) == [ids["C"]]


async def test_a_project_without_documents_finds_nothing_and_does_not_fail(tmp_path):
    from issuedeck.cli import _ensure_demo_config as cfg
    config = tmp_path / 'server.toml'
    cfg(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, 'example')
    _upgrade_database(config)
    app = create_app(config)
    admin = {'Authorization': f'Bearer {server.api_token.get_secret_value()}'}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url='http://t') as client:
            response = await client.post(f'{BASE}/search', headers=admin,
                                         json=search(doc('anything')))

    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_a_document_block_looks_at_a_limited_number_of_documents(world, monkeypatch):
    client, admin, ids, _docs = world
    monkeypatch.setattr(evaluator, "MAX_DOCUMENTS", 1)

    body = await run(client, admin, doc("crash"))

    assert body["partial"] is True
    assert any("only at the first 1 of 3 documents" in note for note in body["notes"])
    assert found(body) == []  # the document with "crash" is the second one


# ------------------------------------------------------------------------------ refusals


@pytest.mark.parametrize(("block", "path"), [
    (doc("x", kinds=["epic"]), "items[0]"),
    (doc("x", kinds=[]), "items[0]"),
    (doc("x", kinds=["report", "report"]), "items[0]"),
    (doc("x", case_sensitive=True), "items[0]"),
    (doc("x", fields=["name"]), "items[0]"),
    (doc("", "simple"), "items[0]"),
    (doc("(a+)+$", "regex"), "items[0]"),
    ({**doc("x"), "extra": 1}, "items[0]"),
])
async def test_a_bad_document_block_is_refused_with_its_path(world, block, path):
    client, admin, _ids, _docs = world

    response = await client.post(f"{BASE}/search", json=search(block), headers=admin)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_search"
    assert response.json()["error"]["details"]["path"] == path


async def test_the_text_block_is_unchanged_by_the_document_block(world):
    client, admin, ids, _docs = world

    body = await run(client, admin, {"type": "text", "value": "nothing"})

    assert set(found(body)) == {ids["A"], ids["B"], ids["C"]}
