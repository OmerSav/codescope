"""CLI entry point for codescope."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from . import __version__
from .config import DEFAULT_DB_DIR, DEFAULT_IGNORE_CONTENT, IGNORE_FILE_NAME, CodeScopeConfig, load_ignore_spec

console = Console()


def _validate_config(config: CodeScopeConfig) -> None:
    """Check provider-specific requirements."""
    if config.is_openai and not config.openai_api_key:
        console.print(
            "[red]Error:[/] OpenAI provider requires OPENAI_API_KEY.\n"
            "  Set it via: [bold]codescope config set openai-api-key sk-...[/]\n"
            "  Or export:  [bold]OPENAI_API_KEY=sk-...[/]"
        )
        raise SystemExit(1)


@click.group()
@click.version_option(__version__, prog_name="codescope")
def main() -> None:
    """codescope — Codebase indexer & semantic search for AI coding agents."""


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--model", default=None, help="Embedding model name.")
@click.option("--full", is_flag=True, help="Force full re-index (ignore cache).")
@click.option("--dry-run", is_flag=True, help="Show file counts without indexing (for debugging ignore).")
def index(path: Path, model: str | None, full: bool, dry_run: bool) -> None:
    """Index a codebase for semantic search.

    By default, only changed files are re-indexed (incremental).
    Use --full to rebuild the entire index from scratch.
    """
    from .indexer import index_project

    path = path.resolve()
    config = CodeScopeConfig(project_root=path)
    if model:
        config.embedding_model = model
    _validate_config(config)

    # Create default .codescopeignore on first index if missing
    ignore_path = config.db_dir / IGNORE_FILE_NAME
    if not ignore_path.exists():
        config.db_dir.mkdir(parents=True, exist_ok=True)
        ignore_path.write_text(DEFAULT_IGNORE_CONTENT, encoding="utf-8")
        console.print(f"  [green]Created:[/] {ignore_path}")
        config.ignore_spec = load_ignore_spec(path)

    if dry_run:
        from .indexer import collect_files

        files = collect_files(config)
        console.print(f"[bold]Dry run[/] — {path}")
        console.print(f"  [cyan]Indexable files:[/] {len(files)}")
        if files:
            for f in files[:5]:
                console.print(f"    [dim]{f.relative_to(path)}[/]")
            if len(files) > 5:
                console.print(f"    [dim]... and {len(files) - 5} more[/]")
        else:
            console.print(
                "  [yellow]No files found.[/] Check extensions and .codescope/.codescopeignore"
            )
        return

    provider_label = f"[dim]({config.embedding_provider})[/]"
    mode = "Full re-index" if full else "Incremental index"
    console.print(f"[bold]{mode}[/] {path} {provider_label}")
    result = index_project(config, full=full)

    console.print(f"[green]Done![/] {result.chunks_indexed} chunks indexed")
    if not full:
        console.print(
            f"  [dim]{result.files_changed} changed, "
            f"{result.files_deleted} deleted, "
            f"{result.files_unchanged} unchanged[/]"
        )


@main.command("reindex-file")
@click.argument("file", type=click.Path(path_type=Path))
@click.option("--project", default=".", type=click.Path(exists=True, path_type=Path),
              help="Project root (default: current directory).")
def reindex_file_cmd(file: Path, project: Path) -> None:
    """Re-index a single file.

    Deletes old chunks for the file, re-chunks, embeds, and upserts.
    If the file was deleted, cleans up its chunks from the index.
    Designed to be called from editor hooks (e.g. Claude Code PostToolUse).
    """
    from .indexer import reindex_file

    project = project.resolve()
    file = file.resolve()
    config = CodeScopeConfig(project_root=project)
    _validate_config(config)

    if not config.db_dir.exists():
        console.print("[yellow]Not indexed.[/] Run `codescope index` first.")
        raise SystemExit(1)

    result = reindex_file(config, file)

    if result.files_deleted:
        console.print(f"[green]Cleaned up[/] {file.relative_to(project)}")
    elif result.chunks_indexed:
        console.print(
            f"[green]Re-indexed[/] {file.relative_to(project)} "
            f"({result.chunks_indexed} chunks)"
        )
    else:
        console.print(f"[dim]Skipped[/] {file.relative_to(project)}")


@main.command()
@click.argument("query")
@click.option("-n", "--num-results", default=10, help="Number of results to return.")
@click.option("--path", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--show-code", is_flag=True, help="Show matching code snippets.")
def search(query: str, num_results: int, path: Path, show_code: bool) -> None:
    """Semantic search over an indexed codebase."""
    from .search import search as do_search

    path = Path(path).resolve()
    config = CodeScopeConfig(project_root=path, n_results=num_results)
    _validate_config(config)

    results = do_search(query, config)

    if not results:
        console.print("[yellow]No results found.[/]")
        return

    for i, r in enumerate(results, 1):
        console.print(f"[bold cyan]{i}.[/] {r.display()}")
        if show_code:
            console.print(
                Panel(
                    Syntax(r.content, "python", line_numbers=True, start_line=r.start_line),
                    border_style="dim",
                )
            )


@main.command()
@click.option("--path", default=".", type=click.Path(exists=True, path_type=Path))
def status(path: Path) -> None:
    """Show indexing status for a project."""
    from .store import VectorStore

    path = Path(path).resolve()
    config = CodeScopeConfig(project_root=path)

    if not config.db_dir.exists():
        console.print("[yellow]Not indexed.[/] Run `codescope index` first.")
        return

    store = VectorStore(config.db_dir)
    console.print(f"[bold]Project:[/]   {path}")
    console.print(f"[bold]DB path:[/]   {config.db_dir}")
    console.print(f"[bold]Provider:[/]  {config.embedding_provider}")
    console.print(f"[bold]Model:[/]     {config.embedding_model}")
    console.print(f"[bold]Chunks:[/]    {store.count}")


# --- Config subcommands ---


@main.group()
def config() -> None:
    """Manage global codescope configuration."""


@config.command("show")
def config_show() -> None:
    """Show current global configuration."""
    from .global_config import GLOBAL_CONFIG_FILE, SENSITIVE_KEYS, VALID_KEYS, load_global_config

    data = load_global_config()
    console.print(f"[bold]Config file:[/] {GLOBAL_CONFIG_FILE}")
    console.print()

    if not data:
        console.print("[dim]No configuration set. Using defaults.[/]")
        console.print("[dim]Run `codescope config set <key> <value>` to configure.[/]")
        console.print()
        console.print("[bold]Available keys:[/]")
        for key, desc in VALID_KEYS.items():
            console.print(f"  [cyan]{key}[/] — {desc}")
        return

    for key, desc in VALID_KEYS.items():
        value = data.get(key)
        if value:
            display = value
            if key in SENSITIVE_KEYS and len(value) > 8:
                display = value[:4] + "..." + value[-4:]
            console.print(f"  [cyan]{key}[/] = [green]{display}[/]")
        else:
            console.print(f"  [cyan]{key}[/] = [dim](not set)[/]  — {desc}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str) -> None:
    """Set a global configuration value.

    Available keys: embedding_provider, embedding_model, openai_api_key
    """
    from .global_config import SENSITIVE_KEYS, VALID_KEYS, set_config_value

    if key not in VALID_KEYS:
        console.print(f"[red]Error:[/] Unknown key '{key}'.")
        console.print("[bold]Valid keys:[/]")
        for k, desc in VALID_KEYS.items():
            console.print(f"  [cyan]{k}[/] — {desc}")
        raise SystemExit(1)

    if key == "embedding_provider" and value not in ("local", "openai"):
        console.print("[red]Error:[/] Provider must be 'local' or 'openai'.")
        raise SystemExit(1)

    set_config_value(key, value)

    display = value
    if key in SENSITIVE_KEYS and len(value) > 8:
        display = value[:4] + "..." + value[-4:]
    console.print(f"[green]Set[/] {key} = {display}")

    if key == "embedding_provider":
        console.print(
            "[yellow]Note:[/] Existing indexes use the previous provider's embeddings.\n"
            "  Run `codescope index --full .` to rebuild with the new provider."
        )


# --- Init subcommands ---

CODESCOPE_INSTRUCTIONS = """\
# codescope — Project Guide for AI Agents

