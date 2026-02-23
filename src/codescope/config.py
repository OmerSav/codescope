"""Configuration and constants for codescope."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from pathspec import PathSpec

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
    ".dart", ".gd", ".tscn", ".tres", ".gdshader", ".gdshaderinc",
    ".sql", ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".toml", ".json",
    ".md", ".mdx", ".txt", ".rst",
    ".html", ".css", ".scss", ".svelte", ".vue",
}

# Directories to always ignore (safety net — never indexable)
IGNORE_DIRS: set[str] = {
    # Version control
    ".git", ".hg", ".svn",
    # Dependencies
    "node_modules", "__pycache__", ".venv", "venv", "env",
    "vendor", "bower_components", ".pub", ".pub-cache", ".dart_tool",
    # Build outputs
    ".codescope", ".next", ".nuxt", "dist", "build", "target", "out", "web-build",
    # Caches & tooling
    ".tox", ".nox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".pytype", ".pyre", "htmlcov", "coverage",
    ".vite", ".turbo", ".gradle", "Pods",
    # Framework / engine
    ".expo", ".godot", ".import", ".mono", ".branches", ".temp",
    ".flutter", ".supabase",
    # AI agent orchestration
    ".applord",
    # Environment
    ".env",
}

# Name of the user-editable ignore file inside .codescope/
IGNORE_FILE_NAME = ".codescopeignore"

# Default content for a freshly-created .codescopeignore
# Full .gitignore syntax — LLMs and tools know this format
DEFAULT_IGNORE_CONTENT = """\
# codescope ignore — same syntax as .gitignore
# https://git-scm.com/docs/gitignore

# ── Codescope & VCS ───────────────────────────────────────────
**/.codescope/
**/.git/
**/.hg/
**/.svn/

# ── Dependencies ──────────────────────────────────────────────
**/node_modules/
**/.venv/
**/venv/
**/env/
**/ENV/
**/vendor/
**/bower_components/
**/.pub/
**/.pub-cache/
**/.dart_tool/

# ── Lock files ────────────────────────────────────────────────
**/package-lock.json
**/yarn.lock
**/pnpm-lock.yaml
**/uv.lock
**/Gemfile.lock
**/Podfile.lock
**/pubspec.lock
**/composer.lock
**/Cargo.lock
**/go.sum

# ── Build outputs ─────────────────────────────────────────────
**/dist/
**/dist-ssr/
**/build/
**/target/
**/out/
**/web-build/
**/*.min.js
**/*.min.css
**/*.map
**/*.egg-info/
**/*.egg
**/*.whl

# ── Python ────────────────────────────────────────────────────
**/__pycache__/
**/*.pyc
**/*.pyo
**/*.py[cod]
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/.tox/
**/.nox/
**/.coverage
**/htmlcov/
**/coverage.xml
**/.pytype/
**/.pyre/
**/.Python

# ── JavaScript / TypeScript ───────────────────────────────────
**/.next/
**/.nuxt/
**/.expo/
**/.vite/
**/.turbo/
**/.metro-health-check*
**/tsconfig.tsbuildinfo
**/*.tsbuildinfo
**/coverage/

# ── Flutter / Dart ────────────────────────────────────────────
**/.flutter/
**/.flutter-plugins
**/.flutter-plugins-dependencies
**/*.g.dart
**/*.freezed.dart
**/*.gr.dart
**/doc/api/

# ── Godot ─────────────────────────────────────────────────────
**/.godot/
**/.import/
**/.mono/
**/*.translation
**/mono_crash.*.json
**/export_presets.cfg

# ── ML / AI models ────────────────────────────────────────────
**/*.pkl
**/*.joblib
**/*.h5
**/*.onnx
**/*.pt
**/*.pth
**/*.safetensors
**/*.bin
**/*.ckpt

# ── Mobile build artifacts ────────────────────────────────────
**/*.apk
**/*.aab
**/*.ipa
**/*.app
**/*.jks
**/*.keystore
**/*.p8
**/*.p12
**/*.mobileprovision
**/*.hprof

# ── Compiled / native ────────────────────────────────────────
**/*.so
**/*.dylib
**/*.dll
**/*.exe
**/*.x86_64
**/*.class
**/*.o
**/*.obj

# ── Environment & secrets ─────────────────────────────────────
**/.env
**/.env.local
**/.env.*.local
**/secrets/
**/.secrets
**/credentials.json

# ── Supabase ──────────────────────────────────────────────────
**/.supabase/
**/.branches/
**/.temp/

# ── Mobile native build ──────────────────────────────────────
**/.gradle/
**/Pods/

# ── AI agent orchestration ───────────────────────────────────
**/.applord/

# ── Docker ────────────────────────────────────────────────────
**/.dockerignore

# ── Test artifacts & mock data ────────────────────────────────
**/*.test.ts
**/*.test.js
**/*.spec.ts
**/*.spec.js
**/*.test.py
**/*_test.py
**/tests/
**/__tests__/
**/test/
**/__test__/
**/past_errors/
**/mock_data/
**/mocks/
**/test_outputs/

# ── IDE & OS ──────────────────────────────────────────────────
**/.vscode/
**/.idea/
**/.fleet/
**/.eclipse/
**/.settings/
**/.project
**/.classpath
**/*.iml
**/.DS_Store
**/Thumbs.db
**/Desktop.ini
**/*.swp
**/*.swo
**/*~

# ── Logs ──────────────────────────────────────────────────────
**/*.log
**/logs/
**/npm-debug.log*
**/yarn-debug.log*
**/yarn-error.log*
**/pnpm-debug.log*

# ── Media & binary ────────────────────────────────────────────
**/*.png
**/*.jpg
**/*.jpeg
**/*.gif
**/*.ico
**/*.svg
**/*.webp
**/*.bmp
**/*.woff
**/*.woff2
**/*.ttf
**/*.eot
**/*.otf
**/*.mp4
**/*.mp3
**/*.wav
**/*.ogg
**/*.flac
**/*.zip
**/*.tar.gz
**/*.rar
**/*.7z
**/*.pdf
**/*.pem
"""


def load_ignore_spec(project_root: Path) -> PathSpec | None:
    """Read .codescope/.codescopeignore and return a gitignore-style PathSpec."""
    ignore_path = project_root / DEFAULT_DB_DIR / IGNORE_FILE_NAME
    if not ignore_path.is_file():
        return None
    lines = ignore_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    return PathSpec.from_lines("gitignore", lines)


def matches_ignore(rel_path: str, spec: PathSpec | None) -> bool:
    """Return True if *rel_path* is ignored by the gitignore spec."""
    if spec is None:
        return False
    # PathSpec expects forward slashes, relative path
    # match_file returns True when path matches a pattern (= should be ignored)
    norm = rel_path.replace("\\", "/")
    return spec.match_file(norm)


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
    ignore_spec: PathSpec | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.db_dir = self.project_root / DEFAULT_DB_DIR
        self._apply_global_config()
        self.ignore_spec = load_ignore_spec(self.project_root)

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
