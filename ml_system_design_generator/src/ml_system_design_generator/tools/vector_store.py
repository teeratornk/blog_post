"""ChromaDB wrapper for document embedding, querying, and lifecycle."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "mlsd_docs"


def _get_client(persist_dir: str | Path):
    """Create a persistent ChromaDB client."""
    import chromadb

    return chromadb.PersistentClient(path=str(persist_dir))


def create_vector_store(
    chunks: list[dict[str, str]],
    persist_dir: str | Path,
) -> int:
    """Embed and store document chunks in ChromaDB.

    Args:
        chunks: list of dicts with keys: file_path, chunk_index, text.
        persist_dir: directory for ChromaDB persistence.

    Returns:
        Number of chunks stored.
    """
    persist = Path(persist_dir)
    persist.mkdir(parents=True, exist_ok=True)

    client = _get_client(persist)

    # Delete existing collection if any
    try:
        client.delete_collection(_COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    if not chunks:
        return 0

    ids = [f"{c['file_path']}::chunk_{c['chunk_index']}" for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [{"file_path": c["file_path"], "chunk_index": c["chunk_index"]} for c in chunks]

    # Batch insert (ChromaDB handles embedding via its default model)
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )

    logger.info("Stored %d chunks in ChromaDB at %s", len(ids), persist)
    return len(ids)


def query_vector_store(
    query: str,
    persist_dir: str | Path,
    *,
    n_results: int = 5,
) -> list[dict[str, Any]]:
    """Query the vector store for relevant chunks.

    Returns list of dicts with keys: text, file_path, chunk_index, distance.
    """
    client = _get_client(persist_dir)

    try:
        collection = client.get_collection(_COLLECTION_NAME)
    except Exception:
        logger.warning("Vector store collection not found at %s", persist_dir)
        return []

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
    )

    items: list[dict[str, Any]] = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 0.0
            items.append({
                "text": doc,
                "file_path": meta.get("file_path", ""),
                "chunk_index": meta.get("chunk_index", ""),
                "distance": distance,
            })

    return items


def vector_store_exists(persist_dir: str | Path) -> bool:
    """Check if a vector store collection exists at the given path."""
    persist = Path(persist_dir)
    if not persist.exists():
        return False
    try:
        client = _get_client(persist)
        client.get_collection(_COLLECTION_NAME)
        return True
    except Exception:
        return False
