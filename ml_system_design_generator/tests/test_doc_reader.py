"""Tests for doc_reader tool."""

import pytest
from pathlib import Path

from ml_system_design_generator.tools.doc_reader import (
    chunk_document,
    list_doc_files,
    read_document,
    total_size_kb,
)


SAMPLE_MD = """\
# Introduction

This is the introduction paragraph. It contains some text about
the system we are designing.

## Background

Background information goes here. We need to explain the context
and motivation for the ML system.

## Problem Statement

The problem we are solving is described here with relevant data.

# Technical Details

## Architecture

The architecture section describes the overall system design.

## Data Pipeline

Data flows from source A to destination B through processing
steps 1, 2, and 3.
"""


class TestChunkDocument:
    def test_basic_chunking(self):
        chunks = chunk_document(SAMPLE_MD)
        assert len(chunks) > 0
        # Each chunk should contain some text
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_respects_headings(self):
        chunks = chunk_document(SAMPLE_MD)
        # Should have multiple chunks (split by headings)
        assert len(chunks) >= 2

    def test_small_document_single_chunk(self):
        small = "# Title\n\nA short document."
        chunks = chunk_document(small, max_tokens=1000)
        assert len(chunks) == 1

    def test_empty_document(self):
        chunks = chunk_document("")
        assert len(chunks) == 0


class TestListDocFiles:
    def test_lists_md_files(self, tmp_path: Path):
        (tmp_path / "doc1.md").write_text("# Doc 1")
        (tmp_path / "doc2.md").write_text("# Doc 2")
        (tmp_path / "readme.txt").write_text("Not a markdown file")

        files = list_doc_files(tmp_path)
        assert len(files) == 2
        assert all(f.suffix == ".md" for f in files)

    def test_empty_directory(self, tmp_path: Path):
        files = list_doc_files(tmp_path)
        assert len(files) == 0

    def test_nonexistent_directory(self):
        files = list_doc_files("/nonexistent/path")
        assert len(files) == 0


class TestReadDocument:
    def test_read_existing_file(self, tmp_path: Path):
        doc = tmp_path / "test.md"
        doc.write_text("# Test\n\nContent here.")
        content = read_document(doc)
        assert "# Test" in content

    def test_read_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            read_document("/nonexistent/file.md")


class TestTotalSizeKb:
    def test_calculates_size(self, tmp_path: Path):
        content = "x" * 1024  # 1KB
        (tmp_path / "doc1.md").write_text(content)
        (tmp_path / "doc2.md").write_text(content)

        size = total_size_kb(tmp_path)
        assert size >= 1.9  # ~2KB
        assert size <= 2.1
