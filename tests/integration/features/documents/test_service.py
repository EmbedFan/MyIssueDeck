"""FEA-0012 phase 1: the document store (files, revisions, conflicts)."""

import hashlib
import json
import threading

import pytest

from issuedeck.core.config import (
    BranchConfig,
    ConfigRegistry,
    KindConfig,
    ProjectConfig,
    ServerConfig,
    StatusConfig,
)
from issuedeck.core.errors import (
    DocumentConflict,
    DocumentExists,
    DocumentNotFound,
    InvalidDocument,
    ProjectNotFound,
)
from issuedeck.features.documents.repo import DocumentStore
from issuedeck.features.documents.service import MAX_REVISIONS, DocumentService, detail, summary


def _registry():
    return ConfigRegistry(
        server=ServerConfig(api_token="t"),
        projects={"test": ProjectConfig(
            key="test", name="Test",
            kinds={"feature": KindConfig(label="Feature", prefix="FEAT")},
            statuses={"proposed": StatusConfig(label="P")},
            branches=[BranchConfig(key="main", label="Main")],
        )},
    )


@pytest.fixture
def service(tmp_path):
    return DocumentService(tmp_path / "documents", _registry())


def _folder(tmp_path):
    return tmp_path / "documents" / "test"


# ------------------------------------------------------------------------------ create


def test_create_stores_one_json_file_named_by_the_id(service, tmp_path):
    document = service.create("test", "Feature request.md", "# Request\n", kind="request",
                              title="The request", actor="me")

    assert document["id"] == "DOC-0001"
    assert (document["name"], document["kind"], document["title"]) == (
        "Feature request.md", "request", "The request")
    assert (document["revision"], document["actor"], document["revisions"]) == (1, "me", [])
    assert document["sha256"] == hashlib.sha256(b"# Request\n").hexdigest()
    files = sorted(p.name for p in _folder(tmp_path).iterdir())
    assert files == ["DOC-0001.json", "documents.json"]  # the name is not a file name
    stored = json.loads((_folder(tmp_path) / "DOC-0001.json").read_text(encoding="utf-8"))
    assert stored["body"] == "# Request\n" and stored["name"] == "Feature request.md"


def test_the_files_are_written_in_one_stable_form(service, tmp_path):
    service.create("test", "b.md", "text é\r\nline")

    raw = (_folder(tmp_path) / "DOC-0001.json").read_bytes()

    assert raw.endswith(b"\n") and b"\r\n" not in raw  # the CR of the text is escaped
    assert raw == (json.dumps(json.loads(raw), indent=2, sort_keys=True,
                              ensure_ascii=False) + "\n").encode("utf-8")
    assert json.loads((_folder(tmp_path) / "documents.json").read_text()) == {"next_id": 2}


@pytest.mark.parametrize("name", [
    "no extension", "spaces and (brackets).md", "árvíztűrő.markdown", "日本語", "notes.txt",
    "UPPER.MD", ".hidden", "a" * 300,
])
def test_any_name_is_accepted(service, name):
    assert service.create("test", name, "text")["name"] == name


def test_a_name_is_never_a_path(service, tmp_path):
    document = service.create("test", "../../../escape.md", "text")

    assert document["name"] == "escape.md"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == [
        "DOC-0001.json", "documents.json"]
    assert {p.parent for p in tmp_path.rglob("*.json")} == {_folder(tmp_path)}


def test_a_binary_body_is_refused_and_nothing_is_stored(service, tmp_path):
    with pytest.raises(InvalidDocument, match="binary"):
        service.create("test", "x.md", "a\x00b")

    assert not _folder(tmp_path).exists()


def test_a_large_document_is_accepted(service):
    big = "# Big\n" + ("line of text that repeats\n" * 400_000)  # about 10 MB

    document = service.create("test", "big.md", big)

    assert detail(service.get("test", document["id"]))["body"] == big
    assert summary(document)["size"] == len(big.encode())


