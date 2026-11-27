"""FEA-0010 phase 1: the search query model, its validation and its description."""

import copy

import pytest

from issuedeck.core.errors import InvalidSearch
from issuedeck.features.search.query import (
    Group,
    Kind,
    Status,
    Text,
    describe,
    parse_query,
    terms,
)

KINDS = ["feature", "bug", "task"]
STATUSES = ["proposed", "in_progress", "done"]

EXAMPLE = {"items": [
    {"type": "text", "mode": "regex", "value": r"import(ing)?\b", "fields": ["title", "body"]},
    {"op": "and", "type": "kind", "values": ["bug"]},
    {"op": "and", "group": [
        {"type": "status", "values": ["proposed"]},
        {"op": "or", "type": "status", "values": ["in_progress"]},
    ]},
]}


def parse(data, **kw):
    return parse_query(data, KINDS, STATUSES, **kw)


def refused(data, message, **kw):
    with pytest.raises(InvalidSearch) as error:
        parse(data, **kw)
    assert message in error.value.message, error.value.message
    return error.value


# ------------------------------------------------------------------------------ a valid query


def test_the_example_of_the_request_is_a_valid_query():
    query = parse(EXAMPLE)

    first, second, third = query.items
    assert (first.op, second.op, third.op) == (None, "and", "and")
    assert isinstance(first.node, Text)
    assert (first.node.mode, first.node.value, first.node.fields) == (
        "regex", r"import(ing)?\b", ("title", "body"))
    assert isinstance(second.node, Kind) and second.node.values == ("bug",)
    assert isinstance(third.node, Group)
    inner = third.node.items
    assert [i.op for i in inner] == [None, "or"]
    assert isinstance(inner[0].node, Status) and inner[1].node.values == ("in_progress",)


def test_defaults_of_a_text_block():
    query = parse({"items": [{"type": "text", "value": "import csv"}]})

    block = query.items[0].node
    assert (block.mode, block.fields, block.case_sensitive) == ("simple", ("title", "body"), False)


def test_the_data_is_not_changed():
    data = copy.deepcopy(EXAMPLE)

    parse(data)

    assert data == EXAMPLE


# ------------------------------------------------------------------------------ the shape


@pytest.mark.parametrize("data", [None, [], "text", {}, {"items": []}, {"items": "x"},
                                  {"items": [{"type": "kind", "values": ["bug"]}], "extra": 1}])
def test_a_search_is_an_object_with_a_list_of_blocks(data):
    with pytest.raises(InvalidSearch):
        parse(data)


def test_the_first_block_has_no_operator_and_the_others_need_one():
    refused({"items": [{"op": "and", "type": "kind", "values": ["bug"]}]},
            "the first block has no operator")
    refused({"items": [{"type": "kind", "values": ["bug"]},
                       {"type": "kind", "values": ["task"]}]}, "'op' must be one of")
    refused({"items": [{"type": "kind", "values": ["bug"]},
                       {"op": "xor", "type": "kind", "values": ["task"]}]}, "'op' must be one of")


def test_a_block_has_either_a_type_or_a_group():
    refused({"items": [{"values": ["bug"]}]}, "either 'type' or 'group'")
    refused({"items": [{"type": "kind", "values": ["bug"], "group": []}]},
            "either 'type' or 'group'")
    refused({"items": ["bug"]}, "a block must be an object")


def test_unknown_keys_are_refused():
    refused({"items": [{"type": "kind", "values": ["bug"], "colour": "red"}]}, "unknown keys")
    refused({"items": [{"type": "text", "value": "x", "boost": 2}]}, "unknown keys")
    refused({"items": [{"group": [{"type": "kind", "values": ["bug"]}], "name": "g"}]},
            "unknown keys")
    refused({"items": [{"type": "wildcard", "value": "x"}]}, "unknown block type")


def test_the_path_of_the_fault_is_given():
    error = refused(EXAMPLE | {"items": [*EXAMPLE["items"][:2], {"op": "and", "group": [
        {"type": "status", "values": ["proposed"]},
        {"op": "or", "type": "status", "values": ["nope"]}]}]}, "unknown status")

    assert error.details["path"] == "items[2].group[1]"
    assert error.details["allowed"] == STATUSES
    assert error.message.startswith("items[2].group[1]: ")


# ------------------------------------------------------------------------------ nesting


def test_a_group_inside_a_group_is_refused():
    deep = {"items": [
        {"type": "kind", "values": ["bug"]},
        {"op": "and", "group": [
            {"type": "status", "values": ["proposed"]},
            {"op": "or", "group": [{"type": "status", "values": ["done"]}]},
        ]},
    ]}

    error = refused(deep, "groups can be nested 2 levels at most")
    assert error.details["path"] == "items[1].group[1]"


def test_the_depth_is_a_parameter_so_deeper_nesting_can_be_allowed_later():
    deep = {"items": [{"group": [{"group": [{"group": [{"type": "kind", "values": ["bug"]}]}]}]}]}

    refused(deep, "nested 2 levels", max_depth=2)
    refused(deep, "nested 3 levels", max_depth=3)
    assert isinstance(parse(deep, max_depth=4).items[0].node, Group)


def test_a_group_must_not_be_empty():
    refused({"items": [{"group": []}]}, "non-empty list")


def test_at_most_twenty_blocks():
    blocks = [{"type": "kind", "values": ["bug"]}] + [
        {"op": "or", "type": "kind", "values": ["task"]} for _ in range(19)]

    assert len(parse({"items": blocks}).items) == 20
    refused({"items": [*blocks, {"op": "or", "type": "kind", "values": ["task"]}]},
            "at most 20 blocks")
    refused({"items": blocks[:3]}, "at most 2 blocks", max_blocks=2)


