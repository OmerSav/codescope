"""MCP server exposing codescope as tools, resources, and prompts for AI coding agents."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import CodeScopeConfig
from .indexer import collect_files, index_project
from .search import search as do_search


def _validate_openai(config: CodeScopeConfig) -> str | None:
    """Return an error string if OpenAI provider is used without an API key."""
    if config.is_openai and not config.openai_api_key:
        return "Error: OpenAI provider requires OPENAI_API_KEY environment variable."
    return None


def main() -> None:
    """Entry point for the codescope MCP server."""

    mcp = FastMCP(
        "codescope",
        instructions="Codebase indexer & semantic search for AI coding agents",
    )

    # -------------------------------------------------------------------------
    # Tools — model-controlled, executable actions
    # -------------------------------------------------------------------------

    @mcp.tool()
    def search_codebase(query: str, project_path: str = ".", n_results: int = 10) -> str:
        """Search the indexed codebase using natural language.

        Args:
            query: Natural language description of what you're looking for.
            project_path: Path to the project root (default: current directory).
            n_results: Number of results to return.
        """
        path = Path(project_path).resolve()
        config = CodeScopeConfig(project_root=path, n_results=n_results)

        if err := _validate_openai(config):
            return err

        if not config.db_dir.exists():
            return f"Error: Project not indexed. Run `codescope index {path}` first."

        results = do_search(query, config)
        if not results:
            return "No results found."

        output = []
        for r in results:
            output.append(
                {
                    "file": r.file_path,
                    "lines": f"{r.start_line}-{r.end_line}",
                    "similarity": f"{1 - r.distance:.2%}",
                    "symbol": r.symbol or None,
                    "content": r.content,
                }
            )
        return json.dumps(output, indent=2)

    @mcp.tool()
    def index_codebase(project_path: str = ".", full: bool = False) -> str:
        """Index or re-index a codebase for semantic search.

        Incremental by default — only changed files are re-embedded.
        Set full=True to rebuild the entire index from scratch.

        Args:
            project_path: Path to the project root (default: current directory).
            full: If True, force a full re-index ignoring cache.
        """
        path = Path(project_path).resolve()
        config = CodeScopeConfig(project_root=path)

        if err := _validate_openai(config):
            return err

        result = index_project(config, full=full)
        return json.dumps(
            {
                "chunks_indexed": result.chunks_indexed,
                "files_changed": result.files_changed,
                "files_deleted": result.files_deleted,
                "files_unchanged": result.files_unchanged,
            },
            indent=2,
        )

    @mcp.tool()
    def begin_session(project_path: str = ".") -> str:
        """Start tracking file changes for a coding session.

        Call this BEFORE making changes to the codebase. Takes a snapshot
        of all file hashes. When done, call end_session to detect changes
        and automatically re-index only modified files.

        Args:
            project_path: Path to the project root (default: current directory).
        """
        from .session import take_snapshot

        path = Path(project_path).resolve()
        config = CodeScopeConfig(project_root=path)

        count = take_snapshot(config)
        return json.dumps(
            {"status": "session_started", "files_tracked": count},
            indent=2,
        )

    @mcp.tool()
    def end_session(project_path: str = ".") -> str:
        """End a coding session, detect changes, and re-index modified files.

        Call this AFTER making changes. Compares current file state against
        the snapshot taken by begin_session, then incrementally re-indexes
        only the files that changed.

        Args:
            project_path: Path to the project root (default: current directory).
        """
        from .session import clear_snapshot, compute_diff

        path = Path(project_path).resolve()
        config = CodeScopeConfig(project_root=path)

        if err := _validate_openai(config):
            return err

        diff = compute_diff(config)
        if diff is None:
            return "Error: No active session. Call begin_session first."

        total_changes = len(diff.modified) + len(diff.created) + len(diff.deleted)

        # Re-index if there were changes
        chunks_reindexed = 0
        if total_changes > 0:
            result = index_project(config)
            chunks_reindexed = result.chunks_indexed

        clear_snapshot(config)

        return json.dumps(
            {
                "status": "session_ended",
                "files_modified": diff.modified,
                "files_created": diff.created,
                "files_deleted": diff.deleted,
                "chunks_reindexed": chunks_reindexed,
            },
            indent=2,
        )

    # -------------------------------------------------------------------------
    # Resources — application-controlled, read-only context data
    # -------------------------------------------------------------------------

    @mcp.resource("codescope://status")
    def resource_status() -> str:
        """Current indexing status — project path, provider, model, chunk count."""
        from .store import VectorStore

        path = Path(".").resolve()
        config = CodeScopeConfig(project_root=path)

        if not config.db_dir.exists():
            return json.dumps(
                {"indexed": False, "project": str(path)},
                indent=2,
            )

        store = VectorStore(config.db_dir)
        return json.dumps(
            {
                "indexed": True,
                "project": str(path),
                "db_path": str(config.db_dir),
                "provider": config.embedding_provider,
                "model": config.embedding_model,
                "chunks": store.count,
            },
            indent=2,
        )

    @mcp.resource("codescope://files")
    def resource_files() -> str:
        """List of all indexed files in the project."""
        from .file_hashes import FileHashRegistry

        path = Path(".").resolve()
        config = CodeScopeConfig(project_root=path)

        if not config.db_dir.exists():
            return json.dumps({"indexed": False, "files": []}, indent=2)

        registry = FileHashRegistry(config.db_dir)
        files = collect_files(config)
        file_list = [str(f.relative_to(config.project_root)) for f in files]

        return json.dumps(
            {
                "project": str(path),
                "total_files": len(file_list),
                "tracked_files": registry.tracked_count,
                "files": file_list,
            },
            indent=2,
        )

    @mcp.resource("codescope://tree")
    def resource_tree() -> str:
        """Project file tree in a nested, human-readable format.

        Returns the directory structure of all indexable files as an
        indented tree (similar to the `tree` command), giving agents an
        at-a-glance overview of how the project is organised.
        """
        path = Path(".").resolve()
        config = CodeScopeConfig(project_root=path)
        files = collect_files(config)
        rel_paths = sorted(str(f.relative_to(config.project_root)) for f in files)

        # Build nested dict representing the directory tree
        tree: dict = {}
        for rp in rel_paths:
            parts = rp.replace("\\", "/").split("/")
            node = tree
            for part in parts:
                node = node.setdefault(part, {})

        # Render to an indented string
        lines: list[str] = [f"{path.name}/"]

        def _render(node: dict, prefix: str = "") -> None:
            entries = sorted(node.keys(), key=lambda k: (not node[k], k.lower()))
            for i, name in enumerate(entries):
                is_last = i == len(entries) - 1
                connector = "+-- " if is_last else "|-- "
                lines.append(f"{prefix}{connector}{name}")
                if node[name]:  # has children — it's a directory
                    extension = "    " if is_last else "|   "
                    _render(node[name], prefix + extension)

        _render(tree)
        return "\n".join(lines)

    @mcp.resource("codescope://config")
    def resource_config() -> str:
        """Current codescope configuration (provider, model, global settings)."""
        from .global_config import SENSITIVE_KEYS, load_global_config, mask_value

        path = Path(".").resolve()
        config = CodeScopeConfig(project_root=path)
        gc = load_global_config()

        # Mask sensitive values
        safe_gc = {
            k: mask_value(k, str(v)) if k in SENSITIVE_KEYS else v
            for k, v in gc.items()
        }

        return json.dumps(
            {
                "active_provider": config.embedding_provider,
                "active_model": config.embedding_model,
                "global_config": safe_gc,
            },
            indent=2,
        )

    # -------------------------------------------------------------------------
    # Prompts — user-controlled, reusable interaction templates
    # -------------------------------------------------------------------------

    @mcp.prompt()
    def search_first(query: str) -> str:
        """Search the codebase before reading files directly.

        Use this prompt to ensure relevant files are found via semantic
        search before opening them, reducing unnecessary file reads.

        Args:
            query: What you're looking for in the codebase.
        """
        return (
            f"Before reading any files, use the search_codebase tool to find "
            f"relevant code for: {query}\n\n"
            f"Review the search results and only read the top matching files. "
            f"This is more efficient than scanning the file tree manually."
        )

    @mcp.prompt()
    def session_workflow() -> str:
        """Recommended workflow for coding sessions with codescope.

        Guides the agent through the begin_session / end_session pattern
        to keep the search index up to date automatically.
        """
        return (
            "Follow this workflow for this coding session:\n\n"
            "1. Call begin_session to start tracking file changes.\n"
            "2. Use search_codebase to find relevant code before reading files.\n"
            "3. Make your code changes as needed.\n"
            "4. When done, call end_session to automatically re-index changed files.\n\n"
            "This keeps the semantic search index up to date with your changes."
        )

    mcp.run()


if __name__ == "__main__":
    main()
