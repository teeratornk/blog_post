"""Pandoc first-pass converter: markdown → LaTeX (deterministic).

Wraps ``pandoc --filter pandoc-crossref --natbib -f markdown -t latex``.
Annotates output with SAFE_ZONE markers for LLM polishing boundaries.
Falls back to raw markdown passthrough if pandoc is unavailable.
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

# Environments/commands whose content the LLM must NOT modify.
_READ_ONLY_PATTERNS = [
    # Math environments
    r"\\begin\{(equation|align|gather|multline|eqnarray|math|displaymath)\*?\}.*?\\end\{\1\*?\}",
    # Inline math
    r"(?<![\\])\$[^$]+\$",
    # Citations
    r"\\cite[tp]?\{[^}]+\}",
    # Labels and refs
    r"\\label\{[^}]+\}",
    r"\\ref\{[^}]+\}",
    r"\\eqref\{[^}]+\}",
    # Figure includes
    r"\\includegraphics\[[^\]]*\]\{[^}]+\}",
    # Table data rows (heuristic: lines with & and \\)
]


def _annotate_safe_zones(latex: str) -> str:
    """Insert ``%% SAFE_ZONE_START`` / ``%% SAFE_ZONE_END`` around editable text.

    Strategy: mark regions that are NOT read-only as safe zones.
    We insert markers around paragraph-like text blocks between structural
    commands.
    """
    lines = latex.split("\n")
    result: list[str] = []
    in_safe = False
    in_readonly_env = False

    # Environments the LLM must not touch
    readonly_envs = {
        "equation", "equation*", "align", "align*", "gather", "gather*",
        "multline", "multline*", "eqnarray", "eqnarray*", "math",
        "displaymath", "tabular", "tabular*",
    }

    for line in lines:
        stripped = line.strip()

        # Check for environment boundaries
        env_begin = re.match(r"\\begin\{(\w+\*?)\}", stripped)
        env_end = re.match(r"\\end\{(\w+\*?)\}", stripped)

        if env_begin and env_begin.group(1) in readonly_envs:
            if in_safe:
                result.append("%% SAFE_ZONE_END")
                in_safe = False
            in_readonly_env = True
            result.append(line)
            continue

        if env_end and env_end.group(1) in readonly_envs:
            in_readonly_env = False
            result.append(line)
            continue

        if in_readonly_env:
            result.append(line)
            continue

        # Structural commands are not editable
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
            # This is editable text
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


def pandoc_crossref_available() -> bool:
    """Check if pandoc-crossref is on PATH."""
    return shutil.which("pandoc-crossref") is not None


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def convert_markdown_to_latex(
    markdown_path: str | Path,
    *,
    use_crossref: bool = True,
    use_natbib: bool = True,
    extra_args: list[str] | None = None,
    annotate: bool = True,
) -> str:
    """Convert a markdown file to LaTeX using pandoc.

    Returns the LaTeX string with optional SAFE_ZONE annotations.
    Falls back to raw markdown content if pandoc is not available.
    """
    md_path = Path(markdown_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    markdown_content = md_path.read_text(encoding="utf-8")

    if not pandoc_available():
        logger.warning("pandoc not found, returning raw markdown as fallback")
        return markdown_content

    cmd = ["pandoc", "-f", "markdown", "-t", "latex"]

    if use_crossref and pandoc_crossref_available():
        cmd.extend(["--filter", "pandoc-crossref"])

    if use_natbib:
        cmd.append("--natbib")

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(str(md_path))

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )

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
    use_crossref: bool = True,
    use_natbib: bool = True,
    annotate: bool = True,
) -> str:
    """Convert a markdown string to LaTeX via pandoc stdin.

    Falls back to returning the input string if pandoc is not available.
    """
    if not pandoc_available():
        logger.warning("pandoc not found, returning raw markdown as fallback")
        return markdown

    cmd = ["pandoc", "-f", "markdown", "-t", "latex"]

    if use_crossref and pandoc_crossref_available():
        cmd.extend(["--filter", "pandoc-crossref"])

    if use_natbib:
        cmd.append("--natbib")

    result = subprocess.run(
        cmd,
        input=markdown,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        logger.error("Pandoc failed: %s", result.stderr)
        raise RuntimeError(f"Pandoc conversion failed:\n{result.stderr}")

    latex = result.stdout

    if annotate:
        latex = _annotate_safe_zones(latex)

    return latex
