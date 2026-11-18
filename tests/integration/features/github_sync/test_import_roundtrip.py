"""IS-0010: after an import with no edits, the check says the repository is up to date."""

import re

from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.items.schemas import CreateItemEventRequest
from issuedeck.features.items.service import ItemService
from issuedeck.features.relationships.repo import RelationshipRepo
from issuedeck.features.relationships.service import RelationshipService
from issuedeck.features.work_sessions.repo import WorkSessionRepo
from issuedeck.features.work_sessions.schemas import CreateWorkSessionRequest
from issuedeck.features.work_sessions.service import WorkSessionService

from .fake_github import FakeGitHub
from .test_first_run import make_app


async def _enrich(registry, Session):
    """Relationships and a work session: the files whose ids an import used to change."""
    async with Session() as session:
        items = ItemRepo(session)
        await RelationshipService(RelationshipRepo(session), items, registry, session).add(
            "p", "FEAT-0001", to_local_id="FEAT-0002", relation_type="blocks")
        await WorkSessionService(WorkSessionRepo(session), items, registry, session).start(
            "p", CreateWorkSessionRequest(
                local_id="FEAT-0001", agent_name="codex", goal="work", branch="main"))


async def _export_p(client):
    await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})


async def _import_p(client):
    data = {"source": "p", "revision": "", "mode": "create", "new_key": "", "target": "",
            "conflict": "keep"}
    preview = await client.post("/dashboard/github/import/preview", data=data)
    token = re.search(r'name="token" value="([0-9a-f]{32})"', preview.text).group(1)
    commit = re.search(r'name="commit" value="([0-9a-f]+)"', preview.text).group(1)
    applied = await client.post(
        "/dashboard/github/import/apply", data={**data, "token": token, "commit": commit})
    assert "Snapshot imported" in applied.text


def _result(page):
    """The headline and the file list of the result block of the page."""
    block = re.search(r"data-github-export-result>(.*?)</div>", page.text, re.S).group(1)
    headline = re.sub(r"<[^>]+>", " ", block.split("</p>")[0]).strip()
    return headline, re.findall(r"<li><code>([^<]+)</code></li>", block)


async def _check(client):
    return await client.post("/dashboard/github/export", data={"project": "p", "action": "preview"})


async def test_an_imported_project_is_up_to_date_and_an_export_makes_no_commit(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path / "a", fake, project=True) as (client, app, registry, Session):
        await _enrich(registry, Session)
        await _export_p(client)
    commits = len(fake.history())

    async with make_app(tmp_path / "b", fake, project=False) as (client, *_):
        await _import_p(client)

        checked = _result(await _check(client))
        exported = _result(await client.post(
            "/dashboard/github/export", data={"project": "p", "action": "export"}))

    assert checked == ("p: the repository is up to date, nothing was exported.", [])
    assert exported[0].startswith("p: the repository is up to date")
    assert len(fake.history()) == commits  # no commit for a project that was only imported


async def test_the_check_is_up_to_date_when_the_other_database_is_busy_too(tmp_path):
    """The usual case: the database that imports already holds other data (and so other ids)."""
    fake = FakeGitHub()
    async with make_app(tmp_path / "a", fake, project=True) as (client, app, registry, Session):
        await _enrich(registry, Session)
        await _export_p(client)

    async with make_app(tmp_path / "b", fake, project=False) as (client, *_):
        data = {"source": "p", "revision": "", "mode": "create", "new_key": "other",
                "target": "", "conflict": "keep"}
        preview = await client.post("/dashboard/github/import/preview", data=data)
        token = re.search(r'name="token" value="([0-9a-f]{32})"', preview.text).group(1)
        commit = re.search(r'name="commit" value="([0-9a-f]+)"', preview.text).group(1)
        await client.post(
            "/dashboard/github/import/apply", data={**data, "token": token, "commit": commit})
        await _import_p(client)  # p now has ids that the first import did not leave free

        assert _result(await _check(client)) == (
            "p: the repository is up to date, nothing was exported.", [])


async def test_a_configuration_with_the_doubled_line_ends_of_earlier_imports_is_no_change(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path / "a", fake, project=True) as (client, app, registry, Session):
        await _enrich(registry, Session)
        await _export_p(client)

    async with make_app(tmp_path / "b", fake, project=False) as (client, app, registry, _):
        await _import_p(client)
        path = registry.server.projects_dir / "p.toml"
        text = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(text.replace(b"\n", b"\r\r\n"))  # what a Windows import used to write

        assert _result(await _check(client))[1] == []


async def test_after_a_real_edit_the_check_names_only_the_files_that_changed(tmp_path):
    fake = FakeGitHub()
    async with make_app(tmp_path / "a", fake, project=True) as (client, app, registry, Session):
        await _enrich(registry, Session)
        await _export_p(client)

    async with make_app(tmp_path / "b", fake, project=False) as (client, app, registry, Session):
        await _import_p(client)
        async with Session() as session:
            await ItemService(ItemRepo(session), registry, session).add_event(
                "p", "FEAT-0001", CreateItemEventRequest(body="a real change", actor_name="me"))
        headline, files = _result(await _check(client))

    assert headline.startswith("p: ") and "would be exported" in headline
    assert sorted(files) == ["items.json", "manifest.json"]  # the manifest is rewritten with them
    assert not {"project.toml", "relationships.json", "work_sessions.json",
                "import_batches.json", "project.json"} & set(files)
