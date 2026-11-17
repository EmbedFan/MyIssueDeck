"""FEA-0008: the Settings section and the dashboard page for GitHub export and import."""

import re

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import ConfigRegistry, ServerConfig, load_project_config
from issuedeck.core.errors import install_error_handlers
from issuedeck.core.runtime_settings import DEFAULT_SETTINGS, RuntimeSettings
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

PROJECT_TOML = "\n".join([
    'key = "p"', 'name = "Project P"',
    "[kinds.feature]", 'label = "Feature"', 'prefix = "FEAT"',
    "[statuses.proposed]", 'label = "Proposed"',
    "[statuses.done]", 'label = "Done"', "terminal = true", "requires_ship = true",
    "[[branches]]", 'key = "main"', 'label = "Main"', "",
])


@pytest.fixture
async def env(tmp_path):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "p.toml").write_text(PROJECT_TOML, encoding="utf-8")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    registry = ConfigRegistry(
        server=ServerConfig(api_token="t", projects_dir=projects_dir, data_dir=tmp_path / "data"),
        projects={"p": load_project_config(projects_dir / "p.toml")},
    )
    async with Session() as session:
        service = ItemService(ItemRepo(session), registry, session)
        for title in ("First card", "Second card"):
            await service.create("p", CreateItemRequest(kind="feature", title=title, body=""))
    runtime = RuntimeSettings(tmp_path / "data")
    runtime.update_settings({"github": {"repository": "octo/exports"}})
    fake = FakeGitHub()

    app = FastAPI()
    app.state.registry = registry
    app.state.session_factory = Session
    app.state.runtime_settings = runtime
    app.state.github_transport = fake.transport
    app.state.github_environ = {"GITHUB_PAT": TOKEN}
    install_error_handlers(app)
    for router in (github_router, snapshot_router, settings_router, dashboard_router):
        app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        yield client, fake, runtime, registry, Session, app, tmp_path
    await engine.dispose()


def _form(**values):
    return {"repository": "octo/exports", "branch": "main", "folder": "",
            "token_env": "GITHUB_PAT", "author_name": "MyIssueDesk",
            "author_email": "issuedeck@users.noreply.github.com", **values}


async def _count(Session, key):
    async with Session() as session:
        return int((await session.execute(
            select(func.count(Item.pk)).where(Item.project_key == key)
        )).scalar())


# ---------------------------------------------------------------------------
# settings section
# ---------------------------------------------------------------------------

async def test_the_settings_page_has_the_github_section(env):
    client, *_ = env
    page = await client.get("/dashboard/settings")
    assert page.status_code == 200
    assert "GitHub exports" in page.text
    for field in ("repository", "branch", "folder", "token_env", "allow_public",
                  "author_name", "author_email"):
        assert f'name="{field}"' in page.text
    assert "the variable is set on this server" in page.text
    assert TOKEN not in page.text


async def test_github_settings_are_saved_audited_and_reset(env):
    client, _, runtime, *_ = env
    saved = await client.post("/dashboard/settings/github", data=_form(
        branch="exports", folder="/team/a/", token_env="MY_TOKEN", allow_public="1",
    ), follow_redirects=False)
    assert saved.status_code == 303
    group = runtime.settings()["github"]
    assert (group["branch"], group["folder"], group["token_env"], group["allow_public"]) == (
        "exports", "team/a", "MY_TOKEN", True)
    assert runtime.audit_log()[0]["action"] == "settings.updated"

    reset = await client.post("/dashboard/settings/github/reset", follow_redirects=False)
    assert reset.status_code == 303
    assert runtime.settings()["github"] == DEFAULT_SETTINGS["github"]
    assert runtime.audit_log()[0]["action"] == "github.reset"


@pytest.mark.parametrize("field, value", [
    ("repository", "not a repository"),
    ("branch", "bad..branch"),
    ("folder", "../up"),
    ("token_env", "1BAD"),
    ("author_email", "nobody"),
])
async def test_invalid_github_settings_are_refused(env, field, value):
    client, _, runtime, *_ = env
    before = runtime.settings()["github"]
    response = await client.post("/dashboard/settings/github", data=_form(**{field: value}))
    assert response.status_code == 422
    assert runtime.settings()["github"] == before


async def test_test_connection_shows_every_check_and_writes_nothing(env):
    client, fake, *_ = env
    page = await client.post("/dashboard/settings/github/test")
    assert page.status_code == 200 and "data-github-check" in page.text
    for name in ("token", "repository", "write access", "privacy", "branch"):
        assert f">{name}</span>" in page.text
    assert fake.calls("POST") == [] and fake.calls("PATCH") == []
    assert TOKEN not in page.text


async def test_test_connection_names_a_missing_token(env):
    client, _, _, _, _, app, _ = env
    app.state.github_environ = {}
    page = await client.post("/dashboard/settings/github/test")
    assert "is not set; it must hold a GitHub token" in page.text
    assert "the variable is not set on this server" in page.text


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

async def test_the_overview_links_to_the_github_page(env):
    client, *_ = env
    page = await client.get("/dashboard/p")
    assert "/dashboard/github?project=p" in page.text


async def test_the_github_page_shows_the_settings_but_never_the_token(env):
    client, *_ = env
    page = await client.get("/dashboard/github?project=p")
    assert page.status_code == 200 and "octo/exports" in page.text
    assert re.search(r'<option value="p" selected>', page.text)
    assert TOKEN not in page.text and "ghp_" not in page.text


