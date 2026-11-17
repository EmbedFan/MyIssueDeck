# Changelog

All notable changes to IssueDeck will be documented in this file.

The format loosely follows Keep a Changelog, and this project uses semantic
versioning once public releases begin.

## [Unreleased]

### Added

- Added a **standalone installer** (FEA-0009): `scripts/build_installer.py` builds
  `myissuedeck-installer-<version>-win64.zip` with the wheel, the dependency wheels for Python
  3.11, 3.12 and 3.13 (the files and hashes recorded in `uv.lock`, so no network is needed to
  install), a checksum manifest and the start and stop scripts. `install.cmd` installs into
  `C:\Utility\MyIssueDesk` (or `--target`) without a source checkout and without administrator
  rights, with a new random administrator token in `server.toml` that is shown once and never
  logged. Run on an installed copy it **updates** it: it stops only that installation's server, backs up
  the database and configuration, builds the new environment beside the old one, applies the
  migrations and restarts the server; any failing step restores the old version and the database.
  The database, `server.toml`, settings and projects are never replaced. `--check` shows what would
  be done; `--repair`, `--allow-downgrade`, `--online`, `--import-data`, `--keep-backups` and
  `--silent` are available. The release workflow attaches the ZIP and its checksum; the release
  checklist covers it. See `docs/installer.md`.
- Added the command `issuedeck db-upgrade [--check]`, which applies the pending database
  migrations (or lists them) without starting the server.

### Changed

