# Requested features

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