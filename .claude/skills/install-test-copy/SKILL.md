---
name: install-test-copy
description: Update the installed MyIssueDeck test copy (C:\Utility\MyIssueDeck_<version>, port 8765) from the current source, keeping its database and configuration. Use when asked to install, deploy or update the test copy after a committable change.
---

# Update the installed test copy (TASK-0005)

Only this one folder may be stopped or changed. The development instance (127.0.0.1:8766) and any
other installation are never touched. This is the explicit exception to the "leave port 8765
alone" rule in CLAUDE.md, and it applies only to the folder given with `--target`.

1. Quality gate: `ruff check .` clean and `pytest -q` green; the work is committed (do not install
   uncommitted work unless asked). The version must be higher than the installed one
   (`install.json` in the folder); otherwise bump it first (see the "bump version" commits).
2. Build: `.venv\Scripts\uv.exe build --system-certs --wheel --out-dir dist`, then
   `.venv\Scripts\python.exe scripts\build_installer.py --wheel dist\myissuedeck-<version>-py3-none-any.whl`.
   (`--system-certs` is needed on this PC: plain `uv build` fails with `UnknownIssuer`.)
3. Plan: `.venv\Scripts\python.exe scripts\update_test_copy.py --target C:\Utility\MyIssueDeck_<old> --check`
4. Run the same command without `--check`. It stops that folder's server, renames the folder to the
   new version, runs the installer (backup, new `.venv`, migrations, start), waits for `/readyz`
   and compares the item and project counts. Starting and stopping takes a while; it waits.
   Use `--no-rename` when Windows refuses the rename because another program (Explorer window,
   terminal, editor) has the folder open; the update still works in place.
5. Track it: set TASK-0005 (or the item being installed) to `in_progress` at the start and to
   `ready_to_ship` at the end, with a work session for the time.
6. Report old and new version, the backup path and the counts. Never print or read the token.
