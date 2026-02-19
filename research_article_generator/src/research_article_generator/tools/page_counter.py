"""Page counting via pdfinfo with log-file fallback."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def pdfinfo_available() -> bool:
    """Check if pdfinfo (from poppler-utils) is on PATH."""
    return shutil.which("pdfinfo") is not None


def count_pages(pdf_path: str | Path) -> int | None:
    """Count pages in a PDF file.

    Tries ``pdfinfo`` first, then falls back to parsing the LaTeX log.
    Returns ``None`` if the page count cannot be determined.
    """
    pdf = Path(pdf_path)

    if pdf.exists() and pdfinfo_available():
        try:
            result = subprocess.run(
                ["pdfinfo", str(pdf)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.startswith("Pages:"):
                        return int(line.split(":")[1].strip())
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass

    # Fallback: parse LaTeX log
    log_path = pdf.with_suffix(".log")
    if log_path.exists():
        return _count_from_log(log_path)

    return None


def _count_from_log(log_path: str | Path) -> int | None:
    """Extract page count from a LaTeX .log file.

    Looks for patterns like ``Output written on main.pdf (12 pages, ...)``.
    """
    log = Path(log_path)
    if not log.exists():
        return None

    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Pattern: "Output written on file.pdf (N pages, ...)"
    m = re.search(r"Output written on .+?\((\d+)\s+page", text)
    if m:
        return int(m.group(1))

    return None
