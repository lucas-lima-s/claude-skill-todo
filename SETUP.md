# Setup: todo

## Prerequisites

| Item | Notes |
|---|---|
| Notion MCP server | The claude.ai Notion connector (Claude Code), the hosted Notion MCP server `https://mcp.notion.com/mcp` (Codex, Cursor, Gemini/agy), or any server exposing `search` / `fetch` / `update-page` equivalents |
| Python 3.11+ | Runs `scripts/todo_sync.py` (stdlib only), the three-way merge. Point `SKILLS_PYTHON` at the interpreter, or have `python3`/`python` on `PATH` |
| Notion page | A page you own to sync with (the skill discovers or creates a link to one titled "TODO") |

The `tests/` suite covers the merge script and repository hygiene: `uv run pytest -q`.

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
3. `data/config.json`: legacy/local fallback, also gitignored.
4. Nothing resolved: the skill asks you to run `/todo setup`.

## Local files

- `data/TODO.md` is created from `data/TODO.template.md` on first run and is gitignored.
- `data/config.json` is an optional legacy fallback for the same two keys `.env` holds, also gitignored.
- `data/.sync-snapshot.md` (merge base), `data/.tombstones.json` (removed items, 90 days) and the transient `data/.remote.md`, `data/.pending-push.md`, `data/.sync.lock` are gitignored sync state. Deleting the snapshot is safe: the next sync falls back to a union merge filtered by tombstones.

## Authentication

Handled entirely by the Notion MCP server's OAuth flow. This skill stores no token and reads no credential file of its own.

## Validation

```
/todo
```

Expected result: the rendered list (or the template's two example items on a fresh install).

Troubleshooting:
- The skill reports no page configured → run `/todo setup`.
- Sync silently no-ops: check that the MCP server is authenticated.
- "sincronização já em andamento" persists: a crashed sync left `data/.sync.lock`; it is reclaimed automatically after 15 minutes, or run `todo_sync.py unlock`.

## Limitations

- Sync is eventual: there is no watcher.
- Edits made directly in Notion appear locally only after the next sync.
- Before the first snapshot exists, an item deleted only in Notion comes back from the local file once; after that, deletions on either side stick.

## `[tool.black]` note

`pyproject.toml` carries a `[tool.black]` section purely so external tooling that only reads Black's config agrees with ruff's line length; ruff is this repository's actual lint and format tool, there is no Black invocation anywhere in CI or in the dev dependencies.
