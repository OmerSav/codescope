"""File hash registry — tracks file content hashes for incremental re-indexing.

Stores a flat JSON dictionary at .codescope/file_hashes.json:
    {
        "src/auth.ts": {"hash": "a1b2c3...", "mtime": 1707820800.0},
        "src/index.ts": {"hash": "d4e5f6...", "mtime": 1707820900.0}
    }
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HASHES_FILENAME = "file_hashes.json"


@dataclass
class FileDiff:
    """Result of comparing current files against stored hashes."""

    changed: list[Path]  # new or modified files → need re-embedding
    deleted: list[str]  # removed files (relative paths) → need cleanup from store


class FileHashRegistry:
    """Manages a flat hash dictionary for change detection."""

    def __init__(self, db_dir: Path) -> None:
        self._path = db_dir / HASHES_FILENAME
        self._hashes: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._hashes = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._hashes = {}

    def save(self) -> None:
        """Persist the hash registry to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._hashes, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def diff(self, files: list[Path], project_root: Path) -> FileDiff:
        """Compare current files against stored hashes.

        Returns which files changed (need re-embedding) and which were
        deleted (need cleanup from the vector store).
        """
        changed: list[Path] = []
        current_rel_paths: set[str] = set()

        for file in files:
            rel = str(file.relative_to(project_root))
            current_rel_paths.add(rel)

            # Quick mtime check first — if mtime hasn't changed, skip hash
            stored = self._hashes.get(rel)
            if stored is not None:
                try:
                    mtime = file.stat().st_mtime
                except OSError:
                    changed.append(file)
                    continue

                if mtime == stored.get("mtime"):
                    continue  # mtime same → file unchanged

            # mtime differs or file is new → compute hash to be sure
            file_hash = _hash_file(file)
            if file_hash is None:
                continue  # unreadable file, skip

            if stored is not None and stored.get("hash") == file_hash:
                # Content identical despite mtime change (e.g. git checkout)
                # Update mtime so next check is fast
                try:
                    stored["mtime"] = file.stat().st_mtime
                except OSError:
                    pass
                continue

            changed.append(file)

        # Detect deleted files
        stored_paths = set(self._hashes.keys())
        deleted = sorted(stored_paths - current_rel_paths)

        return FileDiff(changed=changed, deleted=deleted)

    def update(self, file: Path, project_root: Path) -> None:
        """Update the hash entry for a single file."""
        rel = str(file.relative_to(project_root))
        file_hash = _hash_file(file)
        if file_hash is None:
            return
        try:
            mtime = file.stat().st_mtime
        except OSError:
            mtime = 0.0
        self._hashes[rel] = {"hash": file_hash, "mtime": mtime}

    def remove(self, rel_path: str) -> None:
        """Remove a file entry from the registry."""
        self._hashes.pop(rel_path, None)

    @property
    def tracked_count(self) -> int:
        return len(self._hashes)


def _hash_file(path: Path) -> str | None:
    """Compute SHA-256 hash of a file's contents."""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(content).hexdigest()
