from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = SKILL_ROOT / "data"
TODO_NAME = "TODO.md"
SNAPSHOT_NAME = ".sync-snapshot.md"
PENDING_NAME = ".pending-push.md"
TOMBSTONES_NAME = ".tombstones.json"
LOCK_NAME = ".sync.lock"
LOCK_STALE_SECONDS = 15 * 60
TOMBSTONE_MAX_AGE_DAYS = 90
FUZZY_RATIO = 0.9
TITLE = "# Todo List"
SYNC_LINE_PREFIX = "Items managed"

ITEM_RE = re.compile(r"^- \[(?P<mark>[ xX])\] (?P<body>.+?)\s*$")
DATE_RE = re.compile(r"\s*`(?P<date>\d{4}-\d{2}-\d{2})`\s*$")
KEY_STRIP_RE = re.compile(r"[`*_~]")
SPACE_RE = re.compile(r"\s+")


@dataclass
class Item:
    checked: bool
    text: str
    stamp: str | None
    children: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return item_key(self.text)

    def render(self) -> list[str]:
        mark = "x" if self.checked else " "
        suffix = f" `{self.stamp}`" if self.stamp else ""
        return [f"- [{mark}] {self.text}{suffix}", *self.children]


@dataclass
class Category:
    name: str
    entries: list[Item | str] = field(default_factory=list)

    def items(self) -> list[Item]:
        return [entry for entry in self.entries if isinstance(entry, Item)]

    def notes(self) -> list[str]:
        return [entry for entry in self.entries if isinstance(entry, str)]


@dataclass
class Document:
    header: list[str] = field(default_factory=list)
    categories: list[Category] = field(default_factory=list)

    def category(self, name: str) -> Category | None:
        for category in self.categories:
            if category.name == name:
                return category
        return None


def item_key(text: str) -> str:
    cleaned = KEY_STRIP_RE.sub("", text).lower()
    return SPACE_RE.sub(" ", cleaned).strip().rstrip(".;:")


def note_key(line: str) -> str:
    return SPACE_RE.sub(" ", line).strip().lower()


def parse(text: str) -> Document:
    doc = Document()
    current: Category | None = None
    last_item: Item | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current = Category(line[3:].strip())
            doc.categories.append(current)
            last_item = None
            continue
        if current is None:
            if line.strip():
                doc.header.append(line)
            continue
        if not line.strip() or line.lstrip().startswith("<"):
            continue
        match = ITEM_RE.match(line)
        if match:
            body = match.group("body")
            stamp_match = DATE_RE.search(body)
            stamp = stamp_match.group("date") if stamp_match else None
            if stamp_match:
                body = body[: stamp_match.start()].rstrip()
            last_item = Item(match.group("mark").lower() == "x", body, stamp)
            current.entries.append(last_item)
            continue
        if line.startswith((" ", "\t")) and last_item is not None:
            last_item.children.append(line)
            continue
        current.entries.append(line)
        last_item = None
    return doc


def render(doc: Document, synced_at: str | None = None) -> str:
    header = list(doc.header) or [TITLE]
    if synced_at is not None:
        sync_line = f"Items managed by the `/todo` skill. Last sync: {synced_at}."
        replaced = False
        for index, line in enumerate(header):
            if line.startswith(SYNC_LINE_PREFIX):
                header[index] = sync_line
                replaced = True
        if not replaced:
            header.insert(1, sync_line)
    out: list[str] = []
    for line in header:
        out.append(line)
        out.append("")
    for category in doc.categories:
        out.append(f"## {category.name}")
        for entry in category.entries:
            out.extend(entry.render() if isinstance(entry, Item) else [entry])
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def index_items(doc: Document) -> dict[str, tuple[str, Item]]:
    found: dict[str, tuple[str, Item]] = {}
    for category in doc.categories:
        for item in category.items():
            found.setdefault(item.key, (category.name, item))
    return found


