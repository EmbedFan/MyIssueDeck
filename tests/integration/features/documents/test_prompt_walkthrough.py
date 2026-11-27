"""IS-0014: the example prompts are tried.

An agent that follows the example prompt (docs/agent-prompts) must be able to do every step it
names with the real MCP tools. This test follows the prompt line by line against a real
application with the demo project, whose statuses are only proposed, in_progress, done and wontfix:
that is the case in which the prompt tells the agent to use the closest status.
"""

import re
from pathlib import Path

import pytest

from issuedeck.core.errors import DocumentConflict, InvalidStatus
from issuedeck.mcp import tools

from .test_mcp_tools import mcp  # noqa: F401

PROMPTS = Path(__file__).resolve().parents[4] / "docs" / "agent-prompts"
KEY = "example"  # the <project-key> the user fills in


def _prompt(name: str) -> str:
    text = (PROMPTS / name).read_text(encoding="utf-8")
    return re.search(r"```text\n(.*?)\n```", text, re.S).group(1)


@pytest.mark.parametrize("name", ["claude-prompt.md", "codex-prompt.md"])
async def test_following_the_prompt_step_by_step_works_with_the_real_tools(mcp, name):  # noqa: F811
    prompt = _prompt(name)
    assert "<project-key>" in prompt

    # First steps: list_projects, then get_project_config
    projects = await tools.list_projects()
    assert KEY in [p["key"] for p in projects["projects"]]
    config = await tools.get_project_config(KEY)
    kinds, statuses = set(config["kinds"]), set(config["statuses"])
    assert "feature" in kinds
    # the prompt names five statuses; this project has only some of them
    wanted = ["proposed", "in_progress", "blocked", "ready_to_ship", "done"]
    missing = [s for s in wanted if s not in statuses]
    assert missing == ["blocked", "ready_to_ship"]  # so the "closest status" rule is needed
    assert "use the closest one it lists" in prompt

    # Finding and creating items: look first, then create with an estimate
    assert (await tools.search_items(KEY, "walkthrough"))["items"] == []
    first = await tools.create_item(
        KEY, "feature", "Walkthrough item", body="The requirement as I wrote it.",
        custom_fields={"estimated_time": 2},
    )
    local_id = first["local_id"]
    assert first["custom_fields"]["estimated_time"] == 2
    assert len((await tools.search_items(KEY, "walkthrough"))["items"]) == 1
    # a mentioned item is linked as related
    other = await tools.create_item(KEY, "feature", "The item that was mentioned",
                                    custom_fields={"estimated_time": 1})
    related = await tools.add_relationship(KEY, local_id, other["local_id"], "related_to")
    assert related["relation_type"] == "related_to"

    # The life cycle: 1. start
    session = await tools.start_work_session(KEY, local_id, "claude-code", "Phase 1: do it", "main")
    started = await tools.update_item(KEY, local_id, status="in_progress")
    assert started["status"] == "in_progress"
    # 2. during
    await tools.update_work_session(KEY, session["id"], "A decision: use the simple way.")
    # a status the project does not have is refused, which is why the prompt says to use the
    # closest one it lists and to tell the user
    with pytest.raises(InvalidStatus):
        await tools.update_item(KEY, local_id, status="blocked")
    # 3. end of the phase: finish the session, then time_spent and a note appended to the body
    await tools.finish_work_session(KEY, session["id"], "completed",
                                    "Done: the change. Tests: all passed. Not verified: nothing.")
    after = await tools.update_item(
        KEY, local_id, custom_fields={"time_spent": 1.5},
        append_body="**Phase 1 done:** the change was made.",
    )
    detail = await tools.get_item(KEY, local_id)
    assert after["custom_fields"]["time_spent"] == 1.5
    assert detail["custom_fields"]["estimated_time"] == 2  # setting time_spent keeps the estimate
    assert detail["body"].startswith("The requirement as I wrote it.")  # never rewritten
    assert detail["body"].endswith("**Phase 1 done:** the change was made.")
    # 4. ready_to_ship does not exist here, so the agent stays on in_progress (the closest)
    assert detail["status"] == "in_progress"
    # 5. after the commit and the release: ship_item, and the status becomes done
    shipped = await tools.ship_item(KEY, local_id, "main", "0.1.0", ["abc1234"])
    assert shipped["status"] == "done"
    assert (await tools.get_item(KEY, local_id))["ship_records"][0]["commits"] == ["abc1234"]
    # "Never leave a session active when you stop"
    active = await tools.list_work_sessions(KEY, status="active")
    assert active["sessions"] == []


@pytest.mark.parametrize("name", ["claude-prompt.md", "codex-prompt.md"])
async def test_the_document_steps_of_the_prompt_work(mcp, name):  # noqa: F811
    assert "update_document with the revision you read" in _prompt(name)

    created = await tools.create_document(KEY, name="Request.md", body="# Request\n",
                                          kind="request")
    document_id = created["id"]
    # "get_document first, then update_document with the revision you read"
    read = await tools.get_document(KEY, document_id)
    changed = await tools.update_document(KEY, document_id, revision=read["revision"],
                                          body="# Request\nmy change\n")
    assert changed["revision"] == read["revision"] + 1
    # "On a conflict, read it again and merge"
    with pytest.raises(DocumentConflict):
        await tools.update_document(KEY, document_id, revision=read["revision"], body="stale")
    fresh = await tools.get_document(KEY, document_id)
    assert fresh["body"] == "# Request\nmy change\n"
    # "To add a line, use update_document with append_body"
    appended = await tools.update_document(KEY, document_id, append_body="one more line")
    assert appended["body"].endswith("one more line")
    assert len((await tools.list_document_revisions(KEY, document_id))["items"]) == 3

    # the diagrams: upload_image, then the image: reference
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
    image = await tools.upload_image_data(KEY, "plan.svg", svg_text=svg)
    assert re.fullmatch(r"IMG-\d{4}", image["id"])
    assert (await tools.get_image(KEY, image["id"], include_content=True))["content"] == svg
    assert image["id"] in [i["id"] for i in (await tools.list_images(KEY))["items"]]