## Search Strategy — Use the Right Tool for the Job

This project has a `codescope` MCP server connected. Grep and semantic search solve different problems — use both:

- **Grep/Glob** when you know the exact name: a function, class, variable, import, error message, or string literal. Grep is fast and precise for exact matches.
- **`search_codebase(query)`** when you don't know the exact keyword: exploring how something works, finding related code by concept, or when grep returns too many irrelevant results. Semantic search understands intent, not just text.

If grep doesn't find what you need in 1-2 tries, switch to `search_codebase`. If you're searching for a concept or pattern rather than a specific token, start with `search_codebase`.

## MCP Tools

- `search_codebase(query)` — Semantic search. Returns the most relevant code chunks with file paths and line numbers.

## MCP Resources

- `codescope://tree` — Project file tree at a glance. Read this first to quickly grasp the project structure.
- `codescope://status` — Indexing status, provider, model, and chunk count.
- `codescope://files` — Flat list of all indexed files.
- `codescope://config` — Current codescope configuration.

## Index Updates

The search index is updated automatically via a PostToolUse hook after each Edit/Write.
No manual indexing calls needed — just search and code.
"""

_MCP_JSON_ENTRY = {
    "command": "codescope-mcp",
    "args": [],
}

_HOOK_REINDEX_COMMAND = (
    "codescope reindex-file"
    " --project \"$CLAUDE_PROJECT_DIR\""
    " \"$(cat | python3 -c \"import sys,json; print(json.load(sys.stdin)['tool_input']['file_path'])\")\""
)

_HOOKS_SETTINGS: dict = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": _HOOK_REINDEX_COMMAND,
                        "async": True,
                        "timeout": 30,
                    }
                ],
            }
        ]
    }
}

_CODEX_MCP_TOML = """\

