# Changelog

All notable changes to IssueDeck will be documented in this file.

The format loosely follows Keep a Changelog, and this project uses semantic
versioning once public releases begin.

## [Unreleased]

## [0.13.0] - 2026-11-27

### Added

- A document block in the advanced search, phase 5 of FEAT-0010. A search block of type `document`
  finds the items that have a linked document (FEAT-0012) whose name and title (`fields` `title`)
  or text (`body`) match plain words or a regular expression, optionally only for some kinds of
  document (`prompt`, `description`, `request`, `report`, `other`). The documents are files without
  an index, so they are read and matched when the search runs: words must all occur, ignoring case,
  as written (no stemming); expressions run in the same stopped process, with a budget of their own;
  at most the first 5,000 documents are read (the answer is then `partial` and says so). Deleted
  items and documents that are linked to no item are never found by it. It works in the API
  (`POST .../search`), in the MCP tool `search_items`, in groups, in saved searches and in the
  dialog (a *Document* button with the same options and the kinds of documents; texts in English,
  Hungarian and Chinese). A refused block names its path as for the other blocks. The description of
  a search says "a linked document: name+title+body match words ...". `docs/advanced-search.md`,
  the help and the user guide are updated.

- Saved searches, phase 4 of FEAT-0010. Every advanced search that is run is kept as the latest
  search of its project, and the Search page offers it again (the dialog starts with it, and a
  link runs it). In the dialog a search can be saved under a name, run, renamed and deleted: names
  are unique per project ignoring case (80 characters, 50 searches), saving over a name and deleting
  ask first, and the page says what was done (also in Hungarian and Chinese). A refused search or a
  later result page does not replace the latest search. Each project has `data/searches/<key>.json`,
  written atomically in one stable form; a damaged file reads as empty and bad entries are left out.
  The saved searches travel with the project: the snapshot (audit bundle) and the GitHub export
  carry `searches.json` (only when there are any; counted in the manifest), an import adds the
  names that are free, keeps the project's own search when a name is taken (with a warning) and
  takes the latest search only when the project has none, a project that is deleted loses them and
  its backup restores them. The CLI and the dashboard import reports show the number added.
  `docs/advanced-search.md`, `docs/audit-bundles.md`, `docs/github-exports.md` and the help are
  updated. Saved searches are not available through the API or MCP yet.

- The advanced search in the dashboard, phase 3 of FEAT-0010. The Search page has an
  **Advanced search** button that opens a dialog for building a search from blocks: words or a
  regular expression (title and/or body, case sensitivity for expressions), kinds and statuses
  taken from the project, groups, AND/OR between blocks, and arrows to reorder them. Blocks that
  are still empty are not sent. The search is sent as `?query=<json>` (bookmarkable, back button
  works), the dialog opens with the search that was run, and the result page shows the search in
  words, an amber notice with the reasons when a regular expression did not finish, a message
  instead of an error page when the search is refused (with the path of the fault), and *Load more*
  keeps the search. The dialog and the notices are translated (English, Hungarian, Chinese);
  `search_builder.js` is new, the dashboard CSS is rebuilt, the help and `docs/advanced-search.md`
  describe it. The text search (`?q=`) is unchanged.

- The advanced search through the API and MCP, phase 2 of FEAT-0010.
  `POST /api/v1/projects/{key}/search` takes `{"query": {...}, "limit": 50, "after": cursor}`
  (the search as data of phase 1) and answers with the usual list plus `description` (the search
  in words with explicit brackets), `partial` and `notes`; it is paged newest first like the other
  lists and refuses a bad search with `422` `invalid_search` and the path of the fault (also a bad
  `after` cursor, which the older lists answer with an error). Although it is a POST, it only reads,
  so a token with the `read` scope may use it (a `read` token still cannot write). The MCP tool
  `search_items` gets an optional `query` object (and `after`) next to `q`; exactly one of them
  must be given, and a refused query is reported with its path. `GET .../search?q=` is unchanged.
  New `docs/advanced-search.md` describes the format, the limits, the word matching (stemming) and
  the time budget of regular expressions; the user guide lists the new parameters.

