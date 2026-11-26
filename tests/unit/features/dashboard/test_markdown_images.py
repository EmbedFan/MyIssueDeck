"""FEA-0013: image:<id> addresses in the Markdown renderer (static/js/markdown.js)."""

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
const calls = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = calls.map(([source, project]) => context.renderMarkdown(source, project));
process.stdout.write(JSON.stringify(outputs));
"""


def render(*calls):
    """Each call is (markdown source, project key or None)."""
    result = subprocess.run(
        [NODE, "-e", RUNNER, str(STATIC / "marked.min.js"), str(STATIC / "markdown.js")],
        input=json.dumps([list(call) for call in calls]),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def one(source, project="example"):
    return render((source, project))[0]


def test_an_image_address_becomes_the_dashboard_address_of_the_image():
    html = one("![Pump layout](image:IMG-0001)")

    assert '<img src="/dashboard/example/images/IMG-0001/file" alt="Pump layout"' in html


def test_a_link_to_an_image_opens_in_a_new_page():
    html = one("[the diagram](image:IMG-0042)")

    assert '<a href="/dashboard/example/images/IMG-0042/file"' in html
    assert 'target="_blank" rel="noopener"' in html
    assert ">the diagram</a>" in html


def test_the_project_key_is_encoded_in_the_address():
    html = one("![x](image:IMG-0001)", "a b/c")

    assert 'src="/dashboard/a%20b%2Fc/images/IMG-0001/file"' in html


def test_without_a_project_the_image_is_not_shown():
    html = one("![Pump layout](image:IMG-0001)", None)

    assert "<img" not in html
    assert "Pump layout" in html


@pytest.mark.parametrize("address", [
    "image:IMG-1", "image:IMG-0001/../../x", "image:../x", "image:IMG-0001.svg",
    "image:img-0001", "image: IMG-0001 x", "IMAGE:IMG-0001", "image:IMG-0001%2f..",
    "image://evil.test/x", "image:javascript:alert(1)",
])
def test_only_a_well_formed_image_id_is_accepted(address):
    html = one(f"![alt]({address})")

    assert "<img" not in html
    assert "/dashboard/" not in html


def test_the_project_does_not_leak_into_the_next_render():
    first, second = render(("![a](image:IMG-0001)", "example"), ("![a](image:IMG-0001)", None))

    assert "<img" in first
    assert "<img" not in second


def test_the_other_addresses_are_unchanged():
    html = one(
        "![ok](/dashboard/example/images/IMG-0001/file) ![bad](javascript:alert(1)) "
        "![bad2](data:image/svg+xml;base64,AAAA) [site](https://example.com/)"
    )

    assert 'src="/dashboard/example/images/IMG-0001/file"' in html
    assert "javascript:" not in html
    assert "data:" not in html
    assert 'href="https://example.com/"' in html
