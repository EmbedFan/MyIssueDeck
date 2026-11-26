"""Dashboard pages of the project image store (FEA-0013, phase 2).

The page lists the SVG images of a project and uploads, downloads and deletes them. It uses the
same service as the API (``features/images``); the dashboard authenticates with the session
cookie, so the thumbnails (``<img>`` tags) and the downloads work in the browser.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from issuedeck.core.errors import IssueDeckError
from issuedeck.features.dashboard.helpers import render
from issuedeck.features.dashboard.routes import _ctx
from issuedeck.features.images.routes import content_response, link_service
from issuedeck.features.images.service import ImageService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ACTOR = "dashboard"


def _service(request: Request) -> ImageService:
    return ImageService(
        request.app.state.images_dir, request.app.state.images_config,
        request.app.state.registry,
    )


def human_size(size: int) -> str:
    """Bytes as 12 B, 3.4 KB or 5.0 MB."""
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1000 or unit == "MB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1000
    return f"{size} B"  # pragma: no cover - the loop always returns


async def _page(request: Request, project_key: str, *, status_code: int = 200,
          uploaded: list[str] | None = None, deleted: str | None = None,
          errors: list[str] | None = None):
    config = request.app.state.images_config
    listing = _service(request).list(project_key)
    links, session = link_service(request)
    try:
        linked_counts = await links.counts(project_key)
    finally:
        await session.close()
    return render(
        "pages/images.html", request,
        status_code=status_code,
        **_ctx(request, project_key),
        active_page="images",
        images=listing["items"],
        linked_counts=linked_counts,
        used_text=human_size(listing["total_bytes"]),
        limit_text=human_size(config.max_project_bytes),
        max_file_text=human_size(config.max_file_bytes),
        uploaded=uploaded or [],
        deleted=deleted,
        errors=errors or [],
        human_size=human_size,
    )


@router.get("/{project_key}/images")
async def images_page(project_key: str, request: Request, deleted: str | None = None):
    return await _page(request, project_key, deleted=deleted)


@router.post("/{project_key}/images")
async def upload_images(project_key: str, request: Request,
                        files: list[UploadFile | str] | None = None):
    t = _ctx(request, project_key)["t"]
    # an empty file box is sent as an empty text part, not as a file
    chosen = [f for f in (files or []) if not isinstance(f, str) and f.filename]
    if not chosen:
        return await _page(request, project_key, status_code=422, errors=[t("images.no_file")])

    limit = request.app.state.images_config.max_file_bytes
    service = _service(request)
    uploaded: list[str] = []
    errors: list[str] = []
    for file in chosen:
        data = await file.read(limit + 1)  # one byte more than allowed is enough to refuse it
        try:
            entry = service.upload(project_key, file.filename, data, actor=ACTOR)
            uploaded.append(f"{entry['id']} ({entry['name']})")
        except IssueDeckError as exc:
            errors.append(t("images.refused", name=file.filename, message=exc.message))
    return await _page(request, project_key, status_code=200 if uploaded else 422,
                       uploaded=uploaded, errors=errors)


@router.get("/{project_key}/images/{image_id}/file")
async def image_file(project_key: str, image_id: str, request: Request,
                     download: bool = False):
    entry, data = _service(request).content(project_key, image_id)
    return content_response(request, entry, data, download)


@router.post("/{project_key}/images/{image_id}/delete")
async def delete_image(project_key: str, image_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.delete_image(project_key, image_id, actor=ACTOR)  # and the links to it
    finally:
        await session.close()
    return RedirectResponse(
        url=f"/dashboard/{project_key}/images?deleted={image_id}", status_code=303,
    )


def _item_page(project_key: str, local_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/dashboard/{project_key}/items/{local_id}", status_code=303)


@router.post("/{project_key}/items/{local_id}/images")
async def link_image(project_key: str, local_id: str, request: Request,
                     image_id: str = Form(...)):
    links, session = link_service(request)
    try:
        await links.link(project_key, local_id, image_id, actor=ACTOR)
    finally:
        await session.close()
    return _item_page(project_key, local_id)


@router.post("/{project_key}/items/{local_id}/images/{image_id}/unlink")
async def unlink_image(project_key: str, local_id: str, image_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.unlink(project_key, local_id, image_id, actor=ACTOR)
    finally:
        await session.close()
    return _item_page(project_key, local_id)

