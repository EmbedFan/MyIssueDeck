# Requested features

## FEA-0007: Project Import from a Snapshot

**Status:** Implemented in commit 6359d4c (tracked as FEAT-0007 in MyIssueDesk). Create and update are available from the command line (`issuedeck import-audit-bundle`) and from the dashboard (*Import snapshot*), both with an exact preview before anything is written. Decisions taken at planning: items are matched by their identifier and keep it; for items present in both, the policy is *keep* (default), *newer* or *overwrite*; missing activity entries, relationships, work sessions and import batches are always added; nothing is deleted from an existing project; the import is applied completely or not at all; a project created from the command line needs a restart of a running server. Not restored: tokens and server settings, and the numeric identifiers of events and work sessions.

**Summary:** Allow a project snapshot exported from MyIssueDesk to be imported again, either to create a new project or to update an existing one.

**Description:** A project can already be exported as a snapshot (an audit bundle in a ZIP file), from the project overview with *Export snapshot* or with `issuedeck export-audit-bundle`. A snapshot cannot yet be read back, so it serves as an archive and not as a backup. The software shall be able to import such a snapshot in two ways:

- **Create a project from a snapshot:** the import creates a new project from the contents of the snapshot (configuration, items, relationships, agent work sessions and import history).
- **Update a project from a snapshot:** the import brings an existing project up to the contents of the snapshot.

**Points to settle when the feature is planned:**
- How items of the snapshot are matched with the items of an existing project, and how conflicts are resolved when both have changed.
- Whether the import is checked first and shown as a preview before anything is written, and whether it is applied completely or not at all.
- Whether item identifiers, ship records and the activity timeline are kept exactly as in the snapshot.
- How the import is started (the dashboard, the command line, or both).

**Related items:** FEA-0003 (Safe project deletion: the snapshot kept when a project is deleted could be used to restore it); FEA-0002 and FEA-0001 (the time fields of the items are part of a snapshot).

---

## FEA-0006: Agent Sessions Widget on the Kanban Board and Live View Updates

**Status:** Implemented, not yet committed (tracked as FEAT-0006 in MyIssueDesk). Task 1 and Task 2 are complete with the settings listed below. Two notes: changes written by other processes (the CLI) are noticed by a watcher in the server and shown within a few seconds; the events are not filtered by project on the server, because every dashboard user is an administrator and the events contain identifiers only.

**Summary:** Provide an optional *Active agent sessions* widget at the top of the Kanban board, and make the open dashboard views follow changes made by background tasks (for example AI agent sessions) without a manual reload. Both functions shall be configurable on the Settings page.

### Task 1: *Active agent sessions* widget on the Kanban board

**Description:** The Kanban board shall be able to display the *Active agent sessions* widget, which the Overview page already provides, above the board columns. The widget shall be optional: it is switched on, and configured, on the Settings page.

**Settings** (Settings page, section *Agent sessions widget*). Every setting has a default value and can be reset to it.

| Setting | Allowed values | Default |
|---|---|---|
| Show the widget on the Kanban board | on / off | off |
| Show the widget on the Overview page | on / off | on |
| Session statuses shown | active, paused | active, paused |
| Also show sessions completed within the last | 0 (off) to 240 minutes | 0 |
| Maximum number of sessions shown | 1 to 20 | 8 |
| Scope | current project / all projects | current project |
| Initial state | expanded / collapsed | expanded |
| Information shown for a session | agent name, item, goal, last update, number of updates (each on or off) | all on |

**Requirements:**
- When the widget is switched off, it shall not be displayed and shall not occupy any space.
- Each session entry shall link to its item. When there is no session to show, an explanatory text shall be displayed.
- The widget shall follow the selected language and theme, and its texts shall be available in every supported language.
- A change of these settings shall take effect without restarting the server and shall be recorded in the settings audit log.

**Related items:** FEA-0004 (Settings page: the place of the settings and of the audit log); FEA-0005 (Hungarian localisation: the new texts shall be translated); IS-0002 (the status names shown in the widget follow the language).

### Task 2: Live updates of the dashboard views

**Description:** When a background task, for example an AI agent session, changes data that is shown in the current view, the server shall emit an event and the user interface shall follow it without a manual reload.

