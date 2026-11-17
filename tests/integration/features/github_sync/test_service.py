"""FEA-0008: exporting a project to GitHub and importing it back (local test double)."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issuedeck.core.config import ConfigRegistry, ServerConfig
from issuedeck.core.errors import (
    GitHubConfigError,
    GitHubError,
    ProjectNotFound,
    SnapshotInvalid,
)
from issuedeck.core.runtime_settings import DEFAULT_SETTINGS, RuntimeSettings
from issuedeck.features.github_sync.service import (
    GitHubSettings,
    check_connection,
    export_project,
    import_project,
    list_projects,
)
from issuedeck.features.items.models import Base, Item

from ..export.test_audit_bundle import session_and_registry  # noqa: F401
from .fake_github import TOKEN, FakeGitHub

ENV = {"GITHUB_PAT": TOKEN}
FULL_TOML = "\n".join([
    'key = "p"', 'name = "P"',
    "[kinds.feature]", 'label = "Feature"', 'prefix = "FEAT"',
    "[statuses.proposed]", 'label = "P"',
    "[statuses.done]", 'label = "D"', "terminal = true", "requires_ship = true",
    "[[branches]]", 'key = "main"', 'label = "Main"',
    "[custom_fields.priority]", 'label = "Priority"', 'type = "select"',
    'options = ["low", "high"]', "",
])


def _settings(fake, **over):
    group = {**DEFAULT_SETTINGS["github"], "repository": f"{fake.owner}/{fake.repo}", **over}
    return GitHubSettings.from_group(group)


@pytest.fixture
async def source(session_and_registry):  # noqa: F811
    session, registry = session_and_registry
    (registry.server.projects_dir / "p.toml").write_text(FULL_TOML, encoding="utf-8")
    return session, registry


async def _export(source, fake, **kw):
    session, registry = source
    settings = kw.pop("settings", None) or _settings(fake)
    return await export_project(
        session=session, registry=registry, project_key="p", settings=settings,
        environ=kw.pop("environ", ENV), transport=fake.transport, **kw,
    )


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

async def test_first_export_is_one_commit_with_the_snapshot_files(source):
    fake = FakeGitHub()
    report = await _export(source, fake)

    assert report.up_to_date is False and report.items == 2
    assert report.commit_sha == fake.refs["main"] and len(fake.history()) == 2
    files = fake.files()
    assert {name.split("/", 1)[1] for name in files if name.startswith("p/")} == {
        "manifest.json", "project.json", "project.toml", "items.json",
        "relationships.json", "work_sessions.json", "import_batches.json",
    }
    assert files["README.md"] == b"exports\n"
    commit = fake.commits[report.commit_sha]
    assert "Export p: 2 items" in commit["message"]
    assert commit["author"]["name"] == "MyIssueDesk"
    assert json.loads(files["p/items.json"])[0]["local_id"] == "FEAT-0001"


async def test_a_second_export_without_changes_makes_no_commit(source):
    fake = FakeGitHub()
    await _export(source, fake)
    head, manifest = fake.refs["main"], fake.files()["p/manifest.json"]
    fake.requests.clear()

    report = await _export(source, fake)

    assert report.up_to_date is True and report.commit_sha is None
    assert fake.refs["main"] == head and fake.files()["p/manifest.json"] == manifest
    assert fake.calls("POST") == [] and fake.calls("PATCH") == []


async def test_a_dry_run_writes_nothing_and_lists_the_files(source):
    fake = FakeGitHub()
    report = await _export(source, fake, dry_run=True)

    assert report.dry_run is True and len(report.files_changed) == 7
    assert len(fake.history()) == 1
    assert fake.calls("POST") == [] and fake.calls("PATCH") == []


async def test_a_change_commits_only_the_changed_files(source):
    fake = FakeGitHub()
    await _export(source, fake)
    before = fake.files()
    session, _ = source
    item = (await session.execute(select(Item).where(Item.local_id == "FEAT-0001"))).scalar_one()
    item.title = "First, renamed"
    item.updated_at = "2030-01-01T00:00:00+00:00"
    await session.commit()

    report = await _export(source, fake)

    assert report.up_to_date is False and len(fake.history()) == 3
    assert "items.json" in report.files_changed and "project.toml" not in report.files_changed
    after = fake.files()
    assert after["p/project.toml"] == before["p/project.toml"]
    assert b"First, renamed" in after["p/items.json"]
    assert after["README.md"] == before["README.md"]


async def test_other_projects_and_files_in_the_repository_are_never_touched(source):
    fake = FakeGitHub()
    fake.commit_files({"other/items.json": b"[]", "notes/todo.txt": b"keep me"})
    await _export(source, fake)
    files = fake.files()
    assert files["other/items.json"] == b"[]" and files["notes/todo.txt"] == b"keep me"


async def test_the_folder_setting_places_the_project_inside_the_repository(source):
    fake = FakeGitHub()
    await _export(source, fake, settings=_settings(fake, folder="exports/issuedeck"))
    assert "exports/issuedeck/p/items.json" in fake.files()
    assert "p/items.json" not in fake.files()


async def test_a_public_repository_is_refused_unless_allowed(source):
    fake = FakeGitHub(private=False)
    with pytest.raises(GitHubConfigError, match="public repository"):
        await _export(source, fake)
    assert fake.calls("POST") == [] and len(fake.history()) == 1

    report = await _export(source, fake, settings=_settings(fake, allow_public=True))
    assert report.commit_sha is not None


async def test_a_token_that_cannot_write_is_reported_before_anything_is_written(source):
    fake = FakeGitHub(can_push=False)
    with pytest.raises(GitHubError) as caught:
        await _export(source, fake)
    assert caught.value.kind == "permission" and fake.calls("POST") == []


async def test_a_branch_that_moves_during_the_export_publishes_nothing(source):
    fake = FakeGitHub()
    fake.before_ref_update = lambda: fake.commit_files({"x.txt": b"x"}, "pushed meanwhile")
    with pytest.raises(GitHubError) as caught:
        await _export(source, fake)
    assert caught.value.kind == "conflict"
    assert "p/items.json" not in fake.files()


async def test_a_missing_token_variable_is_explained_and_nothing_is_requested(source):
    fake = FakeGitHub()
    with pytest.raises(GitHubConfigError, match="GITHUB_PAT is not set"):
        await _export(source, fake, environ={})
    assert fake.requests == []

    custom = _settings(fake, token_env="MY_EXPORT_TOKEN")
    report = await _export(source, fake, settings=custom, environ={"MY_EXPORT_TOKEN": TOKEN})
    assert report.commit_sha is not None


async def test_an_unknown_project_fails_before_any_request(source):
    fake = FakeGitHub()
    session, registry = source
    with pytest.raises(ProjectNotFound):
        await export_project(
            session=session, registry=registry, project_key="nope",
            settings=_settings(fake), environ=ENV, transport=fake.transport,
        )
    assert fake.requests == []


async def test_exports_are_audited_without_the_token(source, tmp_path):
    fake = FakeGitHub()
    runtime = RuntimeSettings(tmp_path / "data")
    report = await _export(source, fake, runtime=runtime, actor="cli")

    entries = runtime.audit_log()
    assert entries[0]["action"] == "github.export" and entries[0]["actor"] == "cli"
    assert entries[0]["details"]["commit"] == report.commit_sha
    assert entries[0]["details"]["repository"] == "octo/exports"
    assert TOKEN not in json.dumps(entries) and TOKEN not in json.dumps(report.as_dict())

    await _export(source, fake, runtime=runtime)  # nothing changed: not audited again
    assert len(runtime.audit_log()) == 1


# ---------------------------------------------------------------------------
# list and import
# ---------------------------------------------------------------------------

async def _new_target(tmp_path, name="target"):
    projects = tmp_path / name
    projects.mkdir()
    registry = ConfigRegistry(
        server=ServerConfig(api_token="t", projects_dir=projects), projects={},
    )
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False), registry


async def test_the_projects_in_the_repository_are_listed(source):
    fake = FakeGitHub()
    await _export(source, fake)
    fake.commit_files({"q/manifest.json": b"{ not json", "q/items.json": b"[]"})
    fake.commit_files({"notes/readme.md": b"no manifest here"})

    found = {p.key: p for p in await list_projects(
        _settings(fake), environ=ENV, transport=fake.transport)}

    assert set(found) == {"p", "q"}
    assert found["p"].items == 2 and found["p"].generated_at
    assert found["q"].problem == "manifest.json is not valid"


async def test_a_project_travels_through_the_repository_and_back(source, tmp_path):
    fake = FakeGitHub()
    await _export(source, fake)
    engine, Session, registry = await _new_target(tmp_path)
    async with Session() as session:
        report, commit = await import_project(
            session=session, registry=registry, project_key="p", settings=_settings(fake),
            mode="create", apply=True, environ=ENV, transport=fake.transport,
        )
        assert report.applied and (report.items_created, report.relationships_added) == (2, 2)
        assert commit == fake.refs["main"]
        titles = {i.local_id: i.title for i in (await session.execute(select(Item))).scalars()}
        assert titles == {"FEAT-0001": "First", "FEAT-0002": "Second"}
        assert registry.project("p").name == "P"
    await engine.dispose()


async def test_import_can_use_an_older_revision_and_another_key(source, tmp_path):
    fake = FakeGitHub()
    await _export(source, fake)
    first_commit = fake.refs["main"]
    session, _ = source
    item = (await session.execute(select(Item).where(Item.local_id == "FEAT-0001"))).scalar_one()
    item.title = "Changed later"
    item.updated_at = "2030-01-01T00:00:00+00:00"
    await session.commit()
    await _export(source, fake)

    engine, Session, registry = await _new_target(tmp_path)
    async with Session() as target:
        report, _ = await import_project(
            session=target, registry=registry, project_key="p", settings=_settings(fake),
            mode="create", target_key="old", revision=first_commit, apply=True,
            environ=ENV, transport=fake.transport,
        )
        assert report.project_key == "old"
        titles = {i.title for i in (await target.execute(select(Item))).scalars()}
        assert "First" in titles and "Changed later" not in titles
    await engine.dispose()


async def test_import_previews_without_writing(source, tmp_path):
    fake = FakeGitHub()
    await _export(source, fake)
    engine, Session, registry = await _new_target(tmp_path)
    async with Session() as session:
        report, _ = await import_project(
            session=session, registry=registry, project_key="p", settings=_settings(fake),
            mode="create", apply=False, environ=ENV, transport=fake.transport,
        )
        assert report.applied is False and report.items_created == 2
        assert (await session.execute(select(Item))).first() is None
        assert registry.all_projects() == []
    await engine.dispose()


async def test_a_folder_that_is_not_a_project_export_is_rejected(source, tmp_path):
    fake = FakeGitHub()
    fake.commit_files({"junk/items.json": b"[]"})
    engine, Session, registry = await _new_target(tmp_path)
    async with Session() as session:
        with pytest.raises(SnapshotInvalid, match="lacks: manifest.json"):
            await import_project(
                session=session, registry=registry, project_key="junk",
                settings=_settings(fake), mode="create", environ=ENV, transport=fake.transport,
            )
    await engine.dispose()


async def test_revisions_are_checked(source, tmp_path):
    fake = FakeGitHub()
    engine, Session, registry = await _new_target(tmp_path)
    async with Session() as session:
        with pytest.raises(GitHubConfigError, match="branch, a tag or a commit"):
            await import_project(
                session=session, registry=registry, project_key="p", settings=_settings(fake),
                mode="create", revision="../etc", environ=ENV, transport=fake.transport,
            )
        with pytest.raises(GitHubError) as caught:
            await import_project(
                session=session, registry=registry, project_key="p", settings=_settings(fake),
                mode="create", revision="no-such-tag", environ=ENV, transport=fake.transport,
            )
        assert caught.value.kind == "not_found"
    await engine.dispose()


async def test_imports_are_audited_without_the_token(source, tmp_path):
    fake = FakeGitHub()
    await _export(source, fake)
    engine, Session, registry = await _new_target(tmp_path)
    runtime = RuntimeSettings(tmp_path / "data")
    async with Session() as session:
        await import_project(
            session=session, registry=registry, project_key="p", settings=_settings(fake),
            mode="create", apply=True, environ=ENV, transport=fake.transport,
            runtime=runtime, actor="dashboard",
        )
    entry = runtime.audit_log()[0]
    assert entry["action"] == "github.import" and entry["details"]["items_created"] == 2
    assert TOKEN not in json.dumps(runtime.audit_log())
    await engine.dispose()


# ---------------------------------------------------------------------------
# test connection
# ---------------------------------------------------------------------------

async def test_connection_check_passes_for_a_good_setup():
    fake = FakeGitHub()
    result = await check_connection(_settings(fake), environ=ENV, transport=fake.transport)
    assert result.ok and result.private is True
    # what the check can know: the account's right, and that the token needs a permission
    write = next(detail for name, _, detail in result.checks if name == "write access")
    assert "Contents: Read and write" in write
    assert [name for name, *_ in result.checks] == [
        "token", "repository", "write access", "privacy", "branch",
    ]
    assert fake.calls("POST") == [] and fake.calls("PATCH") == []


async def test_connection_check_names_every_problem():
    fake = FakeGitHub(private=False, can_push=False)
    result = await check_connection(
        _settings(fake, branch="nope"), environ=ENV, transport=fake.transport,
    )
    failed = {name for name, ok, _ in result.checks if not ok}
    assert not result.ok and failed == {"write access", "privacy", "branch"}

    no_token = await check_connection(_settings(fake), environ={}, transport=fake.transport)
    assert [(n, ok) for n, ok, _ in no_token.checks] == [("token", False)]

    wrong = await check_connection(
        _settings(fake), environ={"GITHUB_PAT": "ghp_wrong"}, transport=fake.transport,
    )
    assert any(n == "repository" and not ok and "ghp_wrong" not in d
               for n, ok, d in wrong.checks)
