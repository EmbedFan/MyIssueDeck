"""FEA-0010 phase 4: the saved searches of a project (file store, import plan)."""

import json

import pytest

from issuedeck.core.errors import InvalidSearch
from issuedeck.features.search.saved import (
    MAX_NAME,
    MAX_SEARCHES,
    SavedSearchExists,
    SavedSearchNotFound,
    SavedSearchStore,
    apply_search_plan,
    check_snapshot_file,
    clean_name,
    normalise,
    plan_search_import,
)


def q(word="import"):
    return {"items": [{"type": "text", "mode": "simple", "value": word}]}


@pytest.fixture
def store(tmp_path):
    return SavedSearchStore(tmp_path, "demo")


def test_a_new_store_is_empty_and_writes_nothing(store, tmp_path):
    assert store.read() == {"active": None, "searches": []}
    assert store.is_empty() and store.read_bytes() is None
    assert not (tmp_path / "searches").exists()


def test_the_latest_search_is_remembered_with_or_without_a_name(store):
    store.set_active(q("a"))
    assert store.read()["active"] == {"name": None, "query": q("a")}

    store.set_active(q("b"), "Open bugs")

    assert store.read()["active"] == {"name": "Open bugs", "query": q("b")}
    assert store.path == store.path.parent / "demo.json"


def test_a_search_is_saved_by_name_and_becomes_the_latest(store):
    entry = store.save("  Open   bugs ", q())

    assert entry["name"] == "Open bugs"  # spaces collapsed
    data = store.read()
    assert [s["name"] for s in data["searches"]] == ["Open bugs"]
    assert data["searches"][0]["query"] == q()
    assert data["active"] == {"name": "Open bugs", "query": q()}
    assert store.get("open BUGS")["name"] == "Open bugs"  # found ignoring case


def test_a_name_that_is_taken_needs_permission_to_be_replaced(store):
    store.save("Open bugs", q("a"))

    with pytest.raises(SavedSearchExists) as error:
        store.save("open bugs", q("b"))
    assert error.value.details["name"] == "Open bugs"
    assert store.get("Open bugs")["query"] == q("a")  # nothing changed

    store.save("open bugs", q("b"), overwrite=True)

    assert [s["name"] for s in store.read()["searches"]] == ["open bugs"]
    assert store.get("open bugs")["query"] == q("b")


@pytest.mark.parametrize("name", ["", "   ", None, 5])
def test_a_name_is_required(store, name):
    with pytest.raises(InvalidSearch) as error:
        store.save(name, q())
    assert error.value.details["path"] == "name"
    assert store.is_empty()


def test_a_name_is_limited(store):
    assert clean_name("x" * MAX_NAME) == "x" * MAX_NAME
    with pytest.raises(InvalidSearch):
        clean_name("x" * (MAX_NAME + 1))


def test_a_project_holds_a_limited_number_of_searches(store):
    for number in range(MAX_SEARCHES):
        store.save(f"s{number:02d}", q(str(number)))

    with pytest.raises(InvalidSearch, match="at most"):
        store.save("one too many", q())
    store.save("s00", q("again"), overwrite=True)  # replacing one is not adding one

    assert len(store.read()["searches"]) == MAX_SEARCHES


def test_the_searches_are_sorted_by_name_ignoring_case(store):
    for name in ("banana", "Apple", "cherry"):
        store.save(name, q())

    assert [s["name"] for s in store.read()["searches"]] == ["Apple", "banana", "cherry"]


def test_a_search_is_renamed_and_the_latest_follows_its_name(store):
    store.save("Old", q())

    entry = store.rename("old", "New name")

    assert entry["name"] == "New name"
    data = store.read()
    assert [s["name"] for s in data["searches"]] == ["New name"]
    assert data["active"]["name"] == "New name"


def test_renaming_onto_another_name_asks_first_and_never_onto_itself(store):
    store.save("A", q("a"))
    store.save("B", q("b"))

    with pytest.raises(SavedSearchExists):
        store.rename("A", "b")
    store.rename("A", "a")  # only the case changes: that is not a clash
    store.rename("a", "B", overwrite=True)

    assert [s["name"] for s in store.read()["searches"]] == ["B"]
    assert store.get("B")["query"] == q("a")


def test_renaming_or_deleting_what_is_not_there_is_an_error(store):
    with pytest.raises(SavedSearchNotFound):
        store.rename("nope", "x")
    with pytest.raises(SavedSearchNotFound):
        store.delete("nope")
    with pytest.raises(SavedSearchNotFound):
        store.get("nope")


def test_deleting_a_search_keeps_it_as_the_latest_but_without_a_name(store):
    store.save("Keep", q("k"))
    store.save("Drop", q("d"))

    store.delete("drop")

    data = store.read()
    assert [s["name"] for s in data["searches"]] == ["Keep"]
    assert data["active"] == {"name": None, "query": q("d")}


def test_deleting_the_last_things_removes_the_file(store):
    store.save("Only", q())
    store.delete("Only")
    assert store.path.exists()  # the latest search is still kept
    store.delete_all()

    assert not store.path.exists() and not store.path.parent.exists()


