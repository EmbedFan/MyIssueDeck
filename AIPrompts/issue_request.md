# Requested issues

## IS-0011: A Snapshot Exported by an Earlier Version Cannot Be Imported: the Importer Rejects Doubled Carriage Returns in `project.toml`

**Status:** Implemented in commit 782f54f, released as 0.10.2 (tracked as IS-0011 in MyIssueDesk, registered afterwards because the server was not running). The request was written under the words *feature request*; it describes a defect of an existing function (FEA-0008), so it is kept here as an issue. Decisions taken: the importer always writes the normalised text (LF), also for a snapshot with CR LF, which changes the earlier rule of IS-0010 that the received bytes are written (the exporter writes LF, so a snapshot of this version is still written byte for byte); the repository is repaired by the first export of the imported project, no command rewrites it; the listing of the repository does not warn beforehand (the problem is gone, so the warning would only be noise). The normalisation is in `read_snapshot`, the one place every import path goes through.

**Summary:** On a new installation, with no project on the server, *Import from GitHub* (repository `EmbedFan/MyIssueDeckExports`) fails at the last step with `the project configuration in the snapshot is invalid: Expected newline or end of document after a statement (at line 1, column 20)`; nothing is imported. The importer shall accept the snapshots that are already in the repository, whatever line endings their `project.toml` has, so that a project exported by an earlier version can be restored.

**Reported:** Import a project from `MyIssueDeckExports` after an installation, with no project definition on the server for the selected project. The progress shows every step done (connecting, reading the repository, downloading the 7 files `import_batches.json`, `items.json`, `manifest.json`, `project.json`, `project.toml`, `relationships.json`, `work_sessions.json`, checking the content), the action stops after 3.1 s, and the message above is shown.

**Cause (found and reproduced on 2026-11-23):**
- The `project.toml` in the repository has the line ending CR CR LF (two carriage returns before the line feed). This is the damage that IS-0010 describes: before its correction the importer wrote the configuration of an imported project in text mode, which on Windows doubled every carriage return, and the next export then copied that file as it was. A repository that was filled by such a server holds files like this.
- The importer decodes the file of the snapshot and gives the raw text to the TOML parser (`snapshot_import.py`, `_parse_config`). The parser accepts LF and CR LF but not a lone CR, and stops after the first statement. For the key `myissuedesk` the statement `key = "myissuedesk"` has 19 characters, so the error is at column 20, exactly the message that was reported. The same text with CR CR LF gives that message, with LF or CR LF it gives none.
- The server itself accepts the same file from disk, because it reads its own configuration files in text mode, which turns a lone CR into a line break. So the damaged project worked on the server where it was imported and was exported without any sign of a problem; only the import of the exported snapshot fails.
- Through the importer, with a snapshot whose `project.toml` was changed to CR CR LF, the result is the same error, no row and no configuration file are written, and the same snapshot with LF is imported. Every import path is affected, because all of them use `_parse_config`: the GitHub import of the dashboard, the command `github-import` and the import of a snapshot ZIP.
- It is not a problem of the network, of the token or of the repository: all earlier steps are done.

**Why it matters:** The repository is the backup and the way to move a project to another installation (FEA-0008). The files that are in it now were written by 0.10.0 and 0.10.1 and cannot be restored on a new installation, which is exactly when they are needed, and the correction of IS-0010 does not help them: it only changes what is exported from now on. The message does not tell the user what to do, and the project cannot be repaired by hand without unpacking the files from the repository.

**Requirements:**
1. **The importer accepts every line ending.** A `project.toml` with LF, CR LF, CR CR LF or a lone CR, with or without a byte order mark, is imported. The text is brought to one form, the same one the exporter writes since IS-0010 (every CR+ LF and every lone CR becomes LF, no BOM), before it is parsed. This holds for every import path (GitHub import in the dashboard, `github-import`, snapshot ZIP, preview and apply).
2. **The configuration is written in that form.** The file that the import creates has LF line ends, never a doubled CR, so a project imported from a damaged snapshot exports the same files as one imported from a clean snapshot, and the repository is repaired by the first export of the imported project.
3. **The report says what was done.** When the line ends of the snapshot were changed, the preview and the result of the import say so in one line (*the line endings of project.toml were normalised*), so that nobody has to wonder about the difference.
4. **A configuration that is really invalid is still refused, with a message that helps.** The message names the file (`project.toml`) and the line and shows the text of that line, nothing is written, and a line ending is never mentioned as the cause when it is not.
5. **Nothing else changes.** Snapshots made by this version are imported as before; the rules of FEA-0007 (preview, conflict policies, all or nothing) are not touched; the exporter is not touched.

