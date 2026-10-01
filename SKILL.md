---
name: todo
description: "Lista de TODO persistente entre sessões (data/TODO.md, sincronizada com a página \"TODO\" do Notion). Use em /todo, \"adiciona na minha lista\", \"anota pra depois\", \"o que tá pendente?\", \"marca X como feito\" ou ideia futura. Não é para passos da sessão atual."
---

# Todo — Persistent Task List + Notion Sync

Manages `data/TODO.md` as a persistent cross-conversation task list, synced bidirectionally with a Notion page.

## Configuration

Paths below are relative to this skill's root directory.

Resolve the Notion page id (and, when possible, its URL) in this order:

1. Process environment: `TODO_NOTION_PAGE_ID`, optionally `TODO_NOTION_PAGE_URL`.
2. `.env` at the skill root — plain `KEY=value` lines, `#` comments allowed, optional surrounding quotes stripped. Read it with the Read tool; if a key is assigned more than once, the last assignment wins.
3. `data/config.json` — legacy/local fallback holding the same two keys (`notion_page_id`, `notion_page_url`).
4. If nothing resolves, tell the user to run `/todo setup`.

If `TODO_NOTION_PAGE_URL` is absent but the id is present, derive the URL as `https://www.notion.so/<id-with-dashes-removed>`.

Data paths:
- `data/TODO.md` — the live task list. Created from `data/TODO.template.md` on first run.
- `data/config.json` — optional legacy fallback for the two keys above.

`.env`, `data/config.json` and `data/TODO.md` are gitignored — the repository ships only templates.

Tool names below are the Claude Notion connector's. With a different Notion MCP server, adjust these three call sites.

## Setup (first-time or `/todo setup`)

If nothing resolves per "Configuration" above, run setup before any operation:

1. Search for the Notion page:
   - Use `mcp__claude_ai_Notion__notion-search` with `query: "TODO"` and `query_type: "internal"`
   - From results, find the page titled "TODO" (or closest match)
   - Extract the `url` from the result

2. Fetch the page to get the ID:
   - Use `mcp__claude_ai_Notion__notion-fetch` with `id: <url>`
   - Extract the page UUID from the response

3. Save config to `.env` at the skill root: if `.env` does not exist, write it with these two keys; if it already exists, edit only these two lines and leave the rest untouched:
   ```
   TODO_NOTION_PAGE_ID=<uuid>
   TODO_NOTION_PAGE_URL=<url>
   ```

4. Do initial sync (push local TODO.md to Notion using the Sync Protocol below)

5. Report: "Setup complete. Notion page linked." (see Important Notes below on never echoing the id or URL)

## Commands

Parse the user's intent from their message:

| Intent | Action |
|---|---|
| `/todo` (no args) | Read and display TODO.md |
| `/todo add <item>` | Add item to appropriate category (infer from content, or ask) |
| `/todo done <item>` | Mark item as `[x]` (fuzzy match on description) |
| `/todo remove <item>` | Remove item entirely |
| `/todo category <name>` | Add a new category header |
| `/todo setup` | Re-run setup (re-link Notion page) |

## Execution Rules

There are two flows depending on the command:

### Flow A — Read-only commands (`/todo` list, no args)

1. **Sync first (foreground)**: Launch an Agent (`model: "sonnet"`, `run_in_background: false`) with the Sync Protocol below. This ensures Notion changes are merged into local BEFORE displaying.
2. **Read local**: Read `data/TODO.md` (now up-to-date after sync)
3. **Respond to user**: Display the TODO list.

### Flow B — Write commands (`add`, `done`, `remove`, `category`)

1. **Read local**: Read `data/TODO.md`
2. **Execute command locally**:
   - Use the **Edit tool** (never Write) to modify TODO.md
   - When adding items, append ` \`YYYY-MM-DD\`` timestamp (today's date)
   - When adding, place under the most relevant existing category. If none fits, ask the user or create a new one
   - When marking done, keep the item visible as `[x]` (don't delete — useful for history)
   - When the user mentions an idea during normal conversation that sounds like a future task, suggest: "Want me to add this to your TODO?"
3. **Respond to user**: Show the result immediately. Do NOT wait for sync.
4. **Background Notion Sync**: Launch an Agent in background (`model: "sonnet"`, `run_in_background: true`) with the Sync Protocol below. Pass the current content of TODO.md in the prompt.

## Sync Protocol (for background agent)

The background agent must execute these steps:

### 4a. Resolve configuration
Resolve the page id and URL using the resolution order in "Configuration". If nothing resolves, abort the sync silently and leave a one-line note for the foreground agent.

### 4b. Fetch Notion content
Use `mcp__claude_ai_Notion__notion-fetch` with `id: <notion_page_url>` to get current Notion page content.

### 4c. Parse both sides
Parse both the local TODO.md and the Notion content into a structure:
- Categories (## headers)
- Items under each category (- [ ] or - [x] lines with optional timestamp)
- Sub-items (indented items)

### 4d. Merge (union strategy)
For each category found in either side:
- **Category exists only on Notion** → add it to local
- **Category exists only on local** → already there (will be pushed to Notion)
- **Item exists only on Notion** (not in local) → add to local under same category
- **Item exists only on local** → already there (will be pushed to Notion)
- **Item exists on both sides**:
  - If `[x]` on either side → mark `[x]` on both (checkbox wins)
  - If text differs slightly → keep local version (local is source of truth for text)
- **Items without timestamps** → add today's date

Match items by fuzzy text similarity (ignore checkbox state and timestamp when comparing).

### 4e. Write back local
If there were changes from Notion → use **Edit tool** to update `data/TODO.md`

### 4f. Push to Notion
Build the final markdown content with this format:

```markdown
# Todo List

Items managed via Claude Code `/todo` skill. Last sync: YYYY-MM-DD HH:MM.

## Category Name
- [ ] Item description `YYYY-MM-DD`
- [x] Completed item `YYYY-MM-DD`
```

Use `mcp__claude_ai_Notion__notion-update-page` with:
- `page_id`: resolved per "Configuration"
- `command`: `"replace_content"`
- `new_str`: the full markdown content

## Timestamp Format

- New items: append ` \`YYYY-MM-DD\`` (today's date)
- Existing items: preserve original timestamp
- Items migrated without timestamp: use the date the item was first seen

## Important Notes

- The background sync agent should run silently — no user-facing output needed
- If Notion MCP tools fail (network, auth), the local file is always the source of truth
- If nothing resolves per "Configuration", prompt the user to run `/todo setup`
- Never use the Write tool on TODO.md — always Edit to preserve CRLF line endings
- The first time after setup, use Write (new file, seeded from `data/TODO.template.md`) for TODO.md; after that, always Edit
- Never echo the resolved Notion page id or URL into the visible reply; refer to the page by title
