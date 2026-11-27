"""Request and response of the advanced search (FEA-0010)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from issuedeck.features.items.schemas import ItemListResponse


class SearchRequest(BaseModel):
    """A search as data (see ``features/search/query.py``), with the usual paging."""

    query: dict[str, Any]
    limit: int = Field(default=50, ge=1, le=500)
    after: str | None = None


class SearchResponse(ItemListResponse):
    #: the search in words, with explicit brackets
    description: str
    #: true when a regular expression did not finish or looked at fewer items than there are
    partial: bool = False
    notes: list[str] = Field(default_factory=list)
