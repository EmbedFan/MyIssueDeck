"""Build the HTML help pages from their Markdown sources (IS-0007).

There is one source per supported language in ``help/src/<lang>.md``. Every second-level and
third-level heading carries an explicit anchor, ``## Title {#anchor}``, and the anchors are the
same in every language, so a link to a section works in all of them and a test can check that no
language lacks a section. The generated pages ``help/<lang>.html`` are committed and shipped with
the package; ``python scripts/build_help.py`` regenerates them, ``--check`` only compares.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from markdown_it import MarkdownIt

HELP_DIR = Path(__file__).parent / "help"
SOURCE_DIR = HELP_DIR / "src"

#: The label of the table of contents, in each language.
CONTENTS_LABEL = {"en": "Contents", "hu": "Tartalom", "zh-CN": "目录"}

_ANCHOR = re.compile(r"\s*\{#([a-z0-9-]+)\}\s*$")


def source_path(lang: str) -> Path:
    return SOURCE_DIR / f"{lang}.md"


def html_path(lang: str) -> Path:
    return HELP_DIR / f"{lang}.html"


def anchors(markdown: str) -> list[str]:
    """The section anchors of a source, in order."""
    pattern = re.compile(r"(?m)^#{2,3} .*\{#([a-z0-9-]+)\}\s*$")
    return [match.group(1) for match in pattern.finditer(markdown)]


def build_html(lang: str, markdown: str) -> str:
    """The help page fragment (table of contents and body) for one language."""
    parser = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
    tokens = parser.parse(markdown)
    contents: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag not in ("h2", "h3"):
            continue
        inline = tokens[index + 1]
        match = _ANCHOR.search(inline.content)
        if not match:
            raise ValueError(f"{lang}: the heading '{inline.content}' has no {{#anchor}}")
        anchor = match.group(1)
        if anchor in seen:
            raise ValueError(f"{lang}: the anchor '{anchor}' is used twice")
        seen.add(anchor)
        title = inline.content[: match.start()]
        inline.content = title
        inline.children = parser.parseInline(title)[0].children
        token.attrSet("id", anchor)
        contents.append((int(token.tag[1]), anchor, title))

    body = parser.renderer.render(tokens, parser.options, {})
    if "**" in body:
        # a bold marker that was not recognised: with CJK text, punctuation such as the
        # full-width colon must be written outside the marker ("**label**：text")
        raise ValueError(f"{lang}: a bold marker ** was left in the page; move punctuation outside")
    label = html.escape(CONTENTS_LABEL.get(lang, CONTENTS_LABEL["en"]))
    items = []
    for level, anchor, title in contents:
        indent = " pl-4" if level == 3 else ""
        items.append(
            f'<li class="py-0.5{indent}"><a href="#{anchor}" class="text-primary-700 '
            f'dark:text-primary-300 hover:underline">{html.escape(title)}</a></li>'
        )
    toc = (
        '<nav class="mb-6 rounded-md border border-ledger-line dark:border-ledger-darkLine '
        f'p-4 text-sm" aria-label="{label}" data-help-contents>'
        f'<p class="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 '
        f'dark:text-gray-400">{label}</p><ul>' + "".join(items) + "</ul></nav>"
    )
    return f'{toc}\n<div class="md-content help-body">\n{body}</div>\n'


def build_all(languages: list[str]) -> dict[str, str]:
    return {
        lang: build_html(lang, source_path(lang).read_text(encoding="utf-8"))
        for lang in languages
    }