- The query model of the advanced search, phase 1 of FEAT-0010 (no page or API uses it yet).
  `features/search/query.py` checks a search given as JSON: blocks `text` (mode `simple` or
  `regex`, fields title and body, case sensitivity for regular expressions), `kind` and `status`,
  joined by `and` / `or` (`and` binds tighter), in groups, nested at most 2 levels (a parameter, so
  deeper nesting can be allowed later), at most 20 blocks. It refuses everything else with the path
  of the fault (`items[2].group[1]`): unknown keys, kinds or statuses the project does not have, an
  operator on the first block, a group in a group, a regular expression that is invalid, longer than
  200 characters or repeats a repeat such as `(a+)+`. `features/search/evaluator.py` runs a query:
  every block gives the set of the items it matches and the sets are combined as the query says.
  Plain words go to the full-text index quoted word by word with bound parameters (all words must
  occur; a word such as `OR`, `*` or a quote is only a word; the index stems words, so `import` also
  finds `importing`). A regular expression runs in a separate process that is killed when its time
  is up (2 s by default, after the process has started), so no pattern can hang the server; the
  result then says it is partial and which expression did not finish, and keeps what was finished.
  Only the newest 50,000 items are given to the expressions. `describe()` writes a query in words
  with explicit brackets for the dialog.

- Help and documents for working with an AI agent (IS-0014). The built-in help has a new part
  *Using MyIssueDeck with Claude* and one *Using MyIssueDeck with Codex* (English, Hungarian and
  Chinese): the connection steps (Claude Code, Claude Desktop, and the Codex command line client
  and IDE extension), the 29 MCP tools by group, the working method (the item life cycle), a
  troubleshooting list, and an **example prompt** that teaches the agent how to work with the
  tracker on the user's side (to put in `CLAUDE.md`, or `AGENTS.md` for Codex, or to paste at the
  start of a session). The prompts are also plain files in `docs/agent-prompts/`. `docs/mcp-clients.md`
  (and the Chinese version) gets the Codex setup, the verified `claude mcp add` form and a section
  that points to the prompts; the README (both languages) and the installed `USERGUIDE.md` mention
  the new parts, and the guide now lists all 29 tools (it said 18) and has a Codex section. The setup
  steps follow the official documentation of the tools, checked on 2026-11-27. Tests keep the
  documents true: every tool named in the help or in a prompt exists on the MCP server, every tool
  of the server is in the tool table, the prompt in the help is the prompt of its file, and the
  languages have the same sections.

### Changed

- Compatibility: a snapshot (audit bundle) or GitHub export of a project that has saved searches
  contains `searches.json`; an earlier version refuses such a snapshot because of an unexpected
  file. Snapshots of earlier versions import as before. There is no database migration in this
  release (the saved searches are files under `data/searches/`, which the installer's backup of
  the data folder already copies).

## [0.12.0] - 2026-11-27

### Added

- Documents linked to items, phase 5 and last phase of FEAT-0012. An item can link documents of
  the project's document store (new table `item_documents`, migration 0009), like images. The item
  page has a *Documents* section with the linked documents (open, remove the link) and a list of the
  other documents of the project to link. The API has `GET/POST /api/v1/projects/{key}/items/{id}/
  documents` and `DELETE .../documents/{document_id}`; every link change is written to the item's
  activity (`document_linked`, `document_unlinked`), and linking twice is harmless. Deleting a
  document (API, dashboard, MCP) removes the links to it first, and the activity of those items says
  so. The documents page shows how many items link each document and names that number in the delete
  confirmation; the page of a document lists the items that link it. The snapshot and the GitHub
  export carry the links in `item_documents.json` (only when the project has documents); the import
  adds a link only when its item is in the project and its document was imported, and says how many
  it skipped. Deleting a project removes its link rows.

