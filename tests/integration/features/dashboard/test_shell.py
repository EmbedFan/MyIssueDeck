"""IS-0007: language combo box, optional import entries, application icon and built-in help.

These run against the real application (login, static files, /favicon.ico), because the wiring
of the shell is what they check.
"""

import hashlib
import json
import re
import struct
from pathlib import Path

import httpx
import pytest

from issuedeck import __version__
from issuedeck.app import create_app
from issuedeck.cli import _ensure_demo_config, _ensure_demo_project_config, _upgrade_database
from issuedeck.core.config import load_server_config
from issuedeck.core.errors import InvalidSetting
from issuedeck.core.runtime_settings import DEFAULT_SETTINGS, validate_navigation
from issuedeck.features.dashboard import help_routes
from issuedeck.features.dashboard.help_build import (
    CONTENTS_LABEL,
    HELP_DIR,
    anchors,
    build_html,
    html_path,
    source_path,
)
from issuedeck.features.dashboard.i18n import (
    DASHBOARD_LANG_COOKIE,
    LANGUAGE_NAMES,
    SUPPORTED_LANGS,
)

STATIC = Path(help_routes.__file__).parent / "static"
IMPORT_LINKS = (
    "/dashboard/example/imports/github",
    "/dashboard/example/imports/files",
)
HISTORY_LINK = 'href="/dashboard/example/imports"'


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
            yield client, app, tmp_path


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", data[16:24])


# ---------------------------------------------------------------------------
# part 1: the language combo box
# ---------------------------------------------------------------------------

async def test_the_language_is_chosen_in_a_combo_box(shell):
    client, *_ = shell
    html = (await client.get("/dashboard/example")).text

    assert '<select id="language-select" name="lang"' in html
    assert 'action="/dashboard/language"' in html and 'name="next"' in html
    for code, name in LANGUAGE_NAMES.items():
        assert re.search(rf'<option value="{code}" lang="{code}"[^>]*>\s*{name}\s*</option>', html)
    assert 'value="en" lang="en" selected' in html
    # no more button group; without JavaScript a button applies the choice
    assert not re.search(r'<button[^>]*name="lang"', html)
    assert "<noscript>" in html and 'for="language-select"' in html
    assert "requestSubmit" in html


async def test_the_combo_box_shows_the_current_language_by_its_own_name(shell):
    client, *_ = shell
    for code, name in LANGUAGE_NAMES.items():
        client.cookies.set(DASHBOARD_LANG_COOKIE, code)
        html = (await client.get("/dashboard/example")).text
        assert re.search(rf'<option value="{code}" lang="{code}" selected>\s*{name}', html), code


async def test_every_supported_language_is_in_the_combo_box_and_named():
    assert set(LANGUAGE_NAMES) == set(SUPPORTED_LANGS)


