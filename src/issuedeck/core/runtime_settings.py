"""Runtime settings and tokens that the dashboard can change without a restart (FEA-0004).

Stored in the data directory:
- ``settings.json``: theme colours, default language and theme, default estimated time.
- ``tokens.json``: runtime API tokens. Only the SHA-256 of each token is stored; the
  plaintext is returned once, when a token is created or regenerated.
- ``settings_audit.jsonl``: one line per change, without any secret values.

Config-file tokens (``server.toml``) are still read from the config and are not
editable here.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from issuedeck.core.auth import BearerTokenCredential, sha256_hex
from issuedeck.core.errors import InvalidSetting, TokenNotFound
from issuedeck.core.github_settings import (
    DEFAULT_REPOSITORY,
    DEFAULT_TOKEN_ENV,
    validate_github,
)

SETTINGS_FILE = "settings.json"
TOKENS_FILE = "tokens.json"
AUDIT_FILE = "settings_audit.jsonl"

TOKEN_SCOPES = ("read", "agent", "admin")
LANGUAGES = ("en", "zh-CN", "hu")
THEMES = ("light", "dark", "system")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": {
        "light": {"primary": "#0f766e", "accent": "#b45309"},
        "dark": {"primary": "#2dd4bf", "accent": "#f59e0b"},
    },
    "default_language": "en",
    "default_theme": "light",
    "default_estimated_time": 0.5,
    # FEA-0006, task 1: the "Active agent sessions" widget.
    "agent_widget": {
        "show_kanban": False,
        "show_overview": True,
        "statuses": ["active", "paused"],
        "completed_minutes": 0,
        "max_sessions": 8,
        "scope": "project",
        "initial_state": "expanded",
        "info": {
            "agent": True, "item": True, "goal": True, "last_update": True, "updates": True,
        },
    },
    # FEA-0006, task 2: live updates of the dashboard views.
    "live": {
        "enabled": True,
        "fallback_seconds": 30,
        "highlight_seconds": 3,
        "while_editing": "notice",
        "views": {"kanban": True, "list": True, "overview": True, "item": True},
        "events": {"items": True, "sessions": True, "activity": True},
        "indicator": True,
    },
    # FEA-0008: export of projects to a GitHub repository and import from it.
    "github": {
        "repository": DEFAULT_REPOSITORY,
        "branch": "main",
        "folder": "",
        "token_env": DEFAULT_TOKEN_ENV,
        "allow_public": False,
        "author_name": "MyIssueDesk",
        "author_email": "issuedeck@users.noreply.github.com",
    },
}

#: Settings groups that can be reset to their defaults as a unit.
RESETTABLE_GROUPS = ("theme", "agent_widget", "live", "github")

WIDGET_STATUSES = ("active", "paused")
WIDGET_SCOPES = ("project", "all")
WIDGET_STATES = ("expanded", "collapsed")
WIDGET_INFO = ("agent", "item", "goal", "last_update", "updates")
LIVE_VIEWS = ("kanban", "list", "overview", "item")
LIVE_EVENTS = ("items", "sessions", "activity")
LIVE_EDITING = ("notice", "after_save")

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _check_hex(value: object, field: str) -> str:
    if not isinstance(value, str) or not _HEX_COLOR.fullmatch(value):
        raise InvalidSetting(f"{field} must be a colour like #1a2b3c", details={"field": field})
    return value.lower()


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """``base`` with the keys of ``extra`` applied, nested dicts merged key by key."""
    merged = json.loads(json.dumps(base))
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _int_in(value: object, low: int, high: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float) or value != int(value):
        raise InvalidSetting(f"{field} must be a whole number", details={"field": field})
    number = int(value)
    if not low <= number <= high:
        raise InvalidSetting(
            f"{field} must be between {low} and {high}", details={"field": field},
        )
    return number


def _flags(value: object, allowed: tuple[str, ...], field: str) -> dict[str, bool]:
    if not isinstance(value, dict) or set(value) != set(allowed):
        raise InvalidSetting(f"{field} must set each of: {', '.join(allowed)}",
                             details={"field": field})
    if not all(isinstance(flag, bool) for flag in value.values()):
        raise InvalidSetting(f"{field} values must be on or off", details={"field": field})
    return {name: value[name] for name in allowed}


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise InvalidSetting(f"{field} must be on or off", details={"field": field})
    return value


def _choice(value: object, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise InvalidSetting(
            f"{field} must be one of: {', '.join(allowed)}", details={"field": field},
        )
    return str(value)


def validate_agent_widget(group: dict[str, Any]) -> dict[str, Any]:
    """Check a complete ``agent_widget`` group and return it normalised."""
    statuses = group.get("statuses")
    if not isinstance(statuses, list) or not all(s in WIDGET_STATUSES for s in statuses):
        raise InvalidSetting(
            f"statuses shown must be some of: {', '.join(WIDGET_STATUSES)}",
            details={"field": "statuses"},
        )
    return {
        "show_kanban": _bool(group.get("show_kanban"), "show on the Kanban board"),
        "show_overview": _bool(group.get("show_overview"), "show on the Overview page"),
        "statuses": [s for s in WIDGET_STATUSES if s in statuses],
        "completed_minutes": _int_in(group.get("completed_minutes"), 0, 240, "completed within"),
        "max_sessions": _int_in(group.get("max_sessions"), 1, 20, "maximum sessions"),
        "scope": _choice(group.get("scope"), WIDGET_SCOPES, "scope"),
        "initial_state": _choice(group.get("initial_state"), WIDGET_STATES, "initial state"),
        "info": _flags(group.get("info"), WIDGET_INFO, "information shown"),
    }


def validate_live(group: dict[str, Any]) -> dict[str, Any]:
    """Check a complete ``live`` group and return it normalised."""
    return {
        "enabled": _bool(group.get("enabled"), "live updates"),
        "fallback_seconds": _int_in(group.get("fallback_seconds"), 5, 300, "refresh interval"),
        "highlight_seconds": _int_in(group.get("highlight_seconds"), 0, 30, "highlight time"),
        "while_editing": _choice(group.get("while_editing"), LIVE_EDITING, "while editing"),
        "views": _flags(group.get("views"), LIVE_VIEWS, "views"),
        "events": _flags(group.get("events"), LIVE_EVENTS, "events"),
        "indicator": _bool(group.get("indicator"), "connection indicator"),
    }


def _validate_github(group: dict[str, Any]) -> dict[str, Any]:
    return validate_github(group, bool_check=_bool)


_GROUP_VALIDATORS = {
    "agent_widget": validate_agent_widget,
    "live": validate_live,
    "github": _validate_github,
}


def theme_style(settings: dict[str, Any]) -> str:
    """CSS that overrides the dashboard accent variables for light and dark mode."""
    light = settings["theme"]["light"]
    dark = settings["theme"]["dark"]
    return (
        "<style>"
        f":root{{--dt-primary:{light['primary']};--dt-accent:{light['accent']};}}"
        f".dark{{--dt-primary:{dark['primary']};--dt-accent:{dark['accent']};}}"
        "</style>"
    )


class RuntimeSettings:
    def __init__(self, data_dir: Path):
        self._dir = Path(data_dir)

    # --- settings -----------------------------------------------------------

    def settings(self) -> dict[str, Any]:
        stored = _read_json(self._dir / SETTINGS_FILE, {})
        merged = json.loads(json.dumps(DEFAULT_SETTINGS))
        for key, value in stored.items():
            if key == "theme" and isinstance(value, dict):
                for mode in ("light", "dark"):
                    if isinstance(value.get(mode), dict):
                        merged["theme"][mode].update(value[mode])
            elif key in _GROUP_VALIDATORS and isinstance(value, dict):
                # Keys added in later versions keep their defaults; a stored group
                # that no longer validates falls back to the defaults as a whole.
                candidate = _deep_merge(merged[key], value)
                try:
                    merged[key] = _GROUP_VALIDATORS[key](candidate)
                except InvalidSetting:
                    pass
            elif key in merged:
                merged[key] = value
        return merged

    def update_settings(self, changes: dict[str, Any], *, actor: str = "dashboard") -> dict:
        with _lock:
            current = self.settings()
            updated = json.loads(json.dumps(current))
            for key, value in changes.items():
                if key == "theme":
                    for mode, colours in value.items():
                        for part, colour in colours.items():
                            updated["theme"][mode][part] = _check_hex(
                                colour, f"{mode} {part} colour",
                            )
                elif key == "default_language":
                    if value not in LANGUAGES:
                        raise InvalidSetting("unknown default language", details={"field": key})
                    updated[key] = value
                elif key == "default_theme":
                    if value not in THEMES:
                        raise InvalidSetting("unknown default theme", details={"field": key})
                    updated[key] = value
                elif key == "default_estimated_time":
                    if value is None:
                        updated[key] = None
                    elif isinstance(value, bool) or not isinstance(value, int | float) \
                            or value < 0:
                        raise InvalidSetting(
                            "default estimated time must be a number of hours, 0 or more",
                            details={"field": key},
                        )
                    else:
                        updated[key] = float(value)
                elif key in _GROUP_VALIDATORS:
                    if not isinstance(value, dict):
                        raise InvalidSetting(f"{key} must be a group of settings",
                                             details={"field": key})
                    unknown = set(value) - set(DEFAULT_SETTINGS[key])
                    if unknown:
                        raise InvalidSetting(
                            f"unknown {key} setting(s): {', '.join(sorted(unknown))}",
                            details={"field": key},
                        )
                    updated[key] = _GROUP_VALIDATORS[key](_deep_merge(updated[key], value))
                else:
                    raise InvalidSetting(f"unknown setting '{key}'", details={"field": key})
            _write_json(self._dir / SETTINGS_FILE, updated)
            self._audit(
                "settings.updated", actor,
                {"changed": sorted(changes), "before": _diff(current, updated)},
            )
            return updated

    def reset_theme(self, *, actor: str = "dashboard") -> dict:
        return self.reset_group("theme", actor=actor)

    def reset_group(self, group: str, *, actor: str = "dashboard") -> dict:
        """Put one settings group back to its defaults (theme, agent_widget or live)."""
        if group not in RESETTABLE_GROUPS:
            raise InvalidSetting(f"unknown settings group '{group}'", details={"field": group})
        with _lock:
            current = self.settings()
            updated = json.loads(json.dumps(current))
            updated[group] = json.loads(json.dumps(DEFAULT_SETTINGS[group]))
            _write_json(self._dir / SETTINGS_FILE, updated)
            self._audit(f"{group}.reset", actor, {"changed": [group]})
            return updated

    # --- tokens -------------------------------------------------------------

    def tokens(self) -> list[dict[str, Any]]:
        return list(_read_json(self._dir / TOKENS_FILE, []))

    def token_credentials(self) -> list[BearerTokenCredential]:
        return [
            BearerTokenCredential(
                name=record["name"],
                scopes=frozenset(record["scopes"]),
                token_sha256=record["token_sha256"],
            )
            for record in self.tokens()
        ]

    def create_token(
        self, name: str, scopes: list[str], *, config_names: set[str], actor: str = "dashboard",
    ) -> tuple[dict, str]:
        with _lock:
            clean_name = _clean_token_name(name, config_names, self.tokens())
            clean_scopes = _clean_scopes(scopes)
            plaintext = secrets.token_urlsafe(32)
            record = {
                "id": uuid.uuid4().hex[:12],
                "name": clean_name,
                "scopes": clean_scopes,
                "token_sha256": sha256_hex(plaintext),
                "created_at": _now(),
                "updated_at": _now(),
            }
            tokens = self.tokens()
            tokens.append(record)
            _write_json(self._dir / TOKENS_FILE, tokens)
            self._audit("token.created", actor, {"token": clean_name, "scopes": clean_scopes})
            return _public(record), plaintext

    def update_token(
        self, token_id: str, *, name: str | None = None, scopes: list[str] | None = None,
        config_names: set[str], actor: str = "dashboard",
    ) -> dict:
        with _lock:
            tokens = self.tokens()
            record = _find(tokens, token_id)
            before = {"name": record["name"], "scopes": list(record["scopes"])}
            others = [t for t in tokens if t["id"] != token_id]
            if name is not None:
                record["name"] = _clean_token_name(name, config_names, others)
            if scopes is not None:
                record["scopes"] = _clean_scopes(scopes)
            record["updated_at"] = _now()
            _write_json(self._dir / TOKENS_FILE, tokens)
            self._audit(
                "token.updated", actor,
                {"token": record["name"], "before": before,
                 "after": {"name": record["name"], "scopes": record["scopes"]}},
            )
            return _public(record)

    def regenerate_token(self, token_id: str, *, actor: str = "dashboard") -> tuple[dict, str]:
        with _lock:
            tokens = self.tokens()
            record = _find(tokens, token_id)
            plaintext = secrets.token_urlsafe(32)
            record["token_sha256"] = sha256_hex(plaintext)
            record["updated_at"] = _now()
            _write_json(self._dir / TOKENS_FILE, tokens)
            self._audit("token.regenerated", actor, {"token": record["name"]})
            return _public(record), plaintext

    def delete_token(self, token_id: str, *, actor: str = "dashboard") -> None:
        with _lock:
            tokens = self.tokens()
            record = _find(tokens, token_id)
            _write_json(self._dir / TOKENS_FILE, [t for t in tokens if t["id"] != token_id])
            self._audit("token.deleted", actor, {"token": record["name"]})

    def public_tokens(self) -> list[dict[str, Any]]:
        return [_public(record) for record in self.tokens()]

    # --- audit --------------------------------------------------------------

    def audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            lines = (self._dir / AUDIT_FILE).read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        entries = [json.loads(line) for line in lines if line.strip()]
        return list(reversed(entries))[:limit]

    def record(self, action: str, actor: str, details: dict[str, Any]) -> None:
        """Append an audit entry for a change made elsewhere (e.g. a project edit)."""
        self._audit(action, actor, details)

    def _audit(self, action: str, actor: str, details: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        entry = {"at": _now(), "action": action, "actor": actor, "details": details}
        with (self._dir / AUDIT_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "token_sha256"}


def _find(tokens: list[dict[str, Any]], token_id: str) -> dict[str, Any]:
    for record in tokens:
        if record["id"] == token_id:
            return record
    raise TokenNotFound("token not found", details={"token_id": token_id})


def _clean_scopes(scopes: list[str]) -> list[str]:
    clean = sorted({s for s in scopes if s in TOKEN_SCOPES})
    if not clean:
        raise InvalidSetting("choose at least one scope (read, agent or admin)")
    return clean


def _clean_token_name(name: str, config_names: set[str], others: list[dict]) -> str:
    clean = (name or "").strip()
    if not _NAME.fullmatch(clean):
        raise InvalidSetting(
            "token name must start with a letter and use letters, digits, '.', '_' or '-'",
            details={"field": "name"},
        )
    taken = config_names | {"api_token"} | {t["name"] for t in others}
    if clean in taken:
        raise InvalidSetting(f"a token named '{clean}' already exists", details={"field": "name"})
    return clean


#: Public aliases, shared with the server.toml token editor (IS-0003).
clean_scopes = _clean_scopes
clean_token_name = _clean_token_name


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key in before:
        if before[key] != after.get(key):
            changed[key] = before[key]
    return changed
