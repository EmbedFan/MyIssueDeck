"""Export a project to a GitHub repository and import it back (FEA-0008).

The export reuses the snapshot (audit bundle) files and stores them unpacked in the folder
``<folder>/<project-key>/`` of the repository, as one commit. The import reads that folder
back into a snapshot ZIP and hands it to the FEA-0007 importer, so validation, preview,
conflict policies and the all-or-nothing rule are the same as for a snapshot file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

import issuedeck
from issuedeck.core.config import ConfigRegistry
from issuedeck.core.errors import GitHubConfigError, GitHubError, SnapshotInvalid
from issuedeck.core.github_settings import parse_repository
from issuedeck.core.runtime_settings import RuntimeSettings
from issuedeck.features.export.md_bundle import export_audit_bundle
from issuedeck.features.export.snapshot_import import (
    MAX_UNCOMPRESSED_BYTES,
    ImportReport,
    import_snapshot,
)
from issuedeck.features.github_sync.client import GitHubClient, git_blob_sha

REQUIRED_FILES = (
    "manifest.json",
    "project.json",
    "items.json",
    "relationships.json",
    "work_sessions.json",
    "import_batches.json",
)
SNAPSHOT_FILES = (*REQUIRED_FILES, "project.toml")
_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

#: ``progress("step_key", **details)`` is called as the work moves on, so that a caller
#: (the dashboard) can show what is happening. It is optional and never changes the work.
Progress = Callable[..., None] | None


def _say(progress: Progress, step: str, /, **details: object) -> None:
    if progress is not None:
        progress(step, **details)


@dataclass(frozen=True)
class GitHubSettings:
    owner: str
    repo: str
    branch: str
    folder: str
    token_env: str
    allow_public: bool
    author_name: str
    author_email: str

    @classmethod
    def from_group(cls, group: Mapping[str, Any]) -> GitHubSettings:
        owner, repo = parse_repository(group["repository"])
        return cls(
            owner=owner, repo=repo, branch=group["branch"], folder=group["folder"],
            token_env=group["token_env"], allow_public=bool(group["allow_public"]),
            author_name=group["author_name"], author_email=group["author_email"],
        )

    @property
    def repository(self) -> str:
        return f"{self.owner}/{self.repo}"

    def prefix(self, project_key: str | None = None) -> str:
        parts = [p for p in (self.folder, project_key) if p]
        return "/".join(parts) + "/" if parts else ""


def read_token(token_env: str, environ: Mapping[str, str] | None = None) -> str:
    """The token from the configured environment variable (never logged or shown)."""
    token = (environ if environ is not None else os.environ).get(token_env, "").strip()
    if not token:
        raise GitHubConfigError(
            f"the environment variable {token_env} is not set; it must hold a GitHub token "
            "with read and write access to the repository contents (a running server reads its "
            "environment only when it starts, so stop and start the server again after setting "
            "the variable)",
            details={"token_env": token_env},
        )
    return token


def make_client(
    settings: GitHubSettings, *, environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GitHubClient:
    return GitHubClient(
        read_token(settings.token_env, environ), settings.owner, settings.repo,
        transport=transport,
    )


def _check_revision(revision: str | None) -> str | None:
    if revision is None or revision == "":
        return None
    if not _REVISION_RE.fullmatch(revision) or ".." in revision:
        raise GitHubConfigError(
            "the revision must be a branch, a tag or a commit id", details={"field": "revision"},
        )
    return revision


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

@dataclass
class ConnectionCheck:
    ok: bool = True
    private: bool | None = None
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append((name, ok, detail))
        self.ok = self.ok and ok


async def check_connection(
    settings: GitHubSettings, *, environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ConnectionCheck:
    """Check token, repository, branch, write access and privacy. Writes nothing."""
    result = ConnectionCheck()
    try:
        client = make_client(settings, environ=environ, transport=transport)
        result.add("token", True, f"found in {settings.token_env}")
    except GitHubConfigError as exc:
        result.add("token", False, exc.message)
        return result
    async with client:
        try:
            info = await client.repository()
        except GitHubError as exc:
            result.add("repository", False, exc.message)
            return result
        result.private = info.private
        result.add("repository", True, f"{settings.repository} found")
        result.add(
            "write access", info.can_push,
            "your account can push to the repository; a fine-grained token also needs the "
            "permission 'Contents: Read and write', which GitHub only reveals when writing"
            if info.can_push
            else "your account cannot push to the repository",
        )
        if info.private:
            result.add("privacy", True, "the repository is private")
        elif settings.allow_public:
            result.add("privacy", True, "the repository is public (allowed by the setting)")
        else:
            result.add(
                "privacy", False,
                "the repository is public; exports are refused unless "
                "'Allow a public repository' is on",
            )
        try:
            await client.commit(settings.branch, what=f"branch '{settings.branch}'")
            result.add("branch", True, f"branch {settings.branch} found")
        except GitHubError as exc:
            result.add("branch", False, exc.message)
    return result


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@dataclass
class ExportReport:
    project_key: str
    repository: str
    branch: str
    folder: str
    dry_run: bool
    items: int = 0
    files_total: int = 0
    files_changed: list[str] = field(default_factory=list)
    up_to_date: bool = False
    commit_sha: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


async def _snapshot_files(
    session: AsyncSession, registry: ConfigRegistry, project_key: str,
) -> tuple[dict[str, bytes], int]:
    with tempfile.TemporaryDirectory() as tmp:
        report = await export_audit_bundle(
            session=session, registry=registry, project_key=project_key,
            out_path=Path(tmp) / "snapshot.zip",
        )
        with zipfile.ZipFile(report.bundle_path) as bundle:
            files = {
                name: bundle.read(name) for name in SNAPSHOT_FILES if name in bundle.namelist()
            }
    return files, report.items_written


async def export_project(
    *,
    session: AsyncSession,
    registry: ConfigRegistry,
    project_key: str,
    settings: GitHubSettings,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    dry_run: bool = False,
    runtime: RuntimeSettings | None = None,
    actor: str = "cli",
    progress: Progress = None,
) -> ExportReport:
    """Write the project's snapshot files to the repository as one commit."""
    registry.project(project_key)  # ProjectNotFound before anything else
    client = make_client(settings, environ=environ, transport=transport)
    report = ExportReport(
        project_key=project_key, repository=settings.repository, branch=settings.branch,
        folder=settings.folder, dry_run=dry_run,
    )
    async with client:
        _say(progress, "connecting")
        info = await client.repository()
        if not info.private and not settings.allow_public:
            raise GitHubConfigError(
                f"{settings.repository} is a public repository and items can hold confidential "
                "text, so the export was refused; make the repository private or switch on "
                "'Allow a public repository' in the settings",
                details={"repository": settings.repository},
            )
        if not info.can_push:
            raise GitHubError(
                "your account cannot push to the repository, so it cannot be used for exports",
                details={"kind": "permission"},
            )

        _say(progress, "reading_repo")
        head = await client.commit(settings.branch, what=f"branch '{settings.branch}'")
        prefix = settings.prefix(project_key)
        remote = {
            entry.path: entry.sha
            for entry in await client.tree(head.tree_sha)
            if entry.type == "blob" and entry.path.startswith(prefix)
        }

        _say(progress, "building", project=project_key)
        files, report.items = await _snapshot_files(session, registry, project_key)
        report.files_total = len(files)
        _say(progress, "comparing", count=len(files))
        changed = [
            name for name, data in files.items()
            if remote.get(prefix + name) != git_blob_sha(data)
        ]
        report.files_changed = changed
        # The manifest carries the export time, so it differs every time; it alone is no change.
        if not [name for name in changed if name != "manifest.json"]:
            report.up_to_date = True
            report.files_changed = []
            return report
        if dry_run:
            return report

        blobs: dict[str, str] = {}
        for index, name in enumerate(changed, 1):
            _say(progress, "uploading", i=index, n=len(changed), file=name)
            blobs[prefix + name] = await client.create_blob(files[name])
        _say(progress, "committing")
        tree_sha = await client.create_tree(head.tree_sha, blobs)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        commit_sha = await client.create_commit(
            message=(
                f"Export {project_key}: {report.items} items, {len(changed)} files changed\n\n"
                f"Project: {project_key}\nItems: {report.items}\nExported at: {stamp}\n"
                f"Software: MyIssueDesk {issuedeck.__version__}\n"
            ),
            tree_sha=tree_sha, parent_sha=head.sha,
            author_name=settings.author_name, author_email=settings.author_email,
        )
        _say(progress, "publishing")
        await client.move_branch(settings.branch, commit_sha)
        report.commit_sha = commit_sha

    if runtime is not None:
        runtime.record("github.export", actor, {
            "project": project_key, "repository": settings.repository,
            "branch": settings.branch, "folder": settings.folder, "commit": report.commit_sha,
            "files_changed": len(report.files_changed), "items": report.items,
        })
    return report


