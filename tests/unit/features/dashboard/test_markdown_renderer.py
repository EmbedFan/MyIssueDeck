"""IS-0004: the Markdown renderer (static/js/markdown.js) run in Node with the bundled marked."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
STATIC = (
    Path(__file__).resolve().parents[4]
    / "src" / "issuedeck" / "features" / "dashboard" / "static" / "js"
)

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")

RUNNER = r"""
const vm = require('vm');
const fs = require('fs');
const [markedPath, rendererPath] = process.argv.slice(1);
const context = { console };
context.window = context;
context.globalThis = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(markedPath, 'utf8'), context);
vm.runInContext(fs.readFileSync(rendererPath, 'utf8'), context);
const inputs = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = inputs.map((source) => context.renderMarkdown(source));
process.stdout.write(JSON.stringify(outputs));
"""


def render(*sources):
    result = subprocess.run(
        [NODE, "-e", RUNNER, str(STATIC / "marked.min.js"), str(STATIC / "markdown.js")],
        input=json.dumps(list(sources)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def one(source):
    return render(source)[0]


def test_headings_lists_tables_and_code_are_converted():
    html = one(
        "# Title\n\n## Part\n\n- a\n- b\n\n1. one\n2. two\n\n"
        "| h1 | h2 |\n|---|---|\n| c1 | c2 |\n\n```\nplain code\n```\n\n"
        "text with `inline` and **bold** and *italic*"
    )

    for fragment in (
        "<h1>", "<h2>", "<ul>", "<ol>", "<table>", "<th>", "<td>", "<pre><code>",
        "<code>inline</code>", "<strong>bold</strong>", "<em>italic</em>",
    ):
        assert fragment in html, fragment


def test_blockquote_survives():
    assert "<blockquote>" in one("> a quoted line")


def test_task_lists_get_checkboxes():
    html = one("- [ ] todo\n- [x] done")

    assert html.count('type="checkbox"') == 2


def test_special_characters_are_preserved_in_text_and_code():
    html = one("a < b && c > d with \"quotes\" and 'single'\n\n```\nif (x < 1 && y > 2) {}\n```")

    assert "a &lt; b &amp;&amp; c &gt; d" in html
    assert "if (x &lt; 1 &amp;&amp; y &gt; 2) {}" in html
    assert "&amp;lt;" not in html  # not escaped twice


def test_arrows_and_unicode_are_untouched():
    html = one("routes -> service -> repo, árvíztűrő tükörfúrógép, 日本語")

    assert "routes -&gt; service -&gt; repo" in html
    assert "árvíztűrő tükörfúrógép" in html
    assert "日本語" in html


def test_raw_html_is_shown_as_text_not_executed():
    html = one(
        '<script>alert(1)</script>\n\nhello <img src=x onerror=alert(1)> end\n\n'
        '<b onclick="x()">b</b>'
    )

    assert "<script" not in html
    assert "<img" not in html
    assert "<b " not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


@pytest.mark.parametrize("target", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "  javascript:alert(1)",
    "vbscript:msgbox(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "file:///etc/passwd",
])
def test_unsafe_link_addresses_are_not_active(target):
    html = one(f"[click me]({target})")

    assert "href=" not in html
    assert "click me" in html


def test_unsafe_image_addresses_are_not_active():
    html = one("![alt text](javascript:alert(1))\n\n![d](data:image/png;base64,AAAA)")

    assert "<img" not in html
    assert "alt text" in html


def test_external_links_open_safely_in_a_new_tab():
    html = one('[site](https://example.com "tip")')

    assert 'href="https://example.com"' in html
    assert 'title="tip"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_relative_and_mail_links_work_without_a_new_tab():
    html = one("[home](/dashboard/a) and [mail](mailto:me@example.com) and [anchor](#top)")

    assert 'href="/dashboard/a"' in html
    assert 'href="mailto:me@example.com"' in html
    assert 'href="#top"' in html
    assert "_blank" not in html


def test_safe_images_are_rendered():
    html = one("![logo](https://example.com/a.png \"t\")")

    assert '<img src="https://example.com/a.png"' in html
    assert 'alt="logo"' in html
    assert 'loading="lazy"' in html


def test_quotes_in_urls_cannot_break_out_of_the_attribute():
    html = one('[x](https://example.com/"onmouseover="alert(1))')

    assert 'onmouseover="alert' not in html


def test_empty_values_give_empty_output():
    assert render("", None) == ["", ""]


def test_the_global_marked_is_left_alone():
    # The renderer uses its own instance, so marked.parse keeps its default behaviour.
    script = RUNNER.replace(
        "const outputs = inputs.map((source) => context.renderMarkdown(source));",
        "const outputs = inputs.map(() => context.marked.parse('<b>raw</b>'));",
    )
    probe = subprocess.run(
        [NODE, "-e", script, str(STATIC / "marked.min.js"), str(STATIC / "markdown.js")],
        input=json.dumps(["x"]), capture_output=True, text=True, encoding="utf-8", timeout=60,
    )

    assert probe.returncode == 0, probe.stderr
    assert "<b>raw</b>" in json.loads(probe.stdout)[0]
