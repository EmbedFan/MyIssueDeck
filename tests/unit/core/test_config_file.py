"""IS-0003: surgical edits of server.toml for token management."""

import tomllib

import pytest

from issuedeck.core.config_file import (
    mask_token,
    set_api_token,
    set_token_value,
    update_token,
    validate_server_text,
    write_server_text,
)
from issuedeck.core.errors import InvalidSetting

TEXT = (
    "# my config\n"
    'host = "127.0.0.1"\n'
    'api_token = "admin-old"  # admin token\n'
    "\n"
    "# read-only\n"
    "[[tokens]]\n"
    'name = "reader"\n'
    'token = "read-old"  # keep me\n'
    'scopes = ["read"]\n'
    "\n"
    "[[tokens]]\n"
    'name = "agent"\n'
    'token = "agent-old"\n'
    'scopes = ["agent"]\n'
    "\n"
    "[sqlite]\n"
    "wal_mode = true\n"
)


def test_set_api_token_changes_only_that_line():
    new = set_api_token(TEXT, "admin-new")

    assert 'api_token = "admin-new"  # admin token\n' in new
    assert new.replace("admin-new", "admin-old") == TEXT


def test_set_token_value_targets_the_named_block_only():
    new = set_token_value(TEXT, "agent", "agent-new")

    parsed = tomllib.loads(new)
    assert [t["token"] for t in parsed["tokens"]] == ["read-old", "agent-new"]
    assert "# keep me" in new
    assert "# read-only" in new


def test_set_token_value_keeps_trailing_comment_of_the_edited_line():
    new = set_token_value(TEXT, "reader", "read-new")

    assert 'token = "read-new"  # keep me\n' in new


def test_update_token_renames_and_changes_scopes():
    new = update_token(TEXT, "reader", "viewer", ["agent", "read"])

    parsed = tomllib.loads(new)
    assert parsed["tokens"][0]["name"] == "viewer"
    assert parsed["tokens"][0]["scopes"] == ["agent", "read"]
    assert parsed["tokens"][0]["token"] == "read-old"
    assert parsed["tokens"][1]["name"] == "agent"


def test_unknown_token_is_refused():
    with pytest.raises(InvalidSetting):
        set_token_value(TEXT, "nobody", "x")
    with pytest.raises(InvalidSetting):
        update_token(TEXT, "nobody", "x", ["read"])


def test_missing_api_token_is_refused():
    with pytest.raises(InvalidSetting):
        set_api_token('host = "x"\n[sqlite]\nwal_mode = true\n', "new")


def test_api_token_inside_a_table_is_not_touched():
    text = 'api_token = "top"\n\n[other]\napi_token = "nested"\n'

    new = set_api_token(text, "new")

    assert 'api_token = "nested"' in new
    assert 'api_token = "new"' in new


def test_crlf_line_endings_are_preserved():
    crlf = TEXT.replace("\n", "\r\n")

    new = set_token_value(crlf, "agent", "agent-new")

    assert new.replace("agent-new", "agent-old") == crlf


def test_validate_accepts_a_good_file_and_refuses_a_broken_one():
    assert validate_server_text(TEXT).api_token.get_secret_value() == "admin-old"

    with pytest.raises(InvalidSetting):
        validate_server_text(TEXT.replace('name = "agent"', 'name = "reader"'))  # duplicate
    with pytest.raises(InvalidSetting):
        validate_server_text("api_token = ")  # not TOML
    with pytest.raises(InvalidSetting):
        validate_server_text('host = "x"\n')  # no api_token


def test_duplicate_token_values_are_refused():
    same = set_token_value(TEXT, "agent", "read-old")

    with pytest.raises(InvalidSetting):
        validate_server_text(same)


def test_mask_token_shows_only_the_ends():
    assert mask_token("abcdefghijklmnopqrstuvwxyz") == "abcd...wxyz"
    assert mask_token("short") == "*****"
    assert "efghijklmnop" not in mask_token("abcdefghijklmnopqrstuvwxyz")


def test_write_server_text_replaces_the_file_atomically(tmp_path):
    path = tmp_path / "server.toml"
    path.write_text("old", encoding="utf-8")

    write_server_text(path, TEXT)

    assert path.read_text(encoding="utf-8") == TEXT
    assert not list(tmp_path.glob("*.tmp"))
