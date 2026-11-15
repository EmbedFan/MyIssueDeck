"""FEA-0005: Hungarian dashboard messages."""

import re

from issuedeck.features.dashboard.i18n import (
    _MESSAGES,
    DEFAULT_LANG,
    SUPPORTED_LANGS,
    make_translator,
)

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def test_hungarian_is_a_supported_language():
    assert "hu" in SUPPORTED_LANGS
    assert DEFAULT_LANG == "en"


def test_every_english_key_has_a_hungarian_translation():
    missing = sorted(set(_MESSAGES["en"]) - set(_MESSAGES["hu"]))

    assert missing == []


def test_no_hungarian_key_is_unknown_to_english():
    extra = sorted(set(_MESSAGES["hu"]) - set(_MESSAGES["en"]))

    assert extra == []


def test_placeholders_match_between_english_and_hungarian():
    mismatched = []
    for key, english in _MESSAGES["en"].items():
        hungarian = _MESSAGES["hu"][key]
        if set(PLACEHOLDER.findall(english)) != set(PLACEHOLDER.findall(hungarian)):
            mismatched.append(key)

    assert mismatched == []


def test_no_hungarian_message_is_empty_unless_english_is_empty():
    empty = [
        key for key, value in _MESSAGES["hu"].items()
        if not value.strip() and _MESSAGES["en"][key].strip()
    ]

    assert empty == []


def test_translator_returns_hungarian_and_formats_placeholders():
    t = make_translator("hu")

    assert t("nav.overview") == "Áttekintés"
    assert t("bulk.select_item", id="FEAT-0001") == "FEAT-0001 kiválasztása"
    assert t("home.time_overview_empty").startswith("Még nincs rögzített idő")


def test_unknown_language_falls_back_to_english():
    assert make_translator("xx")("nav.overview") == "Overview"


def test_language_label_is_available_in_every_language():
    for lang in _MESSAGES:
        assert make_translator(lang)("language.hu") == "Magyar"
