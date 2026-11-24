"""Common utilities for hashing, Git versioning, timestamps, and structured logging."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_run_id() -> str:
    """Create a filesystem-safe UTC run identifier."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path | str) -> str:
    """Compute SHA-256 hex digest of a file."""
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_git_info(repo_dir: Path | str | None = None) -> dict[str, Any]:
    """Return current Git commit hash, short hash, branch, and dirty state."""
    cwd = str(repo_dir or PROJECT_ROOT)
    info: dict[str, Any] = {
        "commit": "unknown",
        "short_commit": "unknown",
        "branch": "unknown",
        "is_dirty": None,
    }
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=cwd, stderr=subprocess.DEVNULL, text=True
        ).strip()
        short_commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        info = {
            "commit": commit,
            "short_commit": short_commit,
            "branch": branch,
            "is_dirty": bool(status),
        }
    except Exception:
        pass
    return info


def load_json(path: Path | str) -> dict[str, Any]:
    """Read a JSON file as UTF-8."""
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path | str, payload: dict[str, Any]) -> Path:
    """Write a dictionary to a formatted UTF-8 JSON file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return target


def append_jsonl(path: Path | str, record: dict[str, Any]) -> Path:
    """Append one JSON record to a JSON Lines log file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return target


def load_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load training/pipeline configuration JSON."""
    path = Path(config_path) if config_path else PROJECT_ROOT / "configs" / "train_config.json"
    return load_json(path)
