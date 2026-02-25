"""Pandoc converter: markdown -> LaTeX (deterministic).

Reuses the SAFE_ZONE annotation pattern from research_article_generator.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SAFE_ZONE annotation
# ---------------------------------------------------------------------------

_READ_ONLY_ENVS = {
    "equation", "equation*", "align", "align*", "gather", "gather*",
    "multline", "multline*", "eqnarray", "eqnarray*", "math",
    "displaymath", "tabular", "tabular*", "tikzpicture",
}


def _annotate_safe_zones(latex: str) -> str:
    """Insert SAFE_ZONE markers around editable text blocks."""
    lines = latex.split("\n")
    result: list[str] = []
    in_safe = False
    in_readonly_env = False

    for line in lines:
        stripped = line.strip()

        env_begin = re.match(r"\\begin\{(\w+\*?)\}", stripped)
        env_end = re.match(r"\\end\{(\w+\*?)\}", stripped)

        if env_begin and env_begin.group(1) in _READ_ONLY_ENVS:
            if in_safe:
                result.append("%% SAFE_ZONE_END")
                in_safe = False
            in_readonly_env = True
            result.append(line)
            continue

        if env_end and env_end.group(1) in _READ_ONLY_ENVS:
            in_readonly_env = False
            result.append(line)
            continue

        if in_readonly_env:
            result.append(line)
            continue

        is_structural = bool(re.match(
            r"\\(section|subsection|subsubsection|paragraph|chapter|part|begin|end|label|"
            r"includegraphics|bibliography|bibliographystyle|usepackage|documentclass|"
            r"maketitle|tableofcontents|newcommand|renewcommand|input|include)\b",
            stripped,
        ))

        is_cite_only = bool(re.fullmatch(r"(\\cite[tp]?\{[^}]+\}\s*[.,;]?\s*)+", stripped))

        if is_structural or is_cite_only or not stripped:
            if in_safe:
                result.append("%% SAFE_ZONE_END")
                in_safe = False
            result.append(line)
        else:
            if not in_safe:
                result.append("%% SAFE_ZONE_START")
                in_safe = True
            result.append(line)

    if in_safe:
        result.append("%% SAFE_ZONE_END")

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Pandoc availability
# ---------------------------------------------------------------------------

def pandoc_available() -> bool:
    """Check if pandoc is on PATH."""
    return shutil.which("pandoc") is not None


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def convert_markdown_to_latex(
    markdown_path: str | Path,
    *,
    annotate: bool = True,
) -> str:
    """Convert a markdown file to LaTeX using pandoc.

    Falls back to raw markdown if pandoc is not available.
    """
    md_path = Path(markdown_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    markdown_content = md_path.read_text(encoding="utf-8")

    if not pandoc_available():
        logger.warning("pandoc not found, returning raw markdown as fallback")
        return markdown_content

    cmd = ["pandoc", "-f", "markdown", "-t", "latex", str(md_path)]

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        logger.error("Pandoc failed: %s", result.stderr)
        raise RuntimeError(f"Pandoc conversion failed:\n{result.stderr}")

    latex = result.stdout

    if annotate:
        latex = _annotate_safe_zones(latex)

    return latex


def convert_markdown_string_to_latex(
    markdown: str,
    *,
    annotate: bool = True,
) -> str:
    """Convert a markdown string to LaTeX via pandoc stdin."""
    if not pandoc_available():
        logger.warning("pandoc not found, returning raw markdown as fallback")
        return markdown

    cmd = ["pandoc", "-f", "markdown", "-t", "latex"]
    result = subprocess.run(cmd, input=markdown, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        logger.error("Pandoc failed: %s", result.stderr)
        raise RuntimeError(f"Pandoc conversion failed:\n{result.stderr}")

    latex = result.stdout
    if annotate:
        latex = _annotate_safe_zones(latex)

    return latex
