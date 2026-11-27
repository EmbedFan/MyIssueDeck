"""FastAPI router for the project document store (FEA-0012)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request, Response, status

from issuedeck.features.documents.link_repo import ItemDocumentRepo
from issuedeck.features.documents.link_service import ItemDocumentService
from issuedeck.features.documents.schemas import (
    AppendDocumentRequest,
    CreateDocumentRequest,
    DocumentDetail,
    DocumentListResponse,
    DocumentOut,
    LinkDocumentRequest,
    ReplaceDocumentRequest,
    RevisionDetail,
    RevisionListResponse,
)
from issuedeck.features.documents.service import DocumentService, detail
from issuedeck.features.items.repo import ItemRepo

router = APIRouter(prefix="/api/v1/projects/{project_key}/documents", tags=["documents"])
item_router = APIRouter(
    prefix="/api/v1/projects/{project_key}/items/{local_id}/documents", tags=["documents"],
)

# A document is text for people and agents; it is never something a browser should run.
CONTENT_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cache-Control": "private, no-cache",
}


def _service(request: Request) -> DocumentService:
    return DocumentService(request.app.state.documents_dir, request.app.state.registry)


def link_service(request: Request) -> tuple[ItemDocumentService, object]:
    """The service that links documents to items, and its database session (close it after)."""
    session = request.app.state.session_factory()
    service = ItemDocumentService(
        _service(request), ItemRepo(session), ItemDocumentRepo(session),
        request.app.state.registry, session,
    )
    return service, session


def content_response(request: Request, document: dict, *, download: bool,
                     body: str | None = None, revision: int | None = None) -> Response:
    """The text of a document (or of one of its revisions) as a Markdown response."""
    text = document["body"] if body is None else body
    etag = f'"{document["sha256"] if body is None else revision}-{document["id"]}"'
    headers = {**CONTENT_HEADERS, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="{document["id"]}.md"; '
            f"filename*=UTF-8''{quote(document['name'], safe='')}"
        )
    return Response(content=text.encode("utf-8"), media_type="text/markdown; charset=utf-8",
                    headers=headers)


@router.post("", response_model=DocumentDetail, status_code=status.HTTP_201_CREATED)
async def create_document(project_key: str, req: CreateDocumentRequest, request: Request):
    document = _service(request).create(
        project_key, req.name, req.body, kind=req.kind, title=req.title, replace=req.replace,
    )
    return detail(document)


@router.get("", response_model=DocumentListResponse)
async def list_documents(project_key: str, request: Request,
                         kind: str | None = None, name: str | None = None):
    return {"items": _service(request).list(project_key, kind=kind, name=name)}


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(project_key: str, document_id: str, request: Request):
    return detail(_service(request).get(project_key, document_id))


@router.put("/{document_id}", response_model=DocumentDetail)
async def replace_document(project_key: str, document_id: str, req: ReplaceDocumentRequest,
                           request: Request):
    document = _service(request).replace(
        project_key, document_id, req.body, revision=req.revision, title=req.title,
        kind=req.kind,
    )
    return detail(document)


@router.patch("/{document_id}", response_model=DocumentDetail)
async def append_to_document(project_key: str, document_id: str, req: AppendDocumentRequest,
                             request: Request):
    return detail(_service(request).append(project_key, document_id, req.text))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(project_key: str, document_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.delete_document(project_key, document_id)  # also removes the links to it
    finally:
        await session.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{document_id}/content")
async def get_document_content(project_key: str, document_id: str, request: Request,
                               download: bool = False):
    document = _service(request).get(project_key, document_id)
    return content_response(request, document, download=download)


@router.get("/{document_id}/revisions", response_model=RevisionListResponse)
async def list_revisions(project_key: str, document_id: str, request: Request):
    return {"items": _service(request).revisions(project_key, document_id)}


@router.get("/{document_id}/revisions/{number}", response_model=RevisionDetail)
async def get_revision(project_key: str, document_id: str, number: int, request: Request):
    return _service(request).revision(project_key, document_id, number)


@router.post("/{document_id}/restore/{number}", response_model=DocumentDetail)
async def restore_revision(project_key: str, document_id: str, number: int, request: Request):
    return detail(_service(request).restore(project_key, document_id, number))



@item_router.get("", response_model=DocumentListResponse)
async def list_item_documents(project_key: str, local_id: str, request: Request):
    links, session = link_service(request)
    try:
        return {"items": await links.list(project_key, local_id)}
    finally:
        await session.close()


@item_router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def link_document(project_key: str, local_id: str, req: LinkDocumentRequest,
                        request: Request):
    links, session = link_service(request)
    try:
        return await links.link(project_key, local_id, req.document_id)
    finally:
        await session.close()


@item_router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_document(project_key: str, local_id: str, document_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.unlink(project_key, local_id, document_id)
    finally:
        await session.close()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
