# Requested issues

## IS-0007: Language Combo Box, Optional Import Menu Entries, Application Icon and Built-in Help

**Status:** Implemented, not yet committed (tracked as IS-0007 in MyIssueDesk). All four parts are done; see `docs/dashboard-help-and-icons.md`. Decisions taken at planning: the combo box lists each language by its own name; hiding an import entry removes only the menu entry (the *GitHub* page of FEA-0008 is not part of that setting); the icon sizes are 32, 48, 180, 192 and 512 pixels plus a multi-size `favicon.ico`, generated from the master picture, which stays in the sources; the help sources are Markdown, with the same section anchors in every language, and the Hungarian and Chinese texts still need a review by a native speaker. The check in a real browser (headless Edge) also showed that the left panel was as high as the whole page, so the Help button would have been at the end of the page; the panel now keeps the window height.

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
