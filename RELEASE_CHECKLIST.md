# Release Checklist

Use this before tagging or announcing an IssueDeck release.

## Source

- [ ] `CHANGELOG.md` has a human-readable entry for the release.
- [ ] `README.md`, `CONTRIBUTING.md`, `DEPLOY.md`, and `SECURITY.md` match the shipped behavior.
- [ ] `THIRD_PARTY_NOTICES.md` lists vendored dashboard assets and build-time CSS tooling.
- [ ] No real `.env`, `server.toml`, `projects/*.toml`, `data/`, backups, Docker archives, or local paths are included.

## Checks

```bash
npm ci
npm run build:css
uv run ruff check .
uv run pytest
uv build
uv run python scripts/build_installer.py
docker build -t issuedeck:release-check .
```

`build_installer.py` makes `dist/myissuedeck-installer-<version>-win64.zip` and its `.sha256`. It
stops when the version of `pyproject.toml`, `issuedeck.__version__` and the wheel differ, or when the
installer would contain data, a `server.toml` or a secret. It needs the network once (the libraries
are downloaded from the hashes recorded in `uv.lock`).

After `npm run build:css`, run:

```bash
git diff --exit-code -- src/issuedeck/features/dashboard/static/css/dashboard.css
```

## Smoke Test

- [ ] Start the server with a fresh SQLite database.
- [ ] `GET /healthz` returns 200.
- [ ] `GET /readyz` returns 200.
- [ ] Dashboard unauthenticated requests redirect to `/dashboard/login`.
- [ ] Dashboard login accepts `ISSUEDECK_API_TOKEN` and sets an HTTP-only session cookie.
- [ ] List, kanban, search, create/edit, and item detail pages load without console errors.
- [ ] MCP client can list projects, create an item, search it, update it, and fetch it.
- [ ] `python scripts/restore_smoke.py <backup.db.gz>` validates a recent backup.
- [ ] Windows-edited TOML files with UTF-8 BOM still load correctly.

## Release

- [ ] Confirm package metadata in `pyproject.toml`.
- [ ] Confirm Docker image starts from the built artifact.
- [ ] Confirm the wheel installs in a clean virtual environment and `issuedeck --help` runs.
- [ ] Standalone installer: the ZIP name carries the release version and the SHA-256 matches the
      `.sha256` file; unzip it in a clean folder and run `install.cmd --check`.
- [ ] Standalone installer: a clean installation into a throwaway folder and port starts the server
      (`/readyz` reports the release version), and an update of an older installation keeps its
      database, `server.toml`, settings and projects and leaves a backup under `backups\`.
- [ ] Confirm `uvx issuedeck demo --open` starts a healthy demo from PyPI.
- [ ] Tag the release.
- [ ] Publish package/image artifacts.
- [ ] If `PYPI_PUBLISH=true`, confirm PyPI Trusted Publishing uploaded the release.
- [ ] Attach release notes and migration notes.