def test_the_kind_is_checked_and_defaults_to_other(service):
    assert service.create("test", "a.md", "x")["kind"] == "other"
    for kind in ("prompt", "description", "request", "report"):
        assert service.create("test", f"{kind}.md", "x", kind=kind)["kind"] == kind
    with pytest.raises(InvalidDocument, match="kind"):
        service.create("test", "bad.md", "x", kind="essay")


def test_a_name_that_is_used_gives_409_or_a_new_revision_with_replace(service):
    first = service.create("test", "a.md", "one")

    with pytest.raises(DocumentExists) as error:
        service.create("test", "a.md", "two")
    assert error.value.details["existing_id"] == first["id"]

    again = service.create("test", "a.md", "two", replace=True, actor="upload")
    assert (again["id"], again["revision"], again["body"]) == (first["id"], 2, "two")
    assert [r["body"] for r in again["revisions"]] == ["one"]
    same = service.create("test", "a.md", "two", replace=True)
    assert same["revision"] == 2  # the same text is not a new revision


def test_names_are_compared_exactly(service):
    service.create("test", "Readme.md", "x")

    assert service.create("test", "readme.md", "y")["id"] == "DOC-0002"


def test_ids_are_never_reused_even_after_a_delete(service):
    service.create("test", "a.md", "x")
    second = service.create("test", "b.md", "y")
    service.delete("test", second["id"])

    assert service.create("test", "c.md", "z")["id"] == "DOC-0003"


def test_a_lost_registry_never_lets_an_id_be_used_twice(service, tmp_path):
    service.create("test", "a.md", "x")
    service.create("test", "b.md", "y")
    (_folder(tmp_path) / "documents.json").unlink()

    assert service.create("test", "c.md", "z")["id"] == "DOC-0003"


# ------------------------------------------------------------------------------ read


def test_list_filters_by_kind_and_name_and_leaves_out_the_text(service):
    service.create("test", "a.md", "x", kind="prompt")
    service.create("test", "b.md", "yy", kind="report")

    everything = service.list("test")
    assert [d["id"] for d in everything] == ["DOC-0001", "DOC-0002"]
    assert "body" not in everything[0] and everything[1]["size"] == 2
    assert [d["name"] for d in service.list("test", kind="report")] == ["b.md"]
    assert [d["id"] for d in service.list("test", name="a.md")] == ["DOC-0001"]
    assert service.list("test", name="missing.md") == []


def test_unknown_document_and_project(service):
    with pytest.raises(DocumentNotFound):
        service.get("test", "DOC-0009")
    with pytest.raises(DocumentNotFound):
        service.get("test", "../../x")  # an id that is not an id is just not found
    with pytest.raises(ProjectNotFound):
        service.list("nope")


# ------------------------------------------------------------------------------ change


def test_replace_makes_a_new_revision_and_keeps_the_old_text(service):
    doc = service.create("test", "a.md", "one", actor="first")

    changed = service.replace("test", doc["id"], "two", revision=1, actor="second")

    assert (changed["revision"], changed["body"], changed["actor"]) == (2, "two", "second")
    assert changed["revisions"][0]["body"] == "one"
    assert changed["revisions"][0]["actor"] == "first"
    assert changed["revisions"][0]["sha256"] == hashlib.sha256(b"one").hexdigest()
    assert changed["created_at"] == doc["created_at"]


def test_replace_with_an_old_revision_is_a_conflict_and_writes_nothing(service):
    doc = service.create("test", "a.md", "one")
    service.replace("test", doc["id"], "two", revision=1)

    with pytest.raises(DocumentConflict) as error:
        service.replace("test", doc["id"], "mine", revision=1)

    assert error.value.details["current_revision"] == 2
    assert service.get("test", doc["id"])["body"] == "two"


