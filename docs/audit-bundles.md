# Audit Bundles

Audit bundles are ZIP snapshots for teams that need periodic project archives,
handoffs, or lightweight migration checkpoints.

From the dashboard, open a project overview and use **Export snapshot**.

```bash
uv run issuedeck export-audit-bundle \
  --project-key example \
  --out snapshots/
```

If `--out` is a directory, IssueDeck writes
`snapshots/example-audit-bundle.zip`. If it ends in `.zip`, IssueDeck writes that
exact file.

## Bundle Contents

- `manifest.json`: bundle format, project key, generated timestamp, counts, and
  file list.
- `project.json`: parsed project configuration.
- `project.toml`: original project config, when the TOML exists on disk.
- `items.json`: active and deleted items with tags, branch targets, external
  links, ship records, and lifecycle events.
- `relationships.json`: all relationship rows in the project, including
  bidirectional inverse rows.
- `work_sessions.json`: agent work sessions and progress updates.
- `import_batches.json`: dashboard and CLI import history metadata.
- `images.json`, `images/IMG-0001.svg`, ... and `item_images.json`: the SVG images of the
  project's image store (the registry, the files byte for byte) and the links between items
  and images. They are written only when the project has images, so a project without
  images gives the same files as before.

On import every image is checked on its own: the file must be present, its SHA-256 and size must
match the registry, and it must pass the same SVG safety check as an upload. An image that fails is
skipped and named in a warning, and so are the links to it; the rest of the import goes on. Images
are matched by id (the text of an item refers to `image:IMG-0001`): the same id with the same
content is unchanged, the same id with other content is skipped and the project's own image is
kept, a free id is added. Deleting a project removes its image folder; the backup in
`data/deleted-projects/` keeps the images, so importing it restores them.

- `documents.json` and `documents/DOC-0001.json`, ...: the project's Markdown documents (one file
  per document, exactly as the store wrote it, with its kept revisions) and the list of the ids
  that exist with the next free number, and `item_documents.json`: the links between items and
  documents. Written only when the project has documents.

- `searches.json`: the project's saved searches of the advanced search (see
  [Advanced Search](advanced-search.md)): the named searches and the latest one, in the stable form
  of the store. Written only when the project has any.

On import the saved searches are matched by name, ignoring case: the same name with the same search
is unchanged, the same name with another search is skipped (the project's own is kept) and named in
a warning, a free name is added, up to 50 in a project. The latest search of the snapshot is taken
only when the project has none yet. Deleting a project removes its saved searches; the backup in
`data/deleted-projects/` keeps them, so importing it restores them.

On import every document is checked on its own: valid JSON, the id of its file name, a clean name,
text that is text and not a binary, the SHA-256 of the text and of every kept revision, and at most
50 revisions. A document that fails is skipped and named in a warning; the rest goes on. Only the
documents named in `documents.json` are imported, so a file left behind by a deleted document is
ignored. A link is imported only when its item is in the project and its document was imported.
Documents are matched by id: the same id with the same name and text is unchanged, the same
id with other content is skipped (the project's own document is kept), and a name that another
document of the project already uses is skipped. The files are written just before the commit and
taken back if it fails. Deleting a project removes its documents; the backup in
`data/deleted-projects/` keeps them, so importing it restores them.

Exporting is read-only and does not mutate project data.

## Importing a Snapshot

A snapshot can be imported to **create a new project** or to **update an existing
one**. Nothing is written until you apply: a preview shows exactly what would change.

From the dashboard, open **Import snapshot** on a project overview (to update that project) or
the link on the *New project* page (to create one). Choose the ZIP, check it, then import.

From the command line:

```bash
# preview, then create a project from a snapshot (optionally under another key)
uv run issuedeck import-audit-bundle snapshots/example-audit-bundle.zip   --mode create --project-key example-copy --dry-run
uv run issuedeck import-audit-bundle snapshots/example-audit-bundle.zip   --mode create --project-key example-copy

# bring an existing project up to a snapshot
uv run issuedeck import-audit-bundle snapshots/example-audit-bundle.zip   --mode update --project-key example --conflict newer
```

Rules:

- **Create** writes `projects/<key>.toml` from the snapshot's `project.toml` (the key is
  rewritten when you give another one), then adds the items with their ids, timestamps,
  events, ship records, relationships, agent work sessions and import history. It refuses a key
  that is already in use. A command-line import needs a server restart before a running server
  shows the new project; the dashboard import does not.
- **Update** matches items by their id (`FEAT-0001`). Items the project lacks are created.
  For items present in both, `--conflict` decides: `keep` (default) leaves the project's
  version, `newer` takes the snapshot's when its `updated_at` is later, `overwrite` always
  takes the snapshot's. Activity entries, relationships, work sessions and import batches that
  are missing are always added. Nothing is deleted from the project, so importing the same
  snapshot twice changes nothing the second time.
- Every item's kind, status and branch must exist in the target project's configuration;
  otherwise the import stops before anything is written and lists the problems.
- The import is all or nothing (one database transaction). The ZIP is never extracted: only the
  known file names are read, with a size limit.
- `project.toml` of the snapshot may have any line ending (LF, CR LF, CR CR LF, a lone CR) and a
  byte order mark: it is brought to one form (LF) before it is read, the project configuration is
  written in that form, and the report says so. Earlier versions exported such files from Windows.
- A snapshot made when a project was deleted (`data/deleted-projects/`) can be used to
  restore that project.
- Not restored: tokens and server settings. The files carry no numeric database ids (of events,
  relationships, work sessions, their updates, import batches or links) and are ordered by their
  content, so a project that was imported exports the same files as the one it came from (older
  snapshots that still have the ids are imported as before; new ids are assigned).
