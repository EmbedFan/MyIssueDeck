"""IS-0008: a first start with no project offers the GitHub import and says what it needs."""

import re
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import ConfigRegistry, ServerConfig, load_project_config
from issuedeck.core.errors import install_error_handlers
from issuedeck.core.runtime_settings import RuntimeSettings
from issuedeck.features.dashboard.github_routes import router as github_router
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE
from issuedeck.features.dashboard.routes import router as dashboard_router
from issuedeck.features.dashboard.settings_routes import router as settings_router
from issuedeck.features.dashboard.snapshot_routes import router as snapshot_router
from issuedeck.features.items.models import Base, Item
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.items.schemas import CreateItemRequest
from issuedeck.features.items.service import ItemService

from .fake_github import TOKEN, FakeGitHub
from .test_dashboard import PROJECT_TOML


@asynccontextmanager
async def make_app(tmp_path, fake, *, project, token=True, nav=None):
    """A dashboard app; ``project`` False is the state right after a first installation."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True)
    projects = {}
    if project:
        (projects_dir / "p.toml").write_text(PROJECT_TOML, encoding="utf-8")
        projects["p"] = load_project_config(projects_dir / "p.toml")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    registry = ConfigRegistry(
        server=ServerConfig(api_token="t", projects_dir=projects_dir, data_dir=tmp_path / "data"),
        projects=projects,
    )
    if project:
        async with Session() as session:
            service = ItemService(ItemRepo(session), registry, session)
            for title in ("First card", "Second card"):
                await service.create("p", CreateItemRequest(kind="feature", title=title, body=""))
    runtime = RuntimeSettings(tmp_path / "data")
    runtime.update_settings({"github": {"repository": "octo/exports"}})
    if nav is not None:
        runtime.update_settings({"navigation": {"import_github": nav}})

    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    app.state.runtime_settings = runtime
    app.state.github_transport = fake.transport
    app.state.github_environ = {"GITHUB_PAT": TOKEN} if token else {}
    install_error_handlers(app)
    for router in (github_router, snapshot_router, settings_router, dashboard_router):
        app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, app, registry, Session
    await engine.dispose()


async def _count(Session, key):
    async with Session() as session:
        return int((await session.execute(
            select(func.count(Item.pk)).where(Item.project_key == key)
        )).scalar())


# ---------------------------------------------------------------------------
# the empty start
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nav", [False, True])
async def test_the_empty_start_offers_both_ways_whatever_the_menu_setting_is(tmp_path, nav):
    async with make_app(tmp_path, FakeGitHub(), project=False, nav=nav) as (client, *_):
        page = await client.get("/dashboard/")

    assert page.status_code == 200 and "No projects yet" in page.text
    assert re.search(r'href="/dashboard/projects-new"[^>]*data-onboarding-new-project', page.text)
    assert re.search(r'href="/dashboard/github"[^>]*data-onboarding-github', page.text)
    assert "Import from GitHub" in page.text


async def test_the_empty_start_names_both_ways_and_the_source_repository(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False) as (client, *_):
        page = await client.get("/dashboard/")

    assert "import projects that were exported earlier" in page.text
    assert re.search(
        r"data-onboarding-source[^>]*>The import reads from octo/exports\.<", page.text)
    assert "Create a project config" not in page.text  # the old, technical wording


@pytest.mark.parametrize(("language", "button", "source"), [
    ("hu", "Importálás GitHubról", "Az import innen olvas: octo/exports."),
    ("zh-CN", "从 GitHub 导入", "导入来源：octo/exports。"),
])
async def test_the_empty_start_is_translated(tmp_path, language, button, source):
    async with make_app(tmp_path, FakeGitHub(), project=False) as (client, *_):
        client.cookies.set(DASHBOARD_LANG_COOKIE, language)
        page = await client.get("/dashboard/")

    assert button in page.text and source in page.text
    assert "Import from GitHub" not in page.text


async def test_the_empty_start_renders_even_if_the_settings_cannot_be_read(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False) as (client, app, *_):
        runtime = app.state.runtime_settings
        original = runtime.settings
        runtime.settings = lambda: {**original(), "github": {}}  # the group is unusable
        page = await client.get("/dashboard/")

    assert page.status_code == 200 and "data-onboarding-github" in page.text
    assert "data-onboarding-source" not in page.text


async def test_with_a_project_the_start_is_unchanged(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=True) as (client, *_):
        start = await client.get("/dashboard/", follow_redirects=False)
        overview = await client.get("/dashboard/p")

    assert start.status_code == 302 and start.headers["location"] == "/dashboard/p"
    assert "data-onboarding-github" not in overview.text


# ---------------------------------------------------------------------------
# the GitHub page with no project
# ---------------------------------------------------------------------------

async def test_the_github_page_works_with_no_project_and_has_no_dead_export_form(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False) as (client, *_):
        page = await client.get("/dashboard/github")

    assert page.status_code == 200
    assert "data-github-no-project" in page.text
    assert "An export needs a project" in page.text
    assert 'id="github-project"' not in page.text           # no empty required select
    assert 'action="/dashboard/github/export"' not in page.text
    assert "data-github-hint" not in page.text               # the token is there


async def test_the_import_form_has_only_create_when_there_is_no_project(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path / "a", fake, project=True) as (client, *_):
        await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})
    async with make_app(tmp_path / "b", fake, project=False) as (client, *_):
        page = await client.get("/dashboard/github?load=1")

    assert "data-github-import-form" in page.text
    assert re.search(r'name="mode" value="update"\s+disabled', page.text)
    assert re.search(r'<select id="github-target"[^>]*disabled', page.text)
    assert "so the import creates a new one" in page.text
    assert re.search(r'name="mode" value="create" checked', page.text)


async def test_with_a_project_the_import_form_keeps_update_and_the_target(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path, fake, project=True) as (client, *_):
        await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})
        page = await client.get("/dashboard/github?load=1")

    assert not re.search(r'name="mode" value="update"\s+disabled', page.text)
    assert not re.search(r'<select id="github-target"[^>]*disabled', page.text)
    assert "so the import creates a new one" not in page.text
    assert 'id="github-project"' in page.text


async def test_the_first_project_is_imported_and_served_at_once_without_a_restart(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path / "a", fake, project=True) as (client, *_):
        await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})

    async with make_app(tmp_path / "b", fake, project=False) as (client, app, registry, Session):
        assert (await client.get("/dashboard/", follow_redirects=False)).status_code == 200
        data = {"source": "p", "revision": "", "mode": "create", "new_key": "restored",
                "target": "", "conflict": "keep"}
        preview = await client.post("/dashboard/github/import/preview", data=data)
        assert preview.status_code == 200 and "nothing has been written yet" in preview.text
        token = re.search(r'name="token" value="([0-9a-f]{32})"', preview.text).group(1)
        commit = re.search(r'name="commit" value="([0-9a-f]+)"', preview.text).group(1)
        assert await _count(Session, "restored") == 0

        applied = await client.post("/dashboard/github/import/apply", data={
            **data, "token": token, "commit": commit})

        assert applied.status_code == 200 and "Snapshot imported" in applied.text
        assert 'href="/dashboard/restored"' in applied.text       # the Open project button
        assert await _count(Session, "restored") == 2
        # no restart: the project is known, the start page now leads to it, and it is served
        assert registry.project("restored").name == "Project P"
        start = await client.get("/dashboard/", follow_redirects=False)
        assert start.status_code == 302 and start.headers["location"] == "/dashboard/restored"
        overview = await client.get("/dashboard/restored")
        assert overview.status_code == 200 and "Project P" in overview.text
        assert "data-onboarding-github" not in overview.text


# ---------------------------------------------------------------------------
# guidance when the import cannot work yet
# ---------------------------------------------------------------------------

async def test_a_missing_token_is_explained_before_anything_is_pressed(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path, fake, project=False, token=False) as (client, *_):
        page = await client.get("/dashboard/github")

    assert page.status_code == 200
    hint = re.search(r'data-github-hint="token".*?</div>', page.text, re.S).group(0)
    assert "The GitHub token is missing" in hint
    assert "GITHUB_PAT" in hint                              # the variable is named
    assert "stop and start the server" in hint               # the restart
    assert "reads its environment only when it starts" in hint
    assert 'href="/dashboard/settings#settings-github"' in hint
    assert fake.requests == []                               # no network call on page load


async def test_the_hint_follows_the_chosen_variable_name(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False, token=False) as (client, app, *_):
        app.state.runtime_settings.update_settings({"github": {"token_env": "MY_GH_TOKEN"}})
        page = await client.get("/dashboard/github")

    assert re.search(r'data-github-hint="token".*?MY_GH_TOKEN', page.text, re.S)


async def test_the_hint_is_in_hungarian_too(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False, token=False) as (client, *_):
        client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")
        page = await client.get("/dashboard/github")

    hint = re.search(r'data-github-hint="token".*?</div>', page.text, re.S).group(0)
    assert "Hiányzik a GitHub-token" in hint and "GITHUB_PAT" in hint
    assert "indítsa újra a kiszolgálót" in hint


async def test_a_present_token_gives_no_hint_and_is_never_shown(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False, token=True) as (client, *_):
        page = await client.get("/dashboard/github")
        listing = await client.get("/dashboard/github?load=1")

    for response in (page, listing):
        assert "data-github-hint" not in response.text
        assert TOKEN not in response.text


async def test_trying_to_list_without_a_token_says_to_restart_the_server(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False, token=False) as (client, *_):
        page = await client.get("/dashboard/github?load=1")

    assert page.status_code == 422
    # the error itself (not only the hint panel of the same page) says what to do
    alert = re.search(r'<div role="alert".*?</div>', page.text, re.S).group(0)
    assert "GITHUB_PAT is not set" in alert
    assert "stop and start the server again" in alert


async def test_the_other_problems_keep_their_own_messages(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path, fake, project=False) as (client, app, *_):
        app.state.github_environ = {"GITHUB_PAT": "ghp_wrong"}
        wrong = await client.get("/dashboard/github?load=1")
        app.state.github_environ = {"GITHUB_PAT": TOKEN}
        app.state.runtime_settings.update_settings({"github": {"repository": "octo/missing"}})
        missing = await client.get("/dashboard/github?load=1")

    assert "did not accept the token" in wrong.text and "ghp_wrong" not in wrong.text
    assert missing.status_code == 502 and "octo/missing" in missing.text  # as for any GitHub error
    assert "stop and start the server" not in wrong.text + missing.text


async def test_the_page_offers_the_connection_test_of_the_settings(tmp_path):
    async with make_app(tmp_path, FakeGitHub(), project=False) as (client, *_):
        page = await client.get("/dashboard/github")
        tested = await client.post("/dashboard/settings/github/test")

    assert re.search(r'<form method="post" action="/dashboard/settings/github/test"', page.text)
    assert "Test connection" in page.text
    assert tested.status_code == 200 and "octo/exports" in tested.text
