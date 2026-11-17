MyIssueDesk is a local issue tracker for people and AI coding agents. This page explains the dashboard. Use the contents to jump to a topic; the search of your browser (Ctrl+F) finds words on this page.

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

- An AI agent works with MyIssueDesk through the **MCP server**: `python -m issuedeck.mcp` with the environment variables `ISSUEDECK_BASE_URL` (for example `http://127.0.0.1:8766`) and `ISSUEDECK_TOKEN` (a token with the `agent` scope).
- Register it in your agent's configuration (for example `.mcp.json`) as a stdio server named `issuedeck`, restart the agent, and check that the tools appear.
- A good routine: look up the project, create or find the item, start a work session, record progress and time spent, and ship the item when it is done.
- The server must be running. The `docs` folder (MCP Client Setup, Agent Work Sessions) has the details.

## Troubleshooting {#troubleshooting}

- **Cannot sign in:** use a token with the `admin` scope; check the token on the Settings page of a working session or in the server configuration.
- **A page does not update by itself:** look at the connection indicator; live updates can be switched off in Settings.
- **A GitHub export fails:** the message names the cause (token variable not set, token without write permission, public repository, branch changed meanwhile, rate limit). Use *Test connection* in Settings.
- **More documentation:** the `docs` folder of the software, and the version and project notes in the `README`.