- The installer files moved: `installer\payload\` holds the start and stop scripts, and
  `installer\install-myissuedesk.cmd`, which copied the database of the source folder over the
  installed one, is removed.

## [0.10.0] - 2026-11-17

### Added

- Added a built-in **help** (IS-0007): a Help button at the bottom of the left panel opens an HTML
  help in the chosen language (English, Hungarian, Simplified Chinese), generated from one
  Markdown source per language by `scripts/build_help.py` with a table of contents and anchors
  that are the same in every language; tests fail when a language lacks a page or a section.
- Added the **application icon** (IS-0007): the supplied picture is used as the icon of every
  page; `scripts/make_icons.py` makes small versions (32, 48, 180, 192, 512 px and a multi-size
  `favicon.ico`) inside the package, pages declare them with a hash in the address, a web
  manifest is served, and `/favicon.ico` is answered without signing in.
- Added a **Navigation** section to the Settings page (IS-0007): *Import GitHub*, *Import
  History* and *Import Files* in the left panel can be switched on or off; they are off by
  default in this fork.
- Added export of a project to a GitHub repository and import from it (FEA-0008): files of
  the snapshot are stored unpacked in `<folder>/<project-key>/`, one export is one commit
  created through the GitHub REST API (no local clone), nothing is committed when nothing
  changed, the branch is never forced, other folders are never touched, and a public repository
  is refused unless allowed. The token comes from a configurable environment variable (default
  `GITHUB_PAT`) and is never stored, shown or logged. Certificates are verified against the
  operating system's certificate store (a network that re-signs TLS traffic with a trusted
  certificate works); verification is never switched off. Settings section *GitHub exports* with a
  connection test, dashboard page *GitHub* and the commands `github-test`, `github-list`,
  `github-export` and `github-import`; the import reuses the snapshot import rules and preview.
  Exports and imports are recorded in the settings audit log. The dashboard page does not reload:
  every action runs as a background job and shows its steps (connecting, reading the repository,
  uploading file 2 of 7, creating the commit, ...), the elapsed time and the result or the error
  in place; buttons are disabled while it runs, and the same export cannot run twice at once.
  See `docs/github-exports.md`.
- Added importing of project snapshots (audit bundles) to create a new project or to update an
  existing one (FEA-0007): `issuedeck import-audit-bundle` with `--mode create|update`,
  `--conflict keep|newer|overwrite` and `--dry-run`, and an *Import snapshot* dashboard page
  with an exact preview before anything is written. Items keep their ids; the import is all or
  nothing, never extracts the ZIP, and never deletes data from an existing project.

### Changed

- The language is chosen with a combo box that lists each language by its own name, instead of a
  group of buttons (IS-0007).
- The left panel is as high as the window and stays in place while the page scrolls, so the
  project list and the Help button are always visible (IS-0007).
- The distribution is now named `myissuedeck`, so the wheel is
  `myissuedeck-0.9.0-py3-none-any.whl`. The import package and the `issuedeck`
  command keep their names (TASK-0002).

### Fixed

- Kanban board (IS-0006): drag and drop kept working only for the first move. A live update
  replaces the board's columns, and the drag handlers were attached only once, at page load.
  They are now attached to the new columns after every replacement (never twice to one column),
  the column counters follow the current columns, a card is put back only while it is still on
  the page, and an update held back during a drag is applied when the move is over.

## [0.9.0] - 2026-11-15

### Fixed

- Settings page layout (IS-0005): inputs in one row of the widget and live-update
  sections now line up even when a label wraps, and the Display and Tracking
  cards have the same structure with their Save buttons on the bottom edge.

### Added

- Added `issuedeck validate-project-templates` for local template-pack TOML
  validation with table and JSON output.
- Added `issuedeck list-project-template-examples` and
  `issuedeck install-project-template-example` with support, content, and
  research template-pack examples.
- Added `issuedeck export-project-template` for turning an existing project
  config into a reusable local template pack.
- Added dashboard install controls for local project-template example packs.
- Added built-in `estimated_time` and `time_spent` number custom fields (hours)
  to every project; a project that defines the same key keeps its own
  definition. Added total estimated and spent time to the dashboard Overview
  page and to `GET /api/v1/projects/{key}/time-summary`.
- Added a dashboard Overview chart comparing estimated and spent time per
  status, with an empty state until time is recorded.
- Added an optional `default` for custom fields, applied when an item is
  created without a value. The built-in `estimated_time` field defaults to 0.5
  hours (30 minutes), and migration `0007` backfills that value on existing
  items that have none.

- Added a dashboard settings page (`/dashboard/settings`) whose changes apply
  without a restart: light and dark accent colours with a reset to the built-in
  palette, default language and theme (light, dark or system), the default
  estimated time for new items, project name and description, and API tokens
  (create, rename, change scopes, regenerate, delete). Dashboard-created tokens
  are stored only as SHA-256 hashes in `data/tokens.json`; a new or regenerated
  value is shown once. Tokens in `server.toml` stay read-only. Every change is
  appended to `data/settings_audit.jsonl` without secret values.
- The settings page now manages the tokens defined in `server.toml` too
  (IS-0003): a masked preview, show value, regenerate (new value shown once, the
  old one stops working at once), and rename or change scopes for `[[tokens]]`
  entries. The file is edited in place, so comments and other settings stay,
  and it is validated before it is replaced. The administrator token cannot be
  renamed, and cannot be regenerated while `ISSUEDECK_API_TOKEN` sets it. The
  auth middleware now reads config tokens on every request.
- Agent sessions widget and live view updates (FEA-0006). The *Active agent
  sessions* widget can now also be shown above the Kanban board; it is optional
  and configured on the settings page (show on Kanban, default off; show on
  Overview, default on; statuses, completed-within window, maximum, scope,
  initial state, details shown). Open Kanban, list, Overview and item-page views
  follow changes made by agents, the API, MCP, imports or the CLI without a
  reload: the server publishes small events (item, relationship, work session
  and activity changes) over server-sent events at `/dashboard/events`, the page
  re-fetches itself and swaps the marked regions in place, highlights changed
  entries, shows a connection indicator, and falls back to periodic refresh.
  A region being edited is never overwritten (a notice with an *Apply changes*
  button, or apply after saving, as set). A server-side watcher notices writes
  made by other processes. Everything is configurable under *Live updates* on
  the settings page, each group with a reset. Events carry identifiers only.
- Markdown in the item content pane and the form preview (IS-0004): headings,
  lists, task lists, tables, code, block quotes, links and images are now
  formatted (the page relied on `prose` classes from a plugin that is not
  installed), in light and dark mode. The body reaches the renderer as JSON, so
  `<`, `>`, `&` and quotes are kept, and a new `markdown.js` shows raw HTML as
  text and drops `javascript:`/`data:` link and image addresses; external links
  open with `rel="noopener noreferrer"`. The form's Alpine `x-data` no longer
  breaks when the body contains a double quote.
- Settings page navigation and presentation (IS-0003, part 2): the Settings
  menu item now sits after *Import Files* with a gear icon, and the page shows
  the same project menu as the other pages. Tokens are shown as cards with
  separate name, scope and value elements. Show value, Regenerate, create, edit
  and delete update the card in place instead of reloading the page (the token
  routes answer with JSON when asked for it and still work as plain forms). The
  dashboard stylesheet was rebuilt, because the page used classes that were
  missing from it, and a test now fails when a settings template uses a class
  that is not in `dashboard.css`.
- Hungarian status names (IS-0002): with Hungarian selected, the Kanban headers,
  the Overview charts and the status selectors show the standard status names in
  Hungarian. Custom statuses keep their project label. English and Chinese are
  unchanged.
- Added Hungarian (`hu`) to the dashboard language switcher and login page.
  All dashboard messages have a Hungarian translation in `dashboard/i18n_hu.py`;
  API, MCP and CLI messages stay in English.
- Added safe project deletion in the dashboard (`/dashboard/{key}/delete`,
  linked from the project Overview). The user must type the exact project key,
  deletion is blocked while work sessions are active or paused, an audit-bundle
  backup is written to `data/deleted-projects/` first, all project rows are
  removed in one transaction, and the config file is archived to
  `projects/.deleted/` instead of being erased.

### Changed

- The Overview time chart now uses amber for estimated time and blue for time
  spent to make the two series easier to tell apart.

## [0.8.0] - 2026-05-02

### Added

- Added `issuedeck list-project-templates` and `issuedeck create-project` for
  template-based project config creation from the local CLI.
- Added `issuedeck create-item` for local CLI item creation with tags,
  branches, custom fields, external links, body files, JSON output, and dry-run
  previews.
- Added `issuedeck update-item` for local CLI item updates with status, tags,
  branches, custom fields, external link replacement, body files, append-body
  support, JSON output, and dry-run previews.
- Added `issuedeck bulk-update-items` for local CLI bulk status, tag, branch,
  custom-field, delete, and restore workflows.
- Added `issuedeck ship-item` for local CLI ship records with branch, version,
  commits, JSON output, and dry-run previews.
- Added `issuedeck append-item-event` for local CLI comments, verification
  notes, handoff events, metadata, JSON output, and dry-run previews.
- Added `issuedeck list-items` for local CLI item listing with the same kind,
  status, tag, branch, relationship, custom-field, and deletion filters as the
  REST list API.
- Added `issuedeck get-item` for local CLI item detail output in text or JSON.

## [0.7.0] - 2026-05-02

### Added

- Added range and presence filters for project custom fields in REST list
  queries, dashboard filters, saved filters, and pagination links.
- Added built-in custom-field presets to project templates.
- Added MCP create/update/list support for item custom fields.
- Added an MCP bulk-update tool for agent-driven triage across many items.

## [0.6.0] - 2026-05-02

### Added

- Added optional Slack, Discord, and email lifecycle notifications.
- Added local project-template packs through `project_templates_dir` so new
  dashboard projects can start from custom TOML templates without code changes.
- Added project-defined custom fields with REST, dashboard, Markdown export,
  and audit-bundle support.
- Added custom-field support to local project-template packs.
- Added dashboard/API custom-field list filters and CSV/JSON import mappings.
- Added custom-field support to REST and dashboard bulk updates.
- Added custom-field chips to dashboard list, mobile, and kanban item summaries.

## [0.5.0] - 2026-05-02

### Added

- Added Agent Work Sessions for tracking active, paused, completed, and
  canceled coding-agent work across REST, MCP tools, the dashboard, and demo data.
- Added `issuedeck import-github-issues` for repeatable, lightweight GitHub
  repository issue imports with label/state filters and duplicate skipping.
- Added a dashboard GitHub Issues import page with preview, status mapping,
  branch targets, optional tokens, and duplicate-skipping summaries.
- Added dashboard and REST bulk triage for selected items, including status,
  kind, tag, branch, delete, and restore operations.
- Linked dashboard GitHub imports to bulk triage with per-import batch tags and
  filtered result links.
- Added dashboard file imports for CSV, JSON, and Markdown task lists with
  preview, field aliases, status maps, batch tags, and bulk-triage links.
- Added dashboard import history for reopening successful GitHub, CSV, JSON,
  and Markdown import batches.
- Added a dashboard import-history action for soft-deleting all active items
  from a recorded import batch.
- Added a dashboard import-history restore action for recovering soft-deleted
  items from an import batch.
- Added active/deleted item counts to dashboard import history and disabled
  empty batch delete or restore actions.
- Added source and item-state filters to dashboard import history.
- Added pagination to dashboard import history while preserving selected filters.
- Added built-in starter templates to dashboard project creation.
- Added `issuedeck export-audit-bundle` for project-level ZIP snapshots.
- Added dashboard audit-bundle downloads from the project overview.
- Added maintainer workflow docs for requirements, validation, git commits,
  pushes, and CI checks.
- Documented local browser recovery steps and disabled caching for root
  dashboard redirects to reduce stale preview pages.

## [0.4.0] - 2026-05-01

### Added

- Added `issuedeck import-github-url` for creating IssueDeck items linked to
  GitHub issue, pull request, and commit URLs.
- Added `issuedeck import-markdown-list` for turning plain Markdown task lists
  into IssueDeck items.
- Added `issuedeck import-csv` with common tracker presets, custom column
  aliases, status mapping, and dry-run validation.
- Added `issuedeck import-json` for top-level arrays, single objects, and
  wrapped tracker exports such as `items`, `issues`, `data`, `records`, or
  `tasks`.
- Added a compact dashboard setup checklist for first-run projects after login.
- Added hosted tracker export helper docs for GitHub Issues, Linear, Jira, and
  generic table sources.

### Changed

- Expanded the launch kit with GitHub project-page copy, suggested topics,
  demo assets, feature bullets, and 30-second demo scripts in English and
  Chinese.

### Fixed

- `issuedeck serve` and `issuedeck seed-demo` now apply database migrations
  before touching SQLite, preventing stale local databases from returning
  dashboard 500 errors after upgrades.

## [0.3.2] - 2026-04-30

### Fixed

- Aligned the runtime `issuedeck.__version__` value with the published package
  version so health checks report the current release.

## [0.3.1] - 2026-04-30

### Added

- Added launch-kit docs with reusable public release copy and links for first
  open-source sharing.
- Expanded the starter issue backlog for contributor-friendly docs and
  deployment follow-ups.
- Added webhook receiver examples for FastAPI, Flask, and Node/Express.
- Added Docker Compose hardening notes for small self-hosted deployments.
- Added a dashboard accessibility smoke checklist for UI contributions.
- Added PyPI Trusted Publishing troubleshooting notes for `invalid-publisher`
  failures.
- Updated public install docs now that `issuedeck` is published on PyPI.

### Changed

- Refreshed README, roadmap, and security policy copy for the `v0.3.0` public
  release.

## [0.3.0] - 2026-04-30

### Added

- Added dashboard onboarding empty states for fresh installs and empty projects.
- Added delete controls for project-scoped saved dashboard filters.
- Added first-run troubleshooting docs for setup, token, SQLite, and Docker issues.
- Added GitHub URL inference for item external links in API/MCP payloads and dashboard forms.
- Added keyboard-friendly dashboard shortcuts for search, create, filters, navigation, and item focus.
- Added Markdown import adapter presets for GitHub, Linear, and generic tracker exports.
- Added signed asynchronous lifecycle webhooks for item create, update, ship, delete, and restore events.
- Added a gated PyPI Trusted Publishing workflow and PyPI setup guide for future `uvx issuedeck` installs.
- Added PyPI project URLs and license-file metadata to the Python package.
- Added Dependabot version updates for Python/uv, npm, and GitHub Actions.
- Added `SUPPORT.md` plus refreshed issue, pull request, security, and roadmap guidance for contributors.

### Fixed

- Fixed fresh dashboard installs rendering broken project links when no projects exist yet.
- Fixed generated Tailwind CSS drift between Windows and Linux builds.

### Changed

- Raised Python dependency floors for FastAPI, Uvicorn, SQLAlchemy, Pydantic, and Pydantic Settings.
- Upgraded dashboard CSS builds to Tailwind CSS v4.

## [0.2.1] - 2026-04-29

### Added

- Published Docker images to GitHub Container Registry for stable releases and `edge`.
- Automated release artifacts with Python distributions and `SHA256SUMS.txt`.
- Docker Compose now starts from the published GHCR image by default, with a local-image override for source builds.
- Docker containers now run `uv` with `--no-dev` so production startup does not install development tools.
- Docker build contexts now exclude private project configs, SQLite databases, backups, and temporary files.
- Refreshed English and Chinese deployment docs for one-command Docker startup, pinned versions, offline transfer, and release checksums.

## [0.2.0] - 2026-04-29

### Added

- One-command local demo flow via `issuedeck demo`.
- MCP client setup guides for Claude Desktop, Claude Code, and Cursor.
- Scoped API tokens for read-only, agent, and admin clients.
- Project-scoped saved dashboard filters stored in the local runtime data directory.
- Markdown frontmatter import schema docs plus field alias mapping for legacy trackers.
- Item external links for GitHub issues, pull requests, and commits in REST, MCP, and dashboard detail views.
- SQLite backup restore smoke script with copy-pasteable Docker restore docs.
- Screenshot gallery for list, kanban, item detail, search, and project creation surfaces.

## [0.1.0] - 2026-04-29

### Added

- FastAPI REST server for multi-project item tracking.
- MCP stdio client with tools for projects, items, shipping, search, and relationships.
- SQLite storage with Alembic migrations and FTS5 search.
- Item activity timeline with automatic lifecycle events and manual comments.
- Built-in dashboard work queues for backlog, active, blocked, ready-to-ship,
  done, deleted, and recently touched items.
- Fake demo data seeding for public screenshots and README demos.
- Dashboard project creation and language switch foundation.
- Simplified Chinese README.
- Markdown bundle export and generic frontmatter migration command.
- Server-rendered dashboard foundation.
- Token-backed dashboard login with an HTTP-only signed session cookie.
- `/readyz` endpoint for unauthenticated deployment readiness checks.
- Third-party notices for vendored dashboard browser assets.
- Industrial Developer Ledger design system in `DESIGN.md`.
- Docker and offline deployment assets.
- Compiled dashboard CSS build pipeline for production-safe, CDN-free styling.
- Release checklist for pre-tag validation.

### Fixed

- Aligned MCP tool payloads and routes with REST API names for `applies_to`, `after`, and item-scoped relationships.
- Improved mobile dashboard list layout with compact item cards instead of a clipped table.
- Made dashboard sidebar open/closed state independent of runtime Tailwind class generation.
- Accepted UTF-8 BOM in TOML config files, which helps Windows-edited configs load reliably.

### Changed

- Refined dashboard visual direction around the "Lighter than Jira. More stable than Markdown." positioning.
- CI now verifies lint, tests, Python package builds, and Docker image builds.
- Dashboard now ships prebuilt CSS instead of using Tailwind's browser build at runtime.
