# Example prompt: teach Claude to work with MyIssueDeck

Use this prompt when Claude should track its work in MyIssueDeck. Put it in the `CLAUDE.md` of
your project (Claude Code reads it at the start of every session), or paste it at the start of a
conversation (Claude Desktop). Replace `<project-key>` with the key of your project; nothing else
needs to change. The text can stay English whatever language you talk to Claude in.

The same prompt is in the built-in help (section "Example prompt for Claude"). A test keeps the two
copies identical, so change both together.

```text
# MyIssueDeck: how you track work in this project

The issue tracker of this project is MyIssueDeck. You reach it through the MCP server "issuedeck".
My project key is <project-key>.

## First steps
1. Call list_projects, then get_project_config for <project-key>. Use only the kinds, statuses and tags it lists.
2. If the issuedeck tools are missing, or a call fails with 401 (token) or 404 (project key), stop and tell me. Do not work around it.
3. The life cycle below names the statuses proposed, in_progress, blocked, ready_to_ship and done. If the project has no status with one of these names, use the closest one it lists and tell me which.

## Finding and creating items
- Look before you create: search_items and list_items (filters: kind, status, tag). Do not create duplicates.
- create_item: pick a kind from the project config, write a short title, put the requirement in the body, and always set the custom field estimated_time (hours).
- When I mention another item, link it with add_relationship (related_to).
- Never rewrite text I wrote. Add to it with append_body in update_item.

## The life cycle of an item you work on
The status changes at the moment the event happens, never afterwards.
1. Start (of the item and of every phase): start_work_session (goal = what this phase does), then update_item with status in_progress.
2. During: update_work_session for decisions, defects found and test results. If you must wait for me: update_item with status blocked and append why to the body; set in_progress again when it is solved.
3. End of every phase: finish_work_session with a summary (what was done, the tests, what you did not verify); then update_item with the custom field time_spent (total hours so far) and a progress note appended to the body. Never leave a session active when you stop.
4. End of the last phase: update_item with status ready_to_ship and a note of what is left to check.
5. After the change is committed and released: ship_item (branch, version, commit ids). The status becomes done.

## Documents and images
- Prompts, requests and reports are kept as documents: create_document, get_document, list_documents, update_document, delete_document, list_document_revisions.
- To change a document: get_document first, then update_document with the revision you read. On a conflict, read it again and merge; never overwrite another person's change. To add a line, use update_document with append_body.
- SVG diagrams are kept with upload_image, list_images, get_image and delete_image. Show an image in an item text with ![name](image:IMG-0001).

## Never, unless I ask you
- Commit, tag, push, or change configuration, tokens or other projects' items.
- Delete items, documents or images.
- Put a token or any other secret into an item, a document or a message.
```
