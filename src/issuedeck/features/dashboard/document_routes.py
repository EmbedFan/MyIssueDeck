"""Dashboard pages of the project document store (FEA-0012, phase 2).

A list with an upload form (several Markdown files at once), a page that shows a document as
Markdown, an edit page with a preview, a history with restore, downloads and a delete. The
pages use the same service as the API (``features/documents``). Uploading is the user's own
act: the software never looks into any folder, it only takes the files that are sent to it.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from issuedeck.core.errors import DocumentConflict, IssueDeckError
from issuedeck.features.dashboard.helpers import render
from issuedeck.features.dashboard.image_routes import human_size
from issuedeck.features.dashboard.routes import _ctx
from issuedeck.features.documents.routes import content_response, link_service
from issuedeck.features.documents.service import KINDS, DocumentService, detail, summary
from issuedeck.features.documents.text import clean_name, decode_upload

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

ACTOR = "dashboard"


def _service(request: Request) -> DocumentService:
    return DocumentService(request.app.state.documents_dir, request.app.state.registry)


def _render(request: Request, project_key: str, template: str, *, status_code: int = 200,
            **context):
    return render(
        template, request, status_code=status_code,
        **_ctx(request, project_key),
        active_page="documents", kinds=KINDS, human_size=human_size, **context,
    )


async def _list_page(request: Request, project_key: str, *, status_code: int = 200,
               stored: list[str] | None = None, deleted: str | None = None,
               errors: list[str] | None = None):
    documents = _service(request).list(project_key)
    links, session = link_service(request)
    try:
        linked_counts = await links.counts(project_key)
    finally:
        await session.close()
    return _render(
        request, project_key, "pages/documents.html", status_code=status_code,
        documents=documents, names=[d["name"] for d in documents], linked_counts=linked_counts,
        stored=stored or [], deleted=deleted, errors=errors or [],
    )


@router.get("/{project_key}/documents")
async def documents_page(project_key: str, request: Request, deleted: str | None = None):
    return await _list_page(request, project_key, deleted=deleted)


@router.post("/{project_key}/documents")
async def upload_documents(project_key: str, request: Request,
                           files: list[UploadFile | str] | None = None,
                           kind: str = Form("other"), replace: str = Form("")):
    t = _ctx(request, project_key)["t"]
    chosen = [f for f in (files or []) if not isinstance(f, str) and f.filename]
    if not chosen:
        return await _list_page(
            request, project_key, status_code=422, errors=[t("documents.no_file")])

    service = _service(request)
    stored: list[str] = []
    errors: list[str] = []
    for file in chosen:
        try:
            name = clean_name(file.filename)
            text = decode_upload(await file.read())
            if service.list(project_key, name=name) and not replace:
                errors.append(t("documents.exists", name=name))
                continue
            document = service.create(
                project_key, name, text, kind=kind, replace=bool(replace), actor=ACTOR,
            )
            stored.append(f"{document['id']} {name} (r{document['revision']})")
        except IssueDeckError as exc:
            errors.append(t("documents.refused", name=file.filename, message=exc.message))
    return await _list_page(request, project_key, status_code=200 if stored else 422,
                            stored=stored, errors=errors)


@router.get("/{project_key}/documents/{document_id}")
async def document_page(project_key: str, document_id: str, request: Request):
    document = _service(request).get(project_key, document_id)
    links, session = link_service(request)
    try:
        linked_items = await links.items_of(project_key, document_id)
    finally:
        await session.close()
    return _render(request, project_key, "pages/document_view.html", document=detail(document),
                   revision=None, linked_items=linked_items)


@router.get("/{project_key}/documents/{document_id}/revisions/{number}")
async def revision_page(project_key: str, document_id: str, number: int, request: Request):
    service = _service(request)
    document = service.get(project_key, document_id)
    revision = service.revision(project_key, document_id, number)
    return _render(request, project_key, "pages/document_view.html", document=detail(document),
                   revision=revision, linked_items=[])


@router.get("/{project_key}/documents/{document_id}/history")
async def history_page(project_key: str, document_id: str, request: Request):
    service = _service(request)
    document = service.get(project_key, document_id)
    return _render(request, project_key, "pages/document_history.html",
                   document=summary(document),
                   revisions=service.revisions(project_key, document_id))


@router.get("/{project_key}/documents/{document_id}/edit")
async def edit_page(project_key: str, document_id: str, request: Request):
    document = _service(request).get(project_key, document_id)
    return _render(request, project_key, "pages/document_edit.html", document=detail(document),
                   body=document["body"], conflict=None, error=None)


@router.post("/{project_key}/documents/{document_id}/edit")
async def edit_submit(project_key: str, document_id: str, request: Request,
                      body: str = Form(""), revision: int = Form(...),
                      title: str = Form(""), kind: str = Form("other")):
    service = _service(request)
    t = _ctx(request, project_key)["t"]
    try:
        service.replace(project_key, document_id, body, revision=revision, title=title,
                        kind=kind, actor=ACTOR)
    except DocumentConflict as exc:
        # keep what the user typed; saving again replaces the newer text, knowingly
        current = service.get(project_key, document_id)
        message = t("documents.conflict", name=current["name"], revision=current["revision"])
        return _render(request, project_key, "pages/document_edit.html", status_code=409,
                       document=detail(current), body=body, conflict=message, error=exc.message)
    except IssueDeckError as exc:
        current = service.get(project_key, document_id)
        return _render(request, project_key, "pages/document_edit.html", status_code=422,
                       document=detail(current), body=body, conflict=None, error=exc.message)
    return RedirectResponse(url=f"/dashboard/{project_key}/documents/{document_id}",
                            status_code=303)


@router.post("/{project_key}/documents/{document_id}/restore/{number}")
async def restore_revision(project_key: str, document_id: str, number: int, request: Request):
    _service(request).restore(project_key, document_id, number, actor=ACTOR)
    return RedirectResponse(url=f"/dashboard/{project_key}/documents/{document_id}",
                            status_code=303)


@router.get("/{project_key}/documents/{document_id}/file")
async def document_file(project_key: str, document_id: str, request: Request,
                        download: bool = False):
    document = _service(request).get(project_key, document_id)
    return content_response(request, document, download=download)


@router.get("/{project_key}/documents/{document_id}/revisions/{number}/file")
async def revision_file(project_key: str, document_id: str, number: int, request: Request,
                        download: bool = False):
    service = _service(request)
    document = service.get(project_key, document_id)
    revision = service.revision(project_key, document_id, number)
    return content_response(request, document, download=download, body=revision["body"],
                            revision=number)


@router.post("/{project_key}/documents/{document_id}/delete")
async def delete_document(project_key: str, document_id: str, request: Request):
    document = _service(request).get(project_key, document_id)
    links, session = link_service(request)
    try:
        await links.delete_document(project_key, document_id, actor=ACTOR)  # and its links
    finally:
        await session.close()
    label = f"{document_id} {document['name']}"
    return RedirectResponse(url=f"/dashboard/{project_key}/documents?deleted={quote(label)}",
                            status_code=303)


def _item_page(project_key: str, local_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/dashboard/{project_key}/items/{local_id}", status_code=303)


@router.post("/{project_key}/items/{local_id}/documents")
async def link_document(project_key: str, local_id: str, request: Request,
                        document_id: str = Form(...)):
    links, session = link_service(request)
    try:
        await links.link(project_key, local_id, document_id, actor=ACTOR)
    finally:
        await session.close()
    return _item_page(project_key, local_id)


@router.post("/{project_key}/items/{local_id}/documents/{document_id}/unlink")
async def unlink_document(project_key: str, local_id: str, document_id: str, request: Request):
    links, session = link_service(request)
    try:
        await links.unlink(project_key, local_id, document_id, actor=ACTOR)
    finally:
        await session.close()
    return _item_page(project_key, local_id)
