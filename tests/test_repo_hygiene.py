from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}

HOME_PATH_RE = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+")
HOME_PATH_ALLOW_RE = re.compile(
    r"\$HOME|\$USERPROFILE|%USERPROFILE%|\$env:USERPROFILE|\$TEMP|%TEMP%|\$SKILLS_",
    re.IGNORECASE,
)
SECRET_RE = re.compile(
    r"sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-|-----BEGIN [A-Z ]*PRIVATE KEY-----"
)
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
BARE_HEX32_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(8192)
    except OSError:
        return True
    return b"\x00" in chunk


def walk():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if _is_binary(path):
            continue
        yield path


def test_no_absolute_user_home_paths():
    offenders = []
    for path in walk():
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if HOME_PATH_RE.search(line) and not HOME_PATH_ALLOW_RE.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_no_secret_shapes():
    offenders = []
    for path in walk():
        for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if SECRET_RE.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_no_bare_uuids_outside_examples():
    offenders = []
    for path in walk():
        if path.name.endswith(".example"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if UUID_RE.search(text) or BARE_HEX32_RE.search(text):
            offenders.append(str(path))
    assert not offenders, "\n".join(offenders)


def test_no_env_or_local_state_committed():
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is unavailable")
        return
    tracked = set(result.stdout.splitlines())
    forbidden = {".env", "data/config.json", "data/TODO.md"}
    assert not (tracked & forbidden), tracked & forbidden
    for required in (".env.example", "data/config.json.example", "data/TODO.template.md"):
        assert required in tracked, required


def test_skill_md_frontmatter():
    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "---"
    closing_index = lines[1:].index("---") + 1
    frontmatter = "\n".join(lines[1:closing_index])
    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    description_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    assert name_match and name_match.group(1).strip()
    assert description_match and description_match.group(1).strip()


def test_baseline_files_present():
    for filename in ("README.md", "LICENSE", "SETUP.md", ".gitignore", ".gitattributes", "CHANGELOG.md"):
        assert (REPO_ROOT / filename).exists(), filename
    assert not (REPO_ROOT / "ROADMAP.md").exists()