[mcp_servers.codescope]
command = "codescope-mcp"
"""


def _ensure_instructions_file(file_path: Path) -> None:
    """Create or append codescope instructions to an agent instructions file."""
    if file_path.exists():
        content = file_path.read_text(encoding="utf-8")
        if "codescope" in content.lower():
            console.print(f"  [dim]Already has codescope instructions:[/] {file_path}")
            return
        with file_path.open("a", encoding="utf-8") as f:
            f.write("\n\n" + CODESCOPE_INSTRUCTIONS)
        console.print(f"  [green]Appended codescope instructions to:[/] {file_path}")
    else:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(CODESCOPE_INSTRUCTIONS, encoding="utf-8")
        console.print(f"  [green]Created:[/] {file_path}")


def _ensure_mcp_json(file_path: Path) -> None:
    """Create or update a JSON MCP config with codescope entry."""
    import json

    existed = file_path.exists()
    data: dict = {}

    if existed:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    servers = data.setdefault("mcpServers", {})
    if "codescope" in servers:
        console.print(f"  [dim]Already has codescope MCP entry:[/] {file_path}")
        return

    servers["codescope"] = _MCP_JSON_ENTRY
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    action = "Updated" if existed else "Created"
    console.print(f"  [green]{action}:[/] {file_path}")


def _ensure_codex_mcp_toml(file_path: Path) -> None:
    """Create or update a Codex config.toml with codescope MCP entry."""
    existed = file_path.exists()

    if existed:
        content = file_path.read_text(encoding="utf-8")
        if "mcp_servers.codescope" in content:
            console.print(f"  [dim]Already has codescope MCP entry:[/] {file_path}")
            return
        with file_path.open("a", encoding="utf-8") as f:
            f.write(_CODEX_MCP_TOML)
        console.print(f"  [green]Updated:[/] {file_path}")
    else:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_CODEX_MCP_TOML.lstrip(), encoding="utf-8")
        console.print(f"  [green]Created:[/] {file_path}")


def _ensure_hooks_settings(file_path: Path) -> None:
    """Create or update a Claude Code settings.json with codescope PostToolUse hooks."""
    import json

    existed = file_path.exists()
    data: dict = {}

    if existed:
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    hooks = data.get("hooks", {})
    post_tool_use = hooks.get("PostToolUse", [])

    # Check if a codescope reindex hook already exists
    for group in post_tool_use:
        for h in group.get("hooks", []):
            if "codescope reindex-file" in h.get("command", ""):
                console.print(f"  [dim]Already has codescope hook:[/] {file_path}")
                return

    post_tool_use.append(_HOOKS_SETTINGS["hooks"]["PostToolUse"][0])
    hooks["PostToolUse"] = post_tool_use
    data["hooks"] = hooks

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    action = "Updated" if existed else "Created"
    console.print(f"  [green]{action}:[/] {file_path} (PostToolUse hook)")


def _ensure_codescopeignore(project: Path) -> None:
    """Create .codescope/.codescopeignore with sensible defaults if missing."""
    codescope_dir = project / DEFAULT_DB_DIR
    codescope_dir.mkdir(parents=True, exist_ok=True)
    ignore_file = codescope_dir / IGNORE_FILE_NAME
    if ignore_file.exists():
        console.print(f"  [dim]Already exists:[/] {ignore_file}")
    else:
        ignore_file.write_text(DEFAULT_IGNORE_CONTENT, encoding="utf-8")
        console.print(f"  [green]Created:[/] {ignore_file}")


@main.group(invoke_without_command=True)
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize codescope for a project.

    Without a subcommand (claude/codex), creates the .codescope/ directory
    with a default .codescopeignore file in the current directory.
    """
    if ctx.invoked_subcommand is not None:
        return
    project = Path(".").resolve()
    console.print(f"[bold]Initializing codescope[/] in {project}\n")
    _ensure_codescopeignore(project)
    console.print(
        "\n[green]Done![/] Next steps:\n"
        "  1. Edit [bold].codescope/.codescopeignore[/] to customise which files to skip\n"
        "  2. Run [bold]codescope index .[/] to index the project\n"
        "  3. Optionally run [bold]codescope init claude .[/] or [bold]codescope init codex .[/] to set up an AI agent"
    )


