"""FEA-0008: the GitHub page works as background jobs, without reloading, with visible progress."""

import asyncio
import re
from pathlib import Path

import httpx
import pytest

from issuedeck.features.dashboard import github_routes
from issuedeck.features.dashboard.github_jobs import JobBusy, JobStore
from issuedeck.features.dashboard.i18n import DASHBOARD_LANG_COOKIE

from .fake_github import TOKEN
from .test_dashboard import env  # noqa: F401 - the shared app fixture

JOB = {"X-Requested-With": "github-job"}
STATIC = Path(github_routes.__file__).parent / "static"


async def _wait(client, job_id, timeout=5.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        response = await client.get(f"/dashboard/github/jobs/{job_id}")
        body = response.json()
        if body["state"] != "running":
            return body
        assert loop.time() < deadline, "the job did not finish"
        await asyncio.sleep(0.01)


async def _job(client, path, data):
    response = await client.post(path, data=data, headers=JOB)
    assert response.status_code == 202, response.text
    assert response.headers["content-type"].startswith("application/json")
    return await _wait(client, response.json()["job"])


class Gate(httpx.AsyncBaseTransport):
    """Holds the first request until released, to keep a job running on purpose."""

    def __init__(self, inner):
        self.inner, self.open, self.reached = inner, asyncio.Event(), asyncio.Event()

    async def handle_async_request(self, request):
        self.reached.set()
        await self.open.wait()
        return await self.inner.handle_async_request(request)


# ---------------------------------------------------------------------------
# export as a job
# ---------------------------------------------------------------------------

async def test_an_export_runs_as_a_job_and_reports_every_step(env):  # noqa: F811
    client, fake, *_ = env
    done = await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})

    assert done["state"] == "done" and done["elapsed"] >= 0
    steps = done["steps"]
    assert steps[:4] == [
        "Connecting to GitHub and checking the repository",
        "Reading the files of the repository",
        "Building the files of project p",
        "Comparing 7 files with the repository",
    ]
    assert steps[4] == "Uploading file 1 of 7 (manifest.json)"
    assert steps[-3:] == ["Uploading file 7 of 7 (project.toml)",
                          "Creating the commit", "Updating the branch"]
    assert "p: exported (2 items)." in done["html"] and "data-github-export-result" in done["html"]
    assert "<html" not in done["html"] and "p/items.json" in fake.files()


async def test_a_check_reports_its_steps_and_writes_nothing(env):  # noqa: F811
    client, fake, *_ = env
    done = await _job(client, "/dashboard/github/export", {"project": "p", "action": "preview"})
    assert done["state"] == "done" and "Creating the commit" not in done["steps"]
    assert "nothing was written" in done["html"] and len(fake.history()) == 1


async def test_nothing_to_export_ends_after_the_comparison(env):  # noqa: F811
    client, fake, *_ = env
    await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})
    again = await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})
    assert again["steps"][-1] == "Comparing 7 files with the repository"
    assert "the repository is up to date" in again["html"] and len(fake.history()) == 2


async def test_the_same_export_cannot_run_twice_at_once(env):  # noqa: F811
    client, fake, _, _, _, app, _ = env
    gate = Gate(fake.transport)
    app.state.github_transport = gate

    first = await client.post("/dashboard/github/export", headers=JOB,
                              data={"project": "p", "action": "export"})
    assert first.status_code == 202
    await asyncio.wait_for(gate.reached.wait(), 5)
    second = await client.post("/dashboard/github/export", headers=JOB,
                               data={"project": "p", "action": "export"})
    assert second.status_code == 409 and "already running" in second.json()["error"]

    running = (await client.get(f"/dashboard/github/jobs/{first.json()['job']}")).json()
    assert running["state"] == "running" and running["steps"] == [
        "Connecting to GitHub and checking the repository"]

    gate.open.set()
    assert (await _wait(client, first.json()["job"]))["state"] == "done"
    third = await client.post("/dashboard/github/export", headers=JOB,
                              data={"project": "p", "action": "preview"})
    assert third.status_code == 202  # allowed again once the first one is finished


