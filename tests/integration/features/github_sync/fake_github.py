"""A local test double of the part of the GitHub REST API that FEA-0008 uses.

It keeps a small Git object store in memory (blobs, flat trees, commits, branches) and answers
through ``httpx.MockTransport``, so that no test needs a network or a real repository.
It checks the ``Authorization`` header, refuses non-fast-forward reference updates like GitHub
does, and can be told to fail, to rate-limit, or to change the branch behind the client's back.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

import httpx

from issuedeck.features.github_sync.client import git_blob_sha

TOKEN = "ghp_test_token_0123456789"


def _sha(payload: Any) -> str:
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()  # noqa: S324


class FakeGitHub:
    def __init__(
        self, owner: str = "octo", repo: str = "exports", *, private: bool = True,
        can_push: bool = True, branch: str = "main", token: str = TOKEN,
    ) -> None:
        self.owner, self.repo, self.branch = owner, repo, branch
        self.private, self.can_push, self.token = private, can_push, token
        self.blobs: dict[str, bytes] = {}
        self.trees: dict[str, dict[str, str]] = {}
        self.commits: dict[str, dict[str, Any]] = {}
        self.refs: dict[str, str] = {}
        self.tags: dict[str, str] = {}
        self.requests: list[dict[str, Any]] = []
        self.queued: list[tuple[str, httpx.Response]] = []
        self.before_ref_update: Callable[[], None] | None = None
        self.commit_files({"README.md": b"exports\n"}, "Initial commit", branch=branch)

    # ---------------------------------------------------------------- seeding and checks

    def _store_tree(self, files: dict[str, bytes], base: dict[str, str] | None = None) -> str:
        tree = dict(base or {})
        for path, content in files.items():
            sha = git_blob_sha(content)
            self.blobs[sha] = content
            tree[path] = sha
        tree_sha = _sha(tree)
        self.trees[tree_sha] = tree
        return tree_sha

    def commit_files(
        self, files: dict[str, bytes], message: str = "seed", *, branch: str | None = None,
    ) -> str:
        """Add files directly (as if someone else had pushed them)."""
        branch = branch or self.branch
        parent = self.refs.get(branch)
        base = self.trees[self.commits[parent]["tree"]] if parent else {}
        tree_sha = self._store_tree(files, base)
        commit = {"tree": tree_sha, "parents": [parent] if parent else [], "message": message,
                  "author": {"name": "seed", "email": "seed@example.com"}}
        sha = _sha(commit)
        self.commits[sha] = commit
        self.refs[branch] = sha
        return sha

    def files(self, branch: str | None = None) -> dict[str, bytes]:
        head = self.commits[self.refs[branch or self.branch]]
        return {path: self.blobs[sha] for path, sha in self.trees[head["tree"]].items()}

    def history(self, branch: str | None = None) -> list[str]:
        out, sha = [], self.refs[branch or self.branch]
        while sha:
            out.append(sha)
            parents = self.commits[sha]["parents"]
            sha = parents[0] if parents else None
        return out

    def queue(self, status: int, *, headers: dict[str, str] | None = None,
              body: Any = None, match: str = "") -> None:
        """Answer the next request whose path contains ``match`` with this response."""
        self.queued.append((match, httpx.Response(status, headers=headers or {}, json=body or {})))

    def calls(self, method: str, fragment: str = "") -> list[dict[str, Any]]:
        return [r for r in self.requests if r["method"] == method and fragment in r["path"]]

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    # ---------------------------------------------------------------- the API

    def _resolve(self, ref: str) -> str | None:
        if ref in self.refs:
            return self.refs[ref]
        if ref in self.tags:
            return self.tags[ref]
        return ref if ref in self.commits else None

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append({
            "method": request.method, "path": path, "url": str(request.url),
            "headers": dict(request.headers), "body": body,
        })
        for index, (match, response) in enumerate(self.queued):
            if match in path:
                del self.queued[index]
                return response
        if request.headers.get("authorization") != f"Bearer {self.token}":
            return httpx.Response(401, json={"message": "Bad credentials"})

        base = f"/repos/{self.owner}/{self.repo}"
        if not path.startswith(base):
            return httpx.Response(404, json={"message": "Not Found"})
        rest = path[len(base):]

        if rest == "" and request.method == "GET":
            return httpx.Response(200, json={
                "private": self.private, "default_branch": self.branch,
                "permissions": {"push": self.can_push},
            })
        match = re.fullmatch(r"/commits/(.+)", rest)
        if match and request.method == "GET":
            sha = self._resolve(match.group(1))
            if sha is None:
                return httpx.Response(404, json={"message": "No commit found for the ref"})
            return httpx.Response(200, json={
                "sha": sha, "commit": {"tree": {"sha": self.commits[sha]["tree"]}},
            })
        match = re.fullmatch(r"/git/trees/([0-9a-f]+)", rest)
        if match and request.method == "GET":
            tree = self.trees.get(match.group(1))
            if tree is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"sha": match.group(1), "truncated": False, "tree": [
                {"path": p, "type": "blob", "sha": s, "size": len(self.blobs[s])}
                for p, s in sorted(tree.items())
            ]})
        match = re.fullmatch(r"/git/blobs/([0-9a-f]+)", rest)
        if match and request.method == "GET":
            data = self.blobs.get(match.group(1))
            if data is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={
                "encoding": "base64", "size": len(data),
                "content": base64.b64encode(data).decode("ascii"),
            })
        if not self.can_push and request.method in ("POST", "PATCH"):
            return httpx.Response(
                403, headers={"x-accepted-github-permissions": "contents=write"},
                json={"message": "Resource not accessible by personal access token"})
        if rest == "/git/blobs" and request.method == "POST":
            data = base64.b64decode(body["content"])
            sha = git_blob_sha(data)
            self.blobs[sha] = data
            return httpx.Response(201, json={"sha": sha})
        if rest == "/git/trees" and request.method == "POST":
            tree = dict(self.trees[body["base_tree"]])
            for entry in body["tree"]:
                tree[entry["path"]] = entry["sha"]
            sha = _sha(tree)
            self.trees[sha] = tree
            return httpx.Response(201, json={"sha": sha})
        if rest == "/git/commits" and request.method == "POST":
            commit = {"tree": body["tree"], "parents": body["parents"],
                      "message": body["message"], "author": body["author"]}
            sha = _sha(commit)
            self.commits[sha] = commit
            return httpx.Response(201, json={"sha": sha})
        match = re.fullmatch(r"/git/refs/heads/(.+)", rest)
        if match and request.method == "PATCH":
            branch = match.group(1)
            if self.before_ref_update:
                hook, self.before_ref_update = self.before_ref_update, None
                hook()
            current = self.refs.get(branch)
            if current is None:
                return httpx.Response(404, json={"message": "Reference does not exist"})
            new = body["sha"]
            ancestors, sha = set(), new
            while sha:
                ancestors.add(sha)
                parents = self.commits[sha]["parents"]
                sha = parents[0] if parents else None
            if current not in ancestors:
                return httpx.Response(422, json={"message": "Update is not a fast forward"})
            self.refs[branch] = new
            return httpx.Response(200, json={"ref": f"refs/heads/{branch}"})
        return httpx.Response(404, json={"message": "Not Found"})