def match_remote_keys(local: dict, remote: dict) -> dict[str, str]:
    aliases = {key: key for key in remote if key in local}
    free_local = [key for key in local if key not in remote]
    for key in remote:
        if key in aliases:
            continue
        best = None
        best_ratio = FUZZY_RATIO
        for candidate in free_local:
            ratio = difflib.SequenceMatcher(None, key, candidate).ratio()
            if ratio >= best_ratio:
                best, best_ratio = candidate, ratio
        if best is not None:
            aliases[key] = best
            free_local.remove(best)
    return aliases


def merge_checked(local: bool, remote: bool, base: bool | None) -> bool:
    if base is None:
        return local or remote
    if local != base:
        return local
    return remote


@dataclass
class MergeReport:
    added_from_remote: list[str] = field(default_factory=list)
    removed_remotely: list[str] = field(default_factory=list)
    removed_locally: list[str] = field(default_factory=list)
    suppressed_by_tombstone: list[str] = field(default_factory=list)
    checkbox_from_remote: list[str] = field(default_factory=list)
    remote_notes_kept: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return dict(self.__dict__)


def merge(
    local: Document,
    remote: Document,
    base: Document | None,
    tombstones: dict[str, str],
    today: str,
) -> tuple[Document, MergeReport]:
    report = MergeReport()
    local_items = index_items(local)
    remote_items = index_items(remote)
    base_items = index_items(base) if base is not None else {}
    base_notes = {note_key(n) for c in (base.categories if base else []) for n in c.notes()}
    aliases = match_remote_keys(local_items, remote_items)
    remote_by_local = {local_key: remote_key for remote_key, local_key in aliases.items()}

    merged = Document(header=list(local.header))
    for category in local.categories:
        target = Category(category.name)
        for entry in category.entries:
            if isinstance(entry, str):
                target.entries.append(entry)
                continue
            key = entry.key
            remote_key = remote_by_local.get(key)
            if remote_key is None:
                if key in base_items:
                    report.removed_remotely.append(entry.text)
                    continue
                target.entries.append(_dated(entry, today))
                continue
            remote_item = remote_items[remote_key][1]
            base_entry = base_items.get(key) or base_items.get(remote_key)
            base_checked = base_entry[1].checked if base_entry else None
            checked = merge_checked(entry.checked, remote_item.checked, base_checked)
            if checked != entry.checked:
                report.checkbox_from_remote.append(entry.text)
            children = entry.children or remote_item.children
            target.entries.append(_dated(Item(checked, entry.text, entry.stamp or remote_item.stamp, children), today))
        merged.categories.append(target)

    base_category_names = {c.name for c in base.categories} if base is not None else set()
    for category in remote.categories:
        target = merged.category(category.name)
        created = False
        removed_locally = False
        if target is None:
            removed_locally = category.name in base_category_names
            target = Category(category.name)
            created = True
        local_notes = {note_key(n) for n in target.notes()}
        for entry in category.entries:
            if isinstance(entry, str):
                nk = note_key(entry)
                if not removed_locally and nk not in local_notes and nk not in base_notes:
                    target.entries.append(entry)
                    report.remote_notes_kept.append(entry)
                continue
            key = entry.key
            if key in aliases:
                continue
            if key in base_items:
                report.removed_locally.append(entry.text)
                continue
            if key in tombstones:
                report.suppressed_by_tombstone.append(entry.text)
                continue
            target.entries.append(_dated(entry, today))
            report.added_from_remote.append(entry.text)
        if created and target.entries:
            merged.categories.append(target)
    return merged, report


def _dated(item: Item, today: str) -> Item:
    if item.stamp:
        return item
    return Item(item.checked, item.text, today, list(item.children))


def read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_bytes().decode("utf-8")


def write_preserving_newlines(path: Path, text: str, like: str | None) -> None:
    newline = "\r\n" if like is not None and "\r\n" in like else "\n"
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def load_tombstones(path: Path, today: date) -> dict[str, str]:
    raw = read_text(path)
    if not raw:
        return {}
    data = json.loads(raw)
    cutoff = today - timedelta(days=TOMBSTONE_MAX_AGE_DAYS)
    return {key: stamp for key, stamp in data.items() if date.fromisoformat(stamp) >= cutoff}


