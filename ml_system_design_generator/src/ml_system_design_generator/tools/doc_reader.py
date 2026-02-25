"""Read and chunk markdown documents for processing."""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def list_doc_files(docs_dir: str | Path) -> list[Path]:
    """List markdown files in the docs directory, sorted by name."""
    d = Path(docs_dir)
    if not d.exists():
        return []
    files = sorted(d.rglob("*.md"))
    return files


def read_document(path: str | Path) -> str:
    """Read a markdown document and return its text content."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Document not found: {p}")
    return p.read_text(encoding="utf-8")


def total_size_kb(docs_dir: str | Path) -> float:
    """Return total size of all .md files in docs_dir in kilobytes."""
    total = 0
    for f in list_doc_files(docs_dir):
        total += f.stat().st_size
    return total / 1024


def chunk_document(
    text: str,
    *,
    max_tokens: int = 500,
    overlap_tokens: int = 50,
) -> list[str]:
    """Chunk a document by headings, then by approximate token count.

    Strategy:
    1. Split on markdown headings (# ## ###).
    2. If a heading section exceeds max_tokens, split further by paragraphs.
    3. Each chunk gets ~overlap_tokens of trailing context from the previous chunk.
    """
    # Split on heading boundaries
    heading_re = re.compile(r"^(#{1,6}\s+.+)", re.MULTILINE)
    parts = heading_re.split(text)

    # Recombine: each heading goes with its body text
    sections: list[str] = []
    current = ""
    for part in parts:
        if heading_re.match(part):
            if current.strip():
                sections.append(current.strip())
            current = part + "\n"
        else:
            current += part
    if current.strip():
        sections.append(current.strip())

    # Sub-chunk sections that are too long
    chunks: list[str] = []
    for section in sections:
        words = section.split()
        # Rough token estimate: 1 word ~ 1.3 tokens
        est_tokens = int(len(words) * 1.3)

        if est_tokens <= max_tokens:
            chunks.append(section)
        else:
            # Split by paragraphs
            paragraphs = re.split(r"\n\n+", section)
            current_chunk: list[str] = []
            current_word_count = 0

            for para in paragraphs:
                para_words = len(para.split())
                if current_word_count + para_words > int(max_tokens / 1.3) and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    # Overlap: keep last bit
                    overlap_text = " ".join(current_chunk[-1].split()[-int(overlap_tokens / 1.3):])
                    current_chunk = [overlap_text, para]
                    current_word_count = len(overlap_text.split()) + para_words
                else:
                    current_chunk.append(para)
                    current_word_count += para_words

            if current_chunk:
                chunks.append("\n\n".join(current_chunk))

    return chunks


def chunk_all_documents(docs_dir: str | Path, **kwargs) -> list[dict[str, str]]:
    """Chunk all markdown files in docs_dir.

    Returns list of dicts with keys: file_path, chunk_index, text.
    """
    results: list[dict[str, str]] = []
    for f in list_doc_files(docs_dir):
        text = read_document(f)
        chunks = chunk_document(text, **kwargs)
        for i, chunk in enumerate(chunks):
            results.append({
                "file_path": str(f),
                "chunk_index": str(i),
                "text": chunk,
            })
    return results
