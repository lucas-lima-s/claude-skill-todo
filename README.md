# claude-skill-todo

An agent skill (Claude Code, Codex, Gemini/agy, Cursor) that keeps a persistent cross-session TODO list in a local markdown file and reconciles it bidirectionally with a Notion page over MCP.

## Why

A session's todo list dies with the session. This one survives, and it lives where you already keep notes (Notion) as well as on disk, so neither side is a silo: add an item mid-conversation and it is on your Notion page within a minute, or add it in Notion and it shows up locally the next time you touch the list.

## How the sync works

`scripts/todo_sync.py` performs a three-way merge between the local file, the freshly fetched Notion page and a snapshot of the last successful push (`data/.sync-snapshot.md`):

- An item present in the snapshot but missing on one side was removed there, so it is removed from both. `/todo remove` and deleting a line in Notion both stick.
- An item on both sides takes the checkbox of the side that changed it since the snapshot, so unchecking works too. On a text conflict the local wording wins.
- A new item on either side is added; Notion-only text blocks are kept in the push.
- Before the first snapshot exists the merge is a union, and tombstones (`data/.tombstones.json`, 90 days) keep locally removed items from coming back.
- Items are matched by normalized text with a small fuzzy tolerance, ignoring checkbox state and timestamp.

Only one sync runs at a time (`data/.sync.lock`), the Notion page is fetched immediately before the push, and the snapshot only advances after a successful push. If the Notion MCP server is down or unauthenticated, the local file stays authoritative and the next sync retries.

## Read vs write flows

- **Flow A** (`/todo` with no arguments) syncs first, in the foreground, then displays the list.
- **Flow B** (`add`, `done`, `undone`, `remove`, `category`) applies the edit locally and answers immediately; Claude Code then syncs in a background subagent, while agents without background subagents (Codex, Gemini/agy, Cursor) sync in the foreground right after answering.

## Install

Clone the repository and link it into your agent's skills directory (for example `~/.claude/skills/todo/` or `~/.agents/skills/todo/`), then:

```bash
cp .env.example .env
```

Run `/todo setup` (or ask the agent to set up the todo skill) to link your Notion page. The sync script needs Python 3.11+ (`SKILLS_PYTHON`).

## Configuration

| `.env` key | Meaning |
|---|---|
| `TODO_NOTION_PAGE_ID` | The Notion page's UUID |
| `TODO_NOTION_PAGE_URL` | The page's full URL (derived from the id if omitted) |

Resolution order: process environment, then `.env`, then `data/config.json` (legacy fallback), then a prompt to run `/todo setup`. Full detail in [SETUP.md](SETUP.md).

No page id, URL, or personal item is committed to this repository; it ships templates only (`.env.example`, `data/config.json.example`, `data/TODO.template.md`).

## Usage

| Command | Effect |
|---|---|
| `/todo` | Show the current list |
| `/todo add <item>` | Add an item |
| `/todo done <item>` | Mark an item complete |
| `/todo remove <item>` | Remove an item |
| `/todo category <name>` | Add a new category |
| `/todo setup` | (Re-)link the Notion page |

It also triggers on natural-language requests, including in Portuguese: "adiciona na minha lista", "anota pra depois", "o que tá pendente?", "marca X como feito", or when you mention a future idea worth saving mid-conversation.

## Sample output

Rendered from a fresh install, straight off `data/TODO.template.md`:

```markdown
# Todo List

Items managed by the `/todo` skill. Last sync: 2026-01-01 09:00.

## Inbox
- [ ] Replace this with your first item `2026-01-01`

## Ideas
- [x] Example of a completed item `2026-01-01`
```

## Prerequisite: Notion MCP

The skill uses three Notion tools: `notion-search`, `notion-fetch` and `notion-update-page`. They exist under those names in both the claude.ai Notion connector (prefixed `mcp__claude_ai_Notion__` in Claude Code) and the hosted Notion MCP server (`https://mcp.notion.com/mcp`) used by other agents. With a different server, use its equivalents; [SKILL.md](SKILL.md) lists them per agent.

## License

MIT, see [LICENSE](LICENSE).