@init.command("claude")
@click.argument("path", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--user", is_flag=True, help="Install MCP at user scope (global) instead of project scope.")
def init_claude(path: Path, user: bool) -> None:
    """Set up codescope for Claude Code.

    Creates .claude/CLAUDE.md with agent instructions and configures the
    codescope MCP server. By default writes .mcp.json in the project root
    (project scope). Use --user to install globally in ~/.claude.json.
    """
    project = path.resolve()
    console.print(f"[bold]Initializing codescope for Claude Code[/] in {project}\n")

    # 1. .codescopeignore
    _ensure_codescopeignore(project)

    # 2. Agent instructions
    claude_md = project / ".claude" / "CLAUDE.md"
    _ensure_instructions_file(claude_md)

    # 3. MCP configuration
    if user:
        mcp_file = Path.home() / ".claude.json"
        _ensure_mcp_json(mcp_file)
        console.print("  [dim]MCP scope: user (all projects)[/]")
    else:
        mcp_file = project / ".mcp.json"
        _ensure_mcp_json(mcp_file)
        console.print("  [dim]MCP scope: project[/]")

    # 4. PostToolUse hook for automatic re-indexing
    if user:
        hooks_file = Path.home() / ".claude" / "settings.json"
    else:
        hooks_file = project / ".claude" / "settings.json"
    _ensure_hooks_settings(hooks_file)

    console.print(
        "\n[green]Done![/] Next steps:\n"
        "  1. Run [bold]codescope index .[/] to index the project\n"
        "  2. Open the project with Claude Code"
    )


@init.command("codex")
@click.argument("path", default=".", type=click.Path(exists=True, path_type=Path))
@click.option("--user", is_flag=True, help="Install MCP at user scope (global) instead of project scope.")
def init_codex(path: Path, user: bool) -> None:
    """Set up codescope for Codex.

    Creates AGENTS.md with agent instructions and configures the codescope
    MCP server. By default writes .codex/config.toml in the project
    (project scope). Use --user to install globally in ~/.codex/config.toml.
    """
    project = path.resolve()
    console.print(f"[bold]Initializing codescope for Codex[/] in {project}\n")

    # 1. .codescopeignore
    _ensure_codescopeignore(project)

    # 2. Agent instructions
    if user:
        agents_md = Path.home() / ".codex" / "AGENTS.md"
    else:
        agents_md = project / "AGENTS.md"
    _ensure_instructions_file(agents_md)

    # 3. MCP configuration
    if user:
        mcp_file = Path.home() / ".codex" / "config.toml"
        _ensure_codex_mcp_toml(mcp_file)
        console.print("  [dim]MCP scope: user (all projects)[/]")
    else:
        mcp_file = project / ".codex" / "config.toml"
        _ensure_codex_mcp_toml(mcp_file)
        console.print("  [dim]MCP scope: project[/]")

    console.print(
        "\n[green]Done![/] Next steps:\n"
        "  1. Run [bold]codescope index .[/] to index the project\n"
        "  2. Open the project with Codex"
    )
