"""FastAPI router for search."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from issuedeck.features.items.schemas import ItemListResponse
from issuedeck.features.search.repo import SearchRepo
from issuedeck.features.search.schemas import SearchRequest, SearchResponse
from issuedeck.features.search.service import SearchService

router = APIRouter(prefix="/api/v1/projects/{project_key}", tags=["search"])


@router.get("/search", response_model=ItemListResponse)
async def search_items(
    project_key: str, request: Request,
    q: str = Query(min_length=1),
    limit: int = 50,
    after: str | None = None,
):
    session = request.app.state.session_factory()
    try:
        svc = SearchService(SearchRepo(session), request.app.state.registry, session)
        return await svc.search(project_key, q, limit=limit, after=after)
    finally:
        await session.close()


@router.post("/search", response_model=SearchResponse)
async def search_items_advanced(project_key: str, req: SearchRequest, request: Request):
    """The advanced search: a query tree (blocks, AND/OR, groups) instead of a text.

    It only reads, so a token with the ``read`` scope may use it although it is a POST.
    """
    session = request.app.state.session_factory()
    try:
        svc = SearchService(SearchRepo(session), request.app.state.registry, session)
        return await svc.search_query(project_key, req.query, limit=req.limit, after=req.after)
    finally:
        await session.close()
