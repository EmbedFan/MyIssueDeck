# Dashboard Help, Icons and Navigation Settings

How the built-in help, the web icons and the optional left-panel entries are maintained.

## The built-in help

The **Help** button at the bottom of the left panel opens `/dashboard/help` in the language the
user has chosen. There is one Markdown source per supported language:

```
src/issuedeck/features/dashboard/help/src/en.md
src/issuedeck/features/dashboard/help/src/hu.md
src/issuedeck/features/dashboard/help/src/zh-CN.md
```

Every second-level and third-level heading carries an explicit anchor, `## Title {#anchor}`. The
anchors are the same in all languages, so a link to a section works everywhere. After editing a
source, regenerate the pages (they are committed and shipped in the package):

```bash
python scripts/build_help.py          # write help/<lang>.html
python scripts/build_help.py --check  # only compare; exit 1 when a page is out of date
```

The generator turns the Markdown into HTML with a table of contents, never passes raw HTML
through, and refuses a heading without an anchor, a repeated anchor, or a bold marker that was
not recognised. (With Chinese text, write punctuation such as the full-width colon outside the
marker: `**label**：text`, not `**label：**text`.) The tests fail when a supported language has no
source or page, when a page is out of date, or when the languages do not have the same sections.

### The Claude and Codex parts (IS-0014)

The help has a part for Claude (`{#claude}` and its subsections) and one for Codex (`{#codex}`),
each with the connection steps, the tools, the working method and an **example prompt** that
teaches the agent how to work with the tracker. The prompts are written once, in
`docs/agent-prompts/claude-prompt.md` and `codex-prompt.md` (the text in the code block), and
copied verbatim into the three help sources. Tests (`tests/unit/features/dashboard/
test_help_agents.py`) fail when a prompt differs from its file, when a tool named in the help or a
prompt does not exist on the MCP server, when a tool of the server is missing from the tool table
of the Claude part, or when a language lacks one of the sections. When you add or rename an MCP
tool, update the table in all three sources. Do not name the prompt files `CLAUDE.md` or
`AGENTS.md`: the agents would read them as standing instructions. A prompt must not contain `**`
(the page generator refuses a bold marker it did not recognise), and the steps for the agents
follow their own documentation, so check them again when a tool changes.

To add a language, add it to `SUPPORTED_LANGS` and `LANGUAGE_NAMES` in `i18n.py`, a label to
`CONTENTS_LABEL` in `help_build.py`, a source `help/src/<lang>.md`, and run the generator.
The Hungarian and Chinese texts were drafted together with the English text and should be
reviewed by a native speaker.

## The web icons

The master picture is `src/resources/favicon_my_issuedeck.png`. It is large and stays in the
sources only. The small versions that the pages use are generated into
`src/issuedeck/features/dashboard/static/img/` (so they are served and shipped):

```bash
python scripts/make_icons.py      # needs Pillow (a tool for this script only)
```

It writes `favicon-32.png`, `favicon-48.png`, `apple-touch-icon.png` (180 px), `icon-192.png`,
`icon-512.png`, a multi-size `favicon.ico` (16, 32, 48 px) and the web manifest. Every page
declares them through `components/icons.html`; the addresses carry a hash of the icon, so a
changed icon is picked up without clearing the browser cache. `/favicon.ico` is also answered
(without signing in), because browsers ask for it by default.

## Language and optional entries

The language is chosen with a combo box in the top bar; each language is listed by its own name.

*Import GitHub*, *Import History* and *Import Files* in the left panel are switched on and off in
the Settings page, section **Navigation**. They are **off** by default in this fork. Switching an
entry off only removes the menu entry; the page stays reachable by its address.
