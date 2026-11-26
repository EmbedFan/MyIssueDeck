"""FEA-0013 phase 4: images linked to items (API, dashboard, events, deleting an image)."""

import httpx
import pytest

from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config

NS = 'xmlns="http://www.w3.org/2000/svg"'
SVG_A = f'<svg {NS}><rect width="1" height="1"/></svg>'.encode()
SVG_B = f'<svg {NS}><circle r="2"/></svg>'.encode()
API = "/api/v1/projects/example"
DASH = "/dashboard/example"


@pytest.fixture
async def world(tmp_path):
    """The real application: an API client (bearer token) and a dashboard client (cookie)."""
    config = tmp_path / "server.toml"
    _ensure_demo_config(config)
    server = load_server_config(config)
    _ensure_demo_project_config(server.projects_dir, "example")
    _upgrade_database(config)
    app = create_app(config)
    token = server.api_token.get_secret_value()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as dash, \
                httpx.AsyncClient(transport=transport, base_url="http://t",
                                  headers={"Authorization": f"Bearer {token}"}) as api:
            await dash.post("/dashboard/login", data={"token": token})
            yield api, dash, server


async def _item(api, title="An item"):
    r = await api.post(f"{API}/items", json={"kind": "feature", "title": title})
    assert r.status_code == 201, r.text
    return r.json()["local_id"]