**Tests:**
- A snapshot with the project configuration in each line ending (LF, CR LF, CR CR LF, lone CR, BOM plus CR LF) is imported as a new project, in the preview and in the apply, through the importer, through the dashboard GitHub import against the local test double of the GitHub API and through the command `github-import`; the written file has LF only.
- The files of the repository as the user has them (a configuration with CR CR LF, key `myissuedesk`, 7 files) are imported, and the project exported afterwards is up to date against a clean export (IS-0010).
- A configuration that is invalid for another reason is refused with the file and the line named, nothing is written, and no configuration file is left behind.
- The report carries the line about the normalised line endings only when something was changed.
- The tests of IS-0010 and of FEA-0007 and FEA-0008 still pass. The test of the exact bytes (IS-0010) is adapted to the decision below.
- Tried on this PC: a throwaway server with no project, a repository double that holds the snapshot with CR CR LF, the import in the dashboard, then the project is open and its export is up to date.

**Points to settle when the issue is planned:**
- Whether the importer writes the normalised text always (recommended: the file equals what the exporter writes, so the round trip is exact whatever the source) or the bytes it received when they are valid (this keeps a CR LF file as CR LF, but then the same project has different bytes on disk depending on where it came from).
- Whether a repository that holds damaged files is repaired by the first export of the imported project only (as proposed) or whether a command rewrites the files in the repository.
- Whether the *Check* of the GitHub page tells beforehand, when it lists the projects of the repository, that a project cannot be imported, so that the user does not wait for the downloads (the problem is found only after all files are downloaded).

**Not part of this request:** changing the exporter, the GitHub API handling, the server's own reading of its configuration files, or the format of the snapshot.

**Related items:** IS-0010 (its defect wrote the files that this issue cannot read; its correction prevents new ones); FEA-0008 (the GitHub import and export); FEA-0007 (the snapshot import, whose parser is the place of the change); IS-0008 (the first-start import from GitHub, where this was found); FEA-0009 (the installation after which it happened).

---

## IS-0010: An Imported Project Is Reported as Changed: the Export Is Not Stable across an Import

**Status:** Implemented in commit bd9a089 (tracked as IS-0010 in MyIssueDesk). The request was written under the words *feature request*; it describes a defect of an existing function (FEA-0008), so it is kept here as an issue. Decisions taken at planning: the ids are removed from the files (they are neither kept nor ignored in the comparison), and everything is ordered by content; the format name stays `issuedeck.audit_bundle.v1` because the new files are read by 0.10.x (the ids were optional there) and the old files are read by the new importer, so no format version had to be raised; `generated_at` stays in the manifest (it alone is never a change); the audit-bundle ZIP and the backup of a deleted project share the code and lose the ids too; the one-time rewrite of projects already in a repository is documented, not announced in the app.

**Summary:** After a project has been imported from the GitHub repository (for example from `MyIssueDeckExports`) and nothing has been edited, *Check what would change* on the GitHub page reports the files `manifest.json`, `items.json`, `relationships.json` and `project.toml` as changed. The export shall be stable across an import: the same project data shall give the same files, so that an unedited, freshly imported project is reported as up to date.

**Reported:** Import a project from `MyIssueDeckExports`, edit nothing, press *Check what would change*: the four files above are listed.

**Why it matters:** The check is meant to show whether an export would add anything (FEA-0008: *the same project data always produces the same files and a commit shows only real changes*). After an import it cannot say so, so every machine that imports a project and then exports it pushes commits without any real change, the history of the repository fills with noise, and the user cannot tell a real change from a false one.

**Reproduced and explained (2026-11-18, on Windows, with the local test double of the GitHub API; a project with items, a relationship, a ship record, exported, imported as a new project, checked again):**
- **`manifest.json`** differs on every export by design, because it carries the export time. By itself it is not counted as a change when a commit is decided, but the file is the first sign in the list.
- **`project.toml`**: the importer writes the project configuration in text mode (`snapshot_import.py`, `config_path.write_text(...)`). On Windows each line end that the snapshot already has as CR LF becomes CR CR LF; in the test, 14 of 14 lines. The file on disk is then not the file that was exported, and the next export differs. (The project still loaded and worked.)
- **`items.json`**: the exported files carry the numeric database ids of the activity events (and, in the other files, of relationships, work sessions, their updates, import batches and external links). These ids belong to one database. The importer cannot restore them (FEA-0007 lists this as *not restored*), so the imported project gets new ones. Even into an empty database the event ids were renumbered (`events[].id` 3 -> 2 and 2 -> 3, because the original ids interleave across items); into a database that already holds other data all of them change (`[[1],[2]]` -> `[[3],[4]]`).
- **`relationships.json`**: the same cause. In an empty database the relationship ids happened to be the same; into a database that already holds a relationship of another project they changed (`[1, 2]` -> `[3, 4]`). This is the usual case on a real installation, which is why the file appears in the report.
- A project that is exported twice without a change is correctly reported as up to date; the problem starts with the import.

