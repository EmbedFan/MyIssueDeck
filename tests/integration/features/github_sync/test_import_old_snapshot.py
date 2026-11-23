"""IS-0011: a repository that holds snapshots with CR CR LF in project.toml (written by 0.10.0 and
0.10.1 from Windows) can be imported on a new installation, and the first export repairs it."""

import asyncio
import re

from issuedeck.cli import _cmd_github_export, _cmd_github_import

from .fake_github import FakeGitHub
from .test_cli import _installation, _items, fake  # noqa: F401
from .test_first_run import make_app
from .test_import_roundtrip import _check, _result

UP_TO_DATE = ("p: the repository is up to date, nothing was exported.", [])
NORMALISED = "line endings of project.toml were normalised"


def _damaged(text: bytes) -> bytes:
    return text.replace(b"\r\n", b"\n").replace(b"\n", b"\r\r\n")


async def test_a_repository_with_doubled_carriage_returns_is_imported_in_the_dashboard(tmp_path):
    repo = FakeGitHub()
    async with make_app(tmp_path / "a", repo, project=True) as (client, *_):
        await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})
    clean = repo.files()["p/project.toml"].replace(b"\r\n", b"\n")
    repo.commit_files({"p/project.toml": _damaged(clean)}, "as an earlier version left it")
    assert b"\r\r\n" in repo.files()["p/project.toml"]

    async with make_app(tmp_path / "b", repo, project=False) as (client, app, registry, _):
        data = {"source": "p", "revision": "", "mode": "create", "new_key": "", "target": "",
                "conflict": "keep"}
        preview = await client.post("/dashboard/github/import/preview", data=data)
        assert preview.status_code == 200 and "nothing has been written yet" in preview.text
        assert NORMALISED in preview.text                       # said before anything is written
        assert not (registry.server.projects_dir / "p.toml").exists()
        token = re.search(r'name="token" value="([0-9a-f]{32})"', preview.text).group(1)
        commit = re.search(r'name="commit" value="([0-9a-f]+)"', preview.text).group(1)

        applied = await client.post(
            "/dashboard/github/import/apply", data={**data, "token": token, "commit": commit})

        assert applied.status_code == 200 and "Snapshot imported" in applied.text
        assert NORMALISED in applied.text
        assert (await client.get("/dashboard/p")).status_code == 200
        written = (registry.server.projects_dir / "p.toml").read_bytes()
        assert written == clean and b"\r" not in written


async def test_the_first_export_of_the_imported_project_repairs_the_repository(tmp_path):
    repo = FakeGitHub()
    async with make_app(tmp_path / "a", repo, project=True) as (client, *_):
        await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})
    clean = repo.files()["p/project.toml"].replace(b"\r\n", b"\n")
    repo.commit_files({"p/project.toml": _damaged(clean)}, "as an earlier version left it")

    async with make_app(tmp_path / "b", repo, project=False) as (client, *_):
        data = {"source": "p", "revision": "", "mode": "create", "new_key": "", "target": "",
                "conflict": "keep"}
        preview = await client.post("/dashboard/github/import/preview", data=data)
        token = re.search(r'name="token" value="([0-9a-f]{32})"', preview.text).group(1)
        commit = re.search(r'name="commit" value="([0-9a-f]+)"', preview.text).group(1)
        await client.post(
            "/dashboard/github/import/apply", data={**data, "token": token, "commit": commit})

        headline, files = _result(await _check(client))
        assert "would be exported" in headline
        assert "project.toml" in files                          # the repository still has CR CR LF

        await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})
        assert repo.files()["p/project.toml"] == clean          # repaired: LF only
        assert _result(await _check(client)) == UP_TO_DATE


def test_a_repository_with_doubled_carriage_returns_is_imported_by_the_command(
        tmp_path, fake, capsys):  # noqa: F811
    _, source = _installation(tmp_path, "src", seeded=True)
    assert asyncio.run(_cmd_github_export(source, "example", False)) == 0
    clean = fake.files()["example/project.toml"].replace(b"\r\n", b"\n")
    fake.commit_files({"example/project.toml": _damaged(clean)}, "as an earlier version left it")
    capsys.readouterr()
    target_root, target = _installation(tmp_path, "dst")

    assert asyncio.run(_cmd_github_import(
        target, "example", "create", "restored", None, "keep", False)) == 0

    err = capsys.readouterr().err
    assert NORMALISED in err and "restart a running server" in err
    assert _items(target_root, "restored") == 8
    written = (target_root / "projects" / "restored.toml").read_bytes()
    assert b"\r" not in written and b'key = "restored"' in written
