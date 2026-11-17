"""A small GitHub REST API client for exporting and importing projects (FEA-0008).

Only what is needed: read a repository, a branch and its files, and write several files as
one commit through the Git Data API (blobs, tree, commit, fast-forward reference update).
No local clone and no Git executable are involved.

Rules kept here:

* TLS certificates are always verified, against the certificate store of the operating
  system (so a company proxy that re-signs traffic with a trusted certificate works).
* The token goes only into the ``Authorization`` header. It is never put in a URL, a log line
  or an error message; every text that leaves this module is scrubbed of it.
* A reference is never forced: when the branch moved meanwhile, the update is refused.
* Rate-limit information is honoured: a short wait is made once, otherwise the error says
  when the limit is lifted.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ssl
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from issuedeck.core.errors import GitHubError

API_URL = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "MyIssueDesk-github-sync"


def git_blob_sha(data: bytes) -> str:
    """The SHA-1 Git gives a file's content, to compare with what the repository holds."""
    header = b"blob " + str(len(data)).encode("ascii") + b"\x00"
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - the Git object format


@dataclass(frozen=True)
class RepoInfo:
    owner: str
    name: str
    private: bool
    can_push: bool
    default_branch: str


@dataclass(frozen=True)
class CommitInfo:
    sha: str
    tree_sha: str


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int
    type: str


def tls_context() -> ssl.SSLContext:
    """A verifying TLS context that trusts the operating system's certificate store.

    httpx alone would use its bundled list of authorities and fail behind a network that
    re-signs TLS traffic with a certificate the system trusts. Verification stays fully on.
    """
    return ssl.create_default_context()