**Requirements:**
1. **Stable round trip.** Export, import (as a new project, into an empty database and into one with other projects and relationships, or as an update of an existing project) and export again give the same files, apart from the export time in `manifest.json`. The exported files do not depend on the numeric row ids of the database in which the project happens to live (events, relationships, work sessions, session updates, import batches, external links); how that is achieved is a point to settle below.
2. **`project.toml` is written exactly as it was exported.** The importer never changes line endings (no doubled CR on Windows); the bytes of the snapshot are the bytes of the file.
3. **Line endings do not make a difference.** The text files of an export have one fixed line ending, so that an export made on Windows and one made on Linux are identical, and a configuration file with CR LF or with the CR CR LF that earlier imports produced does not show up as a change.
4. **The check says what is true.** After an import with no edits, *Check what would change* reports that the repository is up to date. The export time alone is not presented as a change (it can be named separately as *export time*).
5. **Nothing is lost.** Snapshots that were exported before the correction are still imported (the format version is raised and both are read), the content that the files carry is the same, and the audit bundle that is downloaded or written when a project is deleted, which shares the files, keeps working. The first export of a project after the correction may change its files once; this is said in the documentation and the CHANGELOG.
6. **Projects imported earlier** (whose configuration file already has doubled CR) are handled by requirement 3 without any manual repair.

**Tests:**
- A round-trip test with a project that has items, events, relationships (also with a gap in the ids), ship records, work sessions with updates, an import batch and external links: export, import into an empty database, into a database that already holds another project with relationships, and as an update; export again; the files are equal apart from the export time.
- The imported `project.toml` is byte-equal to the exported one, with LF and with CR LF in the snapshot (the check is on the bytes, so it does not depend on the system the test runs on).
- A configuration file with doubled CR gives the same exported file as one with LF.
- After an import without edits the check reports *up to date* and the export makes no commit; after a real edit it names only the files that really changed.
- A snapshot in the old format is still imported; the audit bundle of a deleted project is still written and readable.
- The test of the earlier behaviour that a project exported twice is up to date still passes.
- Tried on this PC against a throwaway repository double: the round trip with the imported project of a real database copy.

**Points to settle when the issue is planned:**
- How the ids are removed from the files: replace them by a sequence number inside the item or the project (the order is already known), drop them from the files and keep them out of the comparison only, or let the importer keep the ids when they are free (this cannot work whenever another project already uses them, so it is not enough on its own).
- Whether `generated_at` stays in `manifest.json` or moves into the commit message only, so that every file is fully deterministic.
- How the one-time change of the files of projects that are already in a repository is announced.
- Whether the same stability is wanted for the audit-bundle ZIP of FEA-0003 (it shares the code and the format).

**Not part of this request:** changing what a snapshot contains for the user, the GitHub API handling, merging two different histories of the same project, or restoring the numeric ids.

**Related items:** FEA-0008 (the export and its *Check what would change*, whose promise of stable files this restores); FEA-0007 (the snapshot import, which does not restore the ids); FEA-0003 (the audit bundle that shares the file format); IS-0008 (the first-start import from GitHub, which leads users into this).

---

## IS-0008: First Start Without Projects Offers No Way to Import from GitHub

**Status:** Implemented in commit 1f48efb (tracked as IS-0008 in MyIssueDesk). Decisions taken at planning: the second button is always shown, the *Import GitHub* menu entry stays off by default and no *Import snapshot* button is added; after an applied import the existing primary *Open project* button is the way into the new project (no automatic redirect, so the first-time user sees what was imported); nothing is sent to GitHub when the GitHub page opens; the installer's closing message, a setup checklist and the project pages (list, Kanban) are unchanged. The Hungarian and Chinese wording needs a review by a native speaker, and the GitHub page has no Chinese text yet (it falls back to English, as before).

**Summary:** After a first installation, when the dashboard has no project yet, the only thing it offers is *New project*. The import of projects from the GitHub repository (FEA-0008, for example the exports in `MyIssueDeckExports`) exists, but a user who has no project cannot find it. The empty start shall offer it next to *New project*, and the import shall work, and explain what it needs, when there is no project at all.

**Current state (checked in the source and on the first real installation, 2026-11-18):**
- With no project the dashboard opens on the page *No projects yet* with the text *Create a project config to start tracking work.* and one button, *New project* (`/dashboard/projects-new`).
- The GitHub page (`/dashboard/github`) works without a selected project: it lists the projects of the repository and imports one as a new project. But the only ways to it are (a) the *GitHub export* button in the header of a project overview, which needs a project, (b) the left-panel entry *Import GitHub*, which is **off by default** since IS-0007 (setting *Navigation*), and (c) typing the address. A first-time user has none of these.
- The import needs two things that a first-time user may not have: the access token in the environment variable named in the settings (default `GITHUB_PAT`), which the server reads from the environment it was started in, and the repository of the settings (default `https://github.com/EmbedFan/MyIssueDeckExports.git`). Without the token the user meets an error on a page that he or she had to find first.
- The text *Create a project config* describes the file-based way of working and says nothing of the other ways to get a project.

