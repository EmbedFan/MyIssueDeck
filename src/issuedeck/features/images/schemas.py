"""Response models of the image API (FEA-0013)."""

from __future__ import annotations

from pydantic import BaseModel


class ImageOut(BaseModel):
    id: str
    name: str
    mime: str
    size: int
    sha256: str
    uploaded_at: str
    actor: str


class ImageListResponse(BaseModel):
    items: list[ImageOut]
    total_bytes: int


class LinkImageRequest(BaseModel):
    image_id: str
