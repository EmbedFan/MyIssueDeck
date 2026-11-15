"""IS-0003: the compiled stylesheet must contain every class the settings templates use.

The dashboard CSS is precompiled (``npm run build:css``) and only holds the Tailwind
classes that existed when it was last built. A template that uses a class missing
from it renders wrongly (for example the token text running together), so this test
fails until the CSS is rebuilt.
"""

import re
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[4] / "src" / "issuedeck" / "features" / "dashboard"
CSS = (DASHBOARD / "static" / "css" / "dashboard.css").read_text(encoding="utf-8")
TEMPLATES = [
    DASHBOARD / "templates" / "pages" / "settings.html",
    DASHBOARD / "templates" / "components" / "token_card.html",
    DASHBOARD / "templates" / "components" / "sidebar_settings_link.html",
]

#: Class names that are set by the page's own CSS or scripts, not by Tailwind.
NOT_TAILWIND = {"x-cloak"}


def _classes(template: Path) -> set[str]:
    text = template.read_text(encoding="utf-8")
    names: set[str] = set()
    # Static class="..." attributes (not :class or data-class).
    for match in re.finditer(r'(?<![:\w-])class="([^"]*)"', text):
        value = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", " ", match.group(1), flags=re.S)
        names.update(token for token in value.split() if token)
    # Alpine :class="cond ? 'a b' : 'c'" expressions: the quoted strings are classes.
    for match in re.finditer(r':class="([^"]*)"', text):
        for quoted in re.findall(r"'([^']*)'", match.group(1)):
            names.update(token for token in quoted.split() if token)
    # Classes built in the page script (e.g. the scope badge).
    for match in re.finditer(r"className = '([^']*)'", text):
        names.update(token for token in match.group(1).split() if token)
    return names - NOT_TAILWIND


def _selector(name: str) -> str:
    # Tailwind escapes every character that is not [A-Za-z0-9_-] in a class selector.
    return "." + re.sub(r"([^A-Za-z0-9_-])", r"\\\1", name)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_every_class_in_the_template_exists_in_the_compiled_css(template):
    missing = sorted(name for name in _classes(template) if _selector(name) not in CSS)

    assert missing == [], (
        f"{template.name} uses classes that are missing from dashboard.css; "
        "run `npm run build:css`: " + ", ".join(missing)
    )


def test_the_css_check_can_fail():
    assert _selector("definitely-not-a-tailwind-class") not in CSS
    assert _selector("sm:flex-row") == r".sm\:flex-row"
