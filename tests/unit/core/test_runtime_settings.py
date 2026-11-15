"""FEA-0004: runtime settings and runtime tokens."""

import json
import tomllib

import pytest

from issuedeck.core.auth import BearerTokenCredential, sha256_hex
from issuedeck.core.errors import InvalidSetting, TokenNotFound
from issuedeck.core.runtime_settings import DEFAULT_SETTINGS, RuntimeSettings, theme_style
from issuedeck.features.dashboard.settings_routes import rewrite_project_header


@pytest.fixture
def store(tmp_path):
    return RuntimeSettings(tmp_path / "data")


def test_defaults_are_returned_when_nothing_is_stored(store):
    assert store.settings() == DEFAULT_SETTINGS


def test_colour_update_is_saved_and_normalised(store):
    store.update_settings({"theme": {"dark": {"primary": "#ABCDEF", "accent": "#101010"}}})

    dark = store.settings()["theme"]["dark"]
    assert dark == {"primary": "#abcdef", "accent": "#101010"}
    assert store.settings()["theme"]["light"] == DEFAULT_SETTINGS["theme"]["light"]


@pytest.mark.parametrize("bad", ["red", "#fff", "#gggggg", "url(x)", "#12345g", ""])
def test_invalid_colour_is_rejected(store, bad):
    with pytest.raises(InvalidSetting):
        store.update_settings({"theme": {"light": {"primary": bad}}})


def test_reset_restores_the_default_palette(store):
    store.update_settings({"theme": {"light": {"primary": "#111111", "accent": "#222222"}}})

    store.reset_theme()

    assert store.settings()["theme"] == DEFAULT_SETTINGS["theme"]


def test_language_and_theme_choices_are_validated(store):
    store.update_settings({"default_language": "hu", "default_theme": "system"})
    assert store.settings()["default_language"] == "hu"
    assert store.settings()["default_theme"] == "system"

    with pytest.raises(InvalidSetting):
        store.update_settings({"default_language": "de"})
    with pytest.raises(InvalidSetting):
        store.update_settings({"default_theme": "neon"})


@pytest.mark.parametrize("bad", [-1, True, "many"])
def test_default_estimated_time_must_be_a_non_negative_number(store, bad):
    with pytest.raises(InvalidSetting):
        store.update_settings({"default_estimated_time": bad})


def test_default_estimated_time_can_be_cleared(store):
    store.update_settings({"default_estimated_time": None})

    assert store.settings()["default_estimated_time"] is None


def test_unknown_setting_is_rejected(store):
    with pytest.raises(InvalidSetting):
        store.update_settings({"secret_mode": True})


def test_theme_style_only_contains_validated_colours(store):
    css = theme_style(store.settings())

    assert "--dt-primary:#0f766e" in css
    assert "--dt-accent:#f59e0b" in css  # dark accent


def test_created_token_is_returned_once_and_only_its_hash_is_stored(store):
    record, plaintext = store.create_token("claude-agent", ["agent"], config_names=set())

    assert "token_sha256" not in record
    assert plaintext not in json.dumps(store.tokens())
    stored = store.tokens()[0]
    assert stored["token_sha256"] == sha256_hex(plaintext)
    assert "token" not in stored or stored["token"] != plaintext


def test_runtime_token_credential_matches_only_the_current_value(store):
    _, first = store.create_token("claude-agent", ["agent"], config_names=set())
    credential = store.token_credentials()[0]

    assert credential.matches(first)
    assert not credential.matches(first + "x")
    assert "agent" in credential.scopes
    assert credential.session_key == sha256_hex(first)


def test_regenerate_invalidates_the_old_value(store):
    record, old = store.create_token("claude-agent", ["read"], config_names=set())

    _, new = store.regenerate_token(record["id"])

    assert new != old
    credential = store.token_credentials()[0]
    assert credential.matches(new)
    assert not credential.matches(old)


def test_token_name_and_scopes_can_be_changed(store):
    record, _ = store.create_token("first", ["read"], config_names=set())

    updated = store.update_token(
        record["id"], name="renamed", scopes=["agent", "read"], config_names=set(),
    )

    assert updated["name"] == "renamed"
    assert updated["scopes"] == ["agent", "read"]


def test_token_name_cannot_clash_with_config_tokens(store):
    with pytest.raises(InvalidSetting):
        store.create_token("api_token", ["admin"], config_names=set())
    with pytest.raises(InvalidSetting):
        store.create_token("claude-read", ["read"], config_names={"claude-read"})


def test_token_name_must_be_unique_among_runtime_tokens(store):
    store.create_token("dup", ["read"], config_names=set())

    with pytest.raises(InvalidSetting):
        store.create_token("dup", ["read"], config_names=set())


@pytest.mark.parametrize("name", ["", "1st", "has space", "x" * 70])
def test_token_name_format_is_checked(store, name):
    with pytest.raises(InvalidSetting):
        store.create_token(name, ["read"], config_names=set())


def test_scopes_must_be_known_and_non_empty(store):
    with pytest.raises(InvalidSetting):
        store.create_token("t", [], config_names=set())
    with pytest.raises(InvalidSetting):
        store.create_token("t", ["root"], config_names=set())


def test_delete_removes_the_token(store):
    record, _ = store.create_token("gone", ["read"], config_names=set())

    store.delete_token(record["id"])

    assert store.tokens() == []
    with pytest.raises(TokenNotFound):
        store.delete_token(record["id"])


def test_audit_log_records_changes_without_secret_values(store):
    _, plaintext = store.create_token("audited", ["read"], config_names=set())
    store.update_settings({"default_language": "hu"})

    log = store.audit_log()

    actions = [entry["action"] for entry in log]
    assert "token.created" in actions
    assert "settings.updated" in actions
    assert plaintext not in json.dumps(log)


def test_credential_dataclass_still_accepts_plaintext_tokens():
    credential = BearerTokenCredential(name="cfg", token="abc", scopes=frozenset({"read"}))

    assert credential.matches("abc")
    assert credential.session_key == "abc"


def test_rewrite_project_header_changes_only_the_header():
    text = (
        'key = "p"\n'
        'name = "Old"\n'
        '# a comment\n'
        'description = "old text"\n'
        '\n'
        '[kinds.feature]\n'
        'label = "Feature"\n'
        'prefix = "FEAT"\n'
    )

    new = rewrite_project_header(text, "New name", "New description")

    parsed = tomllib.loads(new)
    assert parsed["name"] == "New name"
    assert parsed["description"] == "New description"
    assert parsed["kinds"]["feature"] == {"label": "Feature", "prefix": "FEAT"}
    assert "# a comment" in new


def test_rewrite_project_header_adds_missing_keys():
    text = 'key = "p"\n\n[kinds.feature]\nlabel = "Feature"\nprefix = "FEAT"\n'

    new = rewrite_project_header(text, "Named", "Described")

    parsed = tomllib.loads(new)
    assert parsed["name"] == "Named"
    assert parsed["description"] == "Described"


def test_rewrite_project_header_escapes_quotes_and_newlines_safely():
    text = 'key = "p"\nname = "a"\n\n[kinds.feature]\nlabel = "F"\nprefix = "FEAT"\n'

    new = rewrite_project_header(text, 'Say "hi"', "line one\nline two")

    parsed = tomllib.loads(new)
    assert parsed["name"] == 'Say "hi"'
    assert parsed["description"] == "line one\nline two"