def test_the_blocks_of_the_groups_count_too():
    group = {"group": [{"type": "kind", "values": ["bug"]}] + [
        {"op": "or", "type": "kind", "values": ["task"]} for _ in range(9)]}
    two_groups = {"items": [group, {"op": "and", **copy.deepcopy(group)}]}

    assert len(parse(two_groups).items) == 2  # 20 blocks
    two_groups["items"].append({"op": "or", "type": "kind", "values": ["bug"]})
    refused(two_groups, "at most 20 blocks")


# ------------------------------------------------------------------------------ kinds and statuses


def test_values_must_be_kinds_and_statuses_of_the_project():
    refused({"items": [{"type": "kind", "values": ["epic"]}]}, "unknown kind 'epic'")
    refused({"items": [{"type": "status", "values": ["blocked"]}]}, "unknown status 'blocked'")
    refused({"items": [{"type": "kind", "values": ["bug", "bug"]}]}, "listed twice")
    refused({"items": [{"type": "kind", "values": []}]}, "non-empty list")
    refused({"items": [{"type": "kind"}]}, "non-empty list")
    refused({"items": [{"type": "kind", "values": "bug"}]}, "non-empty list")
    refused({"items": [{"type": "kind", "values": [3]}]}, "unknown kind")


# ------------------------------------------------------------------------------ text blocks


def test_text_blocks_are_checked():
    refused({"items": [{"type": "text", "value": ""}]}, "not empty")
    refused({"items": [{"type": "text", "value": "   "}]}, "not empty")
    refused({"items": [{"type": "text"}]}, "not empty")
    refused({"items": [{"type": "text", "value": 5}]}, "not empty")
    refused({"items": [{"type": "text", "value": "x", "mode": "fuzzy"}]}, "'mode' must be one of")
    refused({"items": [{"type": "text", "value": "x", "fields": []}]}, "'fields' must be")
    refused({"items": [{"type": "text", "value": "x", "fields": ["tags"]}]}, "'fields' must be")
    refused({"items": [{"type": "text", "value": "x", "fields": ["title", "title"]}]},
            "'fields' must be")
    refused({"items": [{"type": "text", "value": "x", "case_sensitive": "yes"}]},
            "true or false")


def test_the_full_text_index_ignores_case_so_simple_mode_cannot_be_case_sensitive():
    refused({"items": [{"type": "text", "value": "x", "case_sensitive": True}]},
            "works only with mode 'regex'")
    query = parse({"items": [{"type": "text", "mode": "regex", "value": "x",
                              "case_sensitive": True}]})
    assert query.items[0].node.case_sensitive is True


def test_the_length_of_the_text_is_limited():
    parse({"items": [{"type": "text", "value": "a" * 500}]})
    refused({"items": [{"type": "text", "value": "a" * 501}]}, "longer than 500")
    parse({"items": [{"type": "text", "mode": "regex", "value": "a" * 200}]})
    refused({"items": [{"type": "text", "mode": "regex", "value": "a" * 201}]},
            "longer than 200")


@pytest.mark.parametrize("pattern", ["(", "[a-", "*a", "(?P<x>", "a{2,1}", "\\"])
def test_an_invalid_regular_expression_is_refused_with_the_reason(pattern):
    refused({"items": [{"type": "text", "mode": "regex", "value": pattern}]},
            "the regular expression is not valid")


@pytest.mark.parametrize("pattern", ["(a+)+$", "(a*)*", "(.*)*x", r"(\w+\s?)+$", "((a+))+",
                                     "(?:a+)+", "(a|b+)+", "(x(y*)z)+"])
def test_a_repeat_inside_an_unbounded_repeat_is_refused(pattern):
    refused({"items": [{"type": "text", "mode": "regex", "value": pattern}]},
            "a repeat inside a repeat")


@pytest.mark.parametrize("pattern", [
    r"import(ing)?\b", "(ab)+", "a+b+c*", r"[a-z]+@[a-z]+\.com", r"(\d{4}-)+", "(?:foo|bar)+",
    r"^\s*#\s", r"TODO(\(\w+\))?:", "colou?r", "(a{2})*", r"\bFEAT-\d{4}\b",
])
def test_ordinary_regular_expressions_are_accepted(pattern):
    parse({"items": [{"type": "text", "mode": "regex", "value": pattern}]})


# ------------------------------------------------------------------------------ the meaning


def _ids(chains):
    return [[i.node.values[0] for i in chain] for chain in chains]


def test_and_binds_tighter_than_or():
    query = parse({"items": [
        {"type": "kind", "values": ["feature"]},
        {"op": "and", "type": "kind", "values": ["bug"]},
        {"op": "or", "type": "kind", "values": ["task"]},
        {"op": "and", "type": "status", "values": ["done"]},
    ]})

    assert _ids(terms(query.items)) == [["feature", "bug"], ["task", "done"]]


def test_describe_shows_the_search_in_words_with_brackets():
    assert describe(parse(EXAMPLE)) == (
        'title+body match regex "import(ing)?\\b" AND kind is bug AND '
        "(status is proposed OR status is in_progress)")
    mixed = parse({"items": [
        {"type": "kind", "values": ["bug"]},
        {"op": "and", "type": "status", "values": ["done"]},
        {"op": "or", "type": "text", "value": "search", "fields": ["title"]},
    ]})
    assert describe(mixed) == '(kind is bug AND status is done) OR title match words "search"'
    one = parse({"items": [{"type": "kind", "values": ["bug", "task"]}]})
    assert describe(one) == "kind is bug or task"
    sensitive = parse({"items": [{"type": "text", "mode": "regex", "value": "X",
                                  "case_sensitive": True}]})
    assert describe(sensitive).endswith(", case sensitive")
