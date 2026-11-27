"""FEA-0010 phase 1: running a search query against the items of a project."""

import time

import pytest
from sqlalchemy import func, select

from issuedeck.core.errors import InvalidSearch
from issuedeck.features.items.models import Item
from issuedeck.features.search.evaluator import fts_match, run_query
from issuedeck.features.search.query import parse_query

KINDS = ["feature", "bug", "task"]
STATUSES = ["proposed", "in_progress", "done"]


def query(*items):
    return parse_query({"items": list(items)}, KINDS, STATUSES)


def text(value, mode="simple", **extra):
    return {"type": "text", "mode": mode, "value": value, **extra}


def kind(*values):
    return {"type": "kind", "values": list(values)}


def status(*values):
    return {"type": "status", "values": list(values)}


def _item(project, local_id, kind_, status_, title, body, minute, deleted=False):
    stamp = f"2026-11-27T10:{minute:02d}:00+00:00"
    return Item(
        project_key=project, local_id=local_id, kind=kind_, status=status_, title=title,
        body=body, custom_fields_json="{}", created_at=stamp, updated_at=stamp,
        deleted_at=stamp if deleted else None,
    )


@pytest.fixture
async def items(migrated_session):
    """Six items of project p (one deleted) and one of another project."""
    session = migrated_session
    session.add_all([
        _item("p", "FEAT-0001", "feature", "proposed", "Import of CSV files",
              "The importer reads CSV files.", 1),
        _item("p", "FEAT-0002", "feature", "in_progress", "Export to GitHub",
              "Import and export of snapshots.", 2),
        _item("p", "BUG-0001", "bug", "proposed", "Import fails on an empty file",
              "Stack trace of the failure.", 3),
        _item("p", "BUG-0002", "bug", "done", "Search is slow",
              "The regular expression search takes long.", 4),
        _item("p", "TASK-0001", "task", "done", "Release notes",
              "Write them. Importing is done.", 5),
        _item("p", "BUG-0003", "bug", "proposed", "Import deleted bug", "gone", 6, deleted=True),
        _item("other", "FEAT-0001", "feature", "proposed", "Import elsewhere", "other project", 7),
    ])
    await session.commit()
    return session


async def ids(session, q, **kw):
    result = await run_query(session, "p", q, **kw)
    rows = (await session.execute(select(Item.pk, Item.local_id).where(
        Item.project_key == "p"))).all()
    names = dict(rows)
    return [names[pk] for pk in result.pks]


# ------------------------------------------------------------------------------ simple text


async def test_words_are_found_in_title_and_body_newest_first(items):
    # the index stems words (tokenizer "porter"): "import" also finds "Importing" and "importer"
    assert await ids(items, query(text("import"))) == [
        "TASK-0001", "BUG-0001", "FEAT-0002", "FEAT-0001"]


async def test_all_words_must_occur_in_any_order(items):
    assert await ids(items, query(text("files csv"))) == ["FEAT-0001"]
    assert await ids(items, query(text("import export"))) == ["FEAT-0002"]
    assert await ids(items, query(text("import nonexistentword"))) == []


async def test_the_fields_can_be_chosen(items):
    assert await ids(items, query(text("import", fields=["title"]))) == ["BUG-0001", "FEAT-0001"]
    assert await ids(items, query(text("import", fields=["body"]))) == [
        "TASK-0001", "FEAT-0002", "FEAT-0001"]
    assert await ids(items, query(text("stack trace", fields=["body"]))) == ["BUG-0001"]
    assert await ids(items, query(text("stack trace", fields=["title"]))) == []


async def test_a_deleted_item_and_another_project_never_match(items):
    found = await run_query(items, "p", query(text("import")))
    assert 6 not in found.pks
    other = await run_query(items, "other", query(text("import")))
    assert len(other.pks) == 1


