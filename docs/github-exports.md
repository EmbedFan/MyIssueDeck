# GitHub Exports

Projects can be kept in a GitHub repository: every export is **one commit** of plain text files,
and a project can be restored (or copied to another installation) from the repository. The
software talks to GitHub through the REST API only. No local clone and no Git program are
needed.

## What you need

1. **A repository**, created by you beforehand. Make it **private**: items can hold confidential
   text, and the exporter refuses a public repository unless you allow it.
2. **A token** with read and write access to the repository contents. A fine-grained personal
   access token limited to that one repository (permission *Contents: read and write*) is the
   safest choice. Any other authentication that the REST API accepts as a bearer token works,
   for example a GitHub App installation token.
3. **An environment variable** on the machine that runs the server (or the command) holding the
   token. The default name is `GITHUB_PAT`; the name is a setting.

```powershell
setx GITHUB_PAT "<your token>"      # then restart the server / open a new terminal
```

The token is read from the variable when it is needed. It is never stored in a file or in the
database, never written to a log or to the settings audit log, never shown in the dashboard and
never part of an error message.

## Settings

Settings page, section **GitHub exports**. Every setting has a default, can be reset, and every
change is recorded in the settings audit log.

| Setting | Allowed values | Default |
|---|---|---|
| Repository | `owner/name`, or a `https://github.com/owner/name` URL (with or without `.git`) | `https://github.com/EmbedFan/MyIssueDeckExports.git` |
| Branch | an existing branch | `main` |
| Folder in the repository | a relative path such as `exports/issuedeck`; empty = top level | empty |
| Name of the token environment variable | an environment variable name | `GITHUB_PAT` |
| Allow a public repository | on / off | off |
| Name and e-mail of the commit author | text | `MyIssueDesk`, `issuedeck@users.noreply.github.com` |

**Test connection** checks, without writing anything: the token variable is set, the repository
exists, the token can write, whether the repository is private, and the branch exists. It names
every check that fails and why.

## Layout in the repository

Each project gets its own folder, named with the project key, inside the configured folder:

```
<folder>/<project-key>/manifest.json
                       project.json
                       project.toml
                       items.json
                       relationships.json
                       work_sessions.json
                       import_batches.json
```

These are the files of a snapshot (an audit bundle, see [Audit Bundles](audit-bundles.md)),
stored **unpacked** so that GitHub shows readable differences between two exports. The files
are written in a stable order and format, so the same data always gives the same files.

## The dashboard page

The GitHub page does **not reload**. Every action (*Check what would change*, *Export now*,
*Load projects from the repository*, *Check the snapshot*, *Import now*) runs as a background
job and shows its progress in place: a busy indicator, the step it is on in words (connecting,
reading the repository, comparing files, uploading file 2 of 7, creating the commit, updating the
branch, downloading, checking the content, writing the project), the elapsed time, and finally
the result or the reason it stopped. The buttons are disabled while an action runs, so it
cannot be started twice, and the same project cannot be exported twice at the same time. Without
JavaScript the forms are ordinary posts and do the same work inside the request, without the
progress display.

## Exporting

- **Dashboard:** open **GitHub** (link on the project overview or on the Settings page), choose
  the project, *Check what would change*, then *Export now*.
- **Command line:**

```bash
uv run issuedeck github-test                         # check the settings and the connection
uv run issuedeck github-export --project-key myproject --dry-run
uv run issuedeck github-export --project-key myproject
```

Rules:

- One export is **one commit** with all changed files (blobs, tree, commit and a fast-forward
  update of the branch). Either everything is published or nothing is.
- When nothing changed since the last export, **no commit** is made ("up to date"). The export
  time in `manifest.json` alone is not a change.
- The branch is **never forced**. If somebody pushed to it while the export was running, the
  export stops with a message and nothing is published; run it again.
- Only the folder of the exported project is written. Other projects' folders and any other
  file in the repository are never changed or deleted.
- The commit message names the project, the number of items, the time and the software version.
- Every real export is recorded in the settings audit log (project, repository, branch, commit,
  number of files), without the token.

## Importing

- **Dashboard:** *GitHub*, optionally enter a branch, tag or commit, *Load projects from the
  repository* (key, items, time of the last export), choose one, then *Check the snapshot*. The
  preview is the one of [snapshot import](audit-bundles.md#importing-a-snapshot); nothing is
  written until you apply.
- **Command line:**

```bash
uv run issuedeck github-list [--revision v1]
uv run issuedeck github-import --project-key myproject --mode create --target-key copy --dry-run
uv run issuedeck github-import --project-key myproject --mode create --target-key copy
uv run issuedeck github-import --project-key myproject --mode update --conflict newer
```

The content is read from the folder and handed to the snapshot importer, so the same rules
apply: *create* or *update* a project, conflict policies *keep* (default), *newer* and
*overwrite*, all or nothing, and nothing is ever deleted from an existing project. Content that
is not a valid snapshot (missing files, unknown format, counts that do not match, unknown kinds
or statuses) is rejected before anything is written, with the reasons. A command-line import
that creates a project needs a restart of a running server; the dashboard import does not.
Every applied import is recorded in the settings audit log.

## When something goes wrong

| Message | What to do |
|---|---|
| `the environment variable GITHUB_PAT is not set` | Set the variable in the environment of the server or command, or change the variable name in the settings. |
| `GitHub did not accept the token` | The token is wrong, expired or revoked. Create a new one. |
| `GitHub refused this (Resource not accessible by personal access token)` | The token lacks write access. For a fine-grained token open it in GitHub (Settings, Developer settings), choose the repository and set *Repository permissions: Contents* to *Read and write*. The *Test connection* result "your account can push" only shows your own right, not the token's: GitHub reveals the token's permission only when something is written. |
| `GitHub cannot find repository ..., or the token has no access to it` | Check the repository setting, and that the token may see that repository. GitHub answers "not found" for repositories a token cannot access. |
| `GitHub cannot find branch ...` | Create the branch, or change the branch setting. |
| `... is a public repository ... the export was refused` | Make the repository private, or switch on *Allow a public repository*. |
| `branch ... changed while the export was running` | Someone pushed at the same moment. Run the export again. |
| `the GitHub rate limit is reached; try again after ...` | Wait for the time shown. Short limits are waited out once automatically. |
| `the repository is too large to list through the API` | The repository tree is too big for one listing; use a smaller repository for exports. |

## Limits

- The repository tree is listed in one API call, so a repository with a very large number of
  files cannot be used. Use a repository dedicated to exports.
- Work sessions, deleted items and the import history are part of every export.
- Exports run on request. There is no schedule.
- Certificate verification is always on and cannot be switched off. Certificates are checked
  against the operating system's certificate store, so a company network that re-signs TLS
  traffic with a certificate your system trusts works. If the message says the connection
  could not be made (`ConnectError`), check that the system trusts that certificate.
