"""Dashboard page for exporting projects to GitHub and importing them back (FEA-0008).

Export: pick a project, check what would change, export. Import: load the projects found in
the repository, pick one, check the content with the FEA-0007 preview (nothing is written),
then apply. The settings (repository, branch, folder, token variable) are on the Settings page;
the token itself is read from the environment variable and never shown.

The page does not reload. Its script (``github.js``) starts every action as a background job
(``X-Requested-With: github-job``), shows the steps while the job runs, and puts the finished
result into the page. Without JavaScript the forms are ordinary posts and the same work runs
inside the request.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import GitHubConfigError, IssueDeckError
from issuedeck.features.dashboard.github_jobs import Job, JobBusy, JobStore
from issuedeck.features.dashboard.helpers import get_jinja_env, render
from issuedeck.features.dashboard.i18n import language_from_request, make_translator
from issuedeck.features.dashboard.routes import _ctx
from issuedeck.features.dashboard.snapshot_routes import (
    UPLOAD_DIR_NAME,
    _checked,
    _forget_old_uploads,
    _form,
    _page,
    _target_key,
)
from issuedeck.features.export.snapshot_import import import_snapshot
from issuedeck.features.github_sync.service import (
    ExportReport,
    GitHubSettings,
    RemoteProject,
    export_project,
    fetch_snapshot,
    list_projects,
)

router = APIRouter(prefix="/dashboard/github", tags=["dashboard"])

ACTOR = "dashboard"
JOB_HEADER = "x-requested-with"
JOB_HEADER_VALUE = "github-job"
CONFLICT_POLICIES = ("keep", "newer", "overwrite")
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{7,64}$")
Progress = Callable[..., None] | None


@dataclass
class _Env:
    """Everything a piece of work needs, captured when the request arrives, so that a job can
    keep running after the response has been sent."""

    registry: ConfigRegistry
    session_factory: Any
    runtime: Any
    settings: GitHubSettings
    transport: Any
    environ: Any
    upload_dir: Any
    t: Callable[..., str]


def _env(request: Request) -> _Env:
    runtime = request.app.state.runtime_settings
    registry = request.app.state.registry
    return _Env(
        registry=registry,
        session_factory=request.app.state.session_factory,
        runtime=runtime,
        settings=GitHubSettings.from_group(runtime.settings()["github"]),
        transport=getattr(request.app.state, "github_transport", None),
        environ=getattr(request.app.state, "github_environ", None),
        upload_dir=registry.server.data_dir / UPLOAD_DIR_NAME,
        t=make_translator(language_from_request(request)),
    )


def _wants_job(request: Request) -> bool:
    return request.headers.get(JOB_HEADER, "").lower() == JOB_HEADER_VALUE


def _jobs(request: Request) -> JobStore:
    store = getattr(request.app.state, "github_jobs", None)
    if store is None:
        store = request.app.state.github_jobs = JobStore()
    return store


def _token_present(settings: GitHubSettings, environ) -> bool:
    return bool((environ if environ is not None else os.environ).get(settings.token_env, ""))


# ---------------------------------------------------------------------------
# the work (the same for a job and for a plain post)
# ---------------------------------------------------------------------------

async def _export_work(env: _Env, project: str, action: str, progress: Progress) -> ExportReport:
    if project not in {p.key for p in env.registry.all_projects()} or action not in (
        "preview", "export",
    ):
        raise GitHubConfigError(env.t("github.error.options"))
    session = env.session_factory()
    try:
        return await export_project(
            session=session, registry=env.registry, project_key=project,
            settings=env.settings, environ=env.environ, transport=env.transport,
            dry_run=action != "export", runtime=env.runtime, actor=ACTOR, progress=progress,
        )
    finally:
        await session.close()


async def _list_work(env: _Env, revision: str, progress: Progress) -> list[RemoteProject]:
    return await list_projects(
        env.settings, revision=revision or None, environ=env.environ,
        transport=env.transport, progress=progress,
    )


async def _preview_work(
    env: _Env, source: str, revision: str, mode: str, new_key: str, target: str,
    conflict: str, progress: Progress,
) -> dict[str, Any]:
    if not _checked(mode, conflict) or not source.strip():
        raise GitHubConfigError(env.t("github.error.options"))
    env.upload_dir.mkdir(parents=True, exist_ok=True)
    _forget_old_uploads(env.upload_dir)
    token = secrets.token_hex(16)
    stored = env.upload_dir / f"{token}.zip"
    session = env.session_factory()
    try:
        commit = await fetch_snapshot(
            env.settings, source.strip(), stored, revision=revision.strip() or None,
            environ=env.environ, transport=env.transport, progress=progress,
        )
        if progress:
            progress("checking")
        report = await import_snapshot(
            session=session, registry=env.registry, bundle_path=stored, mode=mode,
            project_key=_target_key(mode, new_key, target), conflict=conflict, apply=False,
        )
    except BaseException:
        stored.unlink(missing_ok=True)
        raise
    finally:
        await session.close()
    return {
        "report": report, "token": token, "commit": commit,
        "form": _form(mode, new_key, target, conflict),
        "source": source.strip(), "revision": revision.strip(),
    }


async def _apply_work(
    env: _Env, token: str, source: str, revision: str, commit: str, mode: str,
    new_key: str, target: str, conflict: str, progress: Progress,
):
    stored = env.upload_dir / f"{token}.zip"
    if (
        not _TOKEN_RE.fullmatch(token) or not stored.exists() or not _checked(mode, conflict)
        or (commit and not _COMMIT_RE.fullmatch(commit))
    ):
        raise GitHubConfigError(env.t("snapshot.error.expired"))
    session = env.session_factory()
    try:
        if progress:
            progress("importing")
        report = await import_snapshot(
            session=session, registry=env.registry, bundle_path=stored, mode=mode,
            project_key=_target_key(mode, new_key, target), conflict=conflict, apply=True,
        )
    finally:
        await session.close()
        stored.unlink(missing_ok=True)
    env.runtime.record("github.import", ACTOR, {
        "project": report.project_key, "source_project": source,
        "repository": env.settings.repository, "branch": env.settings.branch,
        "revision": revision or env.settings.branch, "commit": commit, "mode": mode,
        "conflict": conflict, "items_created": report.items_created,
        "items_updated": report.items_updated,
    })
    return report


# ---------------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------------

def _page_context(request: Request, env: _Env, **extra):
    return render(
        "pages/github.html", request,
        status_code=extra.pop("status_code", 200),
        **_ctx(request),
        active_page="github",
        gh=env.settings,
        token_present=_token_present(env.settings, env.environ),
        targets=[(p.key, p.name) for p in env.registry.all_projects()],
        conflict_policies=CONFLICT_POLICIES,
        selected=extra.pop("selected", ""),
        error=extra.pop("error", None),
        export_report=extra.pop("export_report", None),
        remote=extra.pop("remote", None),
        revision=extra.pop("revision", ""),
        **extra,
    )


@router.get("")
async def github_page(
    request: Request, project: str = "", load: str = "", revision: str = "",
):
    env = _env(request)
    remote: list[RemoteProject] | None = None
    error = None
    status = 200
    if load:
        try:
            remote = await _list_work(env, revision, None)
        except IssueDeckError as exc:
            error, status = exc.message, exc.http_status
    known = {p.key for p in env.registry.all_projects()}
    return _page_context(
        request, env, selected=project if project in known else "",
        remote=remote, revision=revision, error=error, status_code=status,
    )


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def _start(
    request: Request, env: _Env, kind: str, key: str,
    work: Callable[[Job], Awaitable[Any]],
) -> JSONResponse:
    try:
        job = _jobs(request).start(kind, key, work)
    except JobBusy:
        return JSONResponse(
            {"error": env.t("github.error.busy")}, status_code=409,
            headers={"Cache-Control": "no-store"},
        )
    return JSONResponse({"job": job.id}, status_code=202, headers={"Cache-Control": "no-store"})


def _fragment(request: Request, env: _Env, job: Job) -> str:
    """The HTML that replaces a result area when a job is done."""
    ctx = {**_ctx(request), "request": request}
    templates = get_jinja_env()
    if job.kind == "export":
        return templates.get_template("components/github_export_result.html").render(
            **ctx, export_report=job.result,
        )
    if job.kind == "list":
        return templates.get_template("components/github_remote.html").render(
            **ctx, remote=job.result["remote"], revision=job.result["revision"],
            targets=[(p.key, p.name) for p in env.registry.all_projects()],
            conflict_policies=CONFLICT_POLICIES,
        )
    common = {"live_actions": True, "cancel_url": "/dashboard/github"}
    if job.kind == "import_preview":
        result = job.result
        return templates.get_template("components/snapshot_report.html").render(
            **ctx, **common, report=result["report"], applied=False, token=result["token"],
            form=result["form"], apply_action="/dashboard/github/import/apply",
            extra_fields={"source": result["source"], "revision": result["revision"],
                          "commit": result["commit"]},
        )
    return templates.get_template("components/snapshot_report.html").render(
        **ctx, **common, report=job.result, applied=True, form=_form(),
    )


@router.get("/jobs/{job_id}")
async def github_job(request: Request, job_id: str):
    env = _env(request)
    job = _jobs(request).get(job_id)
    if job is None:
        return JSONResponse(
            {"state": "unknown", "error": env.t("github.error.job_unknown")},
            status_code=404, headers={"Cache-Control": "no-store"},
        )
    payload: dict[str, Any] = {
        "state": job.state,
        "elapsed": round(job.elapsed, 1),
        "steps": [env.t(f"github.step.{step}", **params) for step, params in job.steps],
    }
    if job.state == "done":
        payload["html"] = _fragment(request, env, job)
    elif job.state == "error":
        payload["error"], payload["status"] = job.error, job.status
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@router.post("/export")
async def github_export(
    request: Request, project: str = Form(""), action: str = Form("preview"),
):
    env = _env(request)
    if _wants_job(request):
        async def work(job: Job):
            return await _export_work(env, project, action, job.step)
        return _start(request, env, "export", project, work)
    try:
        report = await _export_work(env, project, action, None)
    except IssueDeckError as exc:
        return _page_context(
            request, env, selected=project, error=exc.message, status_code=exc.http_status,
        )
    return _page_context(request, env, selected=project, export_report=report)


# ---------------------------------------------------------------------------
# listing the repository
# ---------------------------------------------------------------------------

@router.post("/list")
async def github_list(request: Request, revision: str = Form("")):
    env = _env(request)
    if not _wants_job(request):
        try:
            remote = await _list_work(env, revision, None)
        except IssueDeckError as exc:
            return _page_context(request, env, error=exc.message, status_code=exc.http_status)
        return _page_context(request, env, remote=remote, revision=revision)

    async def work(job: Job):
        return {"remote": await _list_work(env, revision, job.step), "revision": revision}
    return _start(request, env, "list", "", work)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@router.post("/import/preview")
async def github_import_preview(
    request: Request,
    source: str = Form(""),
    revision: str = Form(""),
    mode: str = Form("create"),
    new_key: str = Form(""),
    target: str = Form(""),
    conflict: str = Form("keep"),
):
    env = _env(request)
    if _wants_job(request):
        async def work(job: Job):
            return await _preview_work(
                env, source, revision, mode, new_key, target, conflict, job.step,
            )
        return _start(request, env, "import_preview", source.strip(), work)
    form = _form(mode, new_key, target, conflict)
    try:
        result = await _preview_work(env, source, revision, mode, new_key, target, conflict, None)
    except IssueDeckError as exc:
        return _page(request, status_code=exc.http_status, form=form, error=exc.message,
                     cancel_url="/dashboard/github")
    return _page(
        request, form=form, report=result["report"], token=result["token"],
        cancel_url="/dashboard/github", apply_action="/dashboard/github/import/apply",
        extra_fields={"source": result["source"], "revision": result["revision"],
                      "commit": result["commit"]},
    )


@router.post("/import/apply")
async def github_import_apply(
    request: Request,
    token: str = Form(...),
    source: str = Form(""),
    revision: str = Form(""),
    commit: str = Form(""),
    mode: str = Form("create"),
    new_key: str = Form(""),
    target: str = Form(""),
    conflict: str = Form("keep"),
):
    env = _env(request)
    if _wants_job(request):
        async def work(job: Job):
            return await _apply_work(
                env, token, source, revision, commit, mode, new_key, target, conflict, job.step,
            )
        return _start(request, env, "import_apply", token, work)
    form = _form(mode, new_key, target, conflict)
    try:
        report = await _apply_work(
            env, token, source, revision, commit, mode, new_key, target, conflict, None,
        )
    except IssueDeckError as exc:
        return _page(request, status_code=exc.http_status, form=form, error=exc.message,
                     cancel_url="/dashboard/github")
    return _page(request, form=_form(), report=report, applied=True,
                 cancel_url="/dashboard/github")