@pytest.mark.parametrize("value", [
    '" OR 1=1 --', "'; DROP TABLE items; --", "*", "OR", "AND", "NOT", "NEAR(a b)", '"', "'",
    "\\", "(", ")", "-import", "title:import", "^import", "{", "a b OR c", "%", "_",
    "import*", '""', "\x00", "日本語", "--",
])
async def test_special_text_is_only_text(items, value):
    """A word is never a command: nothing raises, nothing is injected, the table stays."""
    before = (await items.execute(select(func.count()).select_from(Item))).scalar()

    result = await run_query(items, "p", query(text(value.replace("\x00", "x"))))

    assert isinstance(result.pks, list) and not result.partial
    assert (await items.execute(select(func.count()).select_from(Item))).scalar() == before


async def test_an_operator_word_is_matched_as_a_word(items):
    items.add(_item("p", "TASK-0002", "task", "proposed", "One OR two", "or", 8))
    await items.commit()

    assert await ids(items, query(text("OR"))) == ["TASK-0002"]
    assert await ids(items, query(text("import OR export"))) == []  # three words, all required


def test_fts_match_quotes_every_word():
    assert fts_match('a "b" c', ("title", "body")) == '"a" """b""" "c"'
    assert fts_match("a b", ("title",)) == '{title} : ("a" "b")'
    assert fts_match("a", ("body", "title")) == '"a"'


# ------------------------------------------------------------------------------ kinds, statuses


async def test_kind_and_status_blocks(items):
    assert await ids(items, query(kind("bug"))) == ["BUG-0002", "BUG-0001"]
    assert await ids(items, query(kind("bug", "task"))) == ["TASK-0001", "BUG-0002", "BUG-0001"]
    assert await ids(items, query(status("done"))) == ["TASK-0001", "BUG-0002"]
    assert await ids(items, query(kind("feature"), {"op": "and", **status("in_progress")})) \
        == ["FEAT-0002"]


# ------------------------------------------------------------------------------ and, or, groups


async def test_and_is_an_intersection_and_or_is_a_union(items):
    both = query(text("import"), {"op": "and", **kind("bug")})
    either = query(text("search"), {"op": "or", **kind("task")})

    assert await ids(items, both) == ["BUG-0001"]
    assert await ids(items, either) == ["TASK-0001", "BUG-0002"]


async def test_and_binds_tighter_than_or(items):
    # import AND bug  OR  search   ==   (import AND bug) OR search
    q = query(text("import"), {"op": "and", **kind("bug")}, {"op": "or", **text("search")})

    assert await ids(items, q) == ["BUG-0002", "BUG-0001"]
    # search  OR  import AND bug   ==   search OR (import AND bug): the same set
    q = query(text("search"), {"op": "or", **text("import")}, {"op": "and", **kind("bug")})
    assert await ids(items, q) == ["BUG-0002", "BUG-0001"]
    # without the precedence it would be (search OR import) AND bug = the same here, so make
    # a case that tells them apart: feature OR bug AND done  ->  feature OR (bug AND done)
    q = query(kind("feature"), {"op": "or", **kind("bug")}, {"op": "and", **status("done")})
    assert await ids(items, q) == ["BUG-0002", "FEAT-0002", "FEAT-0001"]


async def test_a_group_changes_the_order_of_evaluation(items):
    # feature OR (bug AND done) differs from (feature OR bug) AND done
    plain = query(kind("feature"), {"op": "or", **kind("bug")}, {"op": "and", **status("done")})
    grouped = query(
        {"group": [kind("feature"), {"op": "or", **kind("bug")}]},
        {"op": "and", **status("done")},
    )

    assert await ids(items, plain) == ["BUG-0002", "FEAT-0002", "FEAT-0001"]
    assert await ids(items, grouped) == ["BUG-0002"]


async def test_the_example_of_the_request(items):
    # text AND kind is bug AND (status proposed OR in_progress)
    q = query(
        text("import"),
        {"op": "and", **kind("bug")},
        {"op": "and", "group": [status("proposed"), {"op": "or", **status("in_progress")}]},
    )

    assert await ids(items, q) == ["BUG-0001"]


