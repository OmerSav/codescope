"""Core indexing logic — walks the project, chunks files, embeds, and stores.

Supports incremental re-indexing: only changed/new files are re-embedded,
deleted files are cleaned up from the store. Uses a flat SHA-256 hash
dictionary persisted at .codescope/file_hashes.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn

from .chunker import Chunk, chunk_file
from .config import CodeScopeConfig
from .embeddings import embed_texts_openai, get_chromadb_embedding_function
from .file_hashes import FileHashRegistry
from .store import VectorStore

console = Console()


@dataclass
class IndexResult:
    """Summary of an indexing run."""

    chunks_indexed: int
    files_changed: int
    files_deleted: int
    files_unchanged: int


def collect_files(config: CodeScopeConfig) -> list[Path]:
    """Walk the project root and collect indexable files."""
    files: list[Path] = []
    for path in config.project_root.rglob("*"):
        if any(part in config.ignore_dirs for part in path.parts):
            continue
        if path.is_file() and path.suffix in config.extensions:
            files.append(path)
    return sorted(files)


def _create_store(config: CodeScopeConfig) -> VectorStore:
    """Create a VectorStore with the appropriate embedding function."""
    ef = get_chromadb_embedding_function(config)
    return VectorStore(config.db_dir, embedding_function=ef)


def index_project(config: CodeScopeConfig, *, full: bool = False) -> IndexResult:
    """Index the project. Incremental by default, full if requested.

    Args:
        config: Project configuration.
        full: If True, re-index everything from scratch.

    Returns:
        IndexResult with stats about what happened.
    """
    store = _create_store(config)
    registry = FileHashRegistry(config.db_dir)
    files = collect_files(config)

    if full:
        store.clear()
        return _full_index(store, registry, files, config)

    return _incremental_index(store, registry, files, config)


def _full_index(
    store: VectorStore,
    registry: FileHashRegistry,
    files: list[Path],
    config: CodeScopeConfig,
) -> IndexResult:
    """Re-index all files from scratch."""
    if not files:
        registry.save()
        return IndexResult(chunks_indexed=0, files_changed=0, files_deleted=0, files_unchanged=0)

    all_chunks: list[Chunk] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Chunking files...", total=len(files))
        for f in files:
            rel = str(f.relative_to(config.project_root))
            chunks = chunk_file(f, max_lines=config.max_chunk_lines, overlap=config.chunk_overlap)
            for c in chunks:
                c.file_path = rel
            all_chunks.extend(chunks)
            registry.update(f, config.project_root)
            progress.advance(task)

    if all_chunks:
        _embed_and_store(store, all_chunks, config)

    registry.save()
    return IndexResult(
        chunks_indexed=len(all_chunks),
        files_changed=len(files),
        files_deleted=0,
        files_unchanged=0,
    )


def _incremental_index(
    store: VectorStore,
    registry: FileHashRegistry,
    files: list[Path],
    config: CodeScopeConfig,
) -> IndexResult:
    """Only re-index changed files, clean up deleted ones."""
    diff = registry.diff(files, config.project_root)

    files_deleted = len(diff.deleted)
    files_changed = len(diff.changed)
    files_unchanged = len(files) - files_changed

    # Clean up deleted files from the store
    for rel_path in diff.deleted:
        store.delete_by_file(rel_path)
        registry.remove(rel_path)

    if not diff.changed:
        registry.save()
        return IndexResult(
            chunks_indexed=0,
            files_changed=0,
            files_deleted=files_deleted,
            files_unchanged=files_unchanged,
        )

    # Chunk only the changed files
    all_chunks: list[Chunk] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task("Chunking changed files...", total=files_changed)
        for f in diff.changed:
            rel = str(f.relative_to(config.project_root))
            # Remove old chunks for this file before re-adding
            store.delete_by_file(rel)
            chunks = chunk_file(f, max_lines=config.max_chunk_lines, overlap=config.chunk_overlap)
            for c in chunks:
                c.file_path = rel
            all_chunks.extend(chunks)
            registry.update(f, config.project_root)
            progress.advance(task)

    if all_chunks:
        _embed_and_store(store, all_chunks, config)

    registry.save()
    return IndexResult(
        chunks_indexed=len(all_chunks),
        files_changed=files_changed,
        files_deleted=files_deleted,
        files_unchanged=files_unchanged,
    )


def _embed_and_store(
    store: VectorStore,
    chunks: list[Chunk],
    config: CodeScopeConfig,
) -> None:
    """Embed chunks and upsert into the vector store."""
    texts = [c.content for c in chunks]

    # Ensure IDs are unique — minified files can produce multiple chunks
    # on the same line range, yielding duplicate IDs.
    raw_ids = [c.id for c in chunks]
    seen: dict[str, int] = {}
    ids: list[str] = []
    for raw_id in raw_ids:
        count = seen.get(raw_id, 0)
        ids.append(f"{raw_id}#{count}" if count > 0 else raw_id)
        seen[raw_id] = count + 1

    metadatas = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "language": c.language or "",
            "symbol": c.symbol or "",
        }
        for c in chunks
    ]

    if config.is_local:
        # ChromaDB handles embedding internally
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Embedding & storing (local)...", total=None)
            store.upsert_documents(ids=ids, documents=texts, metadatas=metadatas)
    else:
        # OpenAI: compute embeddings externally
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task("Generating embeddings (OpenAI)...", total=None)
            embeddings = embed_texts_openai(texts, config)

        store.upsert_embeddings(
            ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
        )