class GitHubClient:
    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        api_url: str = API_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        max_wait: float = 30.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._token = token
        self.owner = owner
        self.repo = repo
        self._max_wait = max_wait
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            transport=transport,
            timeout=httpx.Timeout(30.0),
            verify=tls_context(),  # verification is never switched off
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {token}",
            },
        )

    async def __aenter__(self) -> GitHubClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------ plumbing

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _error(self, kind: str, message: str, **details: Any) -> GitHubError:
        return GitHubError(self._scrub(message), details={"kind": kind, **details})

    @property
    def _repo_path(self) -> str:
        return f"/repos/{self.owner}/{self.repo}"

    async def _request(
        self, method: str, path: str, *, what: str, json: Any = None,
        params: dict[str, Any] | None = None, _retried: bool = False,
    ) -> Any:
        try:
            response = await self._http.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise self._error(
                "network", f"could not reach GitHub ({type(exc).__name__})",
            ) from None

        status = response.status_code
        if status < 400:
            return response.json() if response.content else None

        message = _github_message(response)
        if status == 401:
            raise self._error(
                "auth", "GitHub did not accept the token (it is invalid, expired or revoked)",
            )
        if status in (403, 429):
            wait, reset_at = _rate_limit(response)
            if wait is not None:
                if wait <= self._max_wait and not _retried:
                    await self._sleep(max(wait, 0.0))
                    return await self._request(
                        method, path, what=what, json=json, params=params, _retried=True,
                    )
                until = f" after {reset_at}" if reset_at else " later"
                raise self._error(
                    "rate_limit", f"the GitHub rate limit is reached; try again{until}",
                    reset_at=reset_at,
                )
            needed = response.headers.get("x-accepted-github-permissions", "")
            raise self._error(
                "permission",
                f"GitHub refused this ({message or 'forbidden'}). The token needs write access "
                f"to the repository contents ({needed or 'contents=write'}); for a fine-grained "
                "token, give it the permission 'Contents: Read and write' on this repository",
            )
        if status == 404:
            raise self._error(
                "not_found",
                f"GitHub cannot find {what}, or the token has no access to it",
            )
        if status >= 500:
            raise self._error("network", f"GitHub reported an error (HTTP {status})")
        raise self._error("invalid", f"GitHub refused the request: {message}", status=status)

    # ------------------------------------------------------------------ reading

    async def repository(self) -> RepoInfo:
        data = await self._request(
            "GET", self._repo_path, what=f"repository {self.owner}/{self.repo}",
        )
        return RepoInfo(
            owner=self.owner,
            name=self.repo,
            private=bool(data.get("private")),
            can_push=bool((data.get("permissions") or {}).get("push")),
            default_branch=str(data.get("default_branch") or "main"),
        )

    async def commit(self, ref: str, *, what: str | None = None) -> CommitInfo:
        """The commit a branch, tag or commit id points to."""
        data = await self._request(
            "GET", f"{self._repo_path}/commits/{ref}", what=what or f"revision '{ref}'",
        )
        return CommitInfo(sha=data["sha"], tree_sha=data["commit"]["tree"]["sha"])

    async def tree(self, tree_sha: str) -> list[TreeEntry]:
        data = await self._request(
            "GET", f"{self._repo_path}/git/trees/{tree_sha}", what="the repository tree",
            params={"recursive": "1"},
        )
        if data.get("truncated"):
            raise self._error(
                "too_large", "the repository is too large to list through the API",
            )
        return [
            TreeEntry(path=e["path"], sha=e["sha"], size=int(e.get("size") or 0), type=e["type"])
            for e in data.get("tree", [])
        ]

    async def blob(self, sha: str) -> bytes:
        data = await self._request(
            "GET", f"{self._repo_path}/git/blobs/{sha}", what="a file of the repository",
        )
        if data.get("encoding") != "base64":
            raise self._error("invalid", "GitHub returned a file in an unexpected encoding")
        return base64.b64decode(data["content"])

    # ------------------------------------------------------------------ writing

    async def create_blob(self, content: bytes) -> str:
        data = await self._request(
            "POST", f"{self._repo_path}/git/blobs", what="the repository",
            json={"content": base64.b64encode(content).decode("ascii"), "encoding": "base64"},
        )
        return str(data["sha"])

    async def create_tree(self, base_tree: str, files: dict[str, str]) -> str:
        """A tree that is ``base_tree`` plus the given files (path to blob sha)."""
        data = await self._request(
            "POST", f"{self._repo_path}/git/trees", what="the repository",
            json={
                "base_tree": base_tree,
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob", "sha": sha}
                    for path, sha in sorted(files.items())
                ],
            },
        )
        return str(data["sha"])

    async def create_commit(
        self, *, message: str, tree_sha: str, parent_sha: str,
        author_name: str, author_email: str,
    ) -> str:
        data = await self._request(
            "POST", f"{self._repo_path}/git/commits", what="the repository",
            json={
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha],
                "author": {
                    "name": author_name, "email": author_email,
                    "date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
        )
        return str(data["sha"])

    async def move_branch(self, branch: str, commit_sha: str) -> None:
        """Fast-forward the branch to the commit. Never forced."""
        try:
            await self._request(
                "PATCH", f"{self._repo_path}/git/refs/heads/{branch}",
                what=f"branch '{branch}'", json={"sha": commit_sha, "force": False},
            )
        except GitHubError as exc:
            if exc.details.get("kind") == "invalid" and exc.details.get("status") in (409, 422):
                raise self._error(
                    "conflict",
                    f"branch '{branch}' changed while the export was running; "
                    "nothing was published, run the export again",
                ) from None
            raise


def _github_message(response: httpx.Response) -> str:
    try:
        text = response.json().get("message", "")
    except (ValueError, AttributeError):
        text = ""
    return str(text)[:200]


def _rate_limit(response: httpx.Response) -> tuple[float | None, str | None]:
    """(seconds to wait, reset time) for a rate-limit answer, else (None, None)."""
    headers = response.headers
    message = _github_message(response).lower()
    limited = (
        response.status_code == 429
        or headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in headers
        or "rate limit" in message
    )
    if not limited:
        return None, None
    wait = 60.0
    reset_header = headers.get("x-ratelimit-reset", "")
    if "retry-after" in headers:
        try:
            wait = float(headers["retry-after"])
        except ValueError:
            wait = 60.0
    elif reset_header.isdigit():
        wait = max(int(reset_header) - time.time(), 0.0)
    reset_at = None
    if reset_header.isdigit():
        reset_at = datetime.fromtimestamp(int(reset_header), UTC).strftime("%H:%M:%S UTC")
    return wait, reset_at
