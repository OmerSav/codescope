"""Session tracking — captures file snapshots before/after agent work.

Snapshot is stored at .codescope/session_snapshot.json. The agent calls
begin_session before making changes and end_session when done. The diff
between snapshot and current state drives incremental re-indexing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import CodeScopeConfig
from .indexer import collect_files

SESSION_FILENAME = "session_snapshot.json"


@dataclass
class SessionDiff:
    """Result of comparing session snapshot to current state."""

    modified: list[str]  # relative paths of modified files
    created: list[str]  # relative paths of new files
    deleted: list[str]  # relative paths of deleted files


def take_snapshot(config: CodeScopeConfig) -> int:
    """Take a snapshot of all indexable files.

    Returns the number of files tracked.
    """
    files = collect_files(config)
    snapshot: dict[str, dict[str, Any]] = {}

    for f in files:
        rel = str(f.relative_to(config.project_root))
        file_hash = _hash_file(f)
        if file_hash is not None:
            snapshot[rel] = {"hash": file_hash}

    snapshot_path = config.db_dir / SESSION_FILENAME
    config.db_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return len(snapshot)


def compute_diff(config: CodeScopeConfig) -> SessionDiff | None:
    """Compare current state against the session snapshot.

    Returns None if no snapshot exists (begin_session was not called).
    """
    snapshot_path = config.db_dir / SESSION_FILENAME
    if not snapshot_path.exists():
        return None

    try:
        snapshot: dict[str, dict[str, Any]] = json.loads(
            snapshot_path.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError):
        return None

    files = collect_files(config)
    current_hashes: dict[str, str] = {}
    for f in files:
        rel = str(f.relative_to(config.project_root))
        h = _hash_file(f)
        if h is not None:
            current_hashes[rel] = h

    modified: list[str] = []
    created: list[str] = []
    deleted: list[str] = []

    # Check for modified and new files
    for rel, current_hash in sorted(current_hashes.items()):
        if rel in snapshot:
            if snapshot[rel].get("hash") != current_hash:
                modified.append(rel)
        else:
            created.append(rel)

    # Check for deleted files
    for rel in sorted(snapshot.keys()):
        if rel not in current_hashes:
            deleted.append(rel)

    return SessionDiff(modified=modified, created=created, deleted=deleted)


def clear_snapshot(config: CodeScopeConfig) -> None:
    """Remove the session snapshot file."""
    snapshot_path = config.db_dir / SESSION_FILENAME
    if snapshot_path.exists():
        snapshot_path.unlink()


def _hash_file(path: Path) -> str | None:
    """Compute SHA-256 hash of a file's contents."""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(content).hexdigest()
