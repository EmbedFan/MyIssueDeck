# Standalone Installer and Updates

MyIssueDesk can be installed on a Windows computer that has no copy of the source code, and an
installed copy can be updated without losing any data. Both are done by one installer, which the
build produces next to the wheel. (FEA-0009; replaces `install-myissuedesk.cmd` of TASK-0003.)

## What you need

- Windows, and Python 3.11 or newer (python.org).
- The installer: `myissuedeck-installer-<version>-win64.zip` and the file
  `myissuedeck-installer-<version>-win64.zip.sha256`. Compare the SHA-256 of the ZIP with the
  one in the `.sha256` file before you run anything.
- No internet connection, no administrator rights.

Unzip it to any folder and run:

```
install.cmd
```

`install.cmd` finds Python 3.11 or newer and runs `installer.py` with the same arguments.

## Install or update

By default the software goes to `C:\Utility\MyIssueDesk`. The installer looks at that folder:

| What it finds | What it does |
|---|---|
| nothing (or an interrupted installation) | a **new installation** |
| an older version | an **update** |
| the same version | refuses; `--repair` reinstalls it |
| a newer version | refuses; `--allow-downgrade` forces it (see below) |
| other files, no MyIssueDesk | refuses; nothing is written there |

An installation made by the old `install-myissuedesk.cmd` is recognised and can be updated.

### New installation

1. Checks Python, free disk space, write permission and that the port is free.
2. Creates `data`, `projects`, `project-templates`, `logs`, `run`, `backups` and a virtual
   environment `.venv`, and installs MyIssueDesk and its libraries **from the installer**.
3. Writes `server.toml` from the example with the address `127.0.0.1`, port 8765 (it must be free;
   there is no silent switch to another port) and a **new random administrator token**. The token is
   shown once at the end and is stored only in `server.toml` (the file is limited to your Windows
   account). It is never written to the log or to a command line.
4. Creates the database, copies the start and stop scripts, starts the server to prove it works
   (`/readyz`), and stops it again (use `--start` to leave it running).

### Update

1. Stops the server **of this folder only**. A server of another installation, or another program,
   on the same port is never stopped; if the port is still busy the update stops before changing
   anything.
2. Writes a **backup** to `backups\<time>-<old version>\`: the database (copied with SQLite's backup
   call, so it is consistent), `server.toml`, the settings and their audit log, `projects\` and
   `project-templates\`. The newest 5 backups are kept (`--keep-backups`).
3. Moves the old environment aside to `.venv.old`, builds the new one at the same place and checks
   that `issuedeck --version` reports the new version. (An environment cannot be renamed after it
   was made, because its launchers contain its path; this is why the new one is built at the final
   place and the old one is renamed back on a failure.)
4. Applies the database migrations (`issuedeck db-upgrade`).
5. Replaces the start and stop scripts, writes `install.json`, starts the server again when it was
   running, and checks that it reports the new version.
6. Removes `.venv.old` (read-only files do not stop this) and reports: old and new version, the
   backup folder, the migrations applied, and options that exist in the new example configuration
   but not in your `server.toml` (**reported only, never added**).

**What is never replaced:** the database, `server.toml`, tokens, settings, projects, project
templates and logs. The installer has no step that copies a database over an installed one.

### If something fails

Every step after the first change is covered: the new environment is removed, the old one is
renamed back, the database is restored from the backup when a migration had started, the old
`install.json` is put back, and the old server is started again when it was running. The message
says what failed and where the backup is. Exit code 1. A failed *new* installation says so and can
be repeated.

If the restoring itself meets a problem (a file locked by another program, for example), the
message lists it; the backup is complete and you can restore by hand from it.

## Options

| Option | Meaning |
|---|---|
| `--target FOLDER` | installation folder (default `C:\Utility\MyIssueDesk`) |
| `--host`, `--port` | address of a new installation (default `127.0.0.1`, `8765`) |
| `--check` | show what would be done, change nothing |
| `--repair` | reinstall the same version |
| `--allow-downgrade` | install an older version (see below) |
| `--keep-backups N` | backups to keep (default 5) |
| `--start` / `--no-start` | leave the server running / do not start it (an updated server that was running is still restarted) |
| `--online` | download the libraries from the package index instead of using the installer's |
| `--import-data PATH` | new installation only: a project snapshot `.zip` (FEA-0007) or the data folder of another installation |
| `--silent`, `--yes` | no questions |

Exit codes: 0 done, 1 failed and restored, 2 stopped before anything was changed, 3 the installer
itself is damaged (a file does not match the checksums in `installer-manifest.json`).

### Downgrade

The database is not changed back. If the older version does not understand the newer database it
will not start; restore the database from the backup folder, or install the newer version again.

### Other Python versions

The installer carries the libraries for Python 3.11, 3.12 and 3.13 (64-bit). With another Python it
says so; run it with `--online` and it downloads the libraries from the package index (the Windows
certificate store is used; TLS verification is never switched off).

## Building the installer

```
uv run python scripts/build_installer.py                  # full installer, about 100 MB
uv run python scripts/build_installer.py --no-wheelhouse  # small one for tests, needs --online
```

The result is in `dist\`. The build:

- takes the version from `pyproject.toml` and stops if `issuedeck.__version__` or the wheel differ;
- builds the wheel when `dist\` has none for this version;
- downloads exactly the libraries recorded in `uv.lock`, for Windows 64-bit and each Python, and
  checks every file against the hash and size in the lock (a cache in `dist\.wheel-cache` avoids
  repeated downloads). The environment markers are evaluated for Windows, so `pywin32` is bundled
  and `uvloop` is not, wherever the build runs;
- stops if the installer would contain a database, `server.toml`, `.mcp.json`, `.env`, logs, project
  files, a key, or text that looks like a token;
- writes `installer-manifest.json` (the SHA-256 of every file; the installer checks it when it
  starts) and a ZIP with sorted entries and fixed timestamps, so the same input gives the same bytes.

The release workflow (`.github/workflows/release-artifacts.yml`) builds it for each tag and uploads
it with the other release files. CI builds the small variant to check the generator.

## Development

`installer\installer.py` runs from the source tree too (`python installer\installer.py --check
--online`). Its tests are in `tests/unit/installer/`: new installation, update, repair, downgrade,
detection of an installation made by the old script, backups and their retention, and a failure at
every step (software installation, version check, migration, server start, readiness) restoring the
old version and the database. They use a simulated `pip`, `venv`, migration command and server, so
they need no network and run on any system.

## Not covered

An automatic check for new versions, installing Python itself, a Windows service or scheduled task
(the start and stop scripts are used), code signing of the installer, systems other than Windows,
and moving data between installations (use snapshots, FEA-0007, or GitHub exports, FEA-0008).