async def test_a_failing_job_reports_the_reason_in_place(env):  # noqa: F811
    client, _, _, _, _, app, _ = env
    app.state.github_environ = {}
    failed = await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})
    assert failed["state"] == "error" and failed["status"] == 422
    assert "GITHUB_PAT is not set" in failed["error"] and "html" not in failed

    bad = await _job(client, "/dashboard/github/export", {"project": "nope", "action": "export"})
    assert bad["state"] == "error" and "options are not valid" in bad["error"]
    assert TOKEN not in str(failed) + str(bad)


async def test_an_unknown_job_is_reported(env):  # noqa: F811
    client, *_ = env
    response = await client.get("/dashboard/github/jobs/0123456789abcdef")
    assert response.status_code == 404 and response.json()["state"] == "unknown"


async def test_the_steps_follow_the_language(env):  # noqa: F811
    client, *_ = env
    client.cookies.set(DASHBOARD_LANG_COOKIE, "hu")
    done = await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})
    assert "Commit létrehozása" in done["steps"] and "Az ág frissítése" in done["steps"]
    assert "1. fájl feltöltése (7 közül): manifest.json" in done["steps"]


# ---------------------------------------------------------------------------
# listing and importing as jobs
# ---------------------------------------------------------------------------

async def test_loading_the_repository_projects_is_a_job(env):  # noqa: F811
    client, *_ = env
    await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})
    done = await _job(client, "/dashboard/github/list", {"revision": ""})
    assert done["steps"][-1] == "Reading project 1 of 1 (p)"
    html = done["html"]
    assert "data-github-import-form" in html and "data-github-job" in html
    assert 'data-github-target="#github-import-result"' in html and "2 items" in html


async def test_an_empty_repository_is_reported_in_place(env):  # noqa: F811
    client, *_ = env
    done = await _job(client, "/dashboard/github/list", {"revision": ""})
    assert done["state"] == "done" and "data-github-empty" in done["html"]


async def test_import_is_checked_and_applied_in_place(env):  # noqa: F811
    client, _, runtime, registry, Session, _, tmp_path = env
    await _job(client, "/dashboard/github/export", {"project": "p", "action": "export"})
    data = {"source": "p", "revision": "", "mode": "create", "new_key": "restored",
            "target": "", "conflict": "keep"}

    preview = await _job(client, "/dashboard/github/import/preview", data)
    assert preview["state"] == "done"
    assert preview["steps"][-1] == "Checking the content"
    assert any(step.startswith("Downloading file 7 of 7") for step in preview["steps"])
    html = preview["html"]
    assert "nothing has been written yet" in html
    assert 'action="/dashboard/github/import/apply"' in html
    assert "data-github-job" in html and 'data-github-target="#github-import-result"' in html
    assert 'data-github-clear="#github-import-result"' in html
    assert not (registry.server.projects_dir / "restored.toml").exists()

    token = re.search(r'name="token" value="([0-9a-f]{32})"', html).group(1)
    commit = re.search(r'name="commit" value="([0-9a-f]+)"', html).group(1)
    applied = await _job(client, "/dashboard/github/import/apply", {
        **data, "token": token, "commit": commit})
    assert applied["state"] == "done" and applied["steps"] == ["Writing the project"]
    assert "Snapshot imported" in applied["html"]
    assert 'href="/dashboard/restored"' in applied["html"]
    assert registry.project("restored").name == "Project P"
    assert not (tmp_path / "data" / "snapshot-uploads" / f"{token}.zip").exists()
    audit = [e for e in runtime.audit_log() if e["action"] == "github.import"]
    assert len(audit) == 1 and audit[0]["details"]["commit"] == commit

    replay = await _job(client, "/dashboard/github/import/apply", {
        **data, "token": token, "commit": commit})
    assert replay["state"] == "error" and "no longer available" in replay["error"]


