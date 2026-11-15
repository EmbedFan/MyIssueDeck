"""ProjectService — reads project config from ConfigRegistry, item counts from DB."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.config import ConfigRegistry
from issuedeck.features.items.models import Item
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.projects.schemas import (
    ProjectDetail,
    ProjectList,
    ProjectSummary,
    TimeSummary,
)


class ProjectService:
    def __init__(self, registry: ConfigRegistry, session: AsyncSession):
        self._r = registry
        self._s = session

    async def list_projects(self) -> ProjectList:
        rows = (await self._s.execute(
            select(Item.project_key, func.count(Item.pk))
            .where(Item.deleted_at.is_(None))
            .group_by(Item.project_key)
        )).all()
        counts = {k: int(n) for k, n in rows}

        summaries = [
            ProjectSummary(
                key=p.key, name=p.name, description=p.description,
                item_count=counts.get(p.key, 0),
            )
            for p in self._r.all_projects()
        ]
        return ProjectList(projects=summaries)

    async def time_summary(self, key: str) -> TimeSummary:
        self._r.project(key)  # raises ProjectNotFound
        repo = ItemRepo(self._s)
        return TimeSummary(
            project_key=key,
            estimated_time=await repo.sum_custom_number(key, "estimated_time"),
            time_spent=await repo.sum_custom_number(key, "time_spent"),
        )

    def get_project(self, key: str) -> ProjectDetail:
        pc = self._r.project(key)  # raises ProjectNotFound
        return ProjectDetail(
            key=pc.key, name=pc.name, description=pc.description,
            kinds=pc.kinds, statuses=pc.statuses, branches=pc.branches,
        )
