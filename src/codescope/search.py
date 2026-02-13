"""Semantic search over the indexed codebase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import CodeScopeConfig
from .embeddings import embed_query_openai, get_chromadb_embedding_function
from .store import VectorStore


@dataclass
class SearchResult:
    """A single search result."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    distance: float
    symbol: str

    def display(self) -> str:
        """Human-readable one-liner."""
        loc = f"{self.file_path}:{self.start_line}-{self.end_line}"
        sym = f" ({self.symbol})" if self.symbol else ""
        score = f"{1 - self.distance:.2%}"
        return f"{loc}{sym}  [similarity: {score}]"


def search(query: str, config: CodeScopeConfig) -> list[SearchResult]:
    """Run a semantic search query against the indexed codebase."""
    ef = get_chromadb_embedding_function(config)
    store = VectorStore(config.db_dir, embedding_function=ef)

    if config.is_local:
        raw: dict[str, Any] = store.query_text(query, n_results=config.n_results)
    else:
        query_embedding = embed_query_openai(query, config)
        raw = store.query_embedding(query_embedding, n_results=config.n_results)

    return _parse_results(raw)


def _parse_results(raw: dict[str, Any]) -> list[SearchResult]:
    """Parse raw ChromaDB query results into SearchResult objects."""
    results: list[SearchResult] = []
    if not raw["ids"] or not raw["ids"][0]:
        return results

    for i, chunk_id in enumerate(raw["ids"][0]):
        meta = raw["metadatas"][0][i] if raw["metadatas"] else {}
        doc = raw["documents"][0][i] if raw["documents"] else ""
        dist = raw["distances"][0][i] if raw["distances"] else 0.0

        results.append(
            SearchResult(
                file_path=meta.get("file_path", chunk_id),
                start_line=int(meta.get("start_line", 0)),
                end_line=int(meta.get("end_line", 0)),
                content=doc,
                distance=dist,
                symbol=meta.get("symbol", ""),
            )
        )

    return results
