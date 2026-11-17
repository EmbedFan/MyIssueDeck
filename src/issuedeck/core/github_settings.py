"""Checks for the GitHub export settings (FEA-0008).

Kept apart from ``runtime_settings`` so that the settings validators and the GitHub client
read a repository, a branch or a folder in exactly the same way.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from issuedeck.core.errors import InvalidSetting

DEFAULT_REPOSITORY = "https://github.com/EmbedFan/MyIssueDeckExports.git"
DEFAULT_TOKEN_ENV = "GITHUB_PAT"

_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
_NAME = r"[A-Za-z0-9._-]{1,100}"
_REPO_RE = re.compile(
    rf"^(?:https://)?(?:www\.)?(?:github\.com/)?(?P<owner>{_OWNER})/(?P<name>{_NAME}?)/?$",
)
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def parse_repository(value: object) -> tuple[str, str]:
    """``owner/name`` or a github.com URL (with or without ``.git``) to (owner, name)."""
    text = value.strip() if isinstance(value, str) else ""
    if text.endswith(".git"):
        text = text[: -len(".git")]
    match = _REPO_RE.fullmatch(text)
    if not match or match["name"] in {".", ".."}:
        raise InvalidSetting(
            "repository must be owner/name or a https://github.com/owner/name URL",
            details={"field": "repository"},
        )
    return match["owner"], match["name"]


def clean_branch(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    bad = (
        not _BRANCH_RE.fullmatch(text) or ".." in text or "//" in text
        or text.endswith(("/", ".", ".lock"))
    )
    if bad:
        raise InvalidSetting("branch is not a valid branch name", details={"field": "branch"})
    return text


def clean_folder(value: object) -> str:
    """A relative folder inside the repository; empty means the top level."""
    text = value.strip() if isinstance(value, str) else ""
    text = text.strip("/")
    if not text:
        return ""
    segments = text.split("/")
    if len(text) > 200 or any(
        not _SEGMENT_RE.fullmatch(seg) or seg in {".", ".."} for seg in segments
    ):
        raise InvalidSetting(
            "folder must be a relative path such as exports/issuedeck",
            details={"field": "folder"},
        )
    return "/".join(segments)


def clean_token_env(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not _ENV_RE.fullmatch(text):
        raise InvalidSetting(
            "token variable must be an environment variable name (letters, digits, _)",
            details={"field": "token_env"},
        )
    return text


def clean_author_name(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > 100 or any(ord(c) < 32 or c in "<>" for c in text):
        raise InvalidSetting(
            "commit author name must be 1 to 100 characters, without < or >",
            details={"field": "author_name"},
        )
    return text


def clean_author_email(value: object) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if len(text) > 200 or not _EMAIL_RE.fullmatch(text):
        raise InvalidSetting(
            "commit author e-mail address is not valid", details={"field": "author_email"},
        )
    return text


def validate_github(
    group: dict[str, Any], *, bool_check: Callable[[object, str], bool],
) -> dict[str, Any]:
    """Check a complete ``github`` group and return it normalised."""
    parse_repository(group.get("repository"))
    return {
        "repository": str(group["repository"]).strip(),
        "branch": clean_branch(group.get("branch")),
        "folder": clean_folder(group.get("folder")),
        "token_env": clean_token_env(group.get("token_env")),
        "allow_public": bool_check(group.get("allow_public"), "allow a public repository"),
        "author_name": clean_author_name(group.get("author_name")),
        "author_email": clean_author_email(group.get("author_email")),
    }
