# MCP Client Setup

IssueDeck ships a local stdio MCP server for coding agents. The MCP process is
only a client for the IssueDeck REST API: it reads `ISSUEDECK_BASE_URL` and
`ISSUEDECK_TOKEN`, sends HTTP requests to the running server, and never opens
SQLite directly.

## Start IssueDeck First

For a local trial, start the demo server:

```bash
uv run issuedeck demo
```

That command starts the REST API at `http://127.0.0.1:8765` and creates the
demo token `issuedeck-local-token` when it creates a fresh `server.toml`.

For an existing server, use your real dashboard/API token instead. The server
reads `ISSUEDECK_API_TOKEN`; the MCP process reads `ISSUEDECK_TOKEN`. In most
local setups they should have the same value, but they are separate environment
variables because the server and the client are different processes.

For production, prefer an IssueDeck token with `scopes = ["agent"]` for MCP
clients. It can read and write REST API resources but cannot sign in to the
dashboard.

## Base Stdio Config

Most MCP clients accept a JSON object under `mcpServers`. Use an absolute path
for the cloned IssueDeck repo so the client can launch the server from any
working directory.

```json
{
  "mcpServers": {
    "issuedeck": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/IssueDeck",
        "run",
        "python",
        "-m",
        "issuedeck.mcp"
      ],
      "env": {
        "ISSUEDECK_BASE_URL": "http://127.0.0.1:8765",
        "ISSUEDECK_TOKEN": "replace-with-your-server-token"
      }
    }
  }
}
```

If `uv` is not on the client's `PATH`, replace `"uv"` with the absolute path
from `which uv` on macOS/Linux or `where uv` on Windows. On Windows, JSON paths
can use forward slashes or escaped backslashes.

## Claude Desktop

Open Claude Desktop settings, go to the developer section, edit the MCP config,
and add IssueDeck under `mcpServers`.

```json
{
  "mcpServers": {
    "issuedeck": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/IssueDeck",
        "run",
        "python",
        "-m",
        "issuedeck.mcp"
      ],
      "env": {
        "ISSUEDECK_BASE_URL": "http://127.0.0.1:8765",
        "ISSUEDECK_TOKEN": "replace-with-your-server-token"
      }
    }
  }
}
```

Save the file and restart Claude Desktop. Keep IssueDeck's REST server running
while you use the tools.

## Claude Code

Claude Code can add a stdio server directly from JSON:

```bash
claude mcp add-json issuedeck '{"type":"stdio","command":"uv","args":["--directory","/absolute/path/to/IssueDeck","run","python","-m","issuedeck.mcp"],"env":{"ISSUEDECK_BASE_URL":"http://127.0.0.1:8765","ISSUEDECK_TOKEN":"replace-with-your-server-token"}}'
claude mcp get issuedeck
```

Use `--scope user` if you want the server available outside the current
project.

The same with flags (checked against the Claude Code documentation on 2026-11-27):

```bash
claude mcp add --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 \
  --env ISSUEDECK_TOKEN=replace-with-your-server-token --transport stdio issuedeck \
  -- uv --directory /absolute/path/to/IssueDeck run python -m issuedeck.mcp
```

Everything after `--` is the server command. Keep `--transport stdio` between the
last `--env` and the server name; otherwise the name is read as a variable. The scope
decides where the server is stored: `local` (default, only you, this project),
`project` (`.mcp.json` in the project root, shared through version control) and `user`
(all your projects). Do not write the token into a shared `.mcp.json`; Claude Code
expands `${VAR}` there, so use `"ISSUEDECK_TOKEN": "${ISSUEDECK_TOKEN}"` and set the
variable in your environment.

Check with `claude mcp list` (a working server shows `Connected`), `claude mcp get issuedeck`
or `/mcp` inside Claude Code. A server from `.mcp.json` waits for your approval: run `claude`
in the folder and approve it. The documentation does not say whether a server added by hand
needs a restart; if the tools do not appear, start a new session.

Claude Code reads standing instructions from `CLAUDE.md` in the project folder (and
`~/.claude/CLAUDE.md` for all projects, `CLAUDE.local.md` for yourself only).

## Codex

Codex (the command line client and the IDE extension share the configuration) reads
`config.toml` in its home folder, `~/.codex` by default, or `.codex/config.toml` of a trusted
project. The documentation gives no separate Windows path. Add the server with a command:

