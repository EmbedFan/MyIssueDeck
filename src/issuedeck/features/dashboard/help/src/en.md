MyIssueDeck is a local issue tracker for people and AI coding agents. This page explains the dashboard. Use the contents to jump to a topic; the search of your browser (Ctrl+F) finds words on this page.

## Getting started {#start}

- **Sign in** with an access token on the login page. Tokens are created on the Settings page (see [Settings](#settings)).
- The **left panel** has the views of the current project (Overview, Kanban, List, Search), the *New item* button, Settings, the list of projects and, at the very bottom, this Help.
- The **top bar** has the search box (press `/`), a connection indicator for live updates, the **language** list and the Settings link.
- The default language and the light or dark theme are set on the Settings page; each person can change the language at any time with the language list.

## Projects {#projects}

- A project is a separate tracker with its own kinds, statuses, branches and extra fields. Switch projects in the *Projects* list at the bottom of the left panel.
- **New project** creates a project from a template (basic, agent workflow, software team). A project can also be created from a snapshot (see [Importing and exporting](#import-export)).
- **Export snapshot** on the Overview downloads the whole project as a ZIP. **Delete project** asks you to type the project key; a backup snapshot is saved first, and deleting is refused while an agent work session is active.

## Items, kinds and statuses {#items}

- An item has an identifier such as `FEAT-0001`, a kind (feature, bug, task, issue, ... as the project defines them), a status, a title, content written in **Markdown**, tags, extra fields, links, relationships and an activity timeline.
- Create an item with *New item* (shortcut `n`). The form shows a preview of the Markdown. Open an item to edit it, comment on it, and see its work sessions.
- **Statuses** move an item from idea to finished (for example Proposed, In Progress, Blocked, Ready to Ship, Done). A status that requires shipping, usually *Done*, is reached by **shipping** the item: a branch and a version (for example a commit) are recorded. Agents do this through the API or MCP (`ship_item`).
- **Time:** *Estimated time* and *Time spent* are in hours and are summed on the Overview.
- **Relationships** link items: *blocks* / *blocked by*, and *related to*.
- A deleted item is only hidden and can be restored.

## Kanban board {#board}

- Each column is a status. **Drag a card** to another column to change its status. A message confirms the change; if it is refused, the card goes back.
- The board follows changes made by other people and by AI agents without a reload. A card you are dragging is never replaced.
- The optional *Active agent sessions* widget above the board is switched on in Settings.

## List, search and filters {#list-search}

- The **List** shows items in a table. Press `f` for the filters (status, kind, tag, extra fields). Filters can be saved per project.
- **Search** finds words in titles and contents. Press `/` to jump to the search box.
- **Advanced search** (button on the Search page) builds a search from blocks: words or a regular expression, kinds and statuses, joined by AND or OR, with groups. AND binds tighter than OR; use a group to change that. Words match by stem (`import` finds `importing`), and all words must occur. A regular expression that takes too long is stopped and the page says the result is incomplete. The search is in the address, so you can bookmark it.
- Select several items in the list to change their status, tags or branches, or to delete or restore them in one step.

## Overview, time and charts {#overview}

- The Overview shows counters per status, the total estimated and spent time, a status chart, a chart that compares estimated and spent time, recent items and, if enabled, the active agent sessions.

## AI agents, work sessions and live updates {#agents}

- An agent starts a **work session** on an item with a goal, adds progress notes and finishes it with a summary. Sessions are shown on the Overview, on the item and in the board widget.
- **Live updates:** open pages follow changes made elsewhere. The indicator in the top bar shows whether the page is up to date. A form you are editing is never overwritten; a notice offers the change instead. The behaviour is set in Settings.

## Settings {#settings}

- **Appearance:** colours for the light and the dark theme, with a reset to the default colours.
- **Display** and **Tracking defaults:** the default language and theme, and the default estimated time of new items.
- **Agent sessions widget** and **Live updates:** what is shown and how pages follow changes.
- **Navigation:** which import tools (*Import GitHub*, *Import History*, *Import Files*) appear in the left panel. They are off by default; the pages stay reachable by their address.
- **GitHub exports:** the repository, branch, folder and the name of the environment variable that holds the token (see [Importing and exporting](#import-export)).
- **Project:** name and description of a project.
- **Access tokens:** create, rename, change the scopes (`read`, `agent`, `admin`), regenerate and delete tokens; the tokens of the server configuration can be shown and regenerated too. After a token is regenerated, update every client that uses it.
- **Audit log:** every change of the settings, without any secret value.

## Importing and exporting {#import-export}

- **Import Files** reads CSV, JSON and Markdown task lists. **Import GitHub** imports the issues of a GitHub repository. **Import History** lists earlier imports. These three entries are shown in the left panel when they are switched on in Settings.
- **Snapshots:** *Export snapshot* writes a ZIP. *Import snapshot* creates a project from a snapshot or updates one, after an exact preview; for items present in both you choose to keep the project's version, take the snapshot's when it is newer, or always take the snapshot's. Nothing is ever deleted from the project.
- **GitHub repository:** the *GitHub* page exports a project to a repository as plain files, one commit per export, and imports a project from it again. Create a private repository first and put a token with read and write access to its contents into the environment variable named in Settings (default `GITHUB_PAT`). The page shows each step while it works and does not reload.
- The same functions exist on the command line: `issuedeck export-audit-bundle`, `import-audit-bundle`, `github-test`, `github-list`, `github-export`, `github-import`.

## Keyboard shortcuts {#shortcuts}

Shortcuts work when the focus is not in a text field.

| Shortcut | Action |
| --- | --- |
| `/` | Focus the search |
| `n` | New item in the current project |
| `f` | Show or hide the filters on the list |
| `j` / `k` | Next / previous item |
| `g` then `h` | Go to the overview |
| `g` then `l` | Go to the list |
| `g` then `k` | Go to the Kanban board |
| `g` then `s` | Go to the search page |

## Connecting an AI agent {#mcp}

- An AI agent works with MyIssueDeck through the **MCP server**: `python -m issuedeck.mcp` with the environment variables `ISSUEDECK_BASE_URL` (for example `http://127.0.0.1:8766`) and `ISSUEDECK_TOKEN` (a token with the `agent` scope).
- Register it in your agent's configuration (for example `.mcp.json`) as a stdio server named `issuedeck`, restart the agent, and check that the tools appear.
- A good routine: look up the project, create or find the item, start a work session, record progress and time spent, and ship the item when it is done.
- The server must be running. The `docs` folder (MCP Client Setup, Agent Work Sessions) has the details.
- Step-by-step guides, each with a prompt that teaches the agent how to work with this tracker: [Claude](#claude) and [Codex](#codex).

## Using MyIssueDeck with Claude {#claude}

Claude Code (the command line and the editor extensions) and Claude Desktop can work with this tracker through the MCP server. This section shows how to connect them, which tools they get, how Claude should work, and a prompt that teaches Claude the working method.

### Connect Claude {#claude-connect}

- Before you start: the server is running, and you have a token with the `agent` scope (Settings). With that scope Claude can read and write items but cannot sign in to the dashboard. You also need the command that runs the MCP server: for the installed copy `<install folder>\.venv\Scripts\python.exe -m issuedeck.mcp`, for a source checkout `uv --directory <folder> run python -m issuedeck.mcp`.
- Claude Code: in your project folder run `claude mcp add --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 --env ISSUEDECK_TOKEN=<your-token> --transport stdio issuedeck -- <the command above>`. Keep `--transport stdio` between the last `--env` and the name, otherwise the name is read as a variable. `--scope project` writes the server to `.mcp.json`, a file that is shared through version control: do not write the token there, write `"ISSUEDECK_TOKEN": "${ISSUEDECK_TOKEN}"` and set that variable in your environment. `--scope user` makes the server available in all your projects.
- Check it: `claude mcp list` shows `Connected` for a working server, and `/mcp` inside Claude Code shows the same. A server from `.mcp.json` first waits for your approval: run `claude` in the folder and approve it. If the tools do not appear, start a new Claude Code session.
- Claude Desktop: open Settings, Developer, Edit Config. The file is `claude_desktop_config.json` (Windows: `%APPDATA%\Claude`, macOS: `~/Library/Application Support/Claude`, Linux: `~/.config/Claude`). Add the server under `mcpServers` with `command`, `args` and `env`, save, then quit Claude Desktop completely and start it again. An example is in `docs/mcp-clients.md`.
- Where the teaching prompt goes: Claude Code reads `CLAUDE.md` in the project folder at the start of every session (`~/.claude/CLAUDE.md` applies to all projects, `CLAUDE.local.md` only to you). Keep it short, about 200 lines at most. Claude Desktop has no such file: paste the prompt at the start of a conversation.
- These steps follow the documentation of the tools, checked on 2026-11-27. Tools change: if a command is refused, look at the tool's own documentation.

### What Claude can do {#claude-tools}

Claude gets 29 tools from the MCP server:

| Group | Tools |
|---|---|
| Projects | `list_projects`, `get_project_config` |
| Items | `create_item`, `get_item`, `update_item`, `bulk_update_items`, `delete_item`, `list_items`, `search_items`, `append_item_event`, `ship_item` |
| Relationships | `add_relationship`, `remove_relationship` |
| Work sessions | `start_work_session`, `update_work_session`, `finish_work_session`, `get_work_session`, `list_work_sessions` |
| Images (SVG) | `upload_image`, `upload_image_data`, `list_images`, `get_image`, `delete_image` |
| Documents (Markdown) | `create_document`, `get_document`, `list_documents`, `update_document`, `delete_document`, `list_document_revisions` |

### How Claude should work {#claude-method}

Claude should follow the life cycle of an item, so that the board and the item page always show the true state:

1. Start: `start_work_session` with a goal, then set the item to `in_progress`.
2. During: `update_work_session` for each step that matters. If it has to wait for you, set the item to `blocked` and write why.
3. End of every phase: `finish_work_session` with a summary, then update the item with the total `time_spent` and a progress note at the end of its text.
4. End of the last phase: set the item to `ready_to_ship`.
5. After the change is committed and released: `ship_item`; the item becomes `done`.

Also: look before creating an item, set `estimated_time` on every new item, link the items you mention as related, and never leave a work session active (an unfinished session keeps showing in the board widget).

### Example prompt for Claude {#claude-prompt}

Copy this text into the `CLAUDE.md` of your project (or paste it at the start of a conversation) and replace `<project-key>` with the key of your project. It works in any language you talk to Claude in. The same text is in `docs/agent-prompts/claude-prompt.md`.

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

### If it does not work {#claude-problems}

- The tools are missing: `claude mcp list` must show `issuedeck` as connected. Check the path of the command, that the server is running, and start a new Claude Code session (Claude Desktop: quit it completely and start it again).
- A call fails with 401: the token is wrong or has no `agent` scope. With 404 the project key is wrong.
- A document change fails with a conflict: someone changed it meanwhile; read it again and merge.

## Using MyIssueDeck with Codex {#codex}

Codex (the command line client and its IDE extension) can work with this tracker through the same MCP server. The connection is written in the Codex configuration file, and Codex reads its standing instructions from `AGENTS.md`.

### Connect Codex {#codex-connect}

- Before you start: the same running server and the same `agent` token and command as for Claude.
- Add the server with `codex mcp add issuedeck --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 --env ISSUEDECK_TOKEN=<your-token> -- <the command from the Claude section>`, or write it in the configuration file as shown below.
- The file is `config.toml` in your Codex home folder (`~/.codex` by default; the documentation gives no separate Windows path), or `.codex/config.toml` of a trusted project. The command line client and the IDE extension share it. To keep the token out of the file, list its name in `env_vars` and set the variable in your environment instead of writing the value (the documentation of this key could only be read in summary).
- Check it: `codex mcp list`, or `/mcp` in the terminal interface. In the IDE extension, restart the extension after you save the file.
- Codex may ask for approval before it calls a tool. How that is set (`default_tools_approval_mode`, and `tools.<tool>.approval_mode` for one tool) is described in the Codex documentation.
- Where the teaching prompt goes: Codex reads `AGENTS.md` (`~/.codex/AGENTS.md` for all projects; in a project the files from the project root down to the current folder, one per folder, the closer ones later). The total size is limited, 32 KiB by default.
- These steps follow the documentation of Codex, checked on 2026-11-27. If a command is refused, look at its own documentation.

```toml
[mcp_servers.issuedeck]
command = 'C:\Utility\MyIssueDeck\.venv\Scripts\python.exe'
args = ["-m", "issuedeck.mcp"]
env_vars = ["ISSUEDECK_TOKEN"]

[mcp_servers.issuedeck.env]
ISSUEDECK_BASE_URL = "http://127.0.0.1:8765"
```

### What Codex can do {#codex-tools}

Codex gets the same 29 tools as Claude: see [What Claude can do](#claude-tools). It follows the same working method.

### Example prompt for Codex {#codex-prompt}

Copy this text into the `AGENTS.md` of your project (or paste it at the start of a session) and replace `<project-key>` with the key of your project. It works in any language you talk to Codex in. The same text is in `docs/agent-prompts/codex-prompt.md`.

```text
# MyIssueDeck: how you track work in this project

The issue tracker of this project is MyIssueDeck. You reach it through the MCP server "issuedeck".
My project key is <project-key>.

## First steps
1. Call list_projects, then get_project_config for <project-key>. Use only the kinds, statuses and tags it lists.
2. If the issuedeck tools are missing, or a call fails with 401 (token) or 404 (project key), stop and tell me. Do not work around it.
3. The life cycle below names the statuses proposed, in_progress, blocked, ready_to_ship and done. If the project has no status with one of these names, use the closest one it lists and tell me which.
4. If a tool call waits for my approval, wait. If I refuse it, do not try the same call again; tell me what you needed.

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

### If it does not work {#codex-problems}

- The tools are missing: `codex mcp list` must show `issuedeck`. Check the path of the command and that the server is running; in the IDE extension restart the extension.
- A call fails with 401: the token is wrong or has no `agent` scope; with 404 the project key is wrong.
- A call waits for approval: Codex asks before it uses a tool; approve it, or change the approval setting in the configuration.

## Troubleshooting {#troubleshooting}

- **Cannot sign in:** use a token with the `admin` scope; check the token on the Settings page of a working session or in the server configuration.
- **A page does not update by itself:** look at the connection indicator; live updates can be switched off in Settings.
- **A GitHub export fails:** the message names the cause (token variable not set, token without write permission, public repository, branch changed meanwhile, rate limit). Use *Test connection* in Settings.
- **More documentation:** the `docs` folder of the software, and the version and project notes in the `README`.