**Requirements:**
1. **A second button on the empty start.** Next to *New project* the page shows *Import from GitHub*, which opens the GitHub page. The button is shown whatever the *Navigation* setting is: that setting hides menu entries, not the first-run choice. The two buttons stack on a narrow window, are reachable and named for the keyboard and screen readers, follow the language and the theme, and are translated (English, Hungarian, Chinese).
2. **The text tells the choices.** The explanation under *No projects yet* names both ways (create a project, or import projects that were exported earlier) in plain words, and shows the repository the import would read from (from the settings), so that it is clear where the projects come from.
3. **The import works with no project.** From a start with an empty database, the GitHub page lists the projects of the repository, an import creates the chosen project (create mode of FEA-0007, with its preview before anything is written) and, when it is applied, the user lands on the overview of the new project. The new project appears in the left panel and in the project selector at once, without restarting the server.
4. **First-run guidance on the GitHub page.** When the import cannot work yet, the page says why and what to do, before the user has to press anything: no token in the environment (the page names the variable, says that the server has to be started again after the variable is set, because it reads its environment when it starts, and where the repository is chosen: *Settings*, section *GitHub exports*), a token without permission, a repository or a branch that does not exist, no network. The token itself or part of it is never shown. The same page offers the *Test connection* action of the settings.
5. **Existing behaviour is kept.** With at least one project the start page is unchanged, the *Navigation* setting still decides about the left-panel entries, and the import rules of FEA-0007 and FEA-0008 (preview, conflict policies, all or nothing) are not changed.

**Tests:**
- the empty start shows both buttons, in each language, with the nav entry switched on and off, and both links answer after signing in (the existing smoke test of the empty start is extended);
- the GitHub page with zero projects renders and, against the local test double of the GitHub API, a listing, a preview and an import create the project, the response leads to the new project and the project is visible without a restart;
- a missing token, a token without permission and an unknown repository each give their own guidance text that contains the name of the variable and never a token value;
- the compiled dashboard CSS contains the classes of the new buttons (the existing CSS test), and the layout is looked at in a real browser at a narrow and a wide window, in the light and the dark theme.

**Points to settle when the issue is planned:**
- Whether the empty start also offers *Import snapshot* (a ZIP file, FEA-0007), which is the other way to bring in an existing project.
- Whether the *Import GitHub* menu entry is shown while there is no project, even though its setting is off, or only the button of the empty start is added.
- Whether the installer's closing message (FEA-0009) should mention the token variable, because that is where a first-time user is led to the GitHub page.
- Whether the empty start becomes a short checklist (project or import; token; repository), in the style of the setup checklist that a project overview already has.
- What the project pages (list, Kanban) show when someone opens their address while no project exists; they should end on the same empty start.

**Not part of this request:** creating or administering the GitHub repository, storing the token in the software, changing the import rules, or any change to the export.

**Related items:** FEA-0008 (the GitHub export and import that the button leads to); FEA-0007 (the snapshot import used by the import, and the other way to bring in a project); IS-0007 (the *Navigation* setting that hides the entry by default); FEA-0004 (Settings page, section *GitHub exports*); FEA-0009 (the installer that creates the first start); IS-0009 (found on the same first installation); IS-0003 (no secret is shown).

---

## IS-0009: Installer Installs Scripts under the Wrong Name and Leaves the User Guide Out

**Status:** Implemented in commit 627ccdb (tracked as IS-0009 in MyIssueDesk). The request was written as IS-0007, a number that the implemented entry below already has, so it is numbered IS-0009. Decisions taken at planning: the default installation folder and the visible texts were not changed by this issue (later requests made the default `C:\Utility\MyIssueDeck_<version>`, one folder per version, and spelled the product MyIssueDeck everywhere); only the guide is installed, not `README-INSTALL.txt` or `docs\installer.md`; no forwarding scripts under the old names; the old script files and the previous guide go into the backup of the update (`installed-files`). The installation in `C:\Utility\MyIssueDeck` (0.10.0) is updated by the next version's installer or with `--repair`; it was not touched.

**Summary:** The standalone installer (FEA-0009) installs the server start and stop scripts as `start-myissuedesk.vbs` and `stop-myissuedesk.vbs`, with a spelling that differs from the name of the product, and it does not install `USERGUIDE.md`. Both shall be corrected, including for installations that already exist.

**Observed:** On the first real installation (installer 0.10.0, new installation into `C:\Utility\MyIssueDeck`, 2026-11-18 14:31) the installation folder contains `start-myissuedesk.vbs`, `stop-myissuedesk.vbs`, `start-server.ps1`, `stop-server.ps1`, `server.toml` and `install.json`, and no user guide anywhere outside the virtual environment, although the installer ZIP carries `payload/USERGUIDE.md`.