```bash
codex mcp add issuedeck --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 \
  --env ISSUEDECK_TOKEN=replace-with-your-server-token \
  -- uv --directory /absolute/path/to/IssueDeck run python -m issuedeck.mcp
```

or write it in `config.toml`:

```toml
[mcp_servers.issuedeck]
command = "uv"
args = ["--directory", "/absolute/path/to/IssueDeck", "run", "python", "-m", "issuedeck.mcp"]
env_vars = ["ISSUEDECK_TOKEN"]

[mcp_servers.issuedeck.env]
ISSUEDECK_BASE_URL = "http://127.0.0.1:8765"
```

`env_vars` names variables that Codex passes on from your environment, so the token is not
written in the file. Check with `codex mcp list` or `/mcp` in the terminal interface; in the IDE
extension, restart the extension after saving. Codex may ask for approval before it calls a
tool; the settings (`default_tools_approval_mode`, `tools.<tool>.approval_mode`) are in its
documentation. Codex reads standing instructions from `AGENTS.md` (`~/.codex/AGENTS.md` for
all projects; in a project the files from the project root down to the current folder, one
per folder, the closer ones later; 32 KiB in total by default).

Checked against the Codex documentation on 2026-11-27. The pages that describe `env_vars`,
the timeouts and the approval settings could only be read in summary, so check those keys
against the documentation of your Codex version.

## Cursor

For project-scoped tools, create `.cursor/mcp.json`. For global tools, create
`~/.cursor/mcp.json`.

```json
{
  "mcpServers": {
    "issuedeck": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/IssueDeck",
        "run",
        "python",
        "-m",
        "issuedeck.mcp"
      ],
      "env": {
        "ISSUEDECK_BASE_URL": "http://127.0.0.1:8765",
        "ISSUEDECK_TOKEN": "replace-with-your-server-token"
      }
    }
  }
}
```

In Cursor CLI, verify the connection with:

```bash
cursor-agent mcp list
cursor-agent mcp list-tools issuedeck
```

In the Cursor editor, open the Tools & MCP settings and confirm that IssueDeck
appears as an available stdio server.

## Agent Work Sessions

When an agent starts substantial work on an item, ask it to call
`start_work_session`, append progress with `update_work_session`, then close
the loop with `finish_work_session`. The dashboard will show active sessions on
the project overview and session history on each item detail page.

## Teach the Agent How to Work

Connecting a client only gives it the tools. To make it work the way this tracker expects
(find before creating, an estimate on every new item, a work session around each phase, honest
notes, nothing committed or deleted unless you ask), give it an example prompt:

- [`docs/agent-prompts/claude-prompt.md`](agent-prompts/claude-prompt.md) for Claude Code and
  Claude Desktop (put it in `CLAUDE.md`, or paste it at the start of a conversation);
- [`docs/agent-prompts/codex-prompt.md`](agent-prompts/codex-prompt.md) for Codex (put it in
  `AGENTS.md`).

Both are also in the built-in help (the Help button of the dashboard: *Using MyIssueDeck with
Claude* and *Using MyIssueDeck with Codex*), together with the tool list and the working method.

## Smoke Test Prompt

After the client sees the tools, ask:

```text
Use IssueDeck to list projects, then list the latest items in the example project.
```

For the demo server, the project key is `example`. For a real project, use the
key from its `projects/<key>.toml` file.

## Troubleshooting

- `ISSUEDECK_TOKEN` must match the server token. For the demo flow, that token
  is `issuedeck-local-token`.
- Keep the REST server running. MCP starts a stdio helper process, not the
  IssueDeck web server.
- If the client cannot launch `uv`, use an absolute executable path.
- If tools connect but return authorization errors, confirm that the server was
  started with the same token that the MCP config passes as `ISSUEDECK_TOKEN`.
- If tools connect but return project errors, verify the project key exists in
  the server's `projects_dir`.

## References

- [Model Context Protocol server guide](https://modelcontextprotocol.io/docs/develop/build-server)
- [Claude Code MCP guide](https://code.claude.com/docs/en/mcp)
- [Cursor MCP guide](https://docs.cursor.com/context/model-context-protocol)
- [Cursor CLI MCP guide](https://docs.cursor.com/cli/mcp)
