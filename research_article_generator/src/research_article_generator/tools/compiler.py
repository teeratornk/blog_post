"""LaTeX compilation via latexmk with log parsing.

Wraps ``latexmk -pdf -interaction=nonstopmode``.  Parses ``.log`` for
errors/warnings **with line numbers** and extracts ±5 line context windows
from the source ``.tex`` file.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from ..models import CompilationResult, CompilationWarning, Severity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool availability
# ---------------------------------------------------------------------------


def latexmk_available() -> bool:
    """Check if latexmk is on PATH."""
    return shutil.which("latexmk") is not None


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

# Patterns for LaTeX log errors/warnings
_ERROR_RE = re.compile(r"^!\s*(.*)", re.MULTILINE)
_LINE_RE = re.compile(r"^l\.(\d+)\s*(.*)", re.MULTILINE)
_WARNING_RE = re.compile(
    r"(?:LaTeX|Package|Class)\s+(?:\w+\s+)?Warning[:\s]*(.*?)(?:\n(?!\s)|$)",
    re.MULTILINE | re.DOTALL,
)
_UNDEF_REF_RE = re.compile(
    r"LaTeX Warning: Reference `([^']+)' on page",
    re.MULTILINE,
)
_UNDEF_CIT_RE = re.compile(
    r"LaTeX Warning: Citation `([^']+)' on page",
    re.MULTILINE,
)


def _extract_context(tex_content: str, line_num: int, window: int = 5) -> str:
    """Extract ±window lines around a line number from .tex source."""
    lines = tex_content.split("\n")
    start = max(0, line_num - 1 - window)
    end = min(len(lines), line_num + window)
    context_lines: list[str] = []
    for i in range(start, end):
        marker = ">>>" if i == line_num - 1 else "   "
        context_lines.append(f"{marker} {i + 1:4d} | {lines[i]}")
    return "\n".join(context_lines)


def parse_log(log_path: str | Path, tex_content: str = "") -> tuple[list[CompilationWarning], list[CompilationWarning], list[str]]:
    """Parse a LaTeX .log file for errors, warnings, and unresolved refs.

    Returns (errors, warnings, unresolved_refs).
    """
    log = Path(log_path)
    if not log.exists():
        return [], [], []

    log_text = log.read_text(encoding="utf-8", errors="replace")
    errors: list[CompilationWarning] = []
    warnings: list[CompilationWarning] = []
    unresolved: list[str] = []

    # Parse errors with line numbers
    # LaTeX errors look like:
    #   ! Error message
    #   l.42 some code
    error_matches = list(_ERROR_RE.finditer(log_text))
    for em in error_matches:
        error_msg = em.group(1).strip()
        line_num = None
        context = ""

        # Look for l.NNN after the error
        after_error = log_text[em.end():em.end() + 500]
        line_match = _LINE_RE.search(after_error)
        if line_match:
            line_num = int(line_match.group(1))
            if tex_content:
                context = _extract_context(tex_content, line_num)

        errors.append(CompilationWarning(
            file="main.tex",
            line=line_num,
            message=error_msg,
            severity=Severity.ERROR,
            context=context,
        ))

    # Parse warnings
    for wm in _WARNING_RE.finditer(log_text):
        msg = wm.group(1).strip().replace("\n", " ")
        if msg:
            warnings.append(CompilationWarning(
                file="main.tex",
                message=msg,
                severity=Severity.WARNING,
            ))

    # Unresolved references
    for m in _UNDEF_REF_RE.finditer(log_text):
        unresolved.append(f"ref:{m.group(1)}")
    for m in _UNDEF_CIT_RE.finditer(log_text):
        unresolved.append(f"cite:{m.group(1)}")

    return errors, warnings, list(set(unresolved))


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def run_latexmk(
    output_dir: str | Path,
    engine: str = "pdflatex",
    *,
    main_file: str = "main.tex",
    timeout: int = 120,
) -> CompilationResult:
    """Run latexmk in the output directory and return structured results.

    Parameters
    ----------
    output_dir : str | Path
        Directory containing main.tex.
    engine : str
        One of ``pdflatex``, ``xelatex``, ``lualatex``.
    main_file : str
        Name of the main .tex file.
    timeout : int
        Timeout in seconds for the compilation.
    """
    out = Path(output_dir)
    tex_path = out / main_file
    if not tex_path.exists():
        return CompilationResult(
            success=False,
            errors=[CompilationWarning(message=f"{main_file} not found in {out}", severity=Severity.ERROR)],
        )

    if not latexmk_available():
        return CompilationResult(
            success=False,
            errors=[CompilationWarning(message="latexmk not found on PATH", severity=Severity.ERROR)],
        )

    engine_flag = {
        "pdflatex": "-pdf",
        "xelatex": "-xelatex",
        "lualatex": "-lualatex",
    }.get(engine, "-pdf")

    cmd = [
        "latexmk",
        engine_flag,
        "-interaction=nonstopmode",
        "-halt-on-error",
        main_file,
    ]

    logger.info("Running: %s (in %s)", " ".join(cmd), out)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(out),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CompilationResult(
            success=False,
            errors=[CompilationWarning(message=f"Compilation timed out after {timeout}s", severity=Severity.ERROR)],
        )

    # Read the tex source for context extraction
    tex_content = tex_path.read_text(encoding="utf-8", errors="replace")

    # Parse the log file
    log_path = out / main_file.replace(".tex", ".log")
    errors, warnings, unresolved = parse_log(log_path, tex_content)

    # Check for PDF output
    pdf_name = main_file.replace(".tex", ".pdf")
    pdf_path = out / pdf_name
    success = proc.returncode == 0 and pdf_path.exists()

    # Get page count if successful
    page_count = None
    if success:
        from .page_counter import count_pages
        page_count = count_pages(str(pdf_path))

    # Log excerpt
    log_excerpt = ""
    if not success and proc.stderr:
        log_excerpt = proc.stderr[-2000:]

    return CompilationResult(
        success=success,
        pdf_path=str(pdf_path) if success else None,
        errors=errors,
        warnings=warnings,
        page_count=page_count,
        unresolved_refs=unresolved,
        log_excerpt=log_excerpt,
    )


# ---------------------------------------------------------------------------
# Error context extraction (for compile-fix loop)
# ---------------------------------------------------------------------------


def extract_error_context(result: CompilationResult, tex_content: str) -> str:
    """Format compilation errors with source context for LLM fix attempts.

    Returns a human-readable string suitable as an LLM prompt.
    """
    if not result.errors:
        return "No errors found."

    parts: list[str] = []
    for i, err in enumerate(result.errors, 1):
        parts.append(f"Error {i}: {err.message}")
        if err.line:
            parts.append(f"  Line: {err.line}")
        if err.context:
            parts.append(f"  Context:\n{err.context}")
        elif err.line and tex_content:
            parts.append(f"  Context:\n{_extract_context(tex_content, err.line)}")
        parts.append("")

    if result.unresolved_refs:
        parts.append(f"Unresolved references: {', '.join(result.unresolved_refs)}")

    return "\n".join(parts)
