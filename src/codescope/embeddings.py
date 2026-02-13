"""Embedding generation — supports local (ChromaDB built-in) and OpenAI providers."""

from __future__ import annotations

from typing import Any

from .config import CodeScopeConfig


def get_chromadb_embedding_function(config: CodeScopeConfig) -> Any | None:
    """Return a ChromaDB embedding function for the configured provider.

    - Local provider: returns ChromaDB's default SentenceTransformer function
      (all-MiniLM-L6-v2 via onnxruntime, zero extra dependencies).
    - OpenAI provider: returns None (embeddings are computed externally).
    """
    if config.is_local:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        return DefaultEmbeddingFunction()
    return None


def embed_texts_openai(
    texts: list[str],
    config: CodeScopeConfig,
    *,
    batch_size: int = 100,
) -> list[list[float]]:
    """Generate embeddings via OpenAI API. Requires `pip install codescope[openai]`."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "OpenAI provider requires the openai package. "
            "Install with: pip install codescope[openai]"
        ) from None

    client = OpenAI(api_key=config.openai_api_key)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(input=batch, model=config.embedding_model)
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


def embed_query_openai(query: str, config: CodeScopeConfig) -> list[float]:
    """Embed a single query string via OpenAI API."""
    return embed_texts_openai([query], config)[0]