- Documents in snapshots, the GitHub export and the deletion of a project, phase 4 of FEAT-0012.
  A snapshot (audit bundle, and the files of the GitHub export) now carries the project's documents:
  `documents.json` (the ids that exist and the next free number) and `documents/DOC-0001.json`, ...
  (one file per document with its kept revisions, exactly as stored), only when the project has
  documents, so a project without documents exports the files it did before. The import (dashboard,
  CLI, GitHub import) checks every document on its own: valid JSON, the id of its file name, a clean
  name, text that is not a binary, the SHA-256 of the text and of every kept revision, at most 50
  revisions. A document that fails is skipped and named in a warning, and the rest of the import goes
  on. Only the listed documents are imported, so the file of a document that was deleted (an export
  only adds and changes files in the repository folder) does not bring it back. Documents are
  matched by id: the same id with the same name and text is unchanged, the same id with other content
  is skipped (the project's own document is kept), a name that another document already uses is
  skipped, a free id and name is added; the next free number never goes down. The files are written
  just before the commit and taken back if it fails; a snapshot made by this software is restored byte
  for byte and exports the same files again. The preview, the result and the CLI show the number of
  documents added. Deleting a project removes its documents folder (the backup holds them, so
  importing it restores them).

- MCP tools for the document store, phase 3 of FEAT-0012 (29 tools now): `create_document`,
  `get_document`, `list_documents`, `update_document`, `delete_document` and
  `list_document_revisions`. `create_document` takes the text (`body`) or one file
  (`source_path`): the MCP process reads the file, so a local folder or a network share works and
  the server never looks at a path; no folders. The name is free text and defaults to the file
  name; a binary file is refused before anything is sent; a name that is already used is an
  error that names the document, or with `replace=True` a new revision. `update_document`
  appends (`append_body`, no revision needed) or replaces the text, title or kind and then needs
  the `revision` that was read: a stale one fails with a conflict that names the current revision
  and writes nothing. `get_document` can also return the text of an older revision. The client
  maps the document errors to their own exceptions, and now passes the details of every error
  (for example `existing_id`, `current_revision`) on to them. A running MCP process has to be
  restarted to list the new tools.

- Documents page, phase 2 of FEAT-0012: a new *Documents* entry in the sidebar opens
  `/dashboard/<project>/documents` with the list of the project's Markdown documents (name, kind,
  updated, revision, size) and an upload form for several files at once (any file name; a binary
  file is refused with the reason and the other files are still stored; a kind can be chosen).
  A file whose name is already used becomes a new revision of that document only after the user
  confirms it by name; without the confirmation the server refuses the file and never replaces
  silently. A document opens as rendered Markdown (the same safe renderer as the items, images
  through `image:IMG-0001`), has an edit page with a preview, and a history page that lists the
  kept revisions (the last 50) and opens, downloads or restores any of them. A save made on an old
  revision is refused with a message that names the new revision, keeps the typed text and lets the
  user save again on purpose. Documents and revisions download as Markdown files named like the
  document; delete asks first. The pages use the session cookie and the same service and safe
  headers as the API. Translated into English, Hungarian and Chinese. A double quote in a file name
  arrives as `%22` (browsers write it so in an upload).

- Document store, phase 1 of FEAT-0012: a project can keep Markdown documents (prompts,
  descriptions, requests, reports) in the software's own data files, one JSON file per document
  in `data/documents/<project>/` (`DOC-0001.json`, ...; `documents.json` holds only the next
  number, so an id is never reused). There is no rule about the name or the extension of a
  document: it is free text that is only made safe (a folder part, control characters and the
  spaces at both ends are removed) and is never used as a file name. The one rule about the
  content is that it is a text file, not a binary (a NUL byte or bytes that are not valid UTF-8
  are refused); there is no size limit. Every save is a revision: the earlier texts are kept in
  the document file, **50 revisions at most** (the oldest are dropped, the current text never).
  Replacing a text needs the revision that was read, and a different current one gives 409
  (`document_conflict`), so two agents cannot overwrite each other; appending text needs no
  revision. API under `/api/v1/projects/{key}/documents`: create (a name that is used gives 409,
  or with `replace` a new revision), list (filter by `kind` or `name`), read, replace, append,
  delete, the text as Markdown (`/content`, `?download=true` to save it as a file) and the
  revisions (list, read, restore). Files are written atomically in one stable form. The
  dashboard pages, the MCP tools and the export/import follow in later phases.

## [0.11.0] - 2026-11-26

### Added

