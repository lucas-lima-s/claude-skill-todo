# claude-skill-todo

A Claude Code skill that keeps a persistent cross-session TODO list in a local markdown file and reconciles it bidirectionally with a Notion page over MCP.

## Why

A session's todo list dies with the session. This one survives, and it lives where you already keep notes (Notion) as well as on disk, so neither side is a silo: add an item mid-conversation and it is on your Notion page within a minute, or add it in Notion and it shows up locally the next time you touch the list.

## How the sync works

Categories and items from either side are unioned into the merged result. A `[x]` checkbox on either side wins (an item completed in Notion shows as done locally, and vice versa). On a text conflict — the same item worded differently — the local file wins, since it is what you are actively editing. Items are matched by fuzzy text, ignoring checkbox state and timestamp, so a small rewording does not create a duplicate.

Failure mode: if the Notion MCP server is down or unauthenticated, the local file stays authoritative and the push is simply retried on the next operation. You never lose an edit because Notion was unreachable.

## Read vs write flows

- **Flow A** (`/todo` with no arguments) syncs first, in the foreground, then displays the list — so what you see already reflects anything changed in Notion.
- **Flow B** (`add`, `done`, `remove`, `category`) applies the edit locally, answers immediately, and pushes to Notion in a background agent.

The reasoning: you should never wait on a network round-trip just to see your own edit reflected back at you.

## Install

```bash
cp -r . ~/.claude/skills/todo/
cd ~/.claude/skills/todo
cp .env.example .env
```

Then run `/todo setup` inside Claude Code to link your Notion page.

## Configuration

| `.env` key | Meaning |
|---|---|
| `TODO_NOTION_PAGE_ID` | The Notion page's UUID |
| `TODO_NOTION_PAGE_URL` | The page's full URL (derived from the id if omitted) |

Resolution order: process environment → `.env` → `data/config.json` (legacy fallback) → prompt to run `/todo setup`. Full detail in [SETUP.md](SETUP.md).

No page id, URL, or personal item is committed to this repository — it ships templates only (`.env.example`, `data/config.json.example`, `data/TODO.template.md`).

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

Items managed by the Claude Code `/todo` skill. Last sync: 2026-01-01 09:00.

## Inbox
- [ ] Replace this with your first item `2026-01-01`

## Ideas
- [x] Example of a completed item `2026-01-01`
```

## Prerequisite: Notion MCP

This skill calls three tools from the Claude Notion connector: `notion-search`, `notion-fetch`, and `notion-update-page`. With a different Notion MCP server, update those three call sites in [SKILL.md](SKILL.md) to the equivalent tool names.

## License

MIT — see [LICENSE](LICENSE).
