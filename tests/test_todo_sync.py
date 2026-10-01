from __future__ import annotations

import json
import os
import time
from pathlib import Path

import todo_sync

TODAY = "2026-10-01"


def doc(*categories: tuple[str, list[str]]) -> todo_sync.Document:
    lines = ["# Todo List", ""]
    for name, items in categories:
        lines.append(f"## {name}")
        lines.extend(items)
        lines.append("")
    return todo_sync.parse("\n".join(lines))


def texts(document: todo_sync.Document) -> dict[str, bool]:
    return {item.text: item.checked for category in document.categories for item in category.items()}


def test_local_removal_sticks_when_item_was_synced():
    base = doc(("Inbox", ["- [ ] keep `2026-09-01`", "- [ ] drop me `2026-09-01`"]))
    remote = doc(("Inbox", ["- [ ] keep `2026-09-01`", "- [ ] drop me `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] keep `2026-09-01`"]))

    merged, report = todo_sync.merge(local, remote, base, {}, TODAY)

    assert texts(merged) == {"keep": False}
    assert report.removed_locally == ["drop me"]


def test_remote_removal_sticks_when_item_was_synced():
    base = doc(("Inbox", ["- [ ] keep `2026-09-01`", "- [ ] gone in notion `2026-09-01`"]))
    remote = doc(("Inbox", ["- [ ] keep `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] keep `2026-09-01`", "- [ ] gone in notion `2026-09-01`"]))

    merged, report = todo_sync.merge(local, remote, base, {}, TODAY)

    assert texts(merged) == {"keep": False}
    assert report.removed_remotely == ["gone in notion"]


def test_local_uncheck_wins_over_unchanged_remote_check():
    base = doc(("Inbox", ["- [x] task `2026-09-01`"]))
    remote = doc(("Inbox", ["- [x] task `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] task `2026-09-01`"]))

    merged, _ = todo_sync.merge(local, remote, base, {}, TODAY)

    assert texts(merged) == {"task": False}


def test_remote_check_propagates_when_local_unchanged():
    base = doc(("Inbox", ["- [ ] task `2026-09-01`"]))
    remote = doc(("Inbox", ["- [x] task `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] task `2026-09-01`"]))

    merged, report = todo_sync.merge(local, remote, base, {}, TODAY)

    assert texts(merged) == {"task": True}
    assert report.checkbox_from_remote == ["task"]


def test_new_items_on_both_sides_are_kept_and_dated():
    base = doc(("Inbox", []))
    remote = doc(("Inbox", ["- [ ] from notion"]), ("Ideas", ["- [ ] new category item `2026-09-30`"]))
    local = doc(("Inbox", ["- [ ] from local `2026-09-29`"]))

    merged, report = todo_sync.merge(local, remote, base, {}, TODAY)

    assert texts(merged) == {"from local": False, "from notion": False, "new category item": False}
    stamps = {item.text: item.stamp for c in merged.categories for item in c.items()}
    assert stamps["from notion"] == TODAY
    assert [c.name for c in merged.categories] == ["Inbox", "Ideas"]
    assert sorted(report.added_from_remote) == ["from notion", "new category item"]


def test_without_snapshot_union_is_used_but_tombstones_suppress():
    remote = doc(("Inbox", ["- [ ] removed earlier `2026-09-01`", "- [x] shared `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] shared `2026-09-01`"]))
    tombstones = {"removed earlier": "2026-09-30"}

    merged, report = todo_sync.merge(local, remote, None, tombstones, TODAY)

    assert texts(merged) == {"shared": True}
    assert report.suppressed_by_tombstone == ["removed earlier"]


def test_small_rewording_is_matched_not_duplicated():
    base = doc(("Inbox", ["- [ ] Review the deploy checklist `2026-09-01`"]))
    remote = doc(("Inbox", ["- [x] Review the deploy checklist. `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] Review the deploy checklists `2026-09-01`"]))

    merged, _ = todo_sync.merge(local, remote, base, {}, TODAY)

    assert texts(merged) == {"Review the deploy checklists": True}


def test_category_removed_locally_keeps_only_new_remote_items():
    base = doc(("Inbox", ["- [ ] a `2026-09-01`"]), ("Old", ["- [ ] synced `2026-09-01`", "a note"]))
    remote = doc(("Inbox", ["- [ ] a `2026-09-01`"]), ("Old", ["- [ ] synced `2026-09-01`", "a note"]))
    local = doc(("Inbox", ["- [ ] a `2026-09-01`"]))

    merged, _ = todo_sync.merge(local, remote, base, {}, TODAY)

    assert [c.name for c in merged.categories] == ["Inbox"]


def test_remote_only_notes_are_preserved():
    remote = doc(("Inbox", ["Written directly in Notion", "- [ ] a `2026-09-01`"]))
    local = doc(("Inbox", ["- [ ] a `2026-09-01`"]))

    merged, report = todo_sync.merge(local, remote, None, {}, TODAY)

    assert "Written directly in Notion" in merged.categories[0].notes()
    assert report.remote_notes_kept == ["Written directly in Notion"]


