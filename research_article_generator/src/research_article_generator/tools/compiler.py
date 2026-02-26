"""LaTeX compilation with log parsing.

Prefers ``latexmk -pdf -interaction=nonstopmode`` but falls back to calling
the engine directly (``pdflatex`` / ``xelatex`` / ``lualatex``) when latexmk
is unavailable or broken (e.g. MiKTeX latexmk without Perl).

Parses ``.log`` for errors/warnings **with line numbers** and extracts
±5 line context windows from the source ``.tex`` file.
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


def _find_latexmk() -> str | None:
    """Find the latexmk executable, checking both Unix and Windows (.exe) names."""
    path = shutil.which("latexmk")
    if path:
        return path
    # WSL interop: Windows .exe may be on PATH but shutil.which misses it
    path = shutil.which("latexmk.exe")
    return path


def _find_engine(engine: str) -> str | None:
    """Find the LaTeX engine executable (pdflatex, xelatex, lualatex)."""
    path = shutil.which(engine)
    if path:
        return path
    path = shutil.which(f"{engine}.exe")
    return path


def latexmk_available() -> bool:
    """Check if latexmk is on PATH."""
    return _find_latexmk() is not None


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

# Pattern matching file-open events in LaTeX logs.
# TeX Live uses (./sections/foo.tex; MiKTeX omits the ./ prefix.
_FILE_OPEN_RE = re.compile(r"\((?:\./)?([^\s()]+\.tex)\b")


def _is_absolute_path(path: str) -> bool:
    """Return True for absolute/system paths (e.g. C:\\... or /usr/...)."""
    if len(path) >= 3 and path[1] == ":" and path[2] in ("/", "\\"):
        return True  # Windows drive letter, e.g. C:\...
    if path.startswith("/"):
        return True  # Unix absolute
    return False


def _find_current_file(log_text: str, error_pos: int) -> str:
    """Determine which .tex file is active at *error_pos* in the log.

    LaTeX logs track files via parenthesis nesting: ``(./path.tex ...)``.
    We scan from the start up to *error_pos*, maintaining a filename stack.
    Returns the innermost active file, or ``"main.tex"`` if the stack is
    empty or only the root file is open.

    Handles both TeX Live (``(./path.tex``) and MiKTeX (``(path.tex``)
    log formats.  Absolute/system paths are ignored.
    """
    stack: list[str] = []
    i = 0
    text = log_text[:error_pos]

    while i < len(text):
        ch = text[i]
        if ch == "(":
            # Check if this opens a .tex file
            m = _FILE_OPEN_RE.match(text, i)
            if m:
                fname = m.group(1)
                # Skip absolute/system paths — not project files
                if _is_absolute_path(fname):
                    stack.append("")
                    i = m.end()
                    continue
                # Normalise: strip leading "./"
                fname = fname.lstrip("./")
                stack.append(fname)
                i = m.end()
                continue
            # Non-file open paren — push sentinel so ')' tracking stays balanced
            stack.append("")
            i += 1
        elif ch == ")":
            if stack:
                stack.pop()
            i += 1
        else:
            i += 1

    # Walk stack from top to find the innermost real .tex file
    for name in reversed(stack):
        if name:
            return name
    return "main.tex"


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

        # Determine which file the error belongs to
        err_file = _find_current_file(log_text, em.start())

        # Only extract context from tex_content when the error is in main.tex
        # (for section files, tex_content is the main.tex skeleton with \input{}
        # lines, so line numbers won't match — context is re-extracted later)
        if line_num and tex_content and err_file == "main.tex":
            context = _extract_context(tex_content, line_num)

        errors.append(CompilationWarning(
            file=err_file,
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
                file=_find_current_file(log_text, wm.start()),
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


def _build_result(
    proc: subprocess.CompletedProcess,
    out: Path,
    main_file: str,
    label: str,
) -> CompilationResult:
    """Build a CompilationResult from a completed subprocess and log file."""
    tex_path = out / main_file
    tex_content = tex_path.read_text(encoding="utf-8", errors="replace")

    log_path = out / main_file.replace(".tex", ".log")
    errors, warnings, unresolved = parse_log(log_path, tex_content)

    # Re-extract context for errors in section files (parse_log skips these
    # because tex_content is the main.tex skeleton with wrong line numbers)
    for err in errors:
        if "sections/" in (err.file or "") and err.line:
            section_path = out / err.file
            if section_path.exists():
                section_content = section_path.read_text(encoding="utf-8", errors="replace")
                err.context = _extract_context(section_content, err.line)

    pdf_name = main_file.replace(".tex", ".pdf")
    pdf_path = out / pdf_name
    # Accept PDF even with non-zero returncode: the engine may return
    # non-zero for warnings or recoverable errors while still producing a
    # usable PDF.  The parsed errors list is still available for the fix loop.
    success = pdf_path.exists()

    logger.info(
        "%s finished: returncode=%d, pdf_exists=%s, success=%s, errors=%d, cwd=%s",
        label, proc.returncode, pdf_path.exists(), success, len(errors), out,
    )
    if not success:
        if proc.stdout:
            logger.info("%s stdout (last 1000 chars):\n%s", label, proc.stdout[-1000:])
        if proc.stderr:
            logger.info("%s stderr (last 1000 chars):\n%s", label, proc.stderr[-1000:])

    page_count = None
    if success:
        from .page_counter import count_pages
        page_count = count_pages(str(pdf_path))

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


def _run_direct_engine(
    out: Path,
    engine: str,
    main_file: str,
    timeout: int,
) -> CompilationResult:
    """Compile by calling the engine directly (pdflatex/xelatex/lualatex).

    Runs the standard recipe: engine → bibtex → engine → engine.
    This is the fallback when latexmk is unavailable or broken.
    """
    engine_cmd = _find_engine(engine)
    if not engine_cmd:
        return CompilationResult(
            success=False,
            errors=[CompilationWarning(
                message=f"{engine} not found on PATH",
                severity=Severity.ERROR,
            )],
        )

    bibtex_cmd = shutil.which("bibtex") or shutil.which("bibtex.exe")
    base = main_file.replace(".tex", "")
    engine_args = [engine_cmd, "-interaction=nonstopmode", main_file]
    per_pass_timeout = max(timeout // 3, 30)

    # Remove stale PDF
    pdf_path = out / f"{base}.pdf"
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except PermissionError:
            logger.warning(
                "Cannot delete stale PDF %s (file locked by another process). "
                "Close any PDF viewer and retry.",
                pdf_path,
            )

    proc = None  # will hold the last engine run
    for pass_num, cmd in enumerate(
        [
            engine_args,                                        # pass 1
            [bibtex_cmd, base] if bibtex_cmd else None,         # bibtex
            engine_args,                                        # pass 2
            engine_args,                                        # pass 3 (resolve refs)
        ],
        1,
    ):
        if cmd is None:
            continue
        logger.info("Direct compile pass %d: %s (in %s)", pass_num, " ".join(cmd), out)
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(out),
                capture_output=True,
                text=True,
                timeout=per_pass_timeout,
            )
        except subprocess.TimeoutExpired:
            return CompilationResult(
                success=False,
                errors=[CompilationWarning(
                    message=f"Compilation timed out after {per_pass_timeout}s (pass {pass_num})",
                    severity=Severity.ERROR,
                )],
            )

    assert proc is not None  # at least one pass always runs
    return _build_result(proc, out, main_file, engine)


# Patterns in stderr that indicate latexmk itself is broken (not a LaTeX error)
_LATEXMK_ENV_ERRORS = (
    "script engine",      # MiKTeX: could not find the script engine 'perl'
    "perl",               # generic Perl missing
    "not succeed",        # MiKTeX: latexmk.exe did not succeed
)


def run_latexmk(
    output_dir: str | Path,
    engine: str = "pdflatex",
    *,
    main_file: str = "main.tex",
    timeout: int = 120,
) -> CompilationResult:
    """Run latexmk in the output directory and return structured results.

    Falls back to calling the engine directly when latexmk is unavailable
    or broken (e.g. MiKTeX without Perl).

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

    latexmk_cmd = _find_latexmk()
    if not latexmk_cmd:
        logger.info("latexmk not found, falling back to direct %s", engine)
        return _run_direct_engine(out, engine, main_file, timeout)

    engine_flag = {
        "pdflatex": "-pdf",
        "xelatex": "-xelatex",
        "lualatex": "-lualatex",
    }.get(engine, "-pdf")

    cmd = [
        latexmk_cmd,
        engine_flag,
        "-interaction=nonstopmode",
        main_file,
    ]

    # Remove stale PDF so pdf_path.exists() reliably indicates THIS run produced it
    pdf_name = main_file.replace(".tex", ".pdf")
    pdf_path = out / pdf_name
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except PermissionError:
            logger.warning(
                "Cannot delete stale PDF %s (file locked by another process). "
                "Close any PDF viewer and retry.",
                pdf_path,
            )

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

    # Detect latexmk environment failures (e.g. Perl not installed on MiKTeX)
    # and fall back to calling the engine directly.
    stderr_lower = (proc.stderr or "").lower()
    if proc.returncode != 0 and not pdf_path.exists():
        if any(pat in stderr_lower for pat in _LATEXMK_ENV_ERRORS):
            logger.warning(
                "latexmk failed due to environment issue, falling back to direct %s: %s",
                engine, proc.stderr.strip()[:200],
            )
            return _run_direct_engine(out, engine, main_file, timeout)

    return _build_result(proc, out, main_file, "latexmk")


# ---------------------------------------------------------------------------
# Error context extraction (for compile-fix loop)
# ---------------------------------------------------------------------------


def extract_error_context(
    result: CompilationResult,
    tex_content: str,
    *,
    section_file: str = "",
) -> str:
    """Format compilation errors with source context for LLM fix attempts.

    Parameters
    ----------
    result : CompilationResult
        The compilation result containing errors.
    tex_content : str
        The tex source to use for context extraction (typically the section content).
    section_file : str
        When set (e.g. ``"sections/02_methods.tex"``), only errors from that file
        are included and context is re-extracted from *tex_content*.

    Returns a human-readable string suitable as an LLM prompt.
    """
    errors = result.errors
    if section_file:
        errors = [e for e in errors if (e.file or "") == section_file or not e.file]

    if not errors and not result.unresolved_refs:
        return "No errors found."

    parts: list[str] = []

    if not errors:
        parts.append("No LaTeX errors found.")

    for i, err in enumerate(errors, 1):
        parts.append(f"Error {i}: {err.message}")
        if err.line:
            parts.append(f"  Line: {err.line}")

        # When section_file matches, prefer re-extracting from provided tex_content
        if section_file and err.file == section_file and err.line and tex_content:
            parts.append(f"  Context:\n{_extract_context(tex_content, err.line)}")
        elif err.context:
            parts.append(f"  Context:\n{err.context}")
        elif err.line and tex_content:
            parts.append(f"  Context:\n{_extract_context(tex_content, err.line)}")
        parts.append("")

    if result.unresolved_refs:
        parts.append(f"Unresolved references: {', '.join(result.unresolved_refs)}")

    return "\n".join(parts)
