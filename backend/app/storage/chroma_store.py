"""
ChromaDB integration for log vector storage.

Provides:
  - Embedding-based storage of log entries
  - Semantic similarity search for noise reduction & retrieval
  - Deduplication / clustering support
"""

import json
from typing import Any, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings


class ChromaStore:
    """Manages ChromaDB collections for log storage and retrieval."""

    def __init__(self):
        self._client = chromadb.Client(ChromaSettings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=settings.chroma_persist_dir,
            anonymized_telemetry=False,
        ))
        # Main log collection
        self._logs_collection = self._client.get_or_create_collection(
            name="sentinel_logs",
            metadata={"hnsw:space": "cosine"},
        )
        # Cluster centroids (for noise reduction)
        self._clusters_collection = self._client.get_or_create_collection(
            name="log_clusters",
            metadata={"hnsw:space": "cosine"},
        )

    # ── Write ─────────────────────────────────────────────────────────────
    def add_log(self, log_id: str, text: str, metadata: dict[str, Any]) -> None:
        """Add a single log entry to the vector store."""
        # Filter metadata to only include simple types that ChromaDB accepts
        clean_meta = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                clean_meta[k] = v
            else:
                clean_meta[k] = json.dumps(v)

        self._logs_collection.add(
            ids=[log_id],
            documents=[text],
            metadatas=[clean_meta],
        )

    def add_logs_batch(self, ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
        """Add multiple log entries at once."""
        clean_metas = []
        for meta in metadatas:
            clean = {}
            for k, v in meta.items():
                if isinstance(v, (str, int, float, bool)):
                    clean[k] = v
                else:
                    clean[k] = json.dumps(v)
            clean_metas.append(clean)

        self._logs_collection.add(
            ids=ids,
            documents=texts,
            metadatas=clean_metas,
        )

    # ── Read ──────────────────────────────────────────────────────────────
    def search_similar(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """Find logs semantically similar to query."""
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where

        results = self._logs_collection.query(**kwargs)

        docs = []
        for i in range(len(results["ids"][0])):
            docs.append({
                "log_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else None,
            })
        return docs

    def get_log_by_id(self, log_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a specific log by ID."""
        result = self._logs_collection.get(ids=[log_id])
        if result["ids"]:
            return {
                "log_id": result["ids"][0],
                "text": result["documents"][0],
                "metadata": result["metadatas"][0] if result["metadatas"] else {},
            }
        return None

    def count(self) -> int:
        return self._logs_collection.count()

    # ── Noise Reduction ───────────────────────────────────────────────────
    def find_duplicates(self, text: str, threshold: float = 0.15) -> list[dict]:
        """Find near-duplicate logs (cosine distance < threshold)."""
        results = self.search_similar(text, n_results=5)
        return [r for r in results if r["distance"] is not None and r["distance"] < threshold]


# Singleton
_store: ChromaStore | None = None


def get_chroma_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store
