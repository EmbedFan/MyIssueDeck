"""FEA-0004: the settings page, its forms, and runtime token authentication."""

import json
import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.auth import (
    DASHBOARD_SESSION_COOKIE,
    BearerTokenCredential,
    BearerTokenMiddleware,
    is_valid_dashboard_session_cookie,
)
from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    KindConfig,
    ProjectConfig,
    StatusConfig,
    load_server_config,
)
from issuedeck.core.errors import install_error_handlers
from issuedeck.core.runtime_settings import RuntimeSettings
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.dashboard.settings_routes import (
    apply_tracking_defaults,
)
from issuedeck.features.dashboard.settings_routes import (
    router as settings_router,
)
from issuedeck.features.items.models import Base
from issuedeck.features.items.routes import router as items_router
from issuedeck.features.projects.routes import router as projects_router


def _new_token(text: str) -> str:
    """Pull the one-time token value out of the settings page."""
    return text.split('<code class="mt-2 block')[1].split(">", 1)[1].split("<", 1)[0].strip()


@pytest.fixture
async def env(tmp_path):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "a.toml").write_text(
        'key = "a"\nname = "Alpha"\ndescription = "first"\n\n'
        '[kinds.feature]\nlabel = "Feature"\nprefix = "FEAT"\n\n'
        '[statuses.proposed]\nlabel = "Proposed"\n',
        encoding="utf-8",
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    project = ProjectConfig(
        key="a",
        name="Alpha",
        description="first",
        kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
        statuses={"proposed": StatusConfig(label="Proposed")},
        branches=[BranchConfig(key="main", label="Main")],
        custom_fields={},
    )
    server_toml = tmp_path / "server.toml"
    server_toml.write_text(
        "# my server config\n"
        'api_token = "admin-secret"  # the admin token\n'
        f'projects_dir = "{projects_dir.as_posix()}"\n'
        f'data_dir = "{(tmp_path / "data").as_posix()}"\n'
        "\n"
        "# read-only token for the MCP client\n"
        "[[tokens]]\n"
        'name = "claude-read"\n'
        'token = "config-read-secret"\n'
        'scopes = ["read"]\n'
        "\n"
        "[[tokens]]\n"
        'name = "claude-agent"\n'
        'token = "config-agent-secret"\n'
        'scopes = ["agent"]\n'
        "\n"
        "[sqlite]\n"
        "wal_mode = true\n",
        encoding="utf-8",
    )
    server = load_server_config(server_toml)
    registry = ConfigRegistry(server=server, projects={"a": project})
    runtime = RuntimeSettings(tmp_path / "data")

    def auth_credentials():
        # Same shape as app.py: config tokens are read on every request.
        config = [
            BearerTokenCredential(
                name=t.name,
                token=t.token.get_secret_value(),
                scopes=frozenset(t.normalized_scopes()),
            )
            for t in server.auth_tokens()
        ]
        return [*config, *runtime.token_credentials()]

    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    app.state.runtime_settings = runtime
    app.state.server_toml = server_toml
    install_error_handlers(app)
    app.add_middleware(
        BearerTokenMiddleware,
        tokens=[],
        token_provider=auth_credentials,
        exempt_paths=("/dashboard/login", "/dashboard/language"),
        dashboard_paths=("/dashboard",),
    )
    app.include_router(projects_router)
    app.include_router(items_router)
    app.include_router(settings_router)  # before the dashboard router, as in app.py
    app.include_router(dashboard_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://t",
        headers={"Authorization": "Bearer admin-secret"},
    ) as client:
        yield {
            "client": client,
            "registry": registry,
            "runtime": runtime,
            "server": server,
            "server_toml": server_toml,
            "app": app,
        }
    await engine.dispose()


async def test_settings_page_requires_a_dashboard_session(env):
    anon = AsyncClient(transport=env["client"]._transport, base_url="http://t")

    r = await anon.get("/dashboard/settings", follow_redirects=False)

    assert r.status_code == 303
    assert "/dashboard/login" in r.headers["location"]


async def test_settings_page_renders_all_sections(env):
    page = await env["client"].get("/dashboard/settings")

    assert page.status_code == 200
    assert "Theme colours" in page.text
    assert 'name="light_primary"' in page.text
    assert "Tokens from server.toml" in page.text
    assert "claude-read" in page.text
    assert "config-read-secret" not in page.text  # config tokens are never shown


async def test_colour_form_saves_and_applies_to_pages(env):
    r = await env["client"].post("/dashboard/settings/appearance", data={
        "light_primary": "#123456", "light_accent": "#654321",
        "dark_primary": "#abcdef", "dark_accent": "#fedcba",
    }, follow_redirects=False)

    assert r.status_code == 303
    page = await env["client"].get("/dashboard/settings")
    assert "--dt-primary:#123456" in page.text
    assert "--dt-primary:#abcdef" in page.text


async def test_invalid_colour_is_refused_and_nothing_changes(env):
    before = env["runtime"].settings()["theme"]

    r = await env["client"].post("/dashboard/settings/appearance", data={
        "light_primary": "red", "light_accent": "#654321",
        "dark_primary": "#abcdef", "dark_accent": "#fedcba",
    })

    assert r.status_code == 422
    assert "must be a colour" in r.text
    assert env["runtime"].settings()["theme"] == before


async def test_reset_button_restores_default_colours(env):
    await env["client"].post("/dashboard/settings/appearance", data={
        "light_primary": "#111111", "light_accent": "#222222",
        "dark_primary": "#333333", "dark_accent": "#444444",
    })

    r = await env["client"].post("/dashboard/settings/appearance/reset", follow_redirects=False)

    assert r.status_code == 303
    assert "--dt-primary:#0f766e" in (await env["client"].get("/dashboard/settings")).text


async def test_display_form_changes_default_language_without_restart(env):
    await env["client"].post("/dashboard/settings/display", data={
        "default_language": "hu", "default_theme": "dark",
    })

    page = await env["client"].get("/dashboard/a")  # no language cookie yet

    assert '<html lang="hu"' in page.text
    assert "Áttekintés" in page.text


async def test_cookie_still_wins_over_the_default_language(env):
    await env["client"].post("/dashboard/settings/display", data={
        "default_language": "hu", "default_theme": "light",
    })
    env["client"].cookies.set(DASHBOARD_LANG_COOKIE, "en")

    page = await env["client"].get("/dashboard/a")

    assert '<html lang="en"' in page.text


async def test_default_theme_is_used_by_the_page(env):
    await env["client"].post("/dashboard/settings/display", data={
        "default_language": "en", "default_theme": "system",
    })

    page = await env["client"].get("/dashboard/a")

    assert "localStorage.getItem('theme') || 'system'" in page.text
    assert "matchMedia('(prefers-color-scheme: dark)')" in page.text


async def test_tracking_default_applies_to_new_items_at_once(env):
    await env["client"].post("/dashboard/settings/tracking", data={"default_estimated_time": "2"})

    r = await env["client"].post("/api/v1/projects/a/items", json={"kind": "feature", "title": "x"})

    assert r.json()["custom_fields"] == {"estimated_time": 2.0}


async def test_tracking_default_can_be_cleared(env):
    await env["client"].post("/dashboard/settings/tracking", data={"default_estimated_time": ""})

    r = await env["client"].post("/api/v1/projects/a/items", json={"kind": "feature", "title": "x"})

    assert r.json()["custom_fields"] == {}


async def test_tracking_default_rejects_bad_numbers(env):
    r = await env["client"].post(
        "/dashboard/settings/tracking", data={"default_estimated_time": "lots"},
    )

    assert r.status_code == 422


async def test_apply_tracking_defaults_sets_the_field_on_every_project(env):
    apply_tracking_defaults(env["registry"], 3.5)

    assert env["registry"].project("a").custom_fields["estimated_time"].default == 3.5


async def test_project_name_and_description_are_saved_to_the_file(env):
    r = await env["client"].post(
        "/dashboard/settings/projects/a",
        data={"name": "Renamed", "description": "new words"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    assert env["registry"].project("a").name == "Renamed"
    text = (env["server"].projects_dir / "a.toml").read_text(encoding="utf-8")
    assert 'name = "Renamed"' in text
    assert 'description = "new words"' in text
    assert "[kinds.feature]" in text
    audit = env["runtime"].audit_log()
    assert audit[0]["action"] == "project.updated"


async def test_project_form_refuses_an_empty_name(env):
    r = await env["client"].post(
        "/dashboard/settings/projects/a", data={"name": "  ", "description": ""},
    )

    assert r.status_code == 422
    assert env["registry"].project("a").name == "Alpha"


async def test_creating_a_token_shows_its_value_once(env):
    r = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "dashboard-agent", "scopes": ["agent"],
    })

    assert r.status_code == 200
    stored = json.dumps(env["runtime"].tokens())
    value = _new_token(r.text)
    assert value
    assert value not in stored
    again = await env["client"].get("/dashboard/settings")
    assert value not in again.text


async def test_new_runtime_token_authenticates_for_its_scope(env):
    r = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "agent-one", "scopes": ["agent"],
    })
    value = _new_token(r.text)
    bearer = {"Authorization": f"Bearer {value}"}

    read = await env["client"].get("/api/v1/projects", headers=bearer)
    write = await env["client"].post(
        "/api/v1/projects/a/items", json={"kind": "feature", "title": "by agent"}, headers=bearer,
    )

    assert read.status_code == 200
    assert write.status_code == 201


