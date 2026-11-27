MyIssueDeck 是一个供人和 AI 编程代理使用的本地事项跟踪工具。本页介绍控制台的使用。可通过目录跳转到某个主题；浏览器的搜索（Ctrl+F）可以在本页中查找文字。

## 开始使用 {#start}

- 在登录页面使用访问令牌**登录**。令牌在“设置”页面创建（见[设置](#settings)）。
- **左侧面板**包含当前项目的视图（总览、看板、列表、搜索）、“新建事项”按钮、设置、项目列表，最底部是本帮助。
- **顶部栏**有搜索框（按 `/`）、实时更新的连接指示、**语言**列表和设置链接。
- 默认语言以及浅色或深色主题在“设置”页面中设定；每个人都可以随时用语言列表切换语言。

## 项目 {#projects}

- 项目是一个独立的跟踪空间，有自己的类型、状态、分支和附加字段。可在左侧面板底部的“项目”列表中切换项目。
- **新建项目**会根据模板创建项目（基础、代理工作流、软件团队）。也可以从快照创建项目（见[导入与导出](#import-export)）。
- 总览页上的**导出快照**会把整个项目下载为 ZIP 文件。**删除项目**需要输入项目标识；删除前会先保存一份备份快照，并且在有代理工作会话处于活动状态时拒绝删除。

## 事项、类型与状态 {#items}

- 事项有标识（例如 `FEAT-0001`）、类型（功能、缺陷、任务、问题……由项目定义）、状态、标题、使用 **Markdown** 编写的内容、标签、附加字段、链接、关联和活动记录。
- 使用“新建事项”（快捷键 `n`）创建事项。表单会显示 Markdown 预览。打开事项即可编辑、评论，并查看它的工作会话。
- **状态**把事项从想法推进到完成（例如已提议、进行中、已阻塞、待发布、完成）。需要发布的状态（通常是“完成”）要通过**发布**事项来达到：记录分支和版本（例如一次提交）。代理通过 API 或 MCP（`ship_item`）完成这一步。
- **时间**：“预估时间”和“已用时间”以小时为单位，并在总览中汇总。
- **关联**把事项联系起来：*阻塞* / *被阻塞*，以及*相关*。
- 删除的事项只是被隐藏，可以恢复。

## 看板 {#board}

- 每一列是一个状态。**拖动卡片**到另一列即可更改状态。会有消息确认更改；如果被拒绝，卡片会回到原处。
- 看板无需刷新即可跟随他人和 AI 代理所做的更改。正在拖动的卡片绝不会被替换。
- 看板上方可选的“活动代理会话”小组件可在设置中开启。

## 列表、搜索与筛选 {#list-search}

- **列表**以表格显示事项。按 `f` 打开筛选（状态、类型、标签、附加字段）。筛选可按项目保存。
- **搜索**在标题和内容中查找文字。按 `/` 跳到搜索框。
- **高级搜索**（搜索页面上的按钮）用条件块组合搜索：词语或正则表达式、类型和状态，用“且”或“或”连接，可分组。“且”比“或”优先；用分组改变顺序。词语按词干匹配（`import` 能找到 `importing`），所有词都必须出现。“文档”条件块查找关联了匹配文档的事项（词语按原样查找，不做词干匹配；也可以只查某些类型的文档）。耗时过长的正则表达式会被停止，页面会提示结果不完整。搜索条件在地址中，可以加书签。每个项目会保留最近一次搜索，打开搜索页面时会恢复；在对话框中还可以给搜索命名保存，并运行、重命名和删除已保存的搜索。已保存的搜索属于项目快照和 GitHub 导出的一部分。
- 在列表中选择多个事项，可一次性更改它们的状态、标签或分支，或者删除、恢复它们。

## 总览、时间与图表 {#overview}

- 总览显示各状态的计数、预估和已用时间的总计、状态图表、比较预估与已用时间的图表、最近的事项，以及（如已开启）活动的代理会话。

## AI 代理、工作会话与实时更新 {#agents}

- 代理在事项上带着目标启动**工作会话**，添加进展记录，并附总结结束会话。会话显示在总览、事项页和看板小组件中。
- **实时更新**：打开的页面会跟随其他地方所做的更改。顶部栏的指示显示页面是否是最新的。正在编辑的表单绝不会被覆盖，而是通过通知提供更改。行为可在设置中调整。

## 设置 {#settings}

- **外观**：浅色和深色主题的颜色，可恢复为默认颜色。
- **显示**和**跟踪默认值**：默认语言和主题，以及新事项的默认预估时间。
- **代理会话小组件**和**实时更新**：显示什么内容，以及页面如何跟随更改。
- **导航**：哪些导入工具（*导入 GitHub*、*导入历史*、*导入文件*）显示在左侧面板中。默认关闭；这些页面仍可通过地址访问。
- **GitHub 导出**：仓库、分支、文件夹，以及保存令牌的环境变量名称（见[导入与导出](#import-export)）。
- **项目**：项目的名称和描述。
- **访问令牌**：创建、重命名、更改权限范围（`read`、`agent`、`admin`）、重新生成和删除令牌；服务器配置中的令牌也可以显示和重新生成。令牌重新生成后，请更新所有使用它的客户端。
- **审计日志**：设置的每一次更改，不含任何机密值。

## 导入与导出 {#import-export}

- **导入文件**读取 CSV、JSON 和 Markdown 任务列表。**导入 GitHub**导入 GitHub 仓库的问题。**导入历史**列出以前的导入。在设置中开启后，这三个入口才会显示在左侧面板中。
- **快照**：“导出快照”写出一个 ZIP 文件。“导入快照”在精确预览之后，从快照创建项目或更新项目；对两边都有的事项，可以选择保留项目中的版本、在快照较新时采用快照的版本，或始终采用快照的版本。项目中的内容绝不会被删除。
- **GitHub 仓库**：“GitHub”页面把项目导出为仓库中的普通文件，每次导出一个提交，也可以从仓库再导入。请先创建私有仓库，并把对其内容有读写权限的令牌放入设置中指定的环境变量（默认 `GITHUB_PAT`）。页面在工作时会显示每一步，并且不会刷新。
- 命令行中也有相同的功能：`issuedeck export-audit-bundle`、`import-audit-bundle`、`github-test`、`github-list`、`github-export`、`github-import`。

## 键盘快捷键 {#shortcuts}

当焦点不在文本框中时，快捷键才有效。

| 快捷键 | 操作 |
| --- | --- |
| `/` | 聚焦搜索 |
| `n` | 在当前项目中新建事项 |
| `f` | 显示或隐藏列表筛选 |
| `j` / `k` | 下一个 / 上一个事项 |
| `g` 然后 `h` | 前往总览 |
| `g` 然后 `l` | 前往列表 |
| `g` 然后 `k` | 前往看板 |
| `g` 然后 `s` | 前往搜索页 |

## 连接 AI 代理 {#mcp}

- AI 代理通过 **MCP 服务器**使用 MyIssueDeck：运行 `python -m issuedeck.mcp`，并设置环境变量 `ISSUEDECK_BASE_URL`（例如 `http://127.0.0.1:8766`）和 `ISSUEDECK_TOKEN`（具有 `agent` 权限范围的令牌）。
- 在代理的配置（例如 `.mcp.json`）中把它注册为名为 `issuedeck` 的 stdio 服务器，重启代理，并检查工具是否出现。
- 推荐流程：查看项目，创建或查找事项，启动工作会话，记录进展和已用时间，完成后发布事项。
- 服务器必须处于运行状态。详细信息见 `docs` 文件夹（MCP Client Setup、Agent Work Sessions）。
- 分步指南，每一份都带有一个提示词，教智能体如何使用这个跟踪器：[Claude](#claude) 和 [Codex](#codex)。

## 在 Claude 中使用 MyIssueDeck {#claude}

Claude Code（命令行和编辑器扩展）和 Claude Desktop 都可以通过 MCP 服务器使用这个跟踪器。本节说明如何连接、它们能获得哪些工具、Claude 应该如何工作，并给出一个教 Claude 工作方式的提示词。

### 连接 Claude {#claude-connect}

- 开始之前：服务器正在运行，并且您有一个 `agent` 权限范围的令牌（在设置中）。有了这个权限，Claude 可以读写条目，但不能登录仪表盘。您还需要运行 MCP 服务器的命令：已安装的副本用 `<安装文件夹>\.venv\Scripts\python.exe -m issuedeck.mcp`，源码目录用 `uv --directory <文件夹> run python -m issuedeck.mcp`。
- Claude Code：在项目文件夹中运行 `claude mcp add --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 --env ISSUEDECK_TOKEN=<您的令牌> --transport stdio issuedeck -- <上面的命令>`。`--transport stdio` 要放在最后一个 `--env` 和名称之间，否则名称会被当作变量。`--scope project` 会把服务器写入 `.mcp.json`，这个文件会通过版本控制共享：不要把令牌写在里面，请写成 `"ISSUEDECK_TOKEN": "${ISSUEDECK_TOKEN}"`，并在环境中设置该变量。`--scope user` 让服务器在您所有的项目中可用。
- 检查：`claude mcp list` 对正常工作的服务器显示 `Connected`，在 Claude Code 中用 `/mcp` 也能看到。来自 `.mcp.json` 的服务器要先等您批准：在该文件夹中运行 `claude` 并批准。如果工具没有出现，请开始一个新的 Claude Code 会话。
- Claude Desktop：打开 Settings、Developer、Edit Config。文件是 `claude_desktop_config.json`（Windows：`%APPDATA%\Claude`，macOS：`~/Library/Application Support/Claude`，Linux：`~/.config/Claude`）。在 `mcpServers` 下添加服务器，包含 `command`、`args` 和 `env`，保存后完全退出 Claude Desktop 再重新启动。示例见 `docs/mcp-clients.md`。
- 教学提示词放在哪里：Claude Code 在每个会话开始时读取项目文件夹中的 `CLAUDE.md`（`~/.claude/CLAUDE.md` 适用于所有项目，`CLAUDE.local.md` 只对您自己有效）。请保持简短，最多约 200 行。Claude Desktop 没有这样的文件：请在对话开始时粘贴提示词。
- 这些步骤依据各工具的文档，核对日期为 2026-11-27。工具会变化：如果某个命令被拒绝，请查看该工具自己的文档。

### Claude 能做什么 {#claude-tools}

Claude 从 MCP 服务器获得 29 个工具：

| 分组 | 工具 |
|---|---|
| 项目 | `list_projects`, `get_project_config` |
| 条目 | `create_item`, `get_item`, `update_item`, `bulk_update_items`, `delete_item`, `list_items`, `search_items`, `append_item_event`, `ship_item` |
| 关联 | `add_relationship`, `remove_relationship` |
| 工作会话 | `start_work_session`, `update_work_session`, `finish_work_session`, `get_work_session`, `list_work_sessions` |
| 图片（SVG） | `upload_image`, `upload_image_data`, `list_images`, `get_image`, `delete_image` |
| 文档（Markdown） | `create_document`, `get_document`, `list_documents`, `update_document`, `delete_document`, `list_document_revisions` |

### Claude 应该如何工作 {#claude-method}

Claude 应该遵循条目的生命周期，使看板和条目页面始终显示真实状态：

1. 开始：用 `start_work_session` 写明目标，然后把条目设为 `in_progress`。
2. 进行中：每个重要步骤都用 `update_work_session`。如果必须等您，就把条目设为 `blocked` 并写明原因。
3. 每个阶段结束：用 `finish_work_session` 写总结，然后更新条目的累计 `time_spent`，并在条目正文末尾追加进度说明。
4. 最后一个阶段结束：把条目设为 `ready_to_ship`。
5. 变更提交并发布之后：用 `ship_item`，条目变为 `done`。

另外：创建条目之前先查找，每个新条目都设置 `estimated_time`，把提到的条目关联为 related，并且绝不留下未结束的工作会话（未结束的会话会一直显示在看板组件中）。

### 给 Claude 的示例提示词 {#claude-prompt}

把这段文字复制到您项目的 `CLAUDE.md` 中（或者在对话开始时粘贴），并把 `<project-key>` 替换为您项目的键。无论您用哪种语言与 Claude 交流，它都有效。同样的文字也在 `docs/agent-prompts/claude-prompt.md` 中。

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

### 如果不起作用 {#claude-problems}

- 工具缺失：`claude mcp list` 必须显示 `issuedeck` 已连接。检查命令的路径和服务器是否在运行，并开始一个新的 Claude Code 会话（Claude Desktop：完全退出后重新启动）。
- 调用返回 401：令牌错误或没有 `agent` 权限；返回 404 表示项目键错误。
- 修改文档时出现冲突：期间有人改动了它；请重新读取并合并。

## 在 Codex 中使用 MyIssueDeck {#codex}

Codex（命令行客户端及其 IDE 扩展）可以通过同一个 MCP 服务器使用这个跟踪器。连接写在 Codex 的配置文件中，Codex 从 `AGENTS.md` 读取长期指令。

### 连接 Codex {#codex-connect}

- 开始之前：与 Claude 相同的运行中的服务器、相同的 `agent` 令牌和相同的命令。
- 用 `codex mcp add issuedeck --env ISSUEDECK_BASE_URL=http://127.0.0.1:8765 --env ISSUEDECK_TOKEN=<您的令牌> -- <Claude 部分中的命令>` 添加服务器，或者按下面所示写入配置文件。
- 文件是 Codex 主目录中的 `config.toml`（默认为 `~/.codex`；文档没有给出单独的 Windows 路径），或者受信任项目中的 `.codex/config.toml`。命令行客户端和 IDE 扩展共用它。为了不把令牌写进文件，请在 `env_vars` 中列出它的名称，并在环境中设置该变量，而不是写入值（这个键的文档只能以摘要形式读到）。
- 检查：`codex mcp list`，或在终端界面中用 `/mcp`。在 IDE 扩展中，保存文件后请重启扩展。
- Codex 在调用工具之前可能会请求批准。如何设置（`default_tools_approval_mode`，以及单个工具的 `tools.<工具>.approval_mode`）在 Codex 文档中有说明。
- 教学提示词放在哪里：Codex 读取 `AGENTS.md`（`~/.codex/AGENTS.md` 适用于所有项目；在项目中从项目根目录到当前文件夹，每个文件夹一个文件，越近的越靠后）。总大小有限制，默认 32 KiB。
- 这些步骤依据 Codex 的文档，核对日期为 2026-11-27。如果某个命令被拒绝，请查看它自己的文档。

```toml
[mcp_servers.issuedeck]
command = 'C:\Utility\MyIssueDeck\.venv\Scripts\python.exe'
args = ["-m", "issuedeck.mcp"]
env_vars = ["ISSUEDECK_TOKEN"]

[mcp_servers.issuedeck.env]
ISSUEDECK_BASE_URL = "http://127.0.0.1:8765"
```

### Codex 能做什么 {#codex-tools}

Codex 获得与 Claude 相同的 29 个工具：见[Claude 能做什么](#claude-tools)。它遵循相同的工作方式。

### 给 Codex 的示例提示词 {#codex-prompt}

把这段文字复制到您项目的 `AGENTS.md` 中（或者在会话开始时粘贴），并把 `<project-key>` 替换为您项目的键。无论您用哪种语言与 Codex 交流，它都有效。同样的文字也在 `docs/agent-prompts/codex-prompt.md` 中。

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

### 如果不起作用 {#codex-problems}

- 工具缺失：`codex mcp list` 必须列出 `issuedeck`。检查命令的路径和服务器是否在运行；在 IDE 扩展中请重启扩展。
- 调用返回 401：令牌错误或没有 `agent` 权限；返回 404 表示项目键错误。
- 调用在等待批准：Codex 使用工具前会询问；请批准，或在配置中更改批准设置。

## 故障排除 {#troubleshooting}

- **无法登录**：请使用具有 `admin` 权限范围的令牌；可在已登录会话的设置页面或服务器配置中核对令牌。
- **页面不会自动更新**：请查看连接指示；实时更新可在设置中关闭。
- **GitHub 导出失败**：消息会指出原因（未设置令牌变量、令牌没有写权限、公开仓库、分支在此期间发生变化、速率限制）。请使用设置中的“测试连接”。
- **更多文档**：软件的 `docs` 文件夹，以及 `README`。