def save_tombstones(path: Path, tombstones: dict[str, str]) -> None:
    path.write_text(json.dumps(dict(sorted(tombstones.items())), indent=2) + "\n", encoding="utf-8", newline="\n")


def acquire_lock(data_dir: Path, now: float | None = None) -> bool:
    lock = data_dir / LOCK_NAME
    current = time.time() if now is None else now
    if lock.exists() and current - lock.stat().st_mtime > LOCK_STALE_SECONDS:
        lock.unlink()
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    return True


def release_lock(data_dir: Path) -> None:
    lock = data_dir / LOCK_NAME
    if lock.exists():
        lock.unlink()


def cmd_merge(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    today = now.date().isoformat()
    local_path = data_dir / TODO_NAME
    local_text = read_text(local_path)
    if local_text is None:
        print(f"error: {local_path} not found", file=sys.stderr)
        return 2
    remote_text = read_text(Path(args.remote))
    if remote_text is None:
        print(f"error: {args.remote} not found", file=sys.stderr)
        return 2
    base_text = read_text(data_dir / SNAPSHOT_NAME)
    tombstones = load_tombstones(data_dir / TOMBSTONES_NAME, now.date())
    merged, report = merge(
        parse(local_text),
        parse(remote_text),
        parse(base_text) if base_text is not None else None,
        tombstones,
        today,
    )
    content = render(merged, now.strftime("%Y-%m-%d %H:%M"))
    write_preserving_newlines(local_path, content, local_text)
    (data_dir / PENDING_NAME).write_text(content, encoding="utf-8", newline="\n")
    summary = report.as_dict()
    summary["first_sync_without_snapshot"] = base_text is None
    summary["pending_push"] = str(data_dir / PENDING_NAME)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    pending = data_dir / PENDING_NAME
    if not pending.is_file():
        print("error: nothing pending to confirm", file=sys.stderr)
        return 2
    pending.replace(data_dir / SNAPSHOT_NAME)
    release_lock(data_dir)
    print("snapshot updated")
    return 0


def cmd_tombstone(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    today = date.fromisoformat(args.today) if args.today else date.today()
    path = data_dir / TOMBSTONES_NAME
    tombstones = load_tombstones(path, today)
    tombstones[item_key(DATE_RE.sub("", args.text))] = today.isoformat()
    save_tombstones(path, tombstones)
    print(f"tombstone recorded ({len(tombstones)} active)")
    return 0


def cmd_lock(args: argparse.Namespace) -> int:
    if acquire_lock(Path(args.data_dir)):
        print("lock acquired")
        return 0
    print("another sync is running", file=sys.stderr)
    return 3


def cmd_unlock(args: argparse.Namespace) -> int:
    release_lock(Path(args.data_dir))
    print("lock released")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todo_sync.py", description="Three-way merge for the todo skill.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    sub = parser.add_subparsers(dest="command", required=True)
    merge_parser = sub.add_parser("merge", help="merge a fetched Notion page into data/TODO.md")
    merge_parser.add_argument("--remote", required=True, help="file holding the fetched Notion page markdown")
    merge_parser.add_argument("--now", help="ISO timestamp to use instead of the current time")
    merge_parser.set_defaults(func=cmd_merge)
    confirm_parser = sub.add_parser("confirm", help="promote the pushed content to the sync snapshot")
    confirm_parser.set_defaults(func=cmd_confirm)
    tomb_parser = sub.add_parser("tombstone", help="record a removed item so it is not re-imported")
    tomb_parser.add_argument("text")
    tomb_parser.add_argument("--today")
    tomb_parser.set_defaults(func=cmd_tombstone)
    sub.add_parser("lock", help="take the sync lock").set_defaults(func=cmd_lock)
    sub.add_parser("unlock", help="release the sync lock").set_defaults(func=cmd_unlock)
    return parser


def main(argv: list[str] | None = None) -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure:
        reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
