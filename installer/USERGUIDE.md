# MyIssueDesk User Guide: Connecting an AI to the MCP Server

This guide tells **any AI assistant or MCP client** (Claude Code, Claude Desktop, Cursor,
Codex and similar) how to connect to a MyIssueDesk server and work with its items, and gives a
person the same steps. It is written so that an AI can read it and configure the connection by
itself.

MyIssueDesk is a local fork of [IssueDeck](https://github.com/xq520mmy/IssueDeck): a FastAPI +
SQLite issue tracker with a web dashboard and MCP tools for coding agents. The package is named
`myissuedeck`; the Python import package and the command are still `issuedeck`.

---

## 1. How the pieces fit

```
AI client (Claude Code, Cursor, ...)
   | starts as a child process, talks MCP over stdin/stdout
   v
MCP process:  python -m issuedeck.mcp        <- reads ISSUEDECK_BASE_URL and ISSUEDECK_TOKEN
   | HTTP + "Authorization: Bearer <token>"
   v
MyIssueDesk server:  issuedeck serve          <- REST API + dashboard, owns the SQLite database
```

- The MCP process is only a client of the REST API. It **never opens the database**.
- The **server must be running** before the AI uses a tool. If it is not, every tool call fails
  with `All connection attempts failed`.
- The server and the MCP process are separate programs and use different variable names for the
  token: the server reads `ISSUEDECK_API_TOKEN` (or `api_token` in `server.toml`), the MCP process
  reads `ISSUEDECK_TOKEN`. The value is normally the same.

## 2. What you need before you start

| You need | Where to get it |
|---|---|
| The server URL | `host` and `port` in `server.toml`. Example: `http://127.0.0.1:8766`. The default when nothing is set is `http://127.0.0.1:8765`. |
| A token | A token from `server.toml` (`api_token` or a `[[tokens]]` entry) or one created on the dashboard **Settings** page. Prefer a token with the `agent` scope. |
| A Python that can run `issuedeck.mcp` | The virtual environment where `myissuedeck` is installed (see section 3). |

Token scopes:

| Scope | Can do |
|---|---|
| `read` | Read-only API calls. Good for an AI that only reports. |
| `agent` | Read and write items, relationships, events and work sessions. **Use this for MCP.** It cannot sign in to the dashboard. |
| `admin` | Everything, including dashboard sign-in. The legacy `api_token` is always admin. |

> **Never paste a token into chat, a commit, a log or a shared file.** `.mcp.json` and
> `server.toml` are git-ignored in this repository for that reason. If a token leaks, regenerate
> it on the Settings page and update every client that used it.

## 3. Installation facts

- **From source (development):** the repository has a virtual environment at `.venv`. The Python
  is `.venv\Scripts\python.exe` and the package is installed in editable mode.
- **From the wheel:** build with `.venv\Scripts\uv.exe build`, which produces
  `dist\myissuedeck-<version>-py3-none-any.whl`. Install it into a clean virtual environment with
  `python -m pip install <wheel>` (or `uv pip install --system-certs --python <venv python> <wheel>`
  on a PC where pip fails on TLS).
- **Installer:** `installer\install-myissuedesk.cmd` installs the wheel into
  `C:\Utility\MyIssueDesk` with its own `.venv`, copies the data and settings, and adds
  `start-myissuedesk.vbs` and `stop-myissuedesk.vbs`. Read the script before running it: it copies
  `server.toml`, the database and the projects from the source folder.
- Python 3.11 or newer is required.

Check that the MCP module is available in the Python you plan to use:

```powershell
<python> -c "import issuedeck.mcp.tools; print('ok')"
<python> -m issuedeck --version   # or: <venv>\Scripts\issuedeck.exe --version
```

## 4. Start the server

```powershell
cd <folder that holds server.toml>
<venv>\Scripts\issuedeck.exe serve --config server.toml
```

The command applies database migrations and then listens on the configured host and port. Relative
paths in `server.toml` (`data_dir = "./data"`, `projects_dir = "./projects"`) are relative to the
folder you start it from, so always start it from the folder that holds `server.toml`.

Check that it is up (no token needed):

```powershell
curl http://127.0.0.1:<port>/healthz
curl http://127.0.0.1:<port>/readyz     # {"status":"ready","version":"...","projects":N}
```

> Only one server can use a port. If another IssueDeck already uses the port, stop it first or
> give this one a different `port` in `server.toml` and use that port in the client config.

## 5. Configure the AI client

Every client needs the same four things: a **command** (the venv's Python), the **arguments**
`-m issuedeck.mcp`, and two **environment variables**.

Use absolute paths. On Windows, write JSON paths with `/` or `\\`.

### 5.1 Claude Code (project file `.mcp.json`)

Create `.mcp.json` in the project folder:

```json
{
  "mcpServers": {
    "issuedeck": {
      "type": "stdio",
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["-m", "issuedeck.mcp"],
      "env": {
        "ISSUEDECK_BASE_URL": "http://127.0.0.1:8766",
        "ISSUEDECK_TOKEN": "<paste an agent-scope token here>"
      }
    }
  }
}
```

Or add it from the command line, then check it:

```powershell
claude mcp add-json issuedeck '{"type":"stdio","command":"C:/path/to/venv/Scripts/python.exe","args":["-m","issuedeck.mcp"],"env":{"ISSUEDECK_BASE_URL":"http://127.0.0.1:8766","ISSUEDECK_TOKEN":"<token>"}}'
claude mcp get issuedeck
```

Add `--scope user` to make the server available in every project. **Restart the Claude Code
session** after changing the configuration; tools are loaded when a session starts. To keep the
token out of the file, put `"ISSUEDECK_TOKEN": "${ISSUEDECK_TOKEN}"` and set that variable in your
user environment (Claude Code expands `${VAR}` in `.mcp.json`).

### 5.2 Claude Desktop

Settings, Developer, Edit config; add the same `mcpServers.issuedeck` object as above (without the
`"type"` line if the file does not use it), save, and **restart Claude Desktop**.

### 5.3 Cursor

Create `.cursor/mcp.json` in the project, or `~/.cursor/mcp.json` for all projects, with the same
object. Verify with `cursor-agent mcp list` and `cursor-agent mcp list-tools issuedeck`.

### 5.4 Any other MCP client

Register a **stdio** server named `issuedeck` that runs
`<venv python> -m issuedeck.mcp` with the two environment variables. If the client launches
commands through `uv` instead, use
`uv --directory <repo> run python -m issuedeck.mcp`.

### 5.5 Using the server from an installed copy

If you installed with the installer, point `command` at the installed virtual environment,
`C:\Utility\MyIssueDesk\.venv\Scripts\python.exe`, and keep the same `ISSUEDECK_BASE_URL` and
token as the server there uses.

## 6. Verify the connection

Do these in order. Stop at the first failure and use section 10.

1. `curl http://127.0.0.1:<port>/readyz` returns `"status":"ready"`.
2. With a token in a variable (do not echo it):
   `curl -s -H "Authorization: Bearer $env:ISSUEDECK_TOKEN" http://127.0.0.1:<port>/api/v1/projects`
   returns the project list. A `401` means the token is wrong or lacks the scope.
3. In the client, list the MCP tools: 18 tools named as in section 7 should appear.
4. Call `list_projects`, then `get_project_config` for one project key.

## 7. The 18 MCP tools

| Tool | Purpose | Key parameters |
|---|---|---|
| `list_projects` | List projects with item counts. | none |
| `get_project_config` | Kinds (and prefixes), statuses, branches of a project. **Call this first.** | `project_key` |
| `create_item` | Create an item. | `project_key`, `kind`, `title`, `body`, `tags`, `custom_fields`, `applies_to`, `external_links` |
| `update_item` | Change title, body (or `append_body`), status, tags, custom fields. Cannot set `done`. | `project_key`, `local_id`, ... |
| `bulk_update_items` | Change many items at once (status, tags, branches, custom fields, delete, restore). | `project_key`, ids, changes |
| `ship_item` | Record that an item shipped; this is how an item becomes **Done**. | `project_key`, `local_id`, `branch`, `version`, `commits` |
| `append_item_event` | Add a comment or activity entry to an item. | `project_key`, `local_id`, `body`, `event_type` |
| `delete_item` | Soft-delete an item (it can be restored). | `project_key`, `local_id` |
| `get_item` | One item with body, relationships, events, ship records. | `project_key`, `local_id` |
| `list_items` | Filter by status, kind, tag, branch, custom field, date; paged. | `project_key`, `status`, `kind`, `tag`, `custom_field`, `limit`, `after` |
| `search_items` | Full-text search (SQLite FTS5 syntax). | `project_key`, `q` |
| `add_relationship` | Link two items: `blocks` or `related_to`. | `project_key`, `from_local_id`, `to_local_id`, `relation_type` |
| `remove_relationship` | Remove a link and its inverse. | `project_key`, `rel_id` (returned by `add_relationship`) |
| `start_work_session` | Record that an agent starts work on an item. | `project_key`, `local_id`, `agent_name`, `goal`, `branch` |
| `list_work_sessions` | List sessions, for example `active`. | `project_key`, filters |
| `get_work_session` | One session with its updates. | `project_key`, `session_id` |
| `update_work_session` | Append progress; pause or resume. | `project_key`, `session_id`, `message` |
| `finish_work_session` | End a session as `completed` or `canceled` with a summary. | `project_key`, `session_id`, `status`, `summary` |

`list_items` custom-field filters use `FIELD=VALUE`, `FIELD>=VALUE` and `FIELD:missing`.

> In some clients the tools are "deferred": their schemas load on demand. If a call fails with
> an input-schema message, load the tool (in Claude Code: ToolSearch with `select:<tool name>`)
> and call it again.

## 8. How items work

- **Projects** are separate trackers inside one database, each identified by a key such as
  `myissuedesk`. Their TOML files are in `projects/`. Item ids are `PREFIX-0001` style and unique
  per project.
- **Kinds and prefixes** come from the project config. In `myissuedesk`: Feature `FEAT`, Bug
  `BUG`, Task `TASK`, Issue `IS`. Other projects can differ (for example `recipe-wai` has Feature,
  Bug, Improvement `IMP`, Task). Always read `get_project_config` instead of assuming.
- **Statuses:** `proposed`, `in_progress`, `blocked`, `ready_to_ship`, `done`, `wontfix`.
  `done` and `wontfix` are terminal. **`done` can only be reached with `ship_item`**, which binds a
  branch and a version (for example the git commit hash). `update_item` refuses `status=done`.
- **Branches / `applies_to`:** the project lists its branches. In this fork the only branch is `main`.
- **Time fields (hours):** every project has the built-in custom fields `estimated_time` and
  `time_spent`. New items get a default estimate from the Settings page. The Overview page sums
  them and charts estimated against spent time.
- **Relationships:** `related_to` (symmetric) and `blocks`. A relationship is created from one
  item to another.
- **Activity timeline:** status changes and comments are recorded as events on the item.
- **Work sessions** show on the dashboard (Overview and, if switched on in Settings, the Kanban
  board) while an agent works. Open sessions are `active` or `paused`; they end as `completed` or
  `canceled`.
- **Live updates:** changes made through MCP appear in open dashboard views within a few seconds
  without a reload.

## 9. Recommended workflow for an AI agent

1. `list_projects`, then `get_project_config` for the project you will use.
2. `search_items` for the topic before creating anything, to avoid duplicates.
3. `create_item` with a clear title, a body containing the requirement and a short plan, tags,
   and a realistic `custom_fields: {"estimated_time": <hours>}`.
4. If the request mentions other items, `add_relationship` with `related_to`.
5. `start_work_session` (use your own agent name and a one-line goal) and
   `update_item` with `status: "in_progress"`.
6. During the work, `update_work_session` and `append_item_event` for important decisions.
7. When finished: `update_item` with `custom_fields: {"time_spent": <hours actually spent>}`, an
   appended result note (what changed, what was verified, what was not), and
   `status: "ready_to_ship"`; then `finish_work_session` with a summary.
8. After the change is committed, `ship_item` with `branch: "main"`, the commit hash as `version`
   and `commits: ["<hash>"]`. Only then is the item Done.

Be honest in the notes: say what was tested and what was not.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `All connection attempts failed` on every tool | The server is not running, or `ISSUEDECK_BASE_URL` has the wrong host or port. Check `/readyz`, start the server (section 4), correct the URL. |
| `ISSUEDECK_TOKEN env var is required` | The `env` block of the client config is missing the token. |
| HTTP `401` / `403` | Wrong token, or a `read` token used for a write. Use an `agent` token. After a token was regenerated, update the client and restart it. |
| The tools do not appear | The client was not restarted, the `command` path is wrong, or `issuedeck.mcp` cannot be imported by that Python (section 3 check). |
| The server will not start: port in use | Another process owns the port. On Windows: `Get-NetTCPConnection -LocalPort <port> -State Listen`. Stop it or change the port. |
| Server starts but shows no projects or an old database | It was started from the wrong folder; relative `data_dir` and `projects_dir` follow the current folder. Start it from the folder that holds `server.toml`. |
| `UnknownIssuer` or a broken download during install | The network inspects TLS. Use `uv ... --system-certs` so the Windows certificate store is used. Never disable TLS verification. |
| Changes are missing after switching to another install | Each install has its own database copy. Use one server at a time and keep one source of truth. |

## 11. Prompt you can give another AI

> Connect to the MyIssueDesk MCP server. Find the folder that holds `server.toml` and read its
> `host` and `port`. Find the Python of the virtual environment where `myissuedeck` is installed
> and check that `python -c "import issuedeck.mcp.tools"` works. Do not print or log any token:
> read it only to place it in the client configuration, and prefer an `agent`-scope token. Make
> sure the server answers at `/readyz`, starting it with `issuedeck serve --config server.toml`
> from that folder if needed. Register a stdio MCP server named `issuedeck` that runs
> `<python> -m issuedeck.mcp` with `ISSUEDECK_BASE_URL` and `ISSUEDECK_TOKEN` set. Restart the
> client, list the tools (there should be 18), and call `list_projects`. Report what you changed
> and what you could not verify.
