"""Unit tests for the FormSpec DSL parser."""

import pytest
from form_producer.parser import ParseError, parse_spec


# ---------------------------------------------------------------------------
# Blank lines and comments
# ---------------------------------------------------------------------------

def test_blank_lines_ignored():
    dirs, fields = parse_spec("\n\n\n")
    assert fields == []


def test_comment_lines_ignored():
    dirs, fields = parse_spec("# just a comment\n# another comment\n")
    assert fields == []


def test_comment_does_not_produce_field():
    dirs, fields = parse_spec("# not a field\nname -- str<30>\n")
    assert len(fields) == 1
    assert fields[0]["id"] == "name"


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

def test_directive_channel():
    dirs, _ = parse_spec("# channel: my-chan\n")
    assert dirs["channel"] == "my-chan"


def test_directive_outbox():
    dirs, _ = parse_spec("# outbox: ./mybox\n")
    assert dirs["outbox"] == "./mybox"


def test_directive_channel_trimmed():
    dirs, _ = parse_spec("#  channel:   spaced  \n")
    assert dirs["channel"] == "spaced"


def test_unknown_directive_is_just_a_comment():
    dirs, _ = parse_spec("# something: else\n")
    assert "something" not in dirs


# ---------------------------------------------------------------------------
# Field types
# ---------------------------------------------------------------------------

def test_str_field():
    _, fields = parse_spec("name -- str<30>\n")
    assert fields[0] == {"id": "name", "type": "str", "width": 30}


def test_text_field():
    _, fields = parse_spec("notes -- text<60,5>\n")
    assert fields[0] == {"id": "notes", "type": "text", "width": 60, "height": 5}


def test_bool_field():
    _, fields = parse_spec("active -- bool\n")
    assert fields[0] == {"id": "active", "type": "bool"}


def test_date_field():
    _, fields = parse_spec("today -- date\n")
    assert fields[0] == {"id": "today", "type": "date"}


def test_time_field():
    _, fields = parse_spec("now -- time\n")
    assert fields[0] == {"id": "now", "type": "time"}


def test_fixed_field():
    _, fields = parse_spec('label -- "hello world"\n')
    assert fields[0] == {"id": "label", "type": "fixed", "value": "hello world"}


def test_fixed_field_empty_string():
    _, fields = parse_spec('empty -- ""\n')
    assert fields[0] == {"id": "empty", "type": "fixed", "value": ""}


def test_fixed_field_malformed():
    with pytest.raises(ParseError, match="malformed fixed value"):
        parse_spec('x -- "unclosed\n')


def test_int_field():
    _, fields = parse_spec("count -- int<10>\n")
    assert fields[0] == {"id": "count", "type": "int", "width": 10}


def test_float_field():
    _, fields = parse_spec("ratio -- float<15>\n")
    assert fields[0] == {"id": "ratio", "type": "float", "width": 15}


def test_json_field():
    _, fields = parse_spec("payload -- json<60,10>\n")
    assert fields[0] == {"id": "payload", "type": "json", "width": 60, "height": 10}


def test_choice_field():
    _, fields = parse_spec("priority -- choice<low,medium,high>\n")
    assert fields[0] == {"id": "priority", "type": "choice", "items": ["low", "medium", "high"]}


def test_choice_items_trimmed():
    _, fields = parse_spec("size -- choice< small , large >\n")
    assert fields[0]["items"] == ["small", "large"]


# ---------------------------------------------------------------------------
# Inline comments on field lines
# ---------------------------------------------------------------------------

def test_inline_comment_stripped():
    _, fields = parse_spec("name -- str<30>  # user's name\n")
    assert fields[0]["type"] == "str"
    assert fields[0]["width"] == 30


# ---------------------------------------------------------------------------
# Field ordering preserved
# ---------------------------------------------------------------------------

def test_field_order_preserved():
    dsl = "alpha -- str<10>\nbeta -- bool\ngamma -- int<5>\n"
    _, fields = parse_spec(dsl)
    assert [f["id"] for f in fields] == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_error_missing_separator():
    with pytest.raises(ParseError, match="missing '--'"):
        parse_spec("badline\n")


def test_error_empty_identifier():
    with pytest.raises(ParseError, match="empty identifier"):
        parse_spec(" -- str<10>\n")


def test_error_duplicate_identifier():
    with pytest.raises(ParseError, match="duplicate identifier"):
        parse_spec("name -- str<10>\nname -- str<20>\n")


def test_error_unknown_type():
    with pytest.raises(ParseError, match="unknown type"):
        parse_spec("x -- widget<10>\n")


def test_error_missing_angle_bracket():
    with pytest.raises(ParseError, match="unknown type"):
        parse_spec("x -- str\n")


def test_error_missing_closing_bracket():
    with pytest.raises(ParseError, match="missing '>'"):
        parse_spec("x -- str<10\n")


def test_error_non_integer_width():
    with pytest.raises(ParseError, match="integer"):
        parse_spec("x -- str<abc>\n")


def test_error_zero_width():
    with pytest.raises(ParseError, match=">= 1"):
        parse_spec("x -- str<0>\n")


def test_error_text_wrong_arity():
    with pytest.raises(ParseError, match="width,height"):
        parse_spec("x -- text<10>\n")


def test_error_choice_empty_item():
    with pytest.raises(ParseError, match="empty item"):
        parse_spec("x -- choice<a,,b>\n")


def test_error_includes_line_number():
    with pytest.raises(ParseError, match="Line 2"):
        parse_spec("good -- str<10>\nbadline\n")