async def test_choosing_a_language_keeps_the_page(shell):
    client, *_ = shell
    response = await client.post(
        "/dashboard/language", data={"lang": "hu", "next": "/dashboard/example/list?status=x"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard/example/list?status=x"
    assert DASHBOARD_LANG_COOKIE in response.headers["set-cookie"]


# ---------------------------------------------------------------------------
# part 2: optional import entries
# ---------------------------------------------------------------------------

async def test_the_import_entries_are_off_by_default(shell):
    client, *_ = shell
    html = (await client.get("/dashboard/example")).text
    assert DEFAULT_SETTINGS["navigation"] == {
        "import_github": False, "import_history": False, "import_files": False}
    for link in IMPORT_LINKS:
        assert link not in html
    assert HISTORY_LINK not in html
    assert "/dashboard/example/kanban" in html  # the other entries are still there


async def test_each_entry_can_be_switched_on_alone(shell):
    client, app, _ = shell
    runtime = app.state.runtime_settings
    history = 'href="/dashboard/example/imports"'
    for flag, present, absent in (
        ("import_github", "/imports/github", ("/imports/files", history)),
        ("import_files", "/imports/files", ("/imports/github", history)),
        ("import_history", history, ("/imports/github", "/imports/files")),
    ):
        runtime.reset_group("navigation")
        runtime.update_settings({"navigation": {flag: True}})
        html = (await client.get("/dashboard/example")).text
        assert present in html, flag
        assert not any(other in html for other in absent), flag


async def test_the_settings_page_has_the_navigation_section(shell):
    client, *_ = shell
    html = (await client.get("/dashboard/settings")).text
    assert 'aria-labelledby="settings-navigation"' in html
    for name in ("import_github", "import_history", "import_files"):
        assert f'name="{name}" value="1"' in html
    section = html[html.index('name="import_github"'):html.index('name="import_files"')]
    assert "checked" not in section


async def test_the_entries_are_saved_audited_and_reset_without_a_restart(shell):
    client, app, _ = shell
    runtime = app.state.runtime_settings
    saved = await client.post(
        "/dashboard/settings/navigation", data={"import_files": "1", "import_github": "1"},
    )
    assert saved.status_code == 303
    assert runtime.settings()["navigation"] == {
        "import_github": True, "import_history": False, "import_files": True}
    html = (await client.get("/dashboard/example")).text
    assert "/imports/github" in html and "/imports/files" in html
    assert runtime.audit_log()[0]["action"] == "settings.updated"

    reset = await client.post("/dashboard/settings/navigation/reset")
    assert reset.status_code == 303
    assert runtime.settings()["navigation"] == DEFAULT_SETTINGS["navigation"]
    assert "/imports/files" not in (await client.get("/dashboard/example")).text
    assert runtime.audit_log()[0]["action"] == "navigation.reset"


async def test_hidden_pages_stay_reachable_and_keep_their_title(shell):
    client, *_ = shell
    for path, title in (
        ("/dashboard/example/imports/files", "Import Files"),
        ("/dashboard/example/imports/github", "Import GitHub"),
        ("/dashboard/example/imports", "Import History"),
    ):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert title in response.text, path


def test_the_navigation_flags_must_all_be_given_and_be_booleans():
    assert validate_navigation(
        {"import_github": True, "import_history": False, "import_files": False},
    )["import_github"] is True
    wrong = (
        {"import_github": True},
        {"import_github": 1, "import_history": 0, "import_files": 0},
        {"import_github": True, "import_history": False, "import_files": False, "x": True},
    )
    for bad in wrong:
        with pytest.raises(InvalidSetting):
            validate_navigation(bad)


# ---------------------------------------------------------------------------
# part 3: the application icon
# ---------------------------------------------------------------------------

def test_the_small_icons_are_made_from_the_master_and_shipped_in_the_package():
    img = STATIC / "img"
    master = Path(help_routes.__file__).parents[3] / "resources" / "favicon_my_issuedeck.png"
    assert master.exists() and _png_size(master) == (1254, 1254)
    for name, side in {"favicon-32.png": 32, "favicon-48.png": 48, "apple-touch-icon.png": 180,
                       "icon-192.png": 192, "icon-512.png": 512}.items():
        assert _png_size(img / name) == (side, side), name
    # nobody downloads the 950 KB original: the tab icon is tiny and none is large
    assert (img / "favicon-32.png").stat().st_size < 10_000
    assert all(p.stat().st_size < 250_000 for p in img.iterdir())
    assert master.stat().st_size > 10 * max(p.stat().st_size for p in img.iterdir()
                                            if p.name != "icon-512.png")

    ico = (img / "favicon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", ico[:6])
    assert (reserved, kind) == (0, 1) and count == 3
    sizes = {ico[6 + 16 * i] or 256 for i in range(count)}
    assert sizes == {16, 32, 48}


async def test_favicon_ico_is_served_without_signing_in_and_cached(shell):
    _, app, _ = shell
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as anon:
        response = await anon.get("/favicon.ico?v=whatever")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/x-icon"
    assert "max-age" in response.headers["cache-control"]
    assert response.content[:4] == b"\x00\x00\x01\x00"
    assert response.content == (STATIC / "img" / "favicon.ico").read_bytes()


async def test_every_page_declares_the_icons_and_they_can_be_fetched(shell):
    client, app, _ = shell
    version = hashlib.sha1((STATIC / "img" / "favicon.ico").read_bytes()).hexdigest()[:8]  # noqa: S324
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as anon:
        login = (await anon.get("/dashboard/login")).text
    dashboard = (await client.get("/dashboard/example")).text
    for name, html in (("login", login), ("dashboard", dashboard)):
        assert 'rel="icon" href="/favicon.ico?v=' + version in html, name
        assert 'rel="apple-touch-icon"' in html and 'rel="manifest"' in html, name
        link = r'<link rel="(?:icon|apple-touch-icon|manifest)"[^>]*href="([^"]+)"'
        hrefs = re.findall(link, html)
        assert len(hrefs) >= 4, name
        for href in hrefs:
            assert f"v={version}" in href, (name, href)
            assert (await client.get(href)).status_code == 200, (name, href)


async def test_the_manifest_points_to_icons_that_exist(shell):
    client, *_ = shell
    manifest = json.loads((await client.get("/dashboard/static/manifest.json")).text)
    assert manifest["name"] == "MyIssueDeck" and len(manifest["icons"]) == 2
    for icon in manifest["icons"]:
        assert (await client.get(icon["src"])).status_code == 200
        side = int(icon["sizes"].split("x")[0])
        assert _png_size(STATIC / "img" / Path(icon["src"]).name) == (side, side)


# ---------------------------------------------------------------------------
# part 4: the built-in help
# ---------------------------------------------------------------------------

def test_there_is_a_source_and_a_generated_page_for_every_supported_language():
    for lang in SUPPORTED_LANGS:
        assert source_path(lang).exists(), lang
        assert html_path(lang).exists(), lang


def test_the_generated_pages_are_up_to_date_with_their_sources():
    """Fails when a source was changed without running scripts/build_help.py."""
    for lang in SUPPORTED_LANGS:
        built = build_html(lang, source_path(lang).read_text(encoding="utf-8"))
        assert html_path(lang).read_text(encoding="utf-8") == built, (
            f"{lang}: run python scripts/build_help.py"
        )


def test_every_language_has_the_same_sections():
    by_lang = {lang: anchors(source_path(lang).read_text(encoding="utf-8"))
               for lang in SUPPORTED_LANGS}
    english = by_lang["en"]
    assert len(english) >= 10 and len(set(english)) == len(english)
    for required in ("start", "projects", "items", "board", "list-search", "overview", "agents",
                     "settings", "import-export", "shortcuts", "mcp", "troubleshooting"):
        assert required in english
    for lang, found in by_lang.items():
        assert found == english, f"{lang} differs from en"


def test_the_help_lists_the_same_shortcuts_in_every_language():
    for lang in SUPPORTED_LANGS:
        table = source_path(lang).read_text(encoding="utf-8").split("{#shortcuts}")[1]
        rows = [line for line in table.splitlines() if line.startswith("| `")]
        assert len(rows) == 8, lang


def test_the_generator_is_strict_and_never_passes_raw_html():
    with pytest.raises(ValueError, match="no {#anchor}"):
        build_html("en", "## A heading without an anchor\n")
    with pytest.raises(ValueError, match="used twice"):
        build_html("en", "## One {#same}\n\n## Two {#same}\n")
    source = "## Title {#t}\n\n<script>alert(1)</script>\n\n[x](javascript:alert(1))\n"
    page = build_html("en", source)
    assert "<script>" not in page and 'href="javascript:' not in page
    assert 'id="t"' in page and 'href="#t"' in page and "data-help-contents" in page


def test_no_markdown_marker_is_left_in_any_generated_page():
    """With Chinese, "**label：**text" does not close the bold; it showed the stars."""
    for lang in SUPPORTED_LANGS:
        page = html_path(lang).read_text(encoding="utf-8")
        assert "**" not in page, lang
    head, rest = "## T {#t}\n\n- ", "\u6d45\u8272\u548c\u6df1\u8272\n"
    with pytest.raises(ValueError, match="bold marker"):
        build_html("zh-CN", head + "**\u5916\u89c2\uff1a**" + rest)
    ok = build_html("zh-CN", head + "**\u5916\u89c2**\uff1a" + rest)
    assert "<strong>\u5916\u89c2</strong>\uff1a" in ok


def test_the_table_of_contents_links_every_section_in_every_language():
    for lang in SUPPORTED_LANGS:
        page = html_path(lang).read_text(encoding="utf-8")
        for anchor in anchors(source_path(lang).read_text(encoding="utf-8")):
            assert f'id="{anchor}"' in page and f'href="#{anchor}"' in page, (lang, anchor)
        assert f'aria-label="{CONTENTS_LABEL[lang]}"' in page


async def test_the_help_page_follows_the_chosen_language(shell):
    client, *_ = shell
    expected = {"en": ("Help", "Getting started"), "hu": ("Súgó", "Első lépések"),
                "zh-CN": ("帮助", "开始使用")}
    for lang, (title, first) in expected.items():
        client.cookies.set(DASHBOARD_LANG_COOKIE, lang)
        response = await client.get("/dashboard/help")
        assert response.status_code == 200, lang
        html = response.text
        assert f'lang="{lang}"' in html and f">{title}</h1>" in html, lang
        assert f'<h2 id="start">{first}</h2>' in html, lang
        assert "data-help-fallback" not in html
        assert "data-help-version" in html and __version__ in html
        assert "window.print()" in html


async def test_the_help_falls_back_to_english_and_says_so(shell, monkeypatch):
    client, *_ = shell
    real = help_routes.html_path

    def missing_for_hungarian(lang):
        return HELP_DIR / "hu-missing.html" if lang == "hu" else real(lang)

    monkeypatch.setattr(help_routes, "html_path", missing_for_hungarian)
    help_routes._page.cache_clear()
    try:
        client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")
        html = (await client.get("/dashboard/help")).text
    finally:
        help_routes._page.cache_clear()
    assert "data-help-fallback" in html and "az angol szöveg látható" in html
    assert '<h2 id="start">Getting started</h2>' in html


async def test_the_help_button_is_the_last_block_of_the_left_panel(shell):
    client, *_ = shell
    html = (await client.get("/dashboard/example")).text
    aside = html[html.index("<aside"):html.index("</aside>")]
    assert aside.count("data-sidebar-help") == 1
    assert aside.index("data-sidebar-help") > aside.index("Projects")  # below the project list
    assert 'href="/dashboard/help?project=example"' in aside
    assert "<svg" in aside[aside.index("data-sidebar-help"):]
    # nothing follows it: the block holds one link, the help
    assert aside[aside.index("data-sidebar-help"):].count("<a ") == 1


async def test_the_help_page_highlights_its_button_and_keeps_the_project_views(shell):
    client, *_ = shell
    html = (await client.get("/dashboard/help?project=example")).text
    aside = html[html.index("<aside"):html.index("</aside>")]
    assert 'aria-current="page"' in aside[aside.index("data-sidebar-help"):]
    assert "/dashboard/example/kanban" in aside  # the project views stay in the left panel
    plain = (await client.get("/dashboard/help")).text
    block = plain[plain.index("data-sidebar-help"):][:200]
    assert 'href="/dashboard/help"' in block and "?project=" not in block


async def test_sidebar_shows_the_software_version(shell):
    """IS-0013: the top-left box shows V<version> instead of the text "ID"."""
    client, _app, _tmp = shell

    page = await client.get("/dashboard/example/list")

    assert page.status_code == 200
    box = page.text.split("data-app-version>")[1].split("</span>")[0]
    assert box.strip() == f"V{__version__}"


async def _create_item(client, title="Quick save"):
    response = await client.post(
        "/dashboard/example/items-new",
        data={"kind": "feature", "title": title, "applies_to": "main"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response.headers["location"].rsplit("/", 1)[1]


async def test_edit_page_offers_ctrl_s_and_the_create_page_does_not(shell):
    """IS-0012: Ctrl-S is wired on the edit page only."""
    client, _app, _tmp = shell
    local_id = await _create_item(client)

    edit = await client.get(f"/dashboard/example/items/{local_id}/edit")
    create = await client.get("/dashboard/example/items-new")

    assert "@keydown.ctrl.s.window.prevent" in edit.text
    assert "@keydown.meta.s.window.prevent" in edit.text
    assert "data-save-status" in edit.text
    assert "@keydown.ctrl.s" not in create.text
    assert "data-save-status" not in create.text


async def test_ctrl_s_save_returns_json_and_keeps_the_editor_open(shell):
    """IS-0012: the background save stores the item and does not redirect."""
    client, _app, _tmp = shell
    local_id = await _create_item(client)

    response = await client.post(
        f"/dashboard/example/items/{local_id}/edit",
        data={"title": "Saved by Ctrl-S", "body": "Edited text", "tags": "a, b",
              "applies_to": "main"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "local_id": local_id}
    page = await client.get(f"/dashboard/example/items/{local_id}")
    assert "Saved by Ctrl-S" in page.text
    assert "Edited text" in page.text


async def test_save_button_still_redirects_to_the_item_page(shell):
    """IS-0012: without the fetch header the form behaves as before."""
    client, _app, _tmp = shell
    local_id = await _create_item(client)

    response = await client.post(
        f"/dashboard/example/items/{local_id}/edit",
        data={"title": "Saved by button", "body": "", "applies_to": "main"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/dashboard/example/items/{local_id}"


async def test_ctrl_s_save_reports_a_server_error_as_json(shell):
    """IS-0012: a refused save answers with the error message the page shows."""
    client, _app, _tmp = shell
    local_id = await _create_item(client)

    response = await client.post(
        f"/dashboard/example/items/{local_id}/edit",
        data={"title": "x", "body": "", "applies_to": "no-such-branch"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
        follow_redirects=False,
    )

    assert response.status_code >= 400
    assert response.json()["error"]["message"]
