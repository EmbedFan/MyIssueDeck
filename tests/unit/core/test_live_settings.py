"""FEA-0006: the agent_widget and live settings groups."""

import json

import pytest

from issuedeck.core.errors import InvalidSetting
from issuedeck.core.runtime_settings import DEFAULT_SETTINGS, SETTINGS_FILE, RuntimeSettings


@pytest.fixture
def store(tmp_path):
    return RuntimeSettings(tmp_path / "data")


def test_defaults_match_the_request():
    widget = DEFAULT_SETTINGS["agent_widget"]
    live = DEFAULT_SETTINGS["live"]

    assert widget["show_kanban"] is False and widget["show_overview"] is True
    assert widget["statuses"] == ["active", "paused"]
    assert widget["completed_minutes"] == 0 and widget["max_sessions"] == 8
    assert widget["scope"] == "project" and widget["initial_state"] == "expanded"
    assert all(widget["info"].values())
    assert live["enabled"] is True and live["fallback_seconds"] == 30
    assert live["highlight_seconds"] == 3 and live["while_editing"] == "notice"
    assert all(live["views"].values()) and all(live["events"].values()) and live["indicator"]


def test_a_partial_update_keeps_the_other_values(store):
    store.update_settings({"agent_widget": {"show_kanban": True, "max_sessions": 5}})

    widget = store.settings()["agent_widget"]
    assert widget["show_kanban"] is True and widget["max_sessions"] == 5
    assert widget["show_overview"] is True and widget["statuses"] == ["active", "paused"]


def test_nested_flags_can_be_changed_one_at_a_time(store):
    store.update_settings({"live": {"views": {"list": False}, "events": {"activity": False}}})

    live = store.settings()["live"]
    assert live["views"] == {"kanban": True, "list": False, "overview": True, "item": True}
    assert live["events"] == {"items": True, "sessions": True, "activity": False}


@pytest.mark.parametrize("changes", [
    {"agent_widget": {"completed_minutes": 241}},
    {"agent_widget": {"completed_minutes": -1}},
    {"agent_widget": {"max_sessions": 0}},
    {"agent_widget": {"max_sessions": 21}},
    {"agent_widget": {"max_sessions": 2.5}},
    {"agent_widget": {"max_sessions": True}},
    {"agent_widget": {"scope": "world"}},
    {"agent_widget": {"initial_state": "half"}},
    {"agent_widget": {"statuses": ["active", "done"]}},
    {"agent_widget": {"statuses": "active"}},
    {"agent_widget": {"show_kanban": "yes"}},
    {"agent_widget": {"info": {"agent": "yes"}}},
    {"agent_widget": {"info": {"colour": True}}},
    {"agent_widget": {"unknown": 1}},
    {"live": {"fallback_seconds": 4}},
    {"live": {"fallback_seconds": 301}},
    {"live": {"highlight_seconds": 31}},
    {"live": {"highlight_seconds": -1}},
    {"live": {"while_editing": "ignore"}},
    {"live": {"views": {"kanban": "on"}}},
    {"live": {"events": {"items": True, "sessions": True, "activity": True, "x": True}}},
    {"live": {"enabled": 1}},
    {"live": "on"},
])
def test_invalid_values_are_refused_and_nothing_is_saved(store, changes):
    with pytest.raises(InvalidSetting):
        store.update_settings(changes)

    assert store.settings() == DEFAULT_SETTINGS


def test_boundary_values_are_accepted(store):
    store.update_settings({
        "agent_widget": {"completed_minutes": 240, "max_sessions": 20, "statuses": []},
        "live": {"fallback_seconds": 5, "highlight_seconds": 0},
    })

    settings = store.settings()
    assert settings["agent_widget"]["completed_minutes"] == 240
    assert settings["agent_widget"]["statuses"] == []
    assert settings["live"]["highlight_seconds"] == 0


def test_status_order_is_normalised(store):
    store.update_settings({"agent_widget": {"statuses": ["paused", "active"]}})

    assert store.settings()["agent_widget"]["statuses"] == ["active", "paused"]


def test_each_group_can_be_reset_on_its_own(store):
    store.update_settings({
        "agent_widget": {"max_sessions": 3}, "live": {"enabled": False},
        "theme": {"light": {"primary": "#111111"}},
    })

    store.reset_group("agent_widget")

    settings = store.settings()
    assert settings["agent_widget"] == DEFAULT_SETTINGS["agent_widget"]
    assert settings["live"]["enabled"] is False  # untouched
    assert settings["theme"]["light"]["primary"] == "#111111"
    store.reset_group("live")
    assert store.settings()["live"] == DEFAULT_SETTINGS["live"]


def test_unknown_groups_cannot_be_reset(store):
    with pytest.raises(InvalidSetting):
        store.reset_group("default_language")


def test_changes_and_resets_are_audited(store):
    store.update_settings({"agent_widget": {"show_kanban": True}})
    store.reset_group("live")

    actions = [entry["action"] for entry in store.audit_log()]
    assert "settings.updated" in actions and "live.reset" in actions


def test_a_settings_file_from_an_older_version_gets_the_new_defaults(store, tmp_path):
    path = tmp_path / "data" / SETTINGS_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"default_language": "hu"}), encoding="utf-8")

    settings = store.settings()

    assert settings["default_language"] == "hu"
    assert settings["agent_widget"] == DEFAULT_SETTINGS["agent_widget"]
    assert settings["live"] == DEFAULT_SETTINGS["live"]


def test_a_stored_group_missing_newer_keys_is_completed(store, tmp_path):
    path = tmp_path / "data" / SETTINGS_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"live": {"enabled": False}}), encoding="utf-8")

    live = store.settings()["live"]

    assert live["enabled"] is False
    assert live["fallback_seconds"] == 30 and live["views"]["kanban"] is True


def test_a_corrupt_stored_group_falls_back_to_the_defaults(store, tmp_path):
    path = tmp_path / "data" / SETTINGS_FILE
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"live": {"fallback_seconds": "soon"}}), encoding="utf-8")

    assert store.settings()["live"] == DEFAULT_SETTINGS["live"]
