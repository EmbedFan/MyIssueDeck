# Requested issues

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
