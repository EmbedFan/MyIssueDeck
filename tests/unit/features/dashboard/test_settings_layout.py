"""IS-0005: field rows and cards on the Settings page stay aligned."""

import re
from pathlib import Path

from issuedeck.features.dashboard import i18n, i18n_hu

TEMPLATE = (
    Path(i18n.__file__).parent / "templates" / "pages" / "settings.html"
).read_text(encoding="utf-8")


def test_field_rows_align_inputs_to_a_common_line():
    rows = re.findall(r'<div class="([^"]*)" data-settings-row>', TEMPLATE)
    # the widget and live-update sections, and the GitHub section (FEA-0008), have such rows
    assert len(rows) >= 2
    for classes in rows:
        assert "items-end" in classes.split()


def test_side_by_side_cards_share_one_structure():
    assert "data-settings-cards" in TEMPLATE
    for name in ("display", "tracking"):
        section = re.search(
            rf'<section class="[^"]*" aria-labelledby="settings-{name}">(.*?)</section>',
            TEMPLATE,
            re.S,
        )
        assert section, name
        assert "flex flex-col" in TEMPLATE.split(f'aria-labelledby="settings-{name}"')[0][-120:]
        body = section.group(1)
        assert f'settings.{name}_help' in body  # a description line in both cards
        assert "flex flex-1 flex-col" in body  # the form fills the card
        assert 'class="mt-auto"' in body  # Save sits on the bottom edge


def test_display_description_is_translated():
    for catalogue in (i18n._MESSAGES["en"], i18n_hu.MESSAGES_HU):
        assert catalogue["settings.display_help"]
