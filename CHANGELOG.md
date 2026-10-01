# Changelog

## [Unreleased]

- Three-way merge (`scripts/todo_sync.py`) against a snapshot of the last push, with tombstones for removed items, so removals and unchecks on either side no longer come back. Covered by unit tests.
- Syncs are serialized with a lock file, fetch right before the push, and only advance the snapshot after a successful push. Notion-only text blocks are kept.
- New `/todo undone` command.
- Instructions for Codex, Gemini/agy and Cursor: foreground sync and the hosted Notion MCP tool names.
- The background sync subagent uses `haiku` and reads the file itself instead of receiving its content in the prompt.
- Line endings of `data/TODO.md` are preserved as found; the `Last sync` header is updated locally too.
- Notion content is treated as data; user-facing phrases are in Brazilian Portuguese and the page footer no longer names a single agent.
- The hygiene tests scan only files git would track, so local data no longer fails them.

## [1.0.0] - 2026-08-25

- Initial public release.
- `.env`-based configuration for the Notion page id and URL, with `data/config.json` kept only as a gitignored legacy fallback.
- Templates instead of committed state: `.env.example`, `data/config.json.example`, `data/TODO.template.md`.
