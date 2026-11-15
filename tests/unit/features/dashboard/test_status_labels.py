"""IS-0002: status names are localised for Hungarian; everything else is unchanged."""

from issuedeck.core.config import BranchConfig, KindConfig, ProjectConfig, StatusConfig
from issuedeck.features.dashboard.helpers import status_label


def _project() -> ProjectConfig:
    return ProjectConfig(
        key="p",
        name="P",
        kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
        statuses={
            "proposed": StatusConfig(label="Proposed"),
            "in_progress": StatusConfig(label="In Progress"),
            "blocked": StatusConfig(label="Blocked"),
            "ready_to_ship": StatusConfig(label="Ready to Ship"),
            "done": StatusConfig(label="Done", terminal=True, requires_ship=True),
            "wontfix": StatusConfig(label="Won't Fix", terminal=True),
            "review": StatusConfig(label="Review by QA"),
        },
        branches=[BranchConfig(key="main", label="Main")],
    )


def test_hungarian_names_for_the_standard_statuses():
    project = _project()

    assert status_label("proposed", project, lang="hu") == "Javasolt"
    assert status_label("in_progress", project, lang="hu") == "Folyamatban"
    assert status_label("blocked", project, lang="hu") == "Blokkolva"
    assert status_label("ready_to_ship", project, lang="hu") == "Kiadásra kész"
    assert status_label("done", project, lang="hu") == "Kész"
    assert status_label("wontfix", project, lang="hu") == "Nem javítandó"


def test_custom_status_keeps_its_configured_label_in_hungarian():
    assert status_label("review", _project(), lang="hu") == "Review by QA"


def test_english_and_chinese_keep_the_project_labels():
    project = _project()

    assert status_label("in_progress", project) == "In Progress"
    assert status_label("in_progress", project, lang="en") == "In Progress"
    assert status_label("in_progress", project, lang="zh-CN") == "In Progress"
    assert status_label("done", project, lang="zh-CN") == "Done"


def test_unknown_status_without_project_falls_back_to_the_key():
    assert status_label("mystery") == "mystery"
    assert status_label("mystery", lang="hu") == "mystery"
