"""Tests for vector_store tool."""

import pytest
from pathlib import Path

from ml_system_design_generator.tools.vector_store import (
    create_vector_store,
    query_vector_store,
    vector_store_exists,
)


def _chromadb_available() -> bool:
    try:
        import chromadb
        return True
    except ImportError:
        return False


@pytest.fixture
def sample_chunks():
    return [
        {
            "file_path": "docs/doc1.md",
            "chunk_index": "0",
            "text": "This document describes grid operations during normal conditions.",
        },
        {
            "file_path": "docs/doc1.md",
            "chunk_index": "1",
            "text": "Operators must monitor voltage levels and frequency deviations.",
        },
        {
            "file_path": "docs/doc2.md",
            "chunk_index": "0",
            "text": "Hurricane preparation requires pre-staging resources and personnel.",
        },
    ]


class TestVectorStoreExists:
    def test_nonexistent_path(self, tmp_path: Path):
        assert not vector_store_exists(tmp_path / "nonexistent")

    def test_empty_directory(self, tmp_path: Path):
        assert not vector_store_exists(tmp_path)


class TestCreateAndQuery:
    @pytest.mark.skipif(
        not _chromadb_available(),
        reason="chromadb not installed",
    )
    def test_create_and_query(self, tmp_path: Path, sample_chunks):
        persist_dir = tmp_path / ".vectordb"
        count = create_vector_store(sample_chunks, persist_dir)
        assert count == 3
        assert vector_store_exists(persist_dir)

        results = query_vector_store("grid operations voltage", persist_dir, n_results=2)
        assert len(results) <= 2
        assert all("text" in r for r in results)

    @pytest.mark.skipif(
        not _chromadb_available(),
        reason="chromadb not installed",
    )
    def test_empty_chunks(self, tmp_path: Path):
        persist_dir = tmp_path / ".vectordb"
        count = create_vector_store([], persist_dir)
        assert count == 0
