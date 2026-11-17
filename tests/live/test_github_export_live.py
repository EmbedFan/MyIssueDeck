"""Live check of the GitHub export (FEA-0008) against the real repository. Opt-in.

This test really publishes: it exports one project of THIS installation (default
``my-commander``) to the GitHub repository configured on the Settings page, using the token in
the environment variable named there (default ``GITHUB_PAT``). Because of that it is skipped
unless you ask for it, so the normal test run never writes to GitHub.

Run it from the folder that holds ``server.toml``:

    PowerShell:  $env:ISSUEDECK_LIVE_GITHUB = "1"
                 .venv\\Scripts\\python.exe -m pytest tests/live -s -p no:cacheprovider

Optional: ``ISSUEDECK_CONFIG`` (path of server.toml, default ``server.toml``) and
``ISSUEDECK_LIVE_PROJECT`` (project key, default ``my-commander``).

The database is only read. Exports are recorded in the settings audit log like any other
export. The token is never printed or written anywhere.
"""

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from issuedeck.cli import _build_registry
from issuedeck.core.db import make_engine, make_session_factory
from issuedeck.core.runtime_settings import RuntimeSettings
from issuedeck.features.github_sync.service import (
    GitHubSettings,
    check_connection,
    export_project,
    list_projects,
    make_client,
    read_token,
)
from issuedeck.features.items.models import Item

CONFIG = Path(os.environ.get("ISSUEDECK_CONFIG", "server.toml"))
PROJECT = os.environ.get("ISSUEDECK_LIVE_PROJECT", "my-commander")
EXPORT_FILES = (
    "manifest.json", "project.json", "items.json", "relationships.json",
    "work_sessions.json", "import_batches.json",
)


@pytest.fixture
def live():
    if os.environ.get("ISSUEDECK_LIVE_GITHUB") != "1":
        pytest.skip("live GitHub test: set ISSUEDECK_LIVE_GITHUB=1 to run it")
    if not CONFIG.exists():
        pytest.skip(f"no server config at {CONFIG}; run from the folder with server.toml")
    registry = _build_registry(CONFIG)
    runtime = RuntimeSettings(registry.server.data_dir)
    settings = GitHubSettings.from_group(runtime.settings()["github"])
    if not os.environ.get(settings.token_env):
        pytest.skip(f"the environment variable {settings.token_env} is not set")
    if PROJECT not in {p.key for p in registry.all_projects()}:
        pytest.skip(f"this installation has no project '{PROJECT}'")
    return registry, runtime, settings


async def test_export_the_project_to_the_real_repository(live, capsys):
    registry, runtime, settings = live
    token = read_token(settings.token_env)
    prefix = settings.prefix(PROJECT)

    def say(text: str) -> None:
        with capsys.disabled():
            print(text)

    say(f"\nRepository {settings.repository}, branch {settings.branch}, "
        f"folder '{settings.folder or '/'}', project '{PROJECT}'")

    # 1. the connection: token, repository, write access, private, branch
    check = await check_connection(settings)
    for name, ok, detail in check.checks:
        say(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
    assert check.ok, "the connection check failed; see the lines above"
    assert check.private is True or settings.allow_public

    engine = make_engine(f"sqlite+aiosqlite:///{registry.server.data_dir / 'tracker.db'}")
    try:
        async with make_session_factory(engine)() as session:
            expected = int((await session.execute(
                select(func.count(Item.pk)).where(Item.project_key == PROJECT)
            )).scalar())
            say(f"  the project has {expected} items in the database")
            assert expected > 0

            # 2. a dry run changes nothing and tells which files would change
            dry = await export_project(
                session=session, registry=registry, project_key=PROJECT,
                settings=settings, dry_run=True,
            )
            say(f"  dry run: up to date={dry.up_to_date}, files to change={dry.files_changed}")
            assert dry.commit_sha is None and dry.items == expected

            # 3. the real export: one commit, or nothing when the repository is current
            report = await export_project(
                session=session, registry=registry, project_key=PROJECT,
                settings=settings, runtime=runtime, actor="live-test",
            )
            say(f"  export: up to date={report.up_to_date}, commit={report.commit_sha}, "
                f"files changed={report.files_changed}")
            assert report.up_to_date or report.commit_sha

            # 4. a second export finds nothing to do
            again = await export_project(
                session=session, registry=registry, project_key=PROJECT, settings=settings,
            )
            say(f"  second export: up to date={again.up_to_date}")
            assert again.up_to_date and again.commit_sha is None
    finally:
        await engine.dispose()

    # 5. read it back from GitHub: files, counts, and that the project is listed
    async with make_client(settings) as client:
        head = await client.commit(settings.branch)
        if report.commit_sha:
            exported = await client.commit(report.commit_sha)  # the new commit exists on GitHub
            assert exported.sha == report.commit_sha
        files = {e.path: e for e in await client.tree(head.tree_sha) if e.type == "blob"}
        for name in EXPORT_FILES:
            assert prefix + name in files, f"{prefix}{name} is not in the repository"
        manifest = json.loads(await client.blob(files[prefix + "manifest.json"].sha))
        items = json.loads(await client.blob(files[prefix + "items.json"].sha))
    say(f"  repository now holds {len(items)} items for '{PROJECT}' "
        f"(manifest: {manifest['counts']['items']}, exported at {manifest['generated_at']})")
    assert manifest["project_key"] == PROJECT
    assert manifest["counts"]["items"] == len(items) == expected

    listed = {p.key: p for p in await list_projects(settings)}
    assert PROJECT in listed and listed[PROJECT].items == expected

    # 6. the token is nowhere in what was recorded
    audit = json.dumps(runtime.audit_log(5)) + json.dumps(report.as_dict())
    assert token not in audit
    say("  the token does not appear in the audit log or the report")
