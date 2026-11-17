"""FEA-0008: the GitHub export settings are checked before they are stored."""

import pytest

from issuedeck.core.errors import InvalidSetting
from issuedeck.core.github_settings import (
    DEFAULT_REPOSITORY,
    DEFAULT_TOKEN_ENV,
    clean_author_email,
    clean_author_name,
    clean_branch,
    clean_folder,
    clean_token_env,
    parse_repository,
)
from issuedeck.core.runtime_settings import DEFAULT_SETTINGS, RuntimeSettings


@pytest.mark.parametrize("value", [
    "EmbedFan/MyIssueDeckExports",
    "https://github.com/EmbedFan/MyIssueDeckExports",
    "https://github.com/EmbedFan/MyIssueDeckExports.git",
    "https://github.com/EmbedFan/MyIssueDeckExports/",
    "github.com/EmbedFan/MyIssueDeckExports.git",
    "  EmbedFan/MyIssueDeckExports  ",
])
def test_a_repository_can_be_written_in_the_usual_ways(value):
    assert parse_repository(value) == ("EmbedFan", "MyIssueDeckExports")


@pytest.mark.parametrize("value", [
    "", "justaname", "a/b/c", "http://github.com/o/r", "https://gitlab.com/o/r",
    "o/..", "-o/r", "o/r name", "o/r?x=1", None, 5,
])
def test_a_repository_must_be_owner_and_name(value):
    with pytest.raises(InvalidSetting):
        parse_repository(value)


def test_the_default_repository_and_token_variable():
    assert parse_repository(DEFAULT_REPOSITORY) == ("EmbedFan", "MyIssueDeckExports")
    assert DEFAULT_TOKEN_ENV == "GITHUB_PAT"
    assert DEFAULT_SETTINGS["github"]["token_env"] == "GITHUB_PAT"
    assert DEFAULT_SETTINGS["github"]["allow_public"] is False


@pytest.mark.parametrize("branch", ["main", "exports/2026", "release-1.0", "a_b"])
def test_good_branch_names(branch):
    assert clean_branch(branch) == branch


@pytest.mark.parametrize("branch", ["", "a..b", "/x", "x/", "x//y", "a b", "x.lock", ".x", "x."])
def test_bad_branch_names(branch):
    with pytest.raises(InvalidSetting):
        clean_branch(branch)


@pytest.mark.parametrize("raw, clean", [
    ("", ""), ("/", ""), ("exports", "exports"), ("/exports/issuedeck/", "exports/issuedeck"),
])
def test_the_folder_is_a_relative_path(raw, clean):
    assert clean_folder(raw) == clean


@pytest.mark.parametrize("folder", ["../up", "a/../b", "./a", "a//b", "a b", "a\\b", "x" * 201])
def test_a_folder_cannot_leave_the_repository_folder(folder):
    with pytest.raises(InvalidSetting):
        clean_folder(folder)


@pytest.mark.parametrize("name", ["GITHUB_PAT", "MY_TOKEN_2", "_x"])
def test_good_token_variable_names(name):
    assert clean_token_env(name) == name


@pytest.mark.parametrize("name", ["", "1ABC", "A B", "A-B", "A=B", "x" * 65])
def test_bad_token_variable_names(name):
    with pytest.raises(InvalidSetting):
        clean_token_env(name)


def test_the_author_is_checked():
    assert clean_author_name("  MyIssueDesk ") == "MyIssueDesk"
    assert clean_author_email("a@b.example") == "a@b.example"
    for bad in ("", "<x>", "a\nb", "x" * 101):
        with pytest.raises(InvalidSetting):
            clean_author_name(bad)
    for bad in ("", "nobody", "a@b", "a b@c.example", "<a@b.example>"):
        with pytest.raises(InvalidSetting):
            clean_author_email(bad)


def test_settings_are_stored_audited_and_reset_as_a_group(tmp_path):
    runtime = RuntimeSettings(tmp_path)
    assert runtime.settings()["github"] == DEFAULT_SETTINGS["github"]

    stored = runtime.update_settings({"github": {"branch": "exports", "allow_public": True}})
    assert stored["github"]["branch"] == "exports" and stored["github"]["allow_public"] is True
    assert stored["github"]["repository"] == DEFAULT_REPOSITORY  # untouched values stay
    assert runtime.audit_log()[0]["action"] == "settings.updated"

    runtime.reset_group("github")
    assert runtime.settings()["github"] == DEFAULT_SETTINGS["github"]
    assert runtime.audit_log()[0]["action"] == "github.reset"


def test_unknown_or_invalid_values_are_refused_and_nothing_is_stored(tmp_path):
    runtime = RuntimeSettings(tmp_path)
    for bad in ({"nope": 1}, {"allow_public": "yes"}, {"repository": "x"}):
        with pytest.raises(InvalidSetting):
            runtime.update_settings({"github": bad})
    assert runtime.settings()["github"] == DEFAULT_SETTINGS["github"]


def test_a_stored_group_that_no_longer_validates_falls_back_to_the_defaults(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"github": {"repository": "broken value"}}', encoding="utf-8",
    )
    assert RuntimeSettings(tmp_path).settings()["github"] == DEFAULT_SETTINGS["github"]
