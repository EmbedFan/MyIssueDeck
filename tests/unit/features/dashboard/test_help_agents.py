"""IS-0014: the Claude and Codex parts of the help, and their example prompts.

The documents must stay true: every tool they name exists on the MCP server, every tool of the
server is described, the prompt in the help is the prompt of the file in docs/agent-prompts, and the
languages have the same sections.
"""

import asyncio
import re
from pathlib import Path

import pytest

from issuedeck.features.dashboard.help_build import SOURCE_DIR, anchors

ROOT = Path(__file__).resolve().parents[4]
PROMPTS = ROOT / "docs" / "agent-prompts"
LANGUAGES = ("en", "hu", "zh-CN")
CLAUDE_ANCHORS = ("claude", "claude-connect", "claude-tools", "claude-method", "claude-prompt",
                  "claude-problems")
CODEX_ANCHORS = ("codex", "codex-connect", "codex-tools", "codex-prompt", "codex-problems")
#: names that look like tool names but are arguments of a tool
ARGUMENTS = {"append_body"}
TOOL_LIKE = re.compile(
    r"\b(?:list|get|create|update|delete|start|finish|ship|append|add|remove|search|bulk|upload)"
    r"_[a-z_]+\b"
)


def registered_tools() -> set[str]:
    from issuedeck.mcp import __main__ as entry

    server = entry.mcp_server
    found = asyncio.run(server.get_tools() if hasattr(server, "get_tools") else server.list_tools())
    return set(found) if isinstance(found, dict) else {tool.name for tool in found}


def source(lang: str) -> str:
    return (SOURCE_DIR / f"{lang}.md").read_text(encoding="utf-8")


def section(text: str, anchor: str) -> str:
    """The text of a section, from its heading to the next heading of the same or higher level."""
    heading = re.search(rf"(?m)^(#{{2,3}}) .*\{{#{anchor}\}}\s*$", text)
    assert heading, anchor
    level = len(heading.group(1))
    following = re.compile(rf"^#{{2,{level}}} ")
    position = heading.end()
    in_fence = False
    for line in text[heading.end():].splitlines(keepends=True):
        if line.startswith("```"):
            in_fence = not in_fence  # a "## " line inside a code block is not a heading
        elif not in_fence and following.match(line):
            return text[heading.start(): position]
        position += len(line)
    return text[heading.start():]


def prompt_of(file_name: str) -> str:
    text = (PROMPTS / file_name).read_text(encoding="utf-8")
    match = re.search(r"```text\n(.*?)\n```", text, re.S)
    assert match, file_name
    return match.group(1)


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_language_has_the_claude_and_codex_sections(lang):
    found = anchors(source(lang))

    for anchor in (*CLAUDE_ANCHORS, *CODEX_ANCHORS, "mcp"):
        assert anchor in found, f"{lang}: {anchor}"
    assert found.index("claude") < found.index("codex") < found.index("troubleshooting")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_every_tool_of_the_server_is_described_in_the_claude_tools_section(lang):
    tools_section = section(source(lang), "claude-tools")

    missing = sorted(name for name in registered_tools() if f"`{name}`" not in tools_section)

    assert missing == []


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_tools_named_in_the_agent_sections_exist(lang):
    text = source(lang)
    parts = section(text, "claude") + section(text, "codex")
    named = {name for name in TOOL_LIKE.findall(parts) if name not in ARGUMENTS}

    assert named, "the sections name no tool at all"
    assert sorted(named - registered_tools()) == []


@pytest.mark.parametrize("file_name", ["claude-prompt.md", "codex-prompt.md"])
def test_the_tools_named_in_a_prompt_exist(file_name):
    named = {name for name in TOOL_LIKE.findall(prompt_of(file_name)) if name not in ARGUMENTS}

    assert {"list_projects", "create_item", "start_work_session", "finish_work_session",
            "ship_item"} <= named
    assert sorted(named - registered_tools()) == []


@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize(("anchor", "file_name"), [
    ("claude-prompt", "claude-prompt.md"), ("codex-prompt", "codex-prompt.md"),
])
def test_the_prompt_in_the_help_is_the_prompt_of_the_file(lang, anchor, file_name):
    block = re.search(r"```text\n(.*?)\n```", section(source(lang), anchor), re.S)

    assert block is not None
    assert block.group(1) == prompt_of(file_name)


@pytest.mark.parametrize("file_name", ["claude-prompt.md", "codex-prompt.md"])
def test_a_prompt_names_the_whole_working_method_and_keeps_secrets_out(file_name):
    prompt = prompt_of(file_name)

    for needed in ("<project-key>", "get_project_config", "estimated_time", "time_spent",
                   "in_progress", "blocked", "ready_to_ship", "done", "never leave", "Never"):
        assert needed.lower() in prompt.lower(), needed
    assert "**" not in prompt  # the help builder refuses a bold marker
    assert not re.search(r"(?i)\b(token|password)\s*[:=]\s*\S{8,}", prompt)


def test_the_two_prompts_differ_only_by_what_belongs_to_the_agent():
    claude = prompt_of("claude-prompt.md").splitlines()
    codex = prompt_of("codex-prompt.md").splitlines()

    extra = [line for line in codex if line not in claude]
    assert len(extra) == 1 and "approval" in extra[0]
    assert [line for line in claude if line not in codex] == []


def test_the_prompt_files_are_not_named_like_instruction_files():
    # a CLAUDE.md or AGENTS.md in a sub-folder is read by the agents as standing instructions
    names = {path.name.lower() for path in PROMPTS.iterdir()}

    assert not names & {"claude.md", "agents.md", "claude.local.md"}
    assert names == {"claude-prompt.md", "codex-prompt.md"}


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_help_never_holds_a_real_token(lang):
    text = source(lang)

    assert "<your-token>" in text or "<az-On-tokenje>" in text or "<您的令牌>" in text
    assert not re.search(r"ISSUEDECK_TOKEN=(?!<)[A-Za-z0-9_-]{10,}", text)
