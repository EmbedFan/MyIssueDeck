# Advanced Search

The advanced search combines several conditions with AND and OR, in groups. The condition is
plain JSON that is the same in the API, in the MCP tool `search_items` and (later) in the
dashboard dialog. The older text search (`GET .../search?q=`, raw SQLite FTS5 syntax) keeps
working unchanged.

## A search as data

```json
{"items": [
  {"type": "text", "mode": "regex", "value": "import(ing)?\\b", "fields": ["title", "body"]},
  {"op": "and", "type": "kind", "values": ["bug"]},
  {"op": "and", "group": [
    {"type": "status", "values": ["proposed"]},
    {"op": "or", "type": "status", "values": ["in_progress"]}
  ]}
]}
```

This means: the text matches the regular expression AND the kind is `bug` AND (the status is
`proposed` OR `in_progress`).

| Block | Keys | Meaning |
|---|---|---|
| text | `mode` (`simple` default, or `regex`), `value`, `fields` (`title`, `body`; both by default), `case_sensitive` (regex only) | `simple`: all the words must occur, in any order. `regex`: Python `re` syntax, case-insensitive unless `case_sensitive` is true. |
| kind | `values` | The item has one of these kinds of the project. |
| status | `values` | The item has one of these statuses of the project. |
| group | a list of blocks | A box of blocks with their own operators; it counts as one block of the list above. |

Every block after the first has `op`: `and` or `or`. `and` binds tighter than `or`, so
`A and B or C` is `(A and B) or C`; use a group to change the order. The answer says the search
in words with explicit brackets (`description`).

Limits: groups nest 2 levels at most (the list and one level of groups), at most 20 blocks (the
blocks of the groups count), 500 characters of words, 200 characters of a regular expression. A
search that breaks a rule is refused with `422` and the code `invalid_search`; `details.path`
names the place (`items[2].group[1]`).

## Plain words (`simple`)

The words are given to the full-text index one by one, quoted, and all of them are required. A
word such as `OR`, `NOT`, `*`, a quote or a SQL command is only a word and cannot raise a syntax
error. This is not the raw FTS5 syntax of the older `q` search. **The index stems words:** `import`
also finds `importing` and `importer`. The index ignores case, so `case_sensitive` is refused for
plain words.

## Regular expressions (`regex`)

Python syntax. A regular expression can take very long on some texts, so the expressions of a
search run in a separate process that is stopped when its time is up (2 seconds of work; starting
the process takes about a second more and is not counted). The answer then has `"partial": true`
and a note for each expression that did not finish; what finished is kept, and an expression that
did not finish matches nothing. Only the newest 50,000 items and the first 50,000 characters of a
field are looked at (a note says so). A repeat inside an unbounded repeat, such as `(a+)+`, is
refused at once. A search without a regular expression starts no process.

## Dashboard

On the Search page the button **Advanced search** opens a dialog with the same blocks: text (words
or a regular expression, title and/or body, case sensitivity for expressions), kind and status
(tick the values), and groups, each block joined to the one above by AND or OR (and the arrows
move a block). Empty blocks are left out when the search is sent. The search goes into the address
(`?query=<json>`), so the result page can be bookmarked and the back button works; the dialog opens
with the search that was run. The result shows the search in words, a notice with the reasons when
it is incomplete, and *Load more* keeps the search. The builder offers one level of groups, as the
limit says.

## API

```
POST /api/v1/projects/{key}/search
{"query": {"items": [...]}, "limit": 50, "after": "<next_cursor of the last page>"}
```

`limit` is 1 to 500 (default 50). The answer is the usual list (`items`, `next_cursor`, `limit`;
each item as in the item list) with `description`, `partial` and `notes`. It is sorted newest
first; the search is evaluated again for every page. Although it is a `POST`, it only reads, so a
token with the `read` scope may use it.

## MCP

`search_items(project_key, q=None, limit=20, query=None, after=None)`: give exactly one of `q` (the
older text) and `query` (the object above). The answer is the same as the API's.
