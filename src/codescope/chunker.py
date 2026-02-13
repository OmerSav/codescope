"""Code chunking — splits source files into semantically meaningful chunks.

Uses tree-sitter to parse code into top-level semantic units (functions,
classes, methods). Falls back to a simple line-based sliding window for
unsupported languages or when tree-sitter parsing fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """A single chunk of source code."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str | None = None
    symbol: str | None = None  # function/class name if detected

    @property
    def id(self) -> str:
        """Stable identifier for this chunk."""
        return f"{self.file_path}:{self.start_line}-{self.end_line}"


# --- Tree-sitter language registry ---

# Maps file extensions to (module_name, language_name) for lazy import
EXTENSION_TO_LANGUAGE: dict[str, tuple[str, str]] = {
    ".py": ("tree_sitter_python", "python"),
    ".js": ("tree_sitter_javascript", "javascript"),
    ".jsx": ("tree_sitter_javascript", "javascript"),
    ".ts": ("tree_sitter_typescript", "typescript"),
    ".tsx": ("tree_sitter_typescript", "typescript"),
    ".go": ("tree_sitter_go", "go"),
    ".rs": ("tree_sitter_rust", "rust"),
    ".java": ("tree_sitter_java", "java"),
    ".c": ("tree_sitter_c", "c"),
    ".h": ("tree_sitter_c", "c"),
    ".cpp": ("tree_sitter_cpp", "cpp"),
    ".hpp": ("tree_sitter_cpp", "cpp"),
    ".cc": ("tree_sitter_cpp", "cpp"),
    ".cs": ("tree_sitter_c_sharp", "c_sharp"),
    ".rb": ("tree_sitter_ruby", "ruby"),
    ".html": ("tree_sitter_html", "html"),
    ".css": ("tree_sitter_css", "css"),
}

# Top-level node types we want to extract as individual chunks per language
SEMANTIC_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "function_definition", "class_definition", "decorated_definition",
    },
    "javascript": {
        "function_declaration", "class_declaration", "export_statement",
        "lexical_declaration", "expression_statement",
    },
    "typescript": {
        "function_declaration", "class_declaration", "export_statement",
        "lexical_declaration", "interface_declaration", "type_alias_declaration",
        "enum_declaration",
    },
    "go": {
        "function_declaration", "method_declaration", "type_declaration",
    },
    "rust": {
        "function_item", "impl_item", "struct_item", "enum_item",
        "trait_item", "mod_item",
    },
    "java": {
        "class_declaration", "interface_declaration", "enum_declaration",
        "method_declaration",
    },
    "c": {
        "function_definition", "struct_specifier", "enum_specifier",
        "declaration",
    },
    "cpp": {
        "function_definition", "class_specifier", "struct_specifier",
        "namespace_definition", "template_declaration",
    },
    "c_sharp": {
        "class_declaration", "interface_declaration", "method_declaration",
        "namespace_declaration", "enum_declaration",
    },
    "ruby": {
        "method", "class", "module", "singleton_method",
    },
}

# Cache for loaded parsers
_parser_cache: dict[str, Any] = {}


def _get_parser(language_name: str, module_name: str) -> Any | None:
    """Lazily load and cache a tree-sitter parser for the given language."""
    if language_name in _parser_cache:
        return _parser_cache[language_name]

    try:
        import importlib

        from tree_sitter import Language, Parser

        mod = importlib.import_module(module_name)
        lang_fn = getattr(mod, "language", None)

        if lang_fn is None:
            return None

        # Handle typescript which has language_typescript and language_tsx
        if language_name == "typescript":
            lang_fn = getattr(mod, "language_typescript", lang_fn)

        language = Language(lang_fn())
        parser = Parser(language)
        _parser_cache[language_name] = parser
        return parser
    except Exception:
        logger.debug("Failed to load tree-sitter parser for %s", language_name, exc_info=True)
        return None


def _get_node_name(node: Any) -> str | None:
    """Extract the symbol name from a tree-sitter node."""
    # For decorated definitions, dig into the inner definition
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in (
                "function_definition", "class_definition",
                "method_declaration", "class_declaration",
            ):
                return _get_node_name(child)
        return None

    # Look for a name/identifier child node
    for child in node.children:
        if child.type in ("identifier", "name", "property_identifier", "type_identifier"):
            return child.text.decode("utf-8", errors="replace") if child.text else None
    return None