async def test_import_problems_end_the_job_with_the_reason(env):  # noqa: F811
    client, fake, *_ = env
    fake.commit_files({"junk/items.json": b"[]"})
    junk = await _job(client, "/dashboard/github/import/preview", {
        "source": "junk", "mode": "create", "conflict": "keep"})
    assert junk["state"] == "error" and "is not a project export" in junk["error"]
    nothing = await _job(client, "/dashboard/github/import/preview", {
        "source": "", "mode": "create", "conflict": "keep"})
    assert nothing["state"] == "error" and "options are not valid" in nothing["error"]


# ---------------------------------------------------------------------------
# the page and its script
# ---------------------------------------------------------------------------

async def test_the_page_marks_its_forms_as_jobs_with_a_status_panel_per_section(env):  # noqa: F811
    client, *_ = env
    html = (await client.get("/dashboard/github")).text
    assert html.count("data-github-status") == 2 and html.count('role="status"') == 2
    # a result can hold sections of its own (the snapshot card), so the script finds the
    # status panel through the page's own sections
    assert html.count("data-github-section") == 2
    assert re.search(r'<form[^>]*action="/dashboard/github/export"[^>]*data-github-job', html)
    assert 'data-github-url="/dashboard/github/list"' in html
    assert 'id="github-export-result"' in html and 'id="github-import-result"' in html
    assert 'src="/dashboard/static/js/github.js"' in html
    assert "animate-spin" in html  # the busy indicator


async def test_without_the_script_the_forms_still_work_as_plain_posts(env):  # noqa: F811
    client, fake, *_ = env
    page = await client.post("/dashboard/github/export", data={"project": "p", "action": "export"})
    assert page.status_code == 200 and "p: exported (2 items)." in page.text
    assert "data-github-page" in page.text and "p/items.json" in fake.files()


def test_the_script_never_lets_the_form_reload_the_page():
    script = (STATIC / "js" / "github.js").read_text(encoding="utf-8")
    submit = re.search(r"addEventListener\('submit'.*?\}\);\n", script, re.S).group(0)
    assert "event.preventDefault()" in submit and "aria-busy" in submit
    assert "X-Requested-With" in script and "'github-job'" in script
    assert "aria-current" in script
    assert "[data-github-section]" in script
    assert "setBusy(form, true)" in script and "setBusy(form, false)" in script


# ---------------------------------------------------------------------------
# the job store
# ---------------------------------------------------------------------------

async def test_the_store_refuses_the_same_work_twice_but_not_different_work():
    store = JobStore()
    release = asyncio.Event()

    async def slow(job):
        job.step("connecting")
        await release.wait()
        return "result"

    first = store.start("export", "p", slow)
    with pytest.raises(JobBusy):
        store.start("export", "p", slow)
    other = store.start("export", "q", slow)      # another target
    listing = store.start("list", "", slow)       # no key: never refused
    again = store.start("list", "", slow)
    release.set()
    await asyncio.gather(first.task, other.task, listing.task, again.task)
    assert first.state == "done" and first.result == "result"
    assert first.steps == [("connecting", {})]
    store.start("export", "p", slow)  # allowed once the first has finished


async def test_an_unexpected_error_never_leaks_and_never_stops_the_server():
    store = JobStore()

    async def broken(job):
        raise RuntimeError(f"secret detail {TOKEN}")

    job = store.start("export", "p", broken)
    await job.task
    assert job.state == "error" and job.status == 500
    assert job.error == "an unexpected error occurred" and TOKEN not in job.error


async def test_finished_jobs_are_forgotten_after_a_while(monkeypatch):
    from issuedeck.features.dashboard import github_jobs

    store = JobStore()

    async def quick(job):
        return 1

    job = store.start("list", "", quick)
    await job.task
    assert store.get(job.id) is job
    monkeypatch.setattr(github_jobs, "MAX_AGE_SECONDS", -1)
    store.start("list", "", quick)  # starting a job prunes the old ones
    assert store.get(job.id) is None