async def _image(api, data=SVG_A, name="a.svg"):
    r = await api.post(f"{API}/images", files={"file": (name, data, "image/svg+xml")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _event_types(api, local_id):
    detail = (await api.get(f"{API}/items/{local_id}")).json()
    return [e["event_type"] for e in detail["events"]]


async def test_link_list_and_unlink_through_the_api(world):
    api, _dash, _server = world
    local_id = await _item(api)
    first = await _image(api)
    second = await _image(api, SVG_B, "b.svg")

    linked = await api.post(f"{API}/items/{local_id}/images", json={"image_id": first})
    await api.post(f"{API}/items/{local_id}/images", json={"image_id": second})

    assert linked.status_code == 201 and linked.json()["id"] == first
    listing = (await api.get(f"{API}/items/{local_id}/images")).json()
    assert [i["id"] for i in listing["items"]] == [first, second]
    assert listing["total_bytes"] == len(SVG_A) + len(SVG_B)

    removed = await api.delete(f"{API}/items/{local_id}/images/{first}")

    assert removed.status_code == 204
    after = (await api.get(f"{API}/items/{local_id}/images")).json()
    assert [i["id"] for i in after["items"]] == [second]
    assert (await api.get(f"{API}/images/{first}")).status_code == 200  # the image stays


async def test_linking_twice_is_harmless_and_writes_one_event(world):
    api, _dash, _server = world
    local_id = await _item(api)
    image = await _image(api)

    for _ in range(2):
        r = await api.post(f"{API}/items/{local_id}/images", json={"image_id": image})
        assert r.status_code == 201

    assert len((await api.get(f"{API}/items/{local_id}/images")).json()["items"]) == 1
    assert (await _event_types(api, local_id)).count("image_linked") == 1


async def test_link_changes_are_written_to_the_activity(world):
    api, _dash, _server = world
    local_id = await _item(api)
    image = await _image(api)

    await api.post(f"{API}/items/{local_id}/images", json={"image_id": image})
    await api.delete(f"{API}/items/{local_id}/images/{image}")

    detail = (await api.get(f"{API}/items/{local_id}")).json()
    events = [e for e in detail["events"] if e["event_type"].startswith("image_")]
    assert sorted(e["event_type"] for e in events) == ["image_linked", "image_unlinked"]
    assert all(e["metadata"]["image_id"] == image for e in events)
    assert f"Linked image {image}." in [e["body"] for e in events]


async def test_unknown_item_image_or_link_is_a_404(world):
    api, _dash, _server = world
    local_id = await _item(api)
    image = await _image(api)

    unknown_item = await api.post(f"{API}/items/FEAT-9999/images", json={"image_id": image})
    unknown_image = await api.post(f"{API}/items/{local_id}/images",
                                   json={"image_id": "IMG-0099"})
    not_linked = await api.delete(f"{API}/items/{local_id}/images/{image}")

    assert unknown_item.status_code == 404
    assert unknown_item.json()["error"]["code"] == "item_not_found"
    assert unknown_image.status_code == 404
    assert unknown_image.json()["error"]["code"] == "image_not_found"
    assert not_linked.status_code == 404


async def test_deleting_an_image_removes_its_links_and_says_so_on_the_items(world):
    api, _dash, server = world
    one, two = await _item(api, "one"), await _item(api, "two")
    image = await _image(api)
    other = await _image(api, SVG_B, "b.svg")
    for local_id in (one, two):
        await api.post(f"{API}/items/{local_id}/images", json={"image_id": image})
    await api.post(f"{API}/items/{one}/images", json={"image_id": other})

    assert (await api.delete(f"{API}/images/{image}")).status_code == 204

    assert [i["id"] for i in (await api.get(f"{API}/items/{one}/images")).json()["items"]] \
        == [other]
    assert (await api.get(f"{API}/items/{two}/images")).json()["items"] == []
    assert "image_unlinked" in await _event_types(api, two)
    assert not (server.data_dir / "images" / "example" / f"{image}.svg").exists()


async def test_deleting_an_unknown_image_changes_no_links(world):
    api, _dash, _server = world
    local_id = await _item(api)
    image = await _image(api)
    await api.post(f"{API}/items/{local_id}/images", json={"image_id": image})

    assert (await api.delete(f"{API}/images/IMG-0099")).status_code == 404

    assert len((await api.get(f"{API}/items/{local_id}/images")).json()["items"]) == 1


async def test_the_item_page_shows_linked_images_and_offers_the_others(world):
    api, dash, _server = world
    local_id = await _item(api)
    first = await _image(api)
    second = await _image(api, SVG_B, "b.svg")
    await api.post(f"{API}/items/{local_id}/images", json={"image_id": first})

    page = await dash.get(f"{DASH}/items/{local_id}")

    assert page.status_code == 200
    assert f'data-linked-image="{first}"' in page.text
    assert f'src="{DASH}/images/{first}/file"' in page.text
    assert f'action="{DASH}/items/{local_id}/images/{first}/unlink"' in page.text
    select = page.text.split('id="link_image_id"')[1].split("</select>")[0]
    assert second in select and first not in select
    assert '"example"' in page.text  # the Markdown renderer is told the project


async def test_the_item_page_links_and_unlinks_images(world):
    api, dash, _server = world
    local_id = await _item(api)
    image = await _image(api)

    linked = await dash.post(f"{DASH}/items/{local_id}/images", data={"image_id": image},
                             follow_redirects=False)

    assert linked.status_code == 303
    assert linked.headers["location"] == f"{DASH}/items/{local_id}"
    assert f'data-linked-image="{image}"' in (await dash.get(f"{DASH}/items/{local_id}")).text

    unlinked = await dash.post(f"{DASH}/items/{local_id}/images/{image}/unlink",
                               follow_redirects=False)

    assert unlinked.status_code == 303
    page = await dash.get(f"{DASH}/items/{local_id}")
    assert "data-linked-image" not in page.text and "data-no-linked-images" in page.text


async def test_an_item_without_images_in_the_project_says_so(world):
    api, dash, _server = world
    local_id = await _item(api)

    page = await dash.get(f"{DASH}/items/{local_id}")

    assert "The project has no images yet." in page.text
    assert 'id="link_image_id"' not in page.text


async def test_the_images_page_counts_the_links_and_warns_before_deleting(world):
    api, dash, _server = world
    one, two = await _item(api, "one"), await _item(api, "two")
    image = await _image(api)
    for local_id in (one, two):
        await api.post(f"{API}/items/{local_id}/images", json={"image_id": image})

    page = await dash.get(f"{DASH}/images")

    assert 'data-linked-count="2"' in page.text
    assert "Linked to 2 item(s)" in page.text
    assert "Its links to 2 item(s) are removed." in page.text

    deleted = await dash.post(f"{DASH}/images/{image}/delete", follow_redirects=False)

    assert deleted.status_code == 303
    assert (await api.get(f"{API}/items/{one}/images")).json()["items"] == []


async def test_the_edit_page_can_insert_an_image_reference(world):
    api, dash, _server = world
    local_id = await _item(api)
    image = await _image(api, name="Pump [layout].svg")

    edit = await dash.get(f"{DASH}/items/{local_id}/edit")
    create = await dash.get(f"{DASH}/items-new")

    for page in (edit, create):
        assert "data-insert-image" in page.text
        assert f"(image:{image})" in page.text
    assert "![Pump layout.svg](image:" in edit.text  # brackets removed from the alt text


async def test_pages_without_images_have_no_insert_menu(world):
    api, dash, _server = world
    local_id = await _item(api)

    edit = await dash.get(f"{DASH}/items/{local_id}/edit")

    assert "data-insert-image" not in edit.text


async def test_linking_needs_a_token_or_a_session(world):
    api, dash, _server = world
    local_id = await _item(api)
    image = await _image(api)
    transport = api._transport
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as anonymous:
        by_api = await anonymous.post(f"{API}/items/{local_id}/images",
                                      json={"image_id": image})
        by_page = await anonymous.post(f"{DASH}/items/{local_id}/images",
                                       data={"image_id": image})

    assert by_api.status_code == 401
    assert by_page.status_code == 401