### Problem 1: Spelling of the script names

**Current state:** The product, the Python distribution and the installer are all called *myissuedeck* (`myissuedeck-0.10.0-py3-none-any.whl`, `myissuedeck-installer-<version>-win64.zip`, the `product` field of `install.json`, the remote `MyIssueDeck.git`). Only the two scripts that a user starts by hand carry *myissuedesk*. A user who looks for the scripts by the name of the product does not find them, and the two spellings make it unclear which one is right.

**Requirements:**
- The scripts are named `start-myissuedeck.vbs` and `stop-myissuedeck.vbs`. The PowerShell helpers keep their names (`start-server.ps1`, `stop-server.ps1`).
- The new names are used everywhere the old ones are: the installer's list of files, the files in `installer\payload\`, the final report of the installer (*start: ... stop: ...*), `README-INSTALL.txt`, `installer\USERGUIDE.md`, `docs\installer.md`, the two PowerShell scripts (their comments and log texts), the CHANGELOG entry of the installer and the tests. Historical entries of the CHANGELOG, which describe what an earlier release did, stay as they are.
- **Installations that already exist** (the old names are on disk): an update or a repair installs the scripts under the new names and then removes the old ones, so that the two never exist side by side. The installer says so in its report (*renamed start-myissuedesk.vbs to start-myissuedeck.vbs*) and warns that a shortcut or a scheduled task that points to an old name must be changed. Before an old file is removed, a copy of it is placed in the backup folder of that update, so that a script changed by hand is not lost.
- A failed update puts the old files back with the rest of the old version; the new names are removed again.
- A guard in the tests fails when the old spelling appears in a file that the installer ships, so that the mistake cannot return.

### Problem 2: `USERGUIDE.md` is not installed

**Current state:** The generator puts `USERGUIDE.md` into the ZIP (`payload/USERGUIDE.md`) and the manifest lists it, but the installer copies only the four scripts. The guide that explains how to connect an AI assistant to the server therefore reaches the computer only inside the unpacked ZIP, which the user is likely to delete after the installation.

**Requirements:**
- A new installation, an update and a repair copy the guide to `<installation folder>\USERGUIDE.md`. The guide belongs to the installed version, so an update replaces it; the previous copy is kept in the backup folder of that update, in case it was edited.
- The final report of the installer names the guide and its path.
- The guide describes the installed layout. Statements that are only true in the source tree or that refer to a file that is not installed (the guide now points to `docs\installer.md`) are corrected, or the file they refer to is installed as well.
- A new installation from the small *online* ZIP behaves the same.
- When the guide is missing from the installer, the installer stops with the *damaged* code (3) before it changes anything; the generator already fails when the file is absent.

**Tests:** new installation, update and repair each leave `USERGUIDE.md` in the folder with the content of the installer; the update keeps the old copy in the backup; a failed update leaves the old guide in place; an update of an installation that has the old script names ends with the new names only, the old files in the backup and a report line for each; a rollback restores the old names; the guard against the old spelling. The change is also tried on this PC, where `C:\Utility\MyIssueDeck` is exactly such an installation (a repair with the new installer shows the rename and the guide).