async def test_read_token_cannot_write(env):
    r = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "reader", "scopes": ["read"],
    })
    value = _new_token(r.text)

    r = await env["client"].post(
        "/api/v1/projects/a/items", json={"kind": "feature", "title": "no"},
        headers={"Authorization": f"Bearer {value}"},
    )

    assert r.status_code == 403


async def test_regenerated_token_stops_working_immediately(env):
    created = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "rotate", "scopes": ["read"],
    })
    old = _new_token(created.text)
    token_id = env["runtime"].tokens()[0]["id"]

    regen = await env["client"].post(f"/dashboard/settings/tokens/{token_id}/regenerate")
    new = _new_token(regen.text)

    assert new != old
    assert (await env["client"].get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {old}"},
    )).status_code == 401
    assert (await env["client"].get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {new}"},
    )).status_code == 200


async def test_deleted_token_is_refused(env):
    created = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "temp", "scopes": ["read"],
    })
    value = _new_token(created.text)
    token_id = env["runtime"].tokens()[0]["id"]

    await env["client"].post(f"/dashboard/settings/tokens/{token_id}/delete")

    r = await env["client"].get("/api/v1/projects", headers={"Authorization": f"Bearer {value}"})
    assert r.status_code == 401


async def test_token_rename_and_scope_change_apply_immediately(env):
    await env["client"].post("/dashboard/settings/tokens", data={
        "name": "before", "scopes": ["read"],
    })
    token_id = env["runtime"].tokens()[0]["id"]

    r = await env["client"].post(
        f"/dashboard/settings/tokens/{token_id}",
        data={"name": "after", "scopes": ["read", "agent"]},
        follow_redirects=False,
    )

    assert r.status_code == 303
    record = env["runtime"].tokens()[0]
    assert record["name"] == "after"
    assert record["scopes"] == ["agent", "read"]


