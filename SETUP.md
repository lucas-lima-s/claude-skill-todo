# Setup — todo

## Prerequisites

| Item | Notes |
|---|---|
| Notion MCP server | A Notion MCP server connected in Claude Code — the built-in Notion connector, or any MCP server exposing `search` / `fetch` / `update-page` equivalents |
| Notion page | A page you own to sync with (the skill discovers or creates a link to one titled "TODO") |

No Python is needed to run the skill; the `tests/` suite in this repository validates repository hygiene only, it is not a runtime dependency of `/todo`.

## First-time configuration

```bash
cp .env.example .env
```

Then either:

- Fill `TODO_NOTION_PAGE_ID` by hand. It is the 32 hex characters after the last `-` in the page's Notion URL.
- Or run `/todo setup` and let the skill discover the page and write `.env` for you.

`.env` format:

```
TODO_NOTION_PAGE_ID=<notion-page-uuid>
TODO_NOTION_PAGE_URL=<notion-page-url>
```

`.env` is gitignored and must never be committed.

## Configuration precedence

1. Process environment: `TODO_NOTION_PAGE_ID`, optionally `TODO_NOTION_PAGE_URL`.
2. `.env` at the skill root (last assignment wins if a key repeats).
3. `data/config.json` — legacy/local fallback, also gitignored.
4. Nothing resolved — the skill asks you to run `/todo setup`.

## Local files

- `data/TODO.md` is created from `data/TODO.template.md` on first run and is gitignored.
- `data/config.json` is an optional legacy fallback for the same two keys `.env` holds, also gitignored.

## Authentication

Handled entirely by the Notion MCP server's OAuth flow. This skill stores no token and reads no credential file of its own.

## Validation

```
/todo
```

Expected result: the rendered list (or the template's two example items on a fresh install).

Troubleshooting:
- The skill reports no page configured → run `/todo setup`.
- Sync silently no-ops → check that the MCP server is authenticated.

## Limitations

- Sync is eventual — there is no watcher.
- Edits made directly in Notion appear locally only after the next sync.

## `[tool.black]` note

`pyproject.toml` carries a `[tool.black]` section purely so external tooling that only reads Black's config agrees with ruff's line length; ruff is this repository's actual lint and format tool, there is no Black invocation anywhere in CI or in the dev dependencies.