**Points to settle when the issue is planned:**
- Whether the default installation folder, and the texts that the user sees (the installer's messages, the title of the message boxes of the two `.vbs` files, `README-INSTALL.txt`), also change from *MyIssueDesk* to *MyIssueDeck*; the folder `C:\Utility\MyIssueDeck` in use today suggests that they should. A folder that already exists is never renamed by the installer.
- Whether `README-INSTALL.txt` and `docs\installer.md` are installed with the guide.
- Whether the old names are kept for a transition period as small forwarding scripts.
- Which version ships the correction: an installation at 0.10.0 is updated only by a newer installer or with `--repair`.

**Not part of this request:** renaming the product, the Python package or the repository; changing what the scripts do; any other behaviour of the installer.

**Related items:** FEA-0009 (the standalone installer, where both mistakes were made); TASK-0003 (the first installer, which introduced the script names); IS-0008 (found on the same first installation: the empty start of a new installation); IS-0003 (nothing secret in the guide or the report).

---

## IS-0007: Language Combo Box, Optional Import Menu Entries, Application Icon and Built-in Help

**Status:** Implemented in commit 04f451e (tracked as IS-0007 in MyIssueDesk). All four parts are done; see `docs/dashboard-help-and-icons.md`. Decisions taken at planning: the combo box lists each language by its own name; hiding an import entry removes only the menu entry (the *GitHub* page of FEA-0008 is not part of that setting); the icon sizes are 32, 48, 180, 192 and 512 pixels plus a multi-size `favicon.ico`, generated from the master picture, which stays in the sources; the help sources are Markdown, with the same section anchors in every language, and the Hungarian and Chinese texts still need a review by a native speaker. The check in a real browser (headless Edge) also showed that the left panel was as high as the whole page, so the Help button would have been at the end of the page; the panel now keeps the window height.

**Related items:** FEA-0004 (Settings page: the place of the new settings and of the audit log); FEA-0005 (Hungarian localisation: the supported languages, and the translation of the help); IS-0003 (navigation and presentation of the Settings page); FEA-0007 and FEA-0008 (the import and export pages, which the help describes).

**Summary:** Four improvements of the dashboard shell of this fork: a language combo box instead of the language buttons; the three import entries of the left panel made optional; the supplied picture used as the icon of the web pages; and a Help button at the bottom of the left panel that opens a help in every supported language.

### Part 1: Language selection

**Current state:** The languages are offered as a group of buttons in the top bar. On a narrow window the buttons are crowded or end up under each other, and every new language would make the group wider.

**Requirements:**
- The language is chosen with a **combo box** (a drop-down list). It shows the current language and lists the supported languages, each by its own name (English, Magyar, 中文), whatever the current language is.
- Choosing a language applies it at once and keeps the user on the same page, with the same address and query, exactly as the buttons do now. The choice is remembered as it is today.
- The combo box is operated with the keyboard, has an accessible name, and takes little room on a narrow window. Adding a language to the software adds it to the list without any change of the layout.
- Without JavaScript the combo box still works (it comes with a small button that applies the choice).

### Part 2: Optional import entries in the left panel

**Current state:** The left panel always shows *Import GitHub*, *Import History* and *Import Files*.

**Requirements:**
- Each of the three entries can be switched on or off in the **Settings page**, in a section *Navigation*. The setting takes effect without restarting the server, can be reset to its default, and every change is recorded in the settings audit log.
- The default of every entry is **off** in this fork. An installation that wants the entries switches them on.
- Switching an entry off only removes the menu entry. The page itself stays reachable by its address and from the links on the related pages, so nothing becomes unavailable, and the entry of the page that is open is still highlighted correctly.
- The title of a page that is open while its entry is off is still shown correctly in the top bar.

| Setting | Allowed values | Default |
|---|---|---|
| Show *Import GitHub* in the left panel | on / off | off |
| Show *Import History* in the left panel | on / off | off |
| Show *Import Files* in the left panel | on / off | off |

### Part 3: Application icon

**Current state:** The picture `src\resources\favicon_my_issuedeck.png` has been supplied (1254 × 1254 pixels, about 950 KB). It lies outside the package folder, so it is neither served by the dashboard nor included in the installable package, and no page declares an icon at all, so browsers ask for `/favicon.ico` and get nothing.

**Requirements:**
- The picture is used as the **icon of every page** of the dashboard, including the sign-in page, in light and dark browser themes.
- The icon is part of the installable package and is served by the dashboard from a fixed address. The server also answers `/favicon.ico`, because browsers ask for it by default.
- A browser shall not have to download the 950 KB original on every page. Smaller versions are made from it (for the browser tab, for a bookmark and for a phone's home screen: for example 32, 48, 180, 192 and 512 pixels), and the pages declare them. The original stays in the sources as the master.
- The icon is cached by the browser, and a changed icon is picked up without clearing the cache by hand.
- The page title, the icon and the other pages (for example the printed or exported pages) stay consistent.

### Part 4: Built-in help

**Requirements:**
- A **Help button** is placed at the bottom of the left panel. It is always visible, also when the list of entries is long or the window is low, uses the same style and active-state highlighting as the other entries, and carries an icon and a label.
- The button opens a **help in HTML** inside the dashboard, in the language the user has chosen. A help exists for **every supported language** (English, Hungarian and Simplified Chinese). When a part is missing in a language, the English text is shown, and the missing part is marked.
- The help covers, at least: signing in; projects and how to create, export and delete them; items, kinds and statuses; the Kanban board with drag and drop; the list, search and filters; the time fields and the overview charts; agent work sessions and live updates; the Settings page, colours and tokens; the import and export of files, GitHub issues, snapshots and GitHub repositories; the keyboard shortcuts; and how an AI agent is connected through MCP.
- The help has a table of contents, anchors that can be linked to, and a search or an index; it follows the light and dark theme, can be printed, and shows the version of the software.
- The help pages are **generated** from one source text per language by a script in the repository (so the languages stay in step and a page is regenerated when its source changes), and the generated pages are part of the installable package. A test fails when a supported language has no help, or when a page of one language has no counterpart in another.

**Points to settle when the issue is planned:**
- Whether the language list in the combo box shows names only or also a flag-free short code (for example *EN*).
- Whether hiding the import entries should also hide the *GitHub* page of FEA-0008, or whether that page gets a setting of its own.
- The exact set of icon sizes, and whether the master picture should be reduced in the sources.
- The format of the help sources (Markdown is proposed) and who reviews the Hungarian and Chinese texts, which would otherwise be drafts.
- Whether the help opens in the dashboard layout or in a separate tab, and whether it is also reachable from the sign-in page.
---

## IS-0006: Drag and Drop on the Kanban Board Stops Working After the First Move

**Status:** Implemented in commit e62849a (tracked as IS-0006 in MyIssueDesk). The cause was confirmed: after the first live update the replaced columns had no drag handlers. Verified with the real page and scripts in jsdom (handlers present after repeated updates, counters right, a refused move puts the card back, an update held during a drag is applied after the drop); a real mouse or touch drag was not tried in a browser.

**Related features:** FEA-0006 (live updates replace the board; the agent sessions widget is shown on the same board)

**Summary:** On the Kanban board a card can be moved by drag and drop only once. After the first move, no card can be dragged any more until the page is changed or reloaded.

**Observed behaviour:** After one card has been dragged to another column, further dragging, of the same card or of any other card, has no effect. Navigating to another page and back (or reloading) makes dragging work again, for one move.

**Probable cause** (to be confirmed by reproducing the defect): moving a card changes its status, the server announces the change, and the open board is replaced with the new content (live updates). The drag and drop handlers are attached only once, when the page loads, so the replaced columns have none. Unlike the Overview and the item page, the Kanban page does not prepare itself again after a replacement.

**Circumstances the fix shall cover:**
1. Any number of successive moves, of the same card and of different cards, between any columns, without leaving the page.
2. A move within one column (no status change) and a move to another column.
3. A move whose status change the server rejects or that fails because of the network: the card returns to its place, an error is shown, and dragging keeps working.
4. Changes made by someone else while the board is open (an AI agent, the command line, another browser tab): the board is updated in place, and every card on it, including new and moved ones, can then be dragged.
5. An update that arrives while a card is being dragged: the drag is not interrupted, the update is applied after the drop, and dragging keeps working afterwards.
6. Live updates switched on, switched off in the Settings page, and the automatic fallback refresh when the event channel is unavailable.
7. The agent sessions widget on the board and the column counters stay correct after every move and every replacement.
8. Mouse and touch input, light and dark theme, and every supported language.
9. A board with empty columns, and with a long column that needs scrolling.

**Requirements:**
- Dragging cards shall work after every replacement of the board content, without a page change.
- Handlers shall not be attached twice to the same column, so one move produces one status change and one notification.
- Column counters, the highlight of changed cards and the saved status shall agree with what the board shows after each move.
- Automated tests shall fail when the board is replaced and dragging is not prepared again, and shall cover the circumstances 1 to 6 where a test can reproduce them.
- The change shall be recorded in the CHANGELOG and linked to the related items in MyIssueDesk.

---

## IS-0005: Layout Defects on the Settings Page

**Status:** Open.

**Related features:** FEA-0004 (Settings page), FEA-0006 (Agent sessions widget and live updates)

**Summary:** Form fields and cards on the Settings page are not aligned, which makes the page look unfinished.

**Observed defects** (dark theme, wide window):
1. *Agent sessions widget* section: in the row with *Also show sessions completed within the last* and *Maximum number of sessions*, the first label wraps onto two lines, so its input is lower than the input beside it. The row *Scope* and *Initial state* is affected in the same way.
2. *Live updates* section: in the row with *Fallback refresh interval*, *Highlight changed entries for* and *When the view being edited changes*, the middle label wraps onto two lines, so its input is lower than the other two.
3. *Display* and *Tracking defaults* cards: the first fields of the two cards start at different heights, because only one card has a description line, and the *Save* buttons are at different heights.

**Requirements:**
- The inputs of the fields in one row shall be on the same line, whatever the length of the labels, in every supported language and at every window width.
- Cards that stand side by side shall have the same structure: a heading, a description, the fields, and the action buttons aligned along the bottom edge of the cards.
- On a narrow window the fields shall be stacked without overlap or horizontal scrolling.
- A test shall fail when the alignment rules of these rows and cards are removed.

---

## IS-0004: Markdown Rendering in the Item Content Pane

**Summary:** The content of an item shall be displayed as correctly formatted Markdown on the item page.

**Description:** The content of an item is converted by a script in the browser, but it is displayed without formatting: headings, bullet and numbered lists, tables and code blocks are not distinguishable from plain text, because the style classes the page relies on do not exist in the stylesheet. In addition, characters such as `>`, `<`, `&` and quotation marks are altered before the conversion, so block quotes, comparisons and code samples are displayed incorrectly. The converted content is inserted into the page without any sanitising.

**Requirements:**
- Headings, paragraphs, emphasis, ordered, unordered and task lists, links, block quotes, inline code, fenced code blocks, tables, horizontal rules and images shall be displayed with clear formatting, in both light and dark mode.
- The Markdown source shall reach the converter unchanged, with all characters preserved.
- Raw HTML in the content shall not be executed (it shall be displayed as text), and links and images with unsafe addresses (for example `javascript:`) shall not be active. Links to external addresses shall open in a new tab without access to the opener page.
- The preview in the item form shall use the same conversion and formatting as the item page.
- No new runtime dependency shall be added.

---

## IS-0003: Server Configuration Tokens on the Settings Page

**Status:** Implemented in commit c41fa00 (tracked as IS-0003 in MyIssueDesk), including Part 2.

**Related feature:** FEA-0004 (Settings page)

**Summary:** Make the tokens defined in the server configuration file visible and manageable on the Settings page.

**Description:** The tokens defined in `server.toml` (the administrator token `api_token` and any `[[tokens]]` entries) are currently listed by name only. They shall be treated like the tokens created in the dashboard. For each of them the Settings page shall:

- show the name, the scopes and a masked preview of the value, so the token can be recognised;
- allow the full value to be revealed on request;
- allow the token to be regenerated, with the new value shown once;
- allow a `[[tokens]]` entry to be renamed and its scopes to be changed (the administrator token `api_token` keeps its name and its `admin` scope).

**Requirements:**
- Changes shall be saved to `server.toml`, and shall take effect without restarting the server.
- The configuration file shall be validated before it is written, and shall be replaced atomically.
- Regenerating the administrator token shall not log the current user out.
- Every reveal, regeneration and change shall be recorded in the settings audit log, without the token value.
- The page shall warn that clients using the old value, such as `.mcp.json`, must be updated after a regeneration.

### Part 2: Navigation and presentation of the Settings page

**Navigation**
- The Settings menu item shall be placed in the main navigation directly after *Import Files*, shall carry a gear icon, and shall use the same styling and active-state highlighting as the other menu items. It shall not be placed at the bottom of the sidebar.
- The Settings page shall display the same navigation menu as the main pages of the dashboard, so that the user can move to any project view from it.

**Presentation of tokens**
- Each token shall be presented as a clearly structured entry in which the name, the scopes and the masked value are separate, readable elements. The name, scopes and value shall not run together into one line of text.
- The same presentation shall be used for the tokens defined in `server.toml` and for the tokens created in the dashboard.
- The dashboard styles required for the page shall be part of the compiled stylesheet, so that the layout does not depend on styles that are missing from it.

**Behaviour without page reloads**
- The *Show value* and *Regenerate* actions shall not reload the page. The value shall appear in place, next to the token concerned, shall be possible to copy and to hide, and shall be visible without scrolling.
- Creating, renaming, changing the scopes of, regenerating and deleting a token shall likewise update the token list in place, and errors shall be displayed next to the token concerned.
- Without JavaScript the actions shall continue to work as ordinary form submissions.

---

## IS-0002: Hungarian Localisation of Status Names

**Status:** Implemented in commit 9aee50b (tracked as IS-0002 in MyIssueDesk).

**Related feature:** FEA-0005 (Hungarian localisation)

**Summary:** Show the status names of the Kanban board and the dashboard diagrams in Hungarian when the Hungarian language is selected.

**Description:** The Kanban column headers and the status-based diagrams shall display the status names in Hungarian. The standard statuses shall be translated as follows:

| Status key | English | Hungarian |
|---|---|---|
| `proposed` | Proposed | Javasolt |
| `in_progress` | In Progress | Folyamatban |
| `blocked` | Blocked | Blokkolva |
| `ready_to_ship` | Ready to Ship | Kiadásra kész |
| `done` | Done | Kész |
| `wontfix` | Won't Fix | Nem javítandó |

**Scope:**
- The Kanban board column headers.
- The status doughnut chart and the Estimated vs spent time chart on the Overview page (legend labels, tooltips).
- Status labels in the list view, filters, item badges and the status selector.

**Notes:**
- Status names are read from each project's configuration. A status key that is not one of the standard keys above (a custom status) keeps the label defined in the project configuration.
- The English and Chinese labels stay as they are.

---

## IS-0001: Default Estimated Time and Improved Chart Contrast

**Status:** Implemented in commit 8d7356a (tracked as IS-0001 in MyIssueDesk).

**Summary:** Assign a default estimated time to items that have none, and increase the colour contrast of the time overview diagram.

**Related features:** FEA-0001, FEA-0002

### Part 1 (FEA-0001): Default Estimated time

Every item that does not have an *Estimated time* value shall be assigned a default value of 30 minutes (0.5 hours). This applies to existing items that lack the value as well as to newly created items.

### Part 2 (FEA-0002): Chart colour contrast

The time overview diagram shall use colours with a clearer visual difference between the *Estimated time* series and the *Time spent* series than the current colours provide.

---
