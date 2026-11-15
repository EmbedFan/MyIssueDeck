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
}

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
                else:
                    raise InvalidSetting(f"unknown setting '{key}'", details={"field": key})
            _write_json(self._dir / SETTINGS_FILE, updated)
            self._audit(
                "settings.updated", actor,
                {"changed": sorted(changes), "before": _diff(current, updated)},
            )
            return updated

    def reset_theme(self, *, actor: str = "dashboard") -> dict:
        with _lock:
            current = self.settings()
            updated = json.loads(json.dumps(current))
            updated["theme"] = json.loads(json.dumps(DEFAULT_SETTINGS["theme"]))
            _write_json(self._dir / SETTINGS_FILE, updated)
            self._audit("theme.reset", actor, {"changed": ["theme"]})
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