def test_two_agents_changing_the_same_revision_only_one_wins(service):
    doc = service.create("test", "a.md", "start")
    results = []

    def change(text):
        try:
            service.replace("test", doc["id"], text, revision=1)
            results.append("ok")
        except DocumentConflict:
            results.append("conflict")

    threads = [threading.Thread(target=change, args=(f"agent {i}",)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == ["conflict"] * 7 + ["ok"]
    assert service.get("test", doc["id"])["revision"] == 2


def test_replace_can_change_the_title_and_kind_without_a_new_revision(service):
    doc = service.create("test", "a.md", "same")

    changed = service.replace("test", doc["id"], "same", revision=1, title="New title",
                              kind="prompt")

    assert (changed["revision"], changed["title"], changed["kind"]) == (1, "New title", "prompt")
    assert changed["revisions"] == []


def test_append_adds_text_at_the_end_without_a_revision_number(service):
    doc = service.create("test", "log.md", "# Log\nfirst")

    first = service.append("test", doc["id"], "second")
    second = service.append("test", doc["id"], "\nthird\n")

    assert first["body"] == "# Log\nfirst\nsecond"  # a line break is added when it is missing
    assert second["body"] == "# Log\nfirst\nsecond\nthird\n"
    assert second["revision"] == 3
    with pytest.raises(InvalidDocument):
        service.append("test", doc["id"], "bad \x00")


def test_delete_removes_the_file(service, tmp_path):
    doc = service.create("test", "a.md", "x")

    service.delete("test", doc["id"])

    assert not (_folder(tmp_path) / "DOC-0001.json").exists()
    with pytest.raises(DocumentNotFound):
        service.delete("test", doc["id"])


# ------------------------------------------------------------------------------ revisions


def test_revisions_are_listed_newest_first_and_can_be_read(service):
    doc = service.create("test", "a.md", "v1")
    service.replace("test", doc["id"], "v2", revision=1)
    service.replace("test", doc["id"], "v3", revision=2)

    rows = service.revisions("test", doc["id"])

    assert [(r["revision"], r["current"]) for r in rows] == [(3, True), (2, False), (1, False)]
    assert service.revision("test", doc["id"], 1)["body"] == "v1"
    assert service.revision("test", doc["id"], 3)["body"] == "v3"
    with pytest.raises(DocumentNotFound, match="not kept"):
        service.revision("test", doc["id"], 9)


def test_restore_makes_the_old_text_a_new_revision(service):
    doc = service.create("test", "a.md", "v1")
    service.replace("test", doc["id"], "v2", revision=1)

    restored = service.restore("test", doc["id"], 1, actor="me")

    assert (restored["revision"], restored["body"], restored["actor"]) == (3, "v1", "me")
    assert [r["body"] for r in restored["revisions"]] == ["v1", "v2"]
    assert service.restore("test", doc["id"], 3)["revision"] == 3  # nothing to restore
    with pytest.raises(DocumentNotFound):
        service.restore("test", doc["id"], 99)


def test_at_most_fifty_revisions_are_kept_and_the_current_text_never_goes(service):
    doc = service.create("test", "a.md", "text 1")
    for number in range(2, 81):
        doc = service.replace("test", doc["id"], f"text {number}", revision=number - 1)

    rows = service.revisions("test", doc["id"])

    assert len(rows) == MAX_REVISIONS == 50
    assert (rows[0]["revision"], rows[0]["current"]) == (80, True)
    assert rows[-1]["revision"] == 31  # the oldest 30 were dropped
    assert service.get("test", doc["id"])["body"] == "text 80"
    assert service.revision("test", doc["id"], 31)["body"] == "text 31"
    with pytest.raises(DocumentNotFound):
        service.revision("test", doc["id"], 30)


# ------------------------------------------------------------------------------ the store


def test_the_store_refuses_unsafe_keys_and_ids(tmp_path):
    for key in ("../x", "A", "a/b", ""):
        with pytest.raises(ValueError):
            DocumentStore(tmp_path, key)
    store = DocumentStore(tmp_path, "test")
    with pytest.raises(ValueError):
        store.read("../DOC-0001")