async def test_config_token_name_cannot_be_reused(env):
    r = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "claude-read", "scopes": ["read"],
    })

    assert r.status_code == 422


async def test_dashboard_login_accepts_an_admin_runtime_token(env):
    created = await env["client"].post("/dashboard/settings/tokens", data={
        "name": "dash-admin", "scopes": ["admin"],
    })
    value = _new_token(created.text)

    login = await env["client"].post(
        "/dashboard/login", data={"token": value, "next": "/dashboard/settings"},
        follow_redirects=False,
    )

    assert login.status_code == 303
    assert DASHBOARD_SESSION_COOKIE in login.headers.get("set-cookie", "")


async def test_settings_page_lists_recent_changes(env):
    await env["client"].post("/dashboard/settings/display", data={
        "default_language": "en", "default_theme": "light",
    })

    page = await env["client"].get("/dashboard/settings")

    assert "settings.updated" in page.text


# --- IS-0003: tokens defined in server.toml ----------------------------------------


def _file(env) -> str:
    return env["server_toml"].read_text(encoding="utf-8")


async def test_config_tokens_are_listed_with_a_masked_preview(env):
    page = await env["client"].get("/dashboard/settings")

    assert "api_token" in page.text
    assert "claude-agent" in page.text
    assert "conf...cret" in page.text  # config-read-secret, masked
    assert "config-read-secret" not in page.text
    assert "admin-secret" not in page.text


