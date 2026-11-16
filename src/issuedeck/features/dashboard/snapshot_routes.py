"""Dashboard pages for importing a project snapshot (FEA-0007).

Three steps, so that nothing is written before the user has seen what would happen:
the form uploads the ZIP and shows an exact preview; *Apply* then imports the stored upload.
The upload is kept in the data folder under a random name until it is applied, discarded or
older than an hour.
"""

from __future__ import annotations

import re
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile

from issuedeck.core.errors import IssueDeckError
from issuedeck.features.dashboard.helpers import render
from issuedeck.features.dashboard.i18n import language_from_request, make_translator
from issuedeck.features.dashboard.routes import _ctx
from issuedeck.features.export.snapshot_import import (
    CONFLICT_POLICIES,
    MODES,
    import_snapshot,
)

router = APIRouter(prefix="/dashboard/import-snapshot", tags=["dashboard"])

UPLOAD_DIR_NAME = "snapshot-uploads"
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_TTL_SECONDS = 3600
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
SNAPSHOT_FILE = File(None)


def _upload_dir(request: Request) -> Path:
    return request.app.state.registry.server.data_dir / UPLOAD_DIR_NAME


def _forget_old_uploads(directory: Path) -> None:
    if not directory.exists():
        return
    cutoff = time.time() - UPLOAD_TTL_SECONDS
    for path in directory.glob("*.zip"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:  # pragma: no cover - best effort
            pass


def _form(mode="create", new_key="", target="", conflict="keep") -> dict:
    return {"mode": mode, "new_key": new_key, "target": target, "conflict": conflict}


def _page(request: Request, *, status_code: int = 200, **extra):
    registry = request.app.state.registry
    return render(
        "pages/snapshot_import.html", request,
        status_code=status_code,
        **_ctx(request),
        active_page="snapshot_import",
        targets=[(p.key, p.name) for p in registry.all_projects()],
        conflict_policies=CONFLICT_POLICIES,
        error=extra.pop("error", None),
        form=extra.pop("form", _form()),
        report=extra.pop("report", None),
        token=extra.pop("token", None),
        applied=extra.pop("applied", False),
        **extra,
    )


def _target_key(mode: str, new_key: str, target: str) -> str | None:
    value = (new_key if mode == "create" else target).strip().lower()
    return value or None


def _checked(mode: str, conflict: str) -> bool:
    return mode in MODES and conflict in CONFLICT_POLICIES


@router.get("")
async def snapshot_import_form(request: Request, project: str = ""):
    registry = request.app.state.registry
    known = {p.key for p in registry.all_projects()}
    if project in known:
        return _page(request, form=_form(mode="update", target=project))
    return _page(request)


@router.post("/preview")
async def snapshot_import_preview(
    request: Request,
    snapshot_file: UploadFile | None = SNAPSHOT_FILE,
    mode: str = Form("create"),
    new_key: str = Form(""),
    target: str = Form(""),
    conflict: str = Form("keep"),
):
    t = make_translator(language_from_request(request))
    form = _form(mode, new_key, target, conflict)
    if not _checked(mode, conflict):
        return _page(request, status_code=422, form=form, error=t("snapshot.error.options"))
    if snapshot_file is None or not snapshot_file.filename:
        return _page(request, status_code=422, form=form, error=t("snapshot.error.no_file"))

    content = await snapshot_file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        return _page(request, status_code=413, form=form, error=t("snapshot.error.too_large"))

    directory = _upload_dir(request)
    directory.mkdir(parents=True, exist_ok=True)
    _forget_old_uploads(directory)
    token = secrets.token_hex(16)
    stored = directory / f"{token}.zip"
    stored.write_bytes(content)

    session = request.app.state.session_factory()
    try:
        report = await import_snapshot(
            session=session, registry=request.app.state.registry, bundle_path=stored,
            mode=mode, project_key=_target_key(mode, new_key, target),
            conflict=conflict, apply=False,
        )
    except IssueDeckError as exc:
        stored.unlink(missing_ok=True)
        return _page(request, status_code=exc.http_status, form=form, error=exc.message)
    finally:
        await session.close()
    return _page(request, form=form, report=report, token=token)


@router.post("/apply")
async def snapshot_import_apply(
    request: Request,
    token: str = Form(...),
    mode: str = Form("create"),
    new_key: str = Form(""),
    target: str = Form(""),
    conflict: str = Form("keep"),
):
    t = make_translator(language_from_request(request))
    form = _form(mode, new_key, target, conflict)
    stored = _upload_dir(request) / f"{token}.zip"
    if not _TOKEN_RE.fullmatch(token) or not stored.exists() or not _checked(mode, conflict):
        return _page(request, status_code=422, form=form, error=t("snapshot.error.expired"))

    session = request.app.state.session_factory()
    try:
        report = await import_snapshot(
            session=session, registry=request.app.state.registry, bundle_path=stored,
            mode=mode, project_key=_target_key(mode, new_key, target),
            conflict=conflict, apply=True,
        )
    except IssueDeckError as exc:
        return _page(request, status_code=exc.http_status, form=form, error=exc.message)
    finally:
        await session.close()
        stored.unlink(missing_ok=True)
    return _page(request, form=_form(), report=report, applied=True)
