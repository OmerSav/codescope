"""Configuration and constants for codescope."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Default directory name for the codescope database inside a project
DEFAULT_DB_DIR = ".codescope"

# Embedding providers
PROVIDER_LOCAL = "local"
PROVIDER_OPENAI = "openai"

# Default embedding provider (local = ChromaDB built-in all-MiniLM-L6-v2)
DEFAULT_EMBEDDING_PROVIDER = PROVIDER_LOCAL

# Default embedding models per provider
DEFAULT_LOCAL_MODEL = "all-MiniLM-L6-v2"
DEFAULT_OPENAI_MODEL = "text-embedding-3-small"

# Default chunk overlap (lines)
DEFAULT_CHUNK_OVERLAP = 2

# Default max chunk size (lines)
DEFAULT_MAX_CHUNK_LINES = 60

# Default number of search results
DEFAULT_N_RESULTS = 10

# File extensions to index by default
DEFAULT_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".java", ".kt", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".scala",
    ".sql", ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml", ".json",
    ".md", ".mdx", ".txt", ".rst",
    ".html", ".css", ".scss", ".svelte", ".vue",
}

# Directories to always ignore
IGNORE_DIRS: set[str] = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".venv", "venv", ".env",
    ".codescope", ".next", ".nuxt", "dist", "build", "target",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "vendor", "bower_components",
}


@dataclass
class CodeScopeConfig:
    """Runtime configuration for a codescope session."""

    project_root: Path
    db_dir: Path = field(init=False)
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_model: str = ""
    openai_api_key: str = ""
    max_chunk_lines: int = DEFAULT_MAX_CHUNK_LINES
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    n_results: int = DEFAULT_N_RESULTS
    extensions: set[str] = field(default_factory=lambda: DEFAULT_EXTENSIONS.copy())
    ignore_dirs: set[str] = field(default_factory=lambda: IGNORE_DIRS.copy())

    def __post_init__(self) -> None:
        self.db_dir = self.project_root / DEFAULT_DB_DIR
        self._apply_global_config()

        # Set default model based on provider if not explicitly set
        if not self.embedding_model:
            if self.embedding_provider == PROVIDER_OPENAI:
                self.embedding_model = DEFAULT_OPENAI_MODEL
            else:
                self.embedding_model = DEFAULT_LOCAL_MODEL

        # Read OpenAI key from env if not provided and provider is openai
        if not self.openai_api_key:
            self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")

    def _apply_global_config(self) -> None:
        """Apply global config values where not explicitly overridden.

        Priority: constructor args > env vars > global config > defaults.
        """
        from .global_config import load_global_config

        gc = load_global_config()
        if not gc:
            return

        # Only apply global config if the field still has its default value
        if self.embedding_provider == DEFAULT_EMBEDDING_PROVIDER and "embedding_provider" in gc:
            self.embedding_provider = gc["embedding_provider"]

        if not self.embedding_model and "embedding_model" in gc:
            self.embedding_model = gc["embedding_model"]

        if not self.openai_api_key and "openai_api_key" in gc:
            self.openai_api_key = gc["openai_api_key"]

    @property
    def is_local(self) -> bool:
        return self.embedding_provider == PROVIDER_LOCAL

    @property
    def is_openai(self) -> bool:
        return self.embedding_provider == PROVIDER_OPENAI