async def test_reveal_shows_the_full_value_and_is_audited_without_it(env):
    r = await env["client"].post("/dashboard/settings/config-tokens/claude-read/reveal")

    assert r.status_code == 200
    assert _new_token(r.text) == "config-read-secret"
    assert "Token value" in r.text
    audit = json.dumps(env["runtime"].audit_log())
    assert "config_token.revealed" in audit
    assert "config-read-secret" not in audit


async def test_reveal_of_an_unknown_token_is_404(env):
    r = await env["client"].post("/dashboard/settings/config-tokens/nobody/reveal")

    assert r.status_code == 404


async def test_regenerating_a_config_token_rewrites_the_file_and_applies_at_once(env):
    r = await env["client"].post("/dashboard/settings/config-tokens/claude-read/regenerate")

    assert r.status_code == 200
    new = _new_token(r.text)
    assert new and new != "config-read-secret"
    text = _file(env)
    assert f'token = "{new}"' in text
    assert "config-read-secret" not in text
    # Everything else in the file is untouched.
    assert "# my server config" in text
    assert 'api_token = "admin-secret"  # the admin token' in text
    assert 'token = "config-agent-secret"' in text
    assert "wal_mode = true" in text
    # Live: the old value stops working, the new one works, without a restart.
    old_header = {"Authorization": "Bearer config-read-secret"}
    new_header = {"Authorization": f"Bearer {new}"}
    assert (await env["client"].get("/api/v1/projects", headers=old_header)).status_code == 401
    assert (await env["client"].get("/api/v1/projects", headers=new_header)).status_code == 200


async def test_regeneration_is_audited_without_values(env):
    r = await env["client"].post("/dashboard/settings/config-tokens/claude-agent/regenerate")
    new = _new_token(r.text)

    audit = json.dumps(env["runtime"].audit_log())

    assert "config_token.regenerated" in audit
    assert new not in audit
    assert "config-agent-secret" not in audit


async def test_regenerating_the_admin_token_keeps_the_user_signed_in(env):
    r = await env["client"].post("/dashboard/settings/config-tokens/api_token/regenerate")

    assert r.status_code == 200
    new = _new_token(r.text)
    assert f'api_token = "{new}"  # the admin token' in _file(env)
    cookie = re.search(rf"{DASHBOARD_SESSION_COOKIE}=([^;]+)", r.headers["set-cookie"])
    assert cookie, r.headers.get("set-cookie")
    assert is_valid_dashboard_session_cookie(cookie.group(1), new)
    # The old admin token no longer works, the new one does.
    stale = {"Authorization": "Bearer admin-secret"}
    fresh = {"Authorization": f"Bearer {new}"}
    assert (await env["client"].get("/api/v1/projects", headers=stale)).status_code == 401
    assert (await env["client"].get("/api/v1/projects", headers=fresh)).status_code == 200


async def test_admin_token_regeneration_is_refused_when_set_by_the_environment(env, monkeypatch):
    monkeypatch.setenv("ISSUEDECK_API_TOKEN", "from-env")
    before = _file(env)

    r = await env["client"].post("/dashboard/settings/config-tokens/api_token/regenerate")

    assert r.status_code == 422
    assert "ISSUEDECK_API_TOKEN" in r.text
    assert _file(env) == before


