"""FastAPI router for the project image store (FEA-0013)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request, Response, UploadFile, status

from issuedeck.features.images.link_repo import ItemImageRepo
from issuedeck.features.images.link_service import ItemImageService
from issuedeck.features.images.schemas import (
    ImageListResponse,
    ImageOut,
    LinkImageRequest,
)
from issuedeck.features.images.service import ImageService
from issuedeck.features.items.repo import ItemRepo

router = APIRouter(prefix="/api/v1/projects/{project_key}/images", tags=["images"])
item_router = APIRouter(
    prefix="/api/v1/projects/{project_key}/items/{local_id}/images", tags=["images"],
)

# A file opened in its own browser tab must not be able to run script, whatever it holds.
IMAGE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "Cache-Control": "private, no-cache",
}


def _service(request: Request) -> ImageService:
    return ImageService(
        request.app.state.images_dir, request.app.state.images_config,
        request.app.state.registry,
    )


def link_service(request: Request) -> tuple[ItemImageService, object]:
    """The service that links images to items, and its database session (close it after use)."""
    session = request.app.state.session_factory()
    service = ItemImageService(
        _service(request), ItemRepo(session), ItemImageRepo(session),
        request.app.state.registry, session,
    )
    return service, session


def content_response(request: Request, entry: dict, data: bytes, download: bool) -> Response:
    """The image itself: SVG type, nosniff, sandboxing CSP, ETag from the SHA-256."""
    etag = f'"{entry["sha256"]}"'
    headers = {**IMAGE_HEADERS, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="{entry["stored"]}"; '
            f"filename*=UTF-8''{quote(entry['name'], safe='')}"
        )
    return Response(content=data, media_type=entry["mime"], headers=headers)


@router.post("", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(project_key: str, request: Request, file: UploadFile):
    limit = request.app.state.images_config.max_file_bytes
    data = await file.read(limit + 1)  # one byte more than allowed is enough to refuse it
    return _service(request).upload(project_key, file.filename, data)


@router.get("", response_model=ImageListResponse)
async def list_images(project_key: str, request: Request):
    return _service(request).list(project_key)


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(project_key: str, image_id: str, request: Request):
    return _service(request).get(project_key, image_id)


@router.get("/{image_id}/content")
async def get_image_content(project_key: str, image_id: str, request: Request,
                            download: bool = False):
    entry, data = _service(request).content(project_key, image_id)
    return content_response(request, entry, data, download)


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(project_key: str, image_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.delete_image(project_key, image_id)  # also removes the links to it
    finally:
        await session.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@item_router.get("", response_model=ImageListResponse)
async def list_item_images(project_key: str, local_id: str, request: Request):
    links, session = link_service(request)
    try:
        images = await links.list(project_key, local_id)
    finally:
        await session.close()
    return {"items": images, "total_bytes": sum(entry["size"] for entry in images)}


@item_router.post("", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def link_image(project_key: str, local_id: str, req: LinkImageRequest, request: Request):
    links, session = link_service(request)
    try:
        return await links.link(project_key, local_id, req.image_id)
    finally:
        await session.close()


@item_router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_image(project_key: str, local_id: str, image_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.unlink(project_key, local_id, image_id)
    finally:
        await session.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
