"""ChromaDB vector store wrapper for codescope."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb

COLLECTION_NAME = "codescope"


class VectorStore:
    """Thin wrapper around ChromaDB for storing and querying code embeddings.

    Supports two modes:
    - Local: ChromaDB handles embedding internally (pass documents, not vectors).
    - OpenAI: Embeddings are computed externally and passed as vectors.
    """

    def __init__(self, db_path: Path, *, embedding_function: Any | None = None) -> None:
        db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(db_path))

        kwargs: dict[str, Any] = {
            "name": COLLECTION_NAME,
            "metadata": {"hnsw:space": "cosine"},
        }
        if embedding_function is not None:
            kwargs["embedding_function"] = embedding_function

        self._collection = self._client.get_or_create_collection(**kwargs)

    @property
    def count(self) -> int:
        return self._collection.count()

    # --- Local mode: ChromaDB embeds internally ---

    def upsert_documents(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert with ChromaDB handling embedding (local provider)."""
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def query_text(self, text: str, n_results: int = 10) -> dict[str, Any]:
        """Query using text — ChromaDB embeds the query (local provider)."""
        return self._collection.query(
            query_texts=[text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

    # --- OpenAI mode: External embeddings ---

    def upsert_embeddings(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert with pre-computed embeddings (OpenAI provider)."""
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query_embedding(self, embedding: list[float], n_results: int = 10) -> dict[str, Any]:
        """Query using a pre-computed embedding vector (OpenAI provider)."""
        return self._collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

    # --- Shared ---

    def delete_by_file(self, file_path: str) -> None:
        """Delete all chunks belonging to a specific file."""
        self._collection.delete(where={"file_path": file_path})

    def clear(self) -> None:
        """Delete all data from the collection."""
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