def _node_to_chunk(
    node: Any,
    lines: list[str],
    language: str,
) -> Chunk:
    """Convert a tree-sitter node to a Chunk."""
    start_line = node.start_point[0]  # 0-indexed
    end_line = node.end_point[0]  # 0-indexed

    content = "".join(lines[start_line : end_line + 1])
    symbol = _get_node_name(node)

    return Chunk(
        file_path="",  # caller sets this
        start_line=start_line + 1,  # 1-indexed
        end_line=end_line + 1,
        content=content,
        language=language,
        symbol=symbol,
    )


def _chunk_with_treesitter(
    text: str,
    lines: list[str],
    language_name: str,
    module_name: str,
    max_lines: int,
    overlap: int,
) -> list[Chunk] | None:
    """Try to chunk a file using tree-sitter. Returns None if parsing fails."""
    parser = _get_parser(language_name, module_name)
    if parser is None:
        return None

    try:
        tree = parser.parse(text.encode("utf-8"))
    except Exception:
        return None

    root = tree.root_node
    semantic_types = SEMANTIC_NODE_TYPES.get(language_name, set())

    if not semantic_types:
        return None

    chunks: list[Chunk] = []
    last_end = 0

    for child in root.children:
        child_start = child.start_point[0]
        child_end = child.end_point[0]
        node_lines = child_end - child_start + 1

        if child.type in semantic_types:
            # Capture any "gap" lines before this node (imports, comments, etc.)
            if child_start > last_end and last_end < len(lines):
                gap_content = "".join(lines[last_end:child_start])
                if gap_content.strip():
                    chunks.append(Chunk(
                        file_path="",
                        start_line=last_end + 1,
                        end_line=child_start,
                        content=gap_content,
                        language=language_name,
                        symbol=None,
                    ))

            if node_lines <= max_lines:
                # Node fits in one chunk
                chunks.append(_node_to_chunk(child, lines, language_name))
            else:
                # Node too large — split it with sliding window
                chunks.extend(
                    _sliding_window(
                        lines[child_start : child_end + 1],
                        offset=child_start,
                        max_lines=max_lines,
                        overlap=overlap,
                        language=language_name,
                        symbol=_get_node_name(child),
                    )
                )
            last_end = child_end + 1

    # Capture trailing content after last semantic node
    if last_end < len(lines):
        trailing = "".join(lines[last_end:])
        if trailing.strip():
            chunks.append(Chunk(
                file_path="",
                start_line=last_end + 1,
                end_line=len(lines),
                content=trailing,
                language=language_name,
                symbol=None,
            ))

    return chunks if chunks else None


def _sliding_window(
    lines: list[str],
    *,
    offset: int = 0,
    max_lines: int = 60,
    overlap: int = 2,
    language: str | None = None,
    symbol: str | None = None,
) -> list[Chunk]:
    """Split lines into overlapping chunks using a sliding window."""
    chunks: list[Chunk] = []
    i = 0

    while i < len(lines):
        end = min(i + max_lines, len(lines))
        chunk_content = "".join(lines[i:end])
        chunks.append(
            Chunk(
                file_path="",
                start_line=offset + i + 1,  # 1-indexed
                end_line=offset + end,
                content=chunk_content,
                language=language,
                symbol=symbol if i == 0 else None,
            )
        )
        i = end - overlap if end < len(lines) else end

    return chunks


def chunk_file(path: Path, *, max_lines: int = 60, overlap: int = 2) -> list[Chunk]:
    """Chunk a single file into a list of Chunk objects.

    Uses tree-sitter for supported languages, falls back to sliding window.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines(keepends=True)
    if not lines:
        return []

    # Try tree-sitter first
    lang_info = EXTENSION_TO_LANGUAGE.get(path.suffix.lower())
    if lang_info is not None:
        module_name, language_name = lang_info
        ts_chunks = _chunk_with_treesitter(
            text, lines, language_name, module_name, max_lines, overlap
        )
        if ts_chunks is not None:
            return ts_chunks

    # Fallback: sliding window
    return _sliding_window(lines, max_lines=max_lines, overlap=overlap)
