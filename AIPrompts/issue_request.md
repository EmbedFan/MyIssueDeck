# Requested issues

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