- Images in snapshots, export, import and project deletion, phase 5 and last phase of FEAT-0013.
  A snapshot (audit bundle, and the files of the GitHub export) now carries the project's SVG
  images: `images.json` (the registry in its stable form), `images/IMG-0001.svg`, ... (byte for
  byte) and `item_images.json` (the links to items), only when the project has images, so a
  project without images exports exactly the files it did before. The import (dashboard, CLI,
  GitHub import) checks every image on its own: the file must be present, its SHA-256 and size
  must match the registry, and it must pass the same SVG safety check as an upload. An image that
  fails is skipped and named in a warning together with the links to it, and the rest of the
  import goes on. Images are matched by id, because the text of an item refers to `image:<id>`:
  the same id with the same content is unchanged, the same id with other content is skipped (the
  project's own image is kept), a free id is added; the next free id never goes down. The images
  are written just before the commit and taken back if the import fails. The preview and the
  result show the number of images and links added. Exporting an imported project gives the same
  files again, also for the images (IS-0010). The GitHub export uploads only changed image files;
  an image deleted in the project stays in the repository folder but is no longer listed, so an
  import ignores it. Deleting a project now removes its image folder and the links; the backup in
  `data/deleted-projects/` holds the images, so importing it restores them.

- Images on items, phase 4 of FEAT-0013. An item can link images of the project's image store
  (new table `item_images`, migration 0008). The item page has an *Images* section with the
  linked images (open in a new page, remove the link) and a list of the other images of the
  project to link. The API has `GET/POST /api/v1/projects/{key}/items/{id}/images` and
  `DELETE .../images/{image_id}`; every link change is written to the item's activity
  (`image_linked`, `image_unlinked`), and linking twice is harmless. Deleting an image removes
  the links to it first (the activity of those items says so), and the images page shows how many
  items link each image and names that number in the delete confirmation. In the Markdown text
  of an item, `![name](image:IMG-0001)` shows the image and `[text](image:IMG-0001)` opens it in
  a new page (`markdown.js` accepts the `image:` address only with the project key, and only in
  the form `IMG-` plus digits; every other address rule is unchanged). The edit and new item
  pages have an *Insert image...* menu that adds the Markdown reference to the text. Export,
  import and the deletion of a whole project do not handle the links yet (phase 5).

- MCP tools for the project image store, phase 3 of FEAT-0013: `upload_image(project_key,
  source_path)`, `upload_image_data(project_key, name, data_base64 | svg_text)`,
  `list_images`, `get_image(project_key, image_id, include_content)` and `delete_image`
  (23 tools now). The MCP process runs next to the AI client, so `upload_image` reads the `.svg`
  file there (a local folder or a network share) and uploads it over HTTP: the server never
  reads a path from its disk, and no source folders have to be configured. Only `.svg` files up
  to 10 MB are read; the server checks the content and its size limit as for every upload. The
  client maps the image errors (`invalid_image`, `image_too_large`, `image_not_found`,
  `image_duplicate`) to their own exceptions. A running MCP process has to be restarted to
  list the new tools.

- Images page, phase 2 of FEAT-0013: a new *Images* entry in the sidebar opens
  `/dashboard/<project>/images`, a page with a grid of thumbnails (name, size, date, who uploaded)
  and an upload box (file picker, several files at once, or drag and drop). Each image can be
  opened in a new page, downloaded or deleted (after a confirmation). Files that are refused are
  listed with the reason, and the other files of the same upload are still stored. The page uses
  the session cookie (the `<img>` tags need it) and the same service and safety headers as the API:
  `GET /dashboard/<project>/images/<id>/file` (`?download=true` to save), `POST` to the page to
  upload, `POST .../<id>/delete`. Translated into English, Hungarian and Chinese.

- Project image store, phase 1 of FEAT-0013: a project can hold SVG images, kept under
  `data/images/<project>/` with a registry `images.json` (stable form: sorted keys, LF, written
  atomically). API: `POST /api/v1/projects/{key}/images` (multipart upload), `GET .../images`,
  `GET .../images/{id}`, `GET .../images/{id}/content` (`?download=true` to save) and
  `DELETE .../images/{id}`. Images get ids `IMG-0001`, ... that are never reused. **SVG is the
  only accepted type**, and a file is accepted only when it is well-formed, has the SVG root and
  holds nothing that runs script or loads another resource: no `<script>`, `<foreignObject>`,
  `on*` attributes, outside or `javascript:`/`data:` addresses, DOCTYPE or entity declarations,
  style sheets or outside `url()`s (checked without an extra library); a refused file is never
  rewritten and the message names the reason. Images are served with `nosniff` and a sandboxing
  `Content-Security-Policy`, so a file opened in its own tab cannot run script. The same image is
  stored once (409), and the sizes are limited by `[images] max_file_bytes` (2 MB) and
  `max_project_bytes` (100 MB) in `server.toml`. The dashboard page, MCP tools, item links and
  export/import follow in later phases.

## [0.10.4] - 2026-11-26

### Added

- Ctrl-S (Cmd-S on macOS) saves the item on the edit page without closing the editor (IS-0012). The
  form is sent in the background, so the fields, the cursor and the preview stay as they are; a
  "Saved" message (or the server's error, with the typed text kept) appears in the corner for a
  moment, in English, Hungarian and Chinese. The *Save* button works as before and goes to the item
  page. The new item page is unchanged.

## [0.10.3] - 2026-11-26

### Added

- `scripts/update_test_copy.py` and the project skill `install-test-copy` update the installed test
  copy from the current source in one run (TASK-0005): stop that folder's server, rename the folder
  to the new version, run the installer (backup, migrations, restart), wait for `/readyz` and check
  that the item and project counts are unchanged. Documented in `docs/installer.md`.

### Changed

- The top-left box of the dashboard sidebar shows the software version (for example `V0.10.2`)
  instead of the text "ID" (IS-0013). The version comes from the installed package, so it follows
  every version bump; the box grows to fit it.

### Fixed

- *Estimated time* and *Time spent* (and every other number custom field) accept fractional values
  such as `0.5` on the item edit form again (BUG-0002). The form rendered the number input without
  `step="any"`, so the browser allowed whole numbers only; the server side already stored decimals.
- A snapshot that an earlier version exported from Windows can be imported again (IS-0011). Its
  `project.toml` could have CR CR LF line ends (the importer of 0.10.0 and 0.10.1 doubled every
  carriage return when it wrote a configuration, and the next export copied the file), which the
  TOML parser refuses: the import of such a repository stopped after the download with `Expected
  newline or end of document after a statement (at line 1, column 20)` and nothing was imported. The
  importer now brings `project.toml` to one form (LF, no byte order mark) before it reads it, for
  every way to import (dashboard, `github-import`, snapshot ZIP), writes the configuration in that
  form and says so in the preview and the result; the first export of the imported project repairs
  the repository. A configuration that is really invalid is refused with the file, the line and the
  text of the line named. The importer always writes LF now (it used to write the bytes it received).

## [0.10.2] - 2026-11-23

### Fixed

- A project that was imported from the GitHub repository is no longer reported as changed by
  *Check what would change* when nothing was edited (IS-0010). The files of a snapshot (also
  the downloadable audit bundle and the backup of a deleted project) no longer carry the numeric
  database ids of events, relationships, work sessions, their updates, import batches and
  external links, which an import cannot restore, and everything is ordered by its content;
  `project.toml` is exported with one fixed line ending, and the importer writes it exactly as
  it received it (on Windows it doubled every carriage return). The export of a project that is
  already in a repository is rewritten once, without a change of content; old files are still
  imported. See `docs/github-exports.md`.

### Changed

- The product is now spelled **MyIssueDeck** everywhere it was spelled *MyIssueDesk*: the messages of
  the installer and the message boxes of the start and stop scripts, the READMEs and documents, the
  built-in help in all three languages, the web manifest, the user agent, the commit trailer and the
  **default commit author name** of the GitHub export. A commit author name that is already saved in
  the settings is kept as it is. The lower-case names are unchanged: the tracker project key
  `myissuedesk` and the old script names that an update replaces.
- The standalone installer's default folder is now `C:\Utility\MyIssueDeck_<version>` (one folder per
  version, named after the version the installer installs) instead of `C:\Utility\MyIssueDesk`. A
  run without `--target` therefore never touches an installation that already exists: it makes a new
  one next to it. To update an installation, give its folder with `--target`; the plan and the
  "port in use" message say so. See `docs/installer.md`.

## [0.10.1] - 2026-11-18

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

### Fixed

- The standalone installer now installs the start and stop scripts as `start-myissuedeck.vbs` and
  `stop-myissuedeck.vbs` (the spelling of the product; they were installed as *myissuedesk*) and
  installs the user guide `USERGUIDE.md` into the installation folder, which it left out (IS-0009).
  An update replaces the old script names, so the two never exist side by side: a copy of the old
  scripts and of the previous guide goes into the backup (`installed-files`), the report lists each
  rename and reminds you to change a shortcut that points to an old name, and a failed update puts
  the old files back. The shipped guide no longer points to a file that is not installed. A guide
  missing from the installer stops it as damaged before anything is changed.
- A first start without projects now offers **Import from GitHub** next to *New project*
  (IS-0008), whatever the *Navigation* setting is, with a text that names both ways and the
  repository the import reads from. The GitHub page works with no project: it explains before
  anything is pressed that the token variable is missing (naming the variable, saying that the
  server reads its environment only when it starts, and linking to the settings), offers *Test
  connection*, shows a note instead of an empty export form, and leaves only *create* in the
  import form. The error of a missing token carries the same restart advice.

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
