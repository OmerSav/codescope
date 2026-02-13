# codescope

Give AI coding agents instant semantic search over any codebase.

codescope indexes your project with tree-sitter, embeds it with a local model (or OpenAI), stores vectors in ChromaDB, and exposes everything through an MCP server. Claude Code, Codex, or any MCP-compatible agent can search your code by meaning instead of grepping blindly.

## Quick Start

### 1. Install

```bash
# With uv (recommended) — installs globally, handles Python automatically
uv tool install codescope

# With OpenAI embedding support
uv tool install codescope --with openai

# Or from GitHub directly
uv tool install git+https://github.com/OmerSav/codescope

# Or with pip/pipx
pip install codescope
pipx install codescope
```

> **Note:** codescope requires Python 3.12+. `uv` downloads the correct version automatically — no manual Python setup needed.

### 2. Set up for your agent

```bash
# For Claude Code
codescope init claude .

# For Codex
codescope init codex .
```

This creates the agent instructions file and MCP config in the right places. Use `--user` to install globally instead of per-project:

```bash
codescope init claude --user .
codescope init codex --user .
```

### 3. Index the project

```bash
codescope index .
```

### 4. Start using your agent

Open the project with Claude Code or Codex. The agent will automatically connect to codescope and use semantic search instead of scanning files manually.

## What `init` does

| Command                 | Instructions file   | MCP config (project) | MCP config (--user)    |
| ----------------------- | ------------------- | -------------------- | ---------------------- |
| `codescope init claude` | `.claude/CLAUDE.md` | `.mcp.json`          | `~/.claude.json`       |
| `codescope init codex`  | `AGENTS.md`         | `.codex/config.toml` | `~/.codex/config.toml` |

- If the instructions file already exists, codescope appends its section without touching existing content.
- If the MCP config already exists, codescope adds its entry without removing other servers.
- Running `init` twice is safe — it skips anything already configured.

## CLI Reference

```bash
# Index (incremental by default, only changed files)
codescope index .

# Force full re-index
codescope index . --full

# Semantic search
codescope search "authentication middleware"

# Search with code snippets
codescope search "database connection" --show-code

# Check indexing status
codescope status

# Configuration
codescope config show
codescope config set embedding_provider openai
codescope config set openai_api_key sk-...
codescope config set embedding_provider local
```

## Embedding Providers

| Provider          | Model                  | Cost              | Quality | Setup            |
| ----------------- | ---------------------- | ----------------- | ------- | ---------------- |
| `local` (default) | all-MiniLM-L6-v2       | Free              | Good    | Zero config      |
| `openai`          | text-embedding-3-small | ~$0.03/full index | Better  | API key required |

Install with OpenAI support: `pip install codescope[openai]`

## MCP Server

The MCP server is what agents talk to. You don't run it manually — the agent's MCP client starts it automatically using the `codescope-mcp` command.

### Tools (agent-callable actions)

| Tool              | Description                                          |
| ----------------- | ---------------------------------------------------- |
| `search_codebase` | Semantic search over indexed code                    |
| `index_codebase`  | Index or re-index a project (incremental by default) |
| `begin_session`   | Snapshot file hashes before agent starts working     |
| `end_session`     | Diff against snapshot, auto re-index changed files   |

### Resources (read-only context)

| URI                  | Description                                   |
| -------------------- | --------------------------------------------- |
| `codescope://tree`   | Project file tree — quick structural overview |
| `codescope://status` | Indexing status, provider, model, chunk count |
| `codescope://files`  | Flat list of all indexed files                |
| `codescope://config` | Current configuration                         |

### Prompts (interaction templates)

| Prompt             | Description                                 |
| ------------------ | ------------------------------------------- |
| `search_first`     | Guides agent to search before reading files |
| `session_workflow` | Recommended begin/end session workflow      |

### Session Workflow

Agents use `begin_session` / `end_session` to keep the index fresh automatically:

```
begin_session → snapshot taken
  agent makes code changes...
end_session → diff computed, changed files re-indexed
```

## How It Works

1. **Chunking** — tree-sitter splits code into semantic units (functions, classes, methods). Falls back to sliding window for unsupported languages.
2. **Embedding** — Generates vector embeddings (local all-MiniLM-L6-v2 or OpenAI).
3. **Storage** — ChromaDB persists vectors to `.codescope/` in the project.
4. **Incremental updates** — SHA-256 hash tracking ensures only changed files are re-embedded.
5. **Search** — Query is embedded, nearest neighbors returned with file paths and line ranges.

## Supported Languages (tree-sitter)

Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, C#, Ruby, HTML, CSS.

Other file types fall back to line-based sliding window chunking.

## Development

```bash
git clone https://github.com/OmerSav/codescope.git
cd codescope
uv sync --extra dev --extra openai
uv run pytest
uv run ruff check src/
```

## License

MIT