# ------------------------------------------------------------------------------ regular expressions


async def test_a_regular_expression_ignores_case_by_default(items):
    q = query(text(r"import(ing|er)?\b", "regex"))

    assert await ids(items, q) == ["TASK-0001", "BUG-0001", "FEAT-0002", "FEAT-0001"]


async def test_case_sensitive_and_fields(items):
    assert await ids(items, query(text("^Import", "regex", case_sensitive=True,
                                       fields=["title"]))) == ["BUG-0001", "FEAT-0001"]
    assert await ids(items, query(text("^import", "regex", case_sensitive=True,
                                       fields=["title"]))) == []
    assert await ids(items, query(text("^import", "regex", fields=["title"]))) \
        == ["BUG-0001", "FEAT-0001"]
    assert await ids(items, query(text(r"\bfiles\.$", "regex", fields=["body"]))) == ["FEAT-0001"]


async def test_a_regular_expression_combines_with_the_other_blocks(items):
    q = query(text(r"^import", "regex", fields=["title"]), {"op": "and", **kind("bug")})
    assert await ids(items, q) == ["BUG-0001"]
    q = query(text(r"^release", "regex"), {"op": "or", **text("export")})
    assert await ids(items, q) == ["TASK-0001", "FEAT-0002"]


async def test_a_regular_expression_never_sees_deleted_items_or_other_projects(items):
    found = await run_query(items, "p", query(text("import", "regex")))
    assert 6 not in found.pks and len(found.pks) == 4


async def test_a_regular_expression_that_cannot_finish_is_stopped_and_reported(items):
    items.add(_item("p", "TASK-0009", "task", "proposed", "Long text", "a" * 3000, 9))
    await items.commit()
    # not a nested repeat, so it is accepted; on a text of 3000 letters it would run for ages
    q = query(text("a*a*a*a*a*a*a*b", "regex", fields=["body"]))

    started = time.monotonic()
    result = await run_query(items, "p", q, seconds=1.0)
    elapsed = time.monotonic() - started

    assert elapsed < 12  # the start of the process, one second of work, the kill
    assert result.pks == [] and result.partial
    assert any("did not finish in 1 s" in note for note in result.notes)


async def test_what_finished_is_kept_when_another_expression_runs_out_of_time(items):
    items.add(_item("p", "TASK-0009", "task", "proposed", "Long text", "a" * 3000, 9))
    await items.commit()
    quick = text(r"^release", "regex", fields=["title"])
    slow = text("a*a*a*a*a*a*a*b", "regex", fields=["body"])

    result = await run_query(items, "p", query(quick, {"op": "or", **slow}), seconds=1.0)

    names = {pk: name for pk, name in (await items.execute(
        select(Item.pk, Item.local_id).where(Item.project_key == "p"))).all()}
    assert [names[pk] for pk in result.pks] == ["TASK-0001"]  # the quick one is kept
    assert result.partial and len(result.notes) == 1


async def test_only_the_newest_items_are_given_to_the_expressions(items):
    result = await run_query(items, "p", query(text("import", "regex")), max_rows=2)

    assert result.partial
    assert any("at the newest 2 of 5 items" in note for note in result.notes)
    assert len(result.pks) <= 2


async def test_the_budget_is_not_used_when_there_is_no_regular_expression(items):
    started = time.monotonic()

    result = await run_query(items, "p", query(text("import"), {"op": "and", **kind("bug")}),
                             seconds=0.001)

    assert time.monotonic() - started < 2  # no process is started
    assert not result.partial and result.notes == []


async def test_an_unusable_full_text_query_is_reported_as_a_search_error(items, monkeypatch):
    import issuedeck.features.search.evaluator as evaluator

    monkeypatch.setattr(evaluator, "fts_match", lambda words, fields: "NEAR(")

    with pytest.raises(InvalidSearch, match="cannot be searched"):
        await run_query(items, "p", query(text("anything")))