**Requirements:**
- **Events.** The server shall emit an event when an item is created, updated, changes status, is shipped, deleted or restored, when a relationship changes, when a work session starts, is updated or finishes, and when an activity entry is added. Events shall be emitted whatever the source of the change (dashboard, API, MCP or import).
- **Delivery.** Events shall be delivered to the open views through a push channel (server-sent events). When the channel is unavailable, the views shall fall back to periodic refresh, and the channel shall reconnect automatically.
- **Views that follow.** Kanban board, list, Overview (counters, charts and the widget) and item page (fields, content, activity and work sessions).
- **Applying changes.** Changes shall be applied in place. An element that is being edited (an open form, text being typed, a card being dragged) shall never be overwritten; a notice shall be displayed instead, from which the user can apply the change. Many events in a short time shall be combined, so that the page stays responsive.
- **Feedback.** Changed entries shall be highlighted briefly, and a connection indicator shall show whether the view is up to date.
- **Security.** Events shall be subject to the same authorisation as the rest of the dashboard, shall only concern projects the user may see, and shall not contain secrets.

**Settings** (Settings page, section *Live updates*). Every setting has a default value and can be reset to it.

| Setting | Allowed values | Default |
|---|---|---|
| Live updates | on / off | on |
| Fallback refresh interval | 5 to 300 seconds | 30 |
| Highlight changed entries for | 0 (off) to 30 seconds | 3 |
| When the view being edited changes | show a notice / apply after saving | show a notice |
| Views that follow live updates | Kanban, list, Overview, item page (each on or off) | all on |
| Events followed | item changes, work sessions, activity entries (each on or off) | all on |
| Show the connection indicator | on / off | on |

**Related items:** FEA-0004 (Settings page: the place of the settings and of the audit log); FEA-0002 (Time overview diagram: the Overview charts follow the updates); FEA-0001 (the estimated and spent time fields change when an agent records time); IS-0004 (the Markdown content pane is rendered again after a live update).

---

## FEA-0005: Hungarian Localisation

**Status:** Implemented in commit 9aee50b (tracked as FEAT-0004 in MyIssueDesk).

	Localise the software to Hungarian too.
	
---


## FEA-0004: Settings Page with Theme Colours and Token Management

**Status:** Implemented in commit c41fa00 (tracked as FEAT-0005 in MyIssueDesk). Management of the `server.toml` tokens and the presentation of the page were added by IS-0003 in the same commit. Not done: editing the default values of custom fields other than the estimated time, the display time unit, and an event history in items (changes are written to a separate settings audit log).

**Summary:** Provide a settings page where colours can be set by hand for light and dark mode, with a reset to the default palette, and where access tokens can be changed, added and regenerated.

**Description:** The dashboard shall include a settings page that allows the user to:

- **Theme colours:** set the colour scheme manually for light mode and for dark mode, with a control to reset the colours to the developer-defined default palette;
- **Access tokens:** create new access tokens, change their name and scopes, and regenerate an existing token, with the new value shown once;
- **Project settings:** edit the project name and description and the default values of the custom fields, such as the default estimated time;
- **Tracking defaults:** set the default estimated time for new items, and the time unit shown in the dashboard;
- **Display:** choose the default language and the default theme (light, dark or system).

Changes take effect without restarting the server where possible, and each change is recorded in the item event history.

---

## FEA-0003: Safe Project Deletion

**Status:** Implemented in commit e97ea99 (tracked as FEAT-0003 in MyIssueDesk).

**Summary:** Provide a safe way to delete a project.

**Description:** The dashboard shall offer an option to delete a project. Deletion shall be protected against accidental use, for example by requiring explicit confirmation before the project and its items are removed.

---

## FEA-0002: Time Overview Diagram

**Status:** Implemented in commit 8d7356a (tracked as FEAT-0002 in MyIssueDesk).

**Summary:** Add a diagram showing the estimated and spent time to the Overview page.

**Description:** The dashboard Overview page shall include a new diagram that visualises the *Estimated time* and *Time spent* fields, so that planned and actual effort can be compared at a glance.

---

## FEA-0001: Estimated and Actual Time Fields

**Status:** Implemented in commit efa1c6b (tracked as FEAT-0001 in MyIssueDesk). The default estimated time of 0.5 h is added by IS-0001 (commit 8d7356a).

**Summary:** Add two default fields, *Estimated time* and *Time spent*, to all items.

**Description:** Every item shall record its planned effort (*Estimated time*) and the effort actually spent (*Time spent*), so that planned and actual work can be compared. Both fields are required, and the system shall provide a summary of the total estimated and total spent time across all items.

---