async def test_config_token_can_be_renamed_and_rescoped_live(env):
    r = await env["client"].post(
        "/dashboard/settings/config-tokens/claude-read",
        data={"name": "viewer", "scopes": ["read", "agent"]},
        follow_redirects=False,
    )

    assert r.status_code == 303
    text = _file(env)
    assert 'name = "viewer"' in text
    assert 'scopes = ["agent", "read"]' in text
    assert 'token = "config-read-secret"' in text  # the value is unchanged
    assert "# read-only token for the MCP client" in text
    write = await env["client"].post(
        "/api/v1/projects/a/items", json={"kind": "feature", "title": "by viewer"},
        headers={"Authorization": "Bearer config-read-secret"},
    )
    assert write.status_code == 201  # the agent scope applies without a restart
    assert "viewer" in json.dumps(env["runtime"].audit_log())


async def test_renaming_to_an_existing_name_is_refused_and_the_file_is_unchanged(env):
    before = _file(env)

    r = await env["client"].post(
        "/dashboard/settings/config-tokens/claude-read",
        data={"name": "claude-agent", "scopes": ["read"]},
    )

    assert r.status_code == 422
    assert _file(env) == before


async def test_admin_token_cannot_be_renamed(env):
    before = _file(env)

    r = await env["client"].post(
        "/dashboard/settings/config-tokens/api_token",
        data={"name": "boss", "scopes": ["admin"]},
    )

    assert r.status_code == 422
    assert _file(env) == before


async def test_config_tokens_are_read_only_when_the_file_location_is_unknown(env):
    del env["app"].state.server_toml

    page = await env["client"].get("/dashboard/settings")
    regenerate = await env["client"].post(
        "/dashboard/settings/config-tokens/claude-read/regenerate",
    )

    assert "cannot be changed here" in page.text
    assert "/config-tokens/claude-read/regenerate" not in page.text
    assert regenerate.status_code == 422
    assert "config-read-secret" in _file(env)


# --- IS-0003 Part 2: menu, presentation and in-place actions ---------------------

JSON = {"Accept": "application/json"}


async def test_settings_menu_item_follows_import_files_and_has_a_gear_icon(env):
    page = await env["client"].get("/dashboard/a")
    html = page.text

    files_link = html.index("/dashboard/a/imports/files")
    settings_link = html.index('<a href="/dashboard/settings"')
    create_button = html.index("/dashboard/a/items-new")
    assert files_link < settings_link < create_button
    block = html[settings_link:html.index("</a>", settings_link)]
    assert "<svg" in block  # gear icon
    assert "Settings" in block


async def test_settings_page_has_the_same_menu_as_the_main_pages(env):
    page = await env["client"].get("/dashboard/settings")
    html = page.text

    for path in ("/dashboard/a", "/dashboard/a/kanban", "/dashboard/a/list",
                 "/dashboard/a/imports/files", "/dashboard/a/items-new"):
        assert f'href="{path}"' in html, path
    # The Settings entry is highlighted as the current page.
    current = html.index('aria-current="page"')
    assert "/dashboard/settings" in html[max(0, current - 200):current + 50]


async def test_menu_selects_the_project_chosen_on_the_page(env):
    page = await env["client"].get("/dashboard/settings?project=a")

    assert 'href="/dashboard/a/kanban"' in page.text


async def test_tokens_are_separate_elements_not_one_run_together_line(env):
    page = await env["client"].get("/dashboard/settings")
    html = page.text

    assert html.count("data-token-card") >= 3  # api_token, claude-read, claude-agent
    assert "x-data='tokenCard(" in html
    # Name, scopes and the masked value are different elements.
    assert '<h4 class="min-w-0 break-all font-mono' in html
    assert 'x-text="masked">conf...cret</code>' in html
    assert "api_tokenadmin" not in html


async def test_token_actions_still_work_as_plain_forms_without_javascript(env):
    page = await env["client"].get("/dashboard/settings")
    html = page.text

    for action in (
        "/dashboard/settings/config-tokens/claude-read/reveal",
        "/dashboard/settings/config-tokens/claude-read/regenerate",
        "/dashboard/settings/config-tokens/claude-read",
    ):
        assert f'action="{action}"' in html, action
    assert 'method="post"' in html