# ---------------------------------------------------------------------------
# List and import
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RemoteProject:
    key: str
    items: int | None
    generated_at: str | None
    problem: str | None = None


async def list_projects(
    settings: GitHubSettings, *, revision: str | None = None,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    progress: Progress = None,
) -> list[RemoteProject]:
    """The projects found in the repository folder, with the data of their last export."""
    revision = _check_revision(revision) or settings.branch
    async with make_client(settings, environ=environ, transport=transport) as client:
        _say(progress, "connecting")
        head = await client.commit(revision)
        _say(progress, "reading_repo")
        prefix = settings.prefix()
        manifests: dict[str, str] = {}
        for entry in await client.tree(head.tree_sha):
            if entry.type != "blob" or not entry.path.startswith(prefix):
                continue
            parts = entry.path[len(prefix):].split("/")
            if len(parts) == 2 and parts[1] == "manifest.json":
                manifests[parts[0]] = entry.sha
        found: list[RemoteProject] = []
        for index, (key, sha) in enumerate(sorted(manifests.items()), 1):
            _say(progress, "reading_manifests", i=index, n=len(manifests), project=key)
            try:
                manifest = json.loads((await client.blob(sha)).decode("utf-8"))
                found.append(RemoteProject(
                    key=key, items=int((manifest.get("counts") or {}).get("items", 0)),
                    generated_at=manifest.get("generated_at"),
                ))
            except (ValueError, AttributeError, TypeError):
                found.append(RemoteProject(
                    key=key, items=None, generated_at=None,
                    problem="manifest.json is not valid",
                ))
        return found


