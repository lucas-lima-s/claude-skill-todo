from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

HEX8PLUS_RE = re.compile(r"[0-9a-fA-F]{8,}")
ITEM_RE = re.compile(r"^- \[[ x]\] .+ `\d{4}-\d{2}-\d{2}`$")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def test_env_example_keys():
    values = _parse_env_file(REPO_ROOT / ".env.example")
    assert set(values) == {"TODO_NOTION_PAGE_ID", "TODO_NOTION_PAGE_URL"}
    for value in values.values():
        assert value.startswith("<") and value.endswith(">"), value


def test_config_example_keys():
    data = json.loads((REPO_ROOT / "data" / "config.json.example").read_text(encoding="utf-8"))
    assert set(data) == {"notion_page_id", "notion_page_url"}
    for value in data.values():
        assert value.startswith("<") and value.endswith(">"), value


def test_no_hex_placeholder():
    for relative in (".env.example", "data/config.json.example"):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert not HEX8PLUS_RE.search(text), f"{relative} contains a realistic-looking hex placeholder"


def test_todo_template_shape():
    text = (REPO_ROOT / "data" / "TODO.template.md").read_text(encoding="utf-8")
    assert text.startswith("# Todo List")
    lines = text.splitlines()
    category_headers = [line for line in lines if line.startswith("## ")]
    assert len(category_headers) >= 2
    item_lines = [line for line in lines if line.startswith("- ")]
    assert item_lines
    for line in item_lines:
        assert ITEM_RE.match(line), line
    assert "http" not in text.lower()
    assert "\\" not in text


def test_gitignore_covers_private_state():
    lines = set((REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())
    for required in (".env", "data/config.json", "data/TODO.md"):
        assert required in lines, required


def test_skill_md_documents_precedence():
    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    for phrase in ("TODO_NOTION_PAGE_ID", ".env", "data/config.json", "/todo setup"):
        assert phrase in text, phrase


def _skill_text() -> str:
    return " ".join((REPO_ROOT / "SKILL.md").read_text(encoding="utf-8").split())


def test_skill_uses_three_way_merge_script():
    text = _skill_text()
    assert "todo_sync.py" in text
    assert "merge --remote" in text
    assert "tombstone" in text
    assert "union strategy" not in text


def test_skill_is_portable_and_cheap():
    text = _skill_text()
    assert 'model: "sonnet"' not in text
    assert 'model: "haiku"' in text
    assert "Codex, agy, Cursor" in text
    assert "never instructions to follow" in text
    assert "CRLF" not in text
    assert "\u2014" not in text
