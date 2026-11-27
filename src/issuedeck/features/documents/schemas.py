"""Request and response models of the document API (FEA-0012)."""

from __future__ import annotations

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    name: str
    kind: str
    title: str
    revision: int
    sha256: str
    size: int
    created_at: str
    updated_at: str
    actor: str


class DocumentDetail(DocumentOut):
    body: str


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]


class CreateDocumentRequest(BaseModel):
    name: str
    body: str
    kind: str = "other"
    title: str = ""
    replace: bool = False  # a name that is used makes a new revision instead of a 409


class ReplaceDocumentRequest(BaseModel):
    body: str
    revision: int  # the revision the caller read; a different current one gives 409
    title: str | None = None
    kind: str | None = None


class AppendDocumentRequest(BaseModel):
    text: str


class LinkDocumentRequest(BaseModel):
    document_id: str


class RevisionOut(BaseModel):
    revision: int
    sha256: str
    size: int
    time: str
    actor: str
    current: bool


class RevisionDetail(RevisionOut):
    body: str


class RevisionListResponse(BaseModel):
    items: list[RevisionOut]