async def fetch_snapshot(
    settings: GitHubSettings, project_key: str, dest: Path, *,
    revision: str | None = None, environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None, progress: Progress = None,
) -> str:
    """Write the repository folder of a project as a snapshot ZIP; returns the commit id."""
    revision = _check_revision(revision) or settings.branch
    prefix = settings.prefix(project_key)
    async with make_client(settings, environ=environ, transport=transport) as client:
        _say(progress, "connecting")
        head = await client.commit(revision)
        _say(progress, "reading_repo")
        wanted = {
            entry.path[len(prefix):]: entry
            for entry in await client.tree(head.tree_sha)
            if entry.type == "blob" and entry.path.startswith(prefix)
            and entry.path[len(prefix):] in SNAPSHOT_FILES
        }
        missing = [name for name in REQUIRED_FILES if name not in wanted]
        if missing:
            raise SnapshotInvalid(
                f"the folder '{prefix.rstrip('/')}' of {settings.repository} at {revision} "
                f"is not a project export; it lacks: {', '.join(missing)}",
            )
        if sum(entry.size for entry in wanted.values()) > MAX_UNCOMPRESSED_BYTES:
            raise GitHubError(
                "the exported project is larger than the allowed size",
                details={"kind": "too_large"},
            )
        contents: dict[str, bytes] = {}
        for index, (name, entry) in enumerate(sorted(wanted.items()), 1):
            _say(progress, "downloading", i=index, n=len(wanted), file=name)
            contents[name] = await client.blob(entry.sha)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in contents.items():
            bundle.writestr(name, data)
    return head.sha


async def import_project(
    *,
    session: AsyncSession,
    registry: ConfigRegistry,
    project_key: str,
    settings: GitHubSettings,
    mode: str,
    target_key: str | None = None,
    revision: str | None = None,
    conflict: str = "keep",
    apply: bool = False,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    runtime: RuntimeSettings | None = None,
    actor: str = "cli",
    progress: Progress = None,
) -> tuple[ImportReport, str]:
    """Fetch a project from the repository and import it with the FEA-0007 rules."""
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / f"{project_key}.zip"
        commit = await fetch_snapshot(
            settings, project_key, bundle, revision=revision, environ=environ,
            transport=transport, progress=progress,
        )
        _say(progress, "importing" if apply else "checking")
        report = await import_snapshot(
            session=session, registry=registry, bundle_path=bundle, mode=mode,
            project_key=target_key, conflict=conflict, apply=apply,
        )
    if apply and runtime is not None:
        runtime.record("github.import", actor, {
            "project": report.project_key, "source_project": project_key,
            "repository": settings.repository, "branch": settings.branch,
            "revision": revision or settings.branch, "commit": commit, "mode": mode,
            "conflict": conflict, "items_created": report.items_created,
            "items_updated": report.items_updated,
        })
    return report, commit