def test_children_follow_their_parent():
    local = doc(("Inbox", ["- [ ] parent `2026-09-01`", "  - [ ] child `2026-09-01`"]))
    merged, _ = todo_sync.merge(local, doc(("Inbox", [])), None, {}, TODAY)
    assert todo_sync.render(merged).count("  - [ ] child `2026-09-01`") == 1


def test_render_round_trips_and_updates_sync_line():
    text = "# Todo List\n\nItems managed via X. Last sync: 2026-06-23.\n\n## Inbox\n- [ ] a `2026-09-01`\n"
    rendered = todo_sync.render(todo_sync.parse(text), "2026-10-01 09:00")
    assert "Last sync: 2026-10-01 09:00." in rendered
    assert "2026-06-23" not in rendered
    assert todo_sync.render(todo_sync.parse(rendered)) == rendered


def _seed(data_dir: Path, local: str, remote: str) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "TODO.md").write_bytes(local.encode("utf-8"))
    remote_path = data_dir / ".remote.md"
    remote_path.write_text(remote, encoding="utf-8")
    return remote_path


def test_cli_full_cycle_makes_removal_stick(tmp_path, capsys):
    data_dir = tmp_path / "data"
    synced = "# Todo List\n\n## Inbox\n- [ ] a `2026-09-01`\n- [ ] b `2026-09-01`\n"
    remote_path = _seed(data_dir, synced, synced)
    args = ["--data-dir", str(data_dir)]

    assert todo_sync.main([*args, "lock"]) == 0
    assert todo_sync.main([*args, "merge", "--remote", str(remote_path), "--now", "2026-10-01T09:00"]) == 0
    assert todo_sync.main([*args, "confirm"]) == 0
    assert (data_dir / ".sync-snapshot.md").is_file()
    assert not (data_dir / ".sync.lock").exists()

    (data_dir / "TODO.md").write_text("# Todo List\n\n## Inbox\n- [ ] a `2026-09-01`\n", encoding="utf-8")
    assert todo_sync.main([*args, "tombstone", "b `2026-09-01`", "--today", "2026-10-01"]) == 0
    capsys.readouterr()
    assert todo_sync.main([*args, "merge", "--remote", str(remote_path), "--now", "2026-10-01T10:00"]) == 0
    summary = json.loads(capsys.readouterr().out)

    assert summary["removed_locally"] == ["b"]
    assert "- [ ] b" not in (data_dir / "TODO.md").read_text(encoding="utf-8")
    assert "- [ ] b" not in (data_dir / ".pending-push.md").read_text(encoding="utf-8")


def test_merge_preserves_crlf_of_local_file(tmp_path):
    data_dir = tmp_path / "data"
    local = "# Todo List\r\n\r\n## Inbox\r\n- [ ] a `2026-09-01`\r\n"
    remote_path = _seed(data_dir, local, "# Todo List\n\n## Inbox\n- [ ] a `2026-09-01`\n")

    assert todo_sync.main(["--data-dir", str(data_dir), "merge", "--remote", str(remote_path)]) == 0

    raw = (data_dir / "TODO.md").read_bytes()
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_merge_preserves_lf_of_local_file(tmp_path):
    data_dir = tmp_path / "data"
    local = "# Todo List\n\n## Inbox\n- [ ] a `2026-09-01`\n"
    remote_path = _seed(data_dir, local, local)

    assert todo_sync.main(["--data-dir", str(data_dir), "merge", "--remote", str(remote_path)]) == 0

    assert b"\r\n" not in (data_dir / "TODO.md").read_bytes()


def test_lock_is_exclusive_and_stale_lock_is_reclaimed(tmp_path):
    assert todo_sync.acquire_lock(tmp_path)
    assert not todo_sync.acquire_lock(tmp_path)
    lock = tmp_path / ".sync.lock"
    old = time.time() - todo_sync.LOCK_STALE_SECONDS - 5
    os.utime(lock, (old, old))
    assert todo_sync.acquire_lock(tmp_path)
    todo_sync.release_lock(tmp_path)
    assert not lock.exists()


def test_old_tombstones_expire(tmp_path):
    path = tmp_path / ".tombstones.json"
    path.write_text(json.dumps({"ancient": "2026-01-01", "recent": "2026-09-30"}), encoding="utf-8")
    loaded = todo_sync.load_tombstones(path, todo_sync.date.fromisoformat(TODAY))
    assert loaded == {"recent": "2026-09-30"}


def test_merge_fails_cleanly_without_local_file(tmp_path, capsys):
    remote = tmp_path / "remote.md"
    remote.write_text("# Todo List\n", encoding="utf-8")
    assert todo_sync.main(["--data-dir", str(tmp_path), "merge", "--remote", str(remote)]) == 2
    assert "not found" in capsys.readouterr().err