def test_the_file_is_in_one_stable_form_and_leaves_no_temporary_file(store):
    store.save("B", q("b"))
    store.save("A", q("a"))

    text = store.path.read_text(encoding="utf-8")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False) + "\n" == text
    assert store.read_bytes() == text.encode("utf-8")
    assert [p.name for p in store.path.parent.iterdir()] == ["demo.json"]


def test_non_ascii_names_and_values_are_kept_as_they_are(store):
    store.save("Keresés – árvíztűrő", q("tükörfúrógép"))

    assert "Keresés – árvíztűrő" in store.path.read_text(encoding="utf-8")
    assert store.get("keresés – árvíztűrő")["query"] == q("tükörfúrógép")


@pytest.mark.parametrize("content", ["", "not json", "[]", "null", '{"searches": 5}'])
def test_a_damaged_file_reads_as_empty_and_does_not_stop_the_page(store, content):
    store.path.parent.mkdir(parents=True)
    store.path.write_text(content, encoding="utf-8")

    assert store.read() == {"active": None, "searches": []}
    store.save("Fresh", q())  # and it can be written over
    assert [s["name"] for s in store.read()["searches"]] == ["Fresh"]


def test_bad_entries_are_dropped_and_the_good_ones_kept():
    data = normalise({
        "active": {"name": "x", "query": {"nope": 1}},
        "searches": [
            {"name": "good", "query": q()},
            {"name": "", "query": q()},
            {"name": "no query"},
            {"name": "bad query", "query": {"items": "x"}},
            "text",
            {"name": "GOOD", "query": q("dup")},  # the same name ignoring case
            {"name": "x" * (MAX_NAME + 1), "query": q()},
        ],
    })

    assert data["active"] is None
    assert [s["name"] for s in data["searches"]] == ["good"]


@pytest.mark.parametrize("key", ["../evil", "a/b", "A", "", "x" * 70, "a b"])
def test_a_project_key_that_could_leave_the_folder_is_refused(tmp_path, key):
    with pytest.raises(ValueError):
        SavedSearchStore(tmp_path, key)


# ----------------------------------------------------------------------- the snapshot import


def snapshot(*names, active=None):
    return {"active": active, "searches": [{"name": n, "query": q(n)} for n in names]}


def test_an_import_adds_what_is_new_and_keeps_what_is_there(store):
    store.save("Mine", q("mine"))
    store.save("Same", q("Same"))  # the same search as in the snapshot
    store.save("Clash", q("here"))
    raw = snapshot("Same", "Clash", "New")
    raw["searches"][1]["query"] = q("there")  # a different search under the same name

    plan = plan_search_import(store, raw)

    assert [s["name"] for s in plan.add] == ["New"]
    assert plan.unchanged == 1
    assert plan.skipped == ["Clash (a different search has this name)"]
    assert plan.warnings and "Clash" in plan.warnings[0]
    assert store.get("Clash")["query"] == q("here")  # a plan writes nothing

    apply_search_plan(store, plan)

    assert [s["name"] for s in store.read()["searches"]] == ["Clash", "Mine", "New", "Same"]
    assert store.get("Clash")["query"] == q("here")


def test_the_latest_search_of_a_snapshot_is_taken_only_when_there_is_none(store):
    raw = snapshot("A", active={"name": "A", "query": q("A")})

    apply_search_plan(store, plan_search_import(store, raw))
    assert store.read()["active"] == {"name": "A", "query": q("A")}

    other = snapshot("B", active={"name": None, "query": q("other")})
    apply_search_plan(store, plan_search_import(store, other))

    assert store.read()["active"]["query"] == q("A")  # the project's own one stays


def test_an_import_stops_at_the_limit_and_says_so(store):
    for number in range(MAX_SEARCHES - 1):
        store.save(f"s{number:02d}", q(str(number)))

    plan = plan_search_import(store, snapshot("x1", "x2", "x3"))

    assert [s["name"] for s in plan.add] == ["x1"]
    assert len(plan.skipped) == 2 and "already has" in plan.skipped[0]


def test_nothing_to_import_does_nothing(store):
    plan = plan_search_import(store, None)
    undo = apply_search_plan(store, plan)

    undo()
    assert store.is_empty() and not store.path.parent.exists()


def test_an_applied_import_can_be_taken_back(store):
    plan = plan_search_import(store, snapshot("A", active={"name": "A", "query": q("A")}))
    undo = apply_search_plan(store, plan)
    assert not store.is_empty()

    undo()
    assert store.is_empty() and not store.path.exists()

    store.save("Before", q("b"))
    before = store.path.read_bytes()
    undo = apply_search_plan(store, plan_search_import(store, snapshot("C")))
    assert store.path.read_bytes() != before

    undo()
    assert store.path.read_bytes() == before


def test_a_snapshot_file_that_is_not_an_object_is_refused():
    check_snapshot_file({})
    with pytest.raises(InvalidSearch):
        check_snapshot_file([])