async def test_reveal_returns_json_for_the_in_place_button(env):
    r = await env["client"].post(
        "/dashboard/settings/config-tokens/claude-read/reveal", headers=JSON,
    )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {
        "name": "claude-read", "scopes": ["read"],
        "masked": "conf...cret", "value": "config-read-secret",
    }


async def test_config_regenerate_returns_json_and_keeps_the_admin_signed_in(env):
    r = await env["client"].post(
        "/dashboard/settings/config-tokens/api_token/regenerate", headers=JSON,
    )

    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "api_token"
    assert data["value"] and data["masked"] == data["value"][:4] + "..." + data["value"][-4:]
    cookie = re.search(rf"{DASHBOARD_SESSION_COOKIE}=([^;]+)", r.headers["set-cookie"])
    assert is_valid_dashboard_session_cookie(cookie.group(1), data["value"])


async def test_regenerate_returns_json_for_a_dashboard_token(env):
    created = await env["client"].post(
        "/dashboard/settings/tokens", data={"name": "rot", "scopes": ["read"]}, headers=JSON,
    )
    token = created.json()

    r = await env["client"].post(
        f"/dashboard/settings/tokens/{token['id']}/regenerate", headers=JSON,
    )

    assert r.status_code == 200
    assert r.json()["value"] != token["value"]
    assert r.json()["id"] == token["id"]


async def test_create_update_delete_work_in_json_mode(env):
    created = await env["client"].post(
        "/dashboard/settings/tokens",
        data={"name": "live-one", "scopes": ["read"]}, headers=JSON,
    )
    assert created.status_code == 201
    token = created.json()
    assert token["value"] and token["scopes"] == ["read"]

    updated = await env["client"].post(
        f"/dashboard/settings/tokens/{token['id']}",
        data={"name": "live-two", "scopes": ["agent", "read"]}, headers=JSON,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "live-two"
    assert updated.json()["scopes"] == ["agent", "read"]

    deleted = await env["client"].post(
        f"/dashboard/settings/tokens/{token['id']}/delete", headers=JSON,
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": token["id"]}
    assert env["runtime"].tokens() == []


async def test_config_token_update_returns_json(env):
    r = await env["client"].post(
        "/dashboard/settings/config-tokens/claude-read",
        data={"name": "viewer", "scopes": ["read"]}, headers=JSON,
    )

    assert r.status_code == 200
    assert r.json()["name"] == "viewer"


async def test_errors_come_back_as_json_next_to_the_action(env):
    bad_name = await env["client"].post(
        "/dashboard/settings/tokens", data={"name": "1bad", "scopes": ["read"]}, headers=JSON,
    )
    unknown = await env["client"].post(
        "/dashboard/settings/config-tokens/nobody/reveal", headers=JSON,
    )
    clash = await env["client"].post(
        "/dashboard/settings/tokens", data={"name": "claude-read", "scopes": ["read"]},
        headers=JSON,
    )

    assert bad_name.status_code == 422 and "error" in bad_name.json()
    assert unknown.status_code == 404 and "error" in unknown.json()
    assert clash.status_code == 422 and "already exists" in clash.json()["error"]


async def test_card_fragment_is_served_for_a_new_token(env):
    created = await env["client"].post(
        "/dashboard/settings/tokens", data={"name": "frag", "scopes": ["agent"]}, headers=JSON,
    )
    token_id = created.json()["id"]

    r = await env["client"].get(f"/dashboard/settings/tokens/{token_id}/card")

    assert r.status_code == 200
    assert "data-token-card" in r.text
    assert "frag" in r.text
    assert "<html" not in r.text  # a fragment, not a page
    assert created.json()["value"] not in r.text


async def test_card_fragment_for_an_unknown_token_is_404(env):
    r = await env["client"].get("/dashboard/settings/tokens/doesnotexist/card", headers=JSON)

    assert r.status_code == 404


async def test_page_without_json_header_still_renders_the_one_time_box(env):
    r = await env["client"].post("/dashboard/settings/config-tokens/claude-read/reveal")

    assert r.status_code == 200
    assert "Token value" in r.text
    assert _new_token(r.text) == "config-read-secret"
