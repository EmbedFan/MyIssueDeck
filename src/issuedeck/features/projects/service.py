"""ProjectService — reads project config from ConfigRegistry, item counts from DB."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import (
    ConfigError,
    ProjectDeletionBlocked,
    ProjectDeletionNotConfirmed,
)
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.items.models import Item
from issuedeck.features.items.repo import ItemRepo
from issuedeck.features.projects.repo import ProjectDeletionPreview, ProjectRepo
from issuedeck.features.projects.schemas import (
    ProjectDetail,
    ProjectList,
    ProjectSummary,
    TimeSummary,
)

DELETED_BACKUP_DIR = "deleted-projects"
DELETED_CONFIG_DIR = ".deleted"


@dataclass(frozen=True)
class ProjectDeletionResult:
    project_key: str
    items_deleted: int
    backup_path: Path
    archived_config_path: Path | None


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

    async def deletion_preview(self, key: str) -> ProjectDeletionPreview:
        self._r.project(key)  # raises ProjectNotFound
        return await ProjectRepo(self._s).deletion_preview(key)

    async def delete_project(self, key: str, *, confirm_key: str) -> ProjectDeletionResult:
        """Delete a project: its data, then its config (archived, not erased).

        Safety rules:
        - the caller must pass the exact project key as confirmation;
        - nothing is deleted while a work session is active or paused;
        - an audit-bundle backup is written first, and the delete is aborted if
          the backup fails;
        - the database rows go in one transaction, before the config file moves,
          so a failure can never leave items without a project config (the
          server refuses to start in that state).
        """
        self._r.project(key)  # raises ProjectNotFound
        if confirm_key != key:
            raise ProjectDeletionNotConfirmed(
                "the confirmation does not match the project key",
                details={"project_key": key},
            )

        repo = ProjectRepo(self._s)
        preview = await repo.deletion_preview(key)
        if preview.active_work_sessions:
            raise ProjectDeletionBlocked(
                f"project '{key}' has {preview.active_work_sessions} active or paused "
                "work session(s); finish them before deleting the project",
                details={
                    "project_key": key,
                    "active_work_sessions": preview.active_work_sessions,
                },
            )

        server = self._r.server
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = server.data_dir / DELETED_BACKUP_DIR / f"{key}-{stamp}-audit-bundle.zip"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        await export_audit_bundle(
            session=self._s, registry=self._r, project_key=key, out_path=backup_path,
        )

        try:
            await repo.delete_project_rows(key)
            await self._s.commit()
        except Exception:
            await self._s.rollback()
            raise

        self._r.unregister_project(key)

        # FEA-0013: the image files go too (the backup above holds them), so that a project
        # created later under the same key does not find the images of the deleted one
        shutil.rmtree(server.data_dir / "images" / key, ignore_errors=True)
        # FEA-0012: and its documents (the backup above holds them too)
        shutil.rmtree(server.data_dir / "documents" / key, ignore_errors=True)
        # FEA-0010: and its saved searches (the backup above holds them too)
        (server.data_dir / "searches" / f"{key}.json").unlink(missing_ok=True)

        archived: Path | None = None
        config_path = server.projects_dir / f"{key}.toml"
        if config_path.exists():
            archived = server.projects_dir / DELETED_CONFIG_DIR / f"{key}-{stamp}.toml"
            try:
                archived.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(config_path), str(archived))
            except OSError as exc:
                raise ConfigError(
                    f"project '{key}' data was deleted (backup: {backup_path}) but its "
                    f"config file could not be archived: {exc}",
                    details={"project_key": key, "backup_path": str(backup_path)},
                ) from exc

        return ProjectDeletionResult(
            project_key=key,
            items_deleted=preview.items + preview.deleted_items,
            backup_path=backup_path,
            archived_config_path=archived,
        )

    def get_project(self, key: str) -> ProjectDetail:
        pc = self._r.project(key)  # raises ProjectNotFound
        return ProjectDetail(
            key=pc.key, name=pc.name, description=pc.description,
            kinds=pc.kinds, statuses=pc.statuses, branches=pc.branches,
        )