async def test_export_is_checked_first_then_made_and_audited(env):
    client, fake, runtime, *_ = env

    checked = await client.post("/dashboard/github/export",
                                data={"project": "p", "action": "preview"})
    assert checked.status_code == 200 and "nothing was written" in checked.text
    assert "<code>items.json</code>" in checked.text
    assert len(fake.history()) == 1

    done = await client.post("/dashboard/github/export",
                             data={"project": "p", "action": "export"})
    assert "p: exported (2 items)." in done.text and len(fake.history()) == 2
    assert "p/items.json" in fake.files()

    again = await client.post("/dashboard/github/export",
                              data={"project": "p", "action": "export"})
    assert "the repository is up to date" in again.text and len(fake.history()) == 2

    audit = [e for e in runtime.audit_log() if e["action"] == "github.export"]
    assert len(audit) == 1 and audit[0]["actor"] == "dashboard"
    assert TOKEN not in str(audit) and TOKEN not in done.text


async def test_export_problems_are_explained(env):
    client, fake, _, _, _, app, _ = env
    unknown = await client.post("/dashboard/github/export",
                                data={"project": "nope", "action": "export"})
    assert unknown.status_code == 422 and "options are not valid" in unknown.text

    app.state.github_environ = {}
    no_token = await client.post("/dashboard/github/export",
                                 data={"project": "p", "action": "export"})
    assert no_token.status_code == 422 and "GITHUB_PAT is not set" in no_token.text

    app.state.github_environ = {"GITHUB_PAT": TOKEN}
    fake.private = False
    public = await client.post("/dashboard/github/export",
                               data={"project": "p", "action": "export"})
    assert public.status_code == 422 and "public repository" in public.text
    assert len(fake.history()) == 1


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

async def _exported(env):
    client, *_ = env
    await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})


async def test_the_repository_projects_are_listed(env):
    await _exported(env)
    client, *_ = env
    page = await client.get("/dashboard/github?load=1")
    assert "data-github-import-form" in page.text
    assert "p —" in page.text and "2 items" in page.text


async def test_an_empty_repository_says_so(env):
    client, *_ = env
    page = await client.get("/dashboard/github?load=1")
    assert "data-github-empty" in page.text


async def test_listing_problems_are_shown(env):
    client, _, _, _, _, app, _ = env
    app.state.github_environ = {"GITHUB_PAT": "ghp_wrong"}
    page = await client.get("/dashboard/github?load=1")
    assert page.status_code == 502 and "did not accept the token" in page.text
    assert "ghp_wrong" not in page.text


async def test_import_is_previewed_then_applied_and_audited(env):
    await _exported(env)
    client, _, runtime, registry, Session, _, tmp_path = env
    data = {"source": "p", "revision": "", "mode": "create", "new_key": "restored",
            "target": "", "conflict": "keep"}

    preview = await client.post("/dashboard/github/import/preview", data=data)
    assert preview.status_code == 200 and "nothing has been written yet" in preview.text
    assert 'action="/dashboard/github/import/apply"' in preview.text
    assert 'href="/dashboard/github"' in preview.text
    token = re.search(r'name="token" value="([0-9a-f]{32})"', preview.text).group(1)
    commit = re.search(r'name="commit" value="([0-9a-f]+)"', preview.text).group(1)
    assert await _count(Session, "restored") == 0
    assert not (registry.server.projects_dir / "restored.toml").exists()

    applied = await client.post("/dashboard/github/import/apply", data={
        **data, "token": token, "commit": commit})
    assert applied.status_code == 200 and "Snapshot imported" in applied.text
    assert await _count(Session, "restored") == 2
    assert registry.project("restored").name == "Project P"
    assert not (tmp_path / "data" / "snapshot-uploads" / f"{token}.zip").exists()

    entry = [e for e in runtime.audit_log() if e["action"] == "github.import"][0]
    assert entry["details"]["source_project"] == "p" and entry["details"]["commit"] == commit
    assert TOKEN not in str(entry)

    replay = await client.post("/dashboard/github/import/apply", data={
        **data, "token": token, "commit": commit})
    assert replay.status_code == 422 and "no longer available" in replay.text


async def test_import_problems_are_explained(env):
    client, fake, *_ = env
    nothing = await client.post("/dashboard/github/import/preview",
                                data={"source": "", "mode": "create", "conflict": "keep"})
    assert nothing.status_code == 422 and "options are not valid" in nothing.text

    fake.commit_files({"junk/items.json": b"[]"})
    junk = await client.post("/dashboard/github/import/preview",
                             data={"source": "junk", "mode": "create", "conflict": "keep"})
    assert junk.status_code == 422 and "is not a project export" in junk.text

    bad_token = await client.post("/dashboard/github/import/apply", data={
        "token": "../../x", "mode": "create", "conflict": "keep"})
    assert bad_token.status_code == 422 and "no longer available" in bad_token.text


async def test_the_page_follows_the_language(env):
    client, *_ = env
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")
    page = await client.get("/dashboard/github")
    assert "GitHub: projektek exportálása és importálása" in page.text
    settings = await client.get("/dashboard/settings")
    assert "GitHub-exportok" in settings.text
