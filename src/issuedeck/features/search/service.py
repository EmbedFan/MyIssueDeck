"""SearchService — FTS5 search for items."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import InvalidSearch
from issuedeck.core.pagination import decode_cursor, encode_cursor
from issuedeck.features.items.schemas import ItemListResponse, ItemSummary
from issuedeck.features.search.evaluator import run_query
from issuedeck.features.search.query import describe, parse_query
from issuedeck.features.search.repo import SearchRepo
from issuedeck.features.search.schemas import SearchResponse


def _preview(body: str, n: int = 200) -> str:
    return (body[:n] + "…") if len(body) > n else body


def _summary(i) -> ItemSummary:
    return ItemSummary(
        project_key=i.project_key, local_id=i.local_id,
        kind=i.kind, status=i.status, title=i.title,
        body_preview=_preview(i.body or ""),
        tags=[t.tag for t in i.tags],
        applies_to=[a.branch_key for a in i.applies_to],
        external_links=[
            {
                "id": link.id,
                "link_type": link.link_type,
                "label": link.label,
                "url": link.url,
                "created_at": link.created_at,
            }
            for link in i.external_links
        ],
        created_at=i.created_at, updated_at=i.updated_at,
        deleted_at=i.deleted_at,
    )


class SearchService:
    def __init__(
        self, repo: SearchRepo, registry: ConfigRegistry, session: AsyncSession,
    ):
        self._repo = repo
        self._reg = registry
        self._s = session

    async def search(
        self, project_key: str, query: str, *,
        limit: int = 50, after: str | None = None,
    ) -> ItemListResponse:
        self._reg.project(project_key)
        limit = max(1, min(limit, 500))

        after_ts, after_pk = (None, None)
        if after:
            c = decode_cursor(after)
            after_ts, after_pk = c.updated_at, c.pk

        rows = await self._repo.match(
            project_key, query, limit=limit + 1,
            after_updated_at=after_ts, after_pk=after_pk,
        )
        has_more = len(rows) > limit
        rows = rows[:limit]

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(last.updated_at, last.pk)

        summaries = [_summary(i) for i in rows]
        return ItemListResponse(items=summaries, next_cursor=next_cursor, limit=limit)

    async def search_query(
        self, project_key: str, data, *, limit: int = 50, after: str | None = None,
    ) -> SearchResponse:
        """The advanced search (FEA-0010): a query given as data, paged like the other lists."""
        project = self._reg.project(project_key)
        query = parse_query(data, list(project.kinds), list(project.statuses))
        limit = max(1, min(limit, 500))
        result = await run_query(self._s, project_key, query)

        pks = result.pks
        if after:
            try:
                cursor = decode_cursor(after)
            except ValueError as exc:
                raise InvalidSearch("after: the cursor is not valid",
                                    details={"path": "after"}) from exc
            pks = [pk for pk in pks if (result.updated[pk], pk) < (cursor.updated_at, cursor.pk)]
        page = pks[:limit]
        next_cursor = None
        if len(pks) > limit:
            next_cursor = encode_cursor(result.updated[page[-1]], page[-1])

        rows = await self._repo.items_by_pks(page)
        return SearchResponse(
            items=[_summary(i) for i in rows], next_cursor=next_cursor, limit=limit,
            description=describe(query), partial=result.partial, notes=result.notes,
        )
