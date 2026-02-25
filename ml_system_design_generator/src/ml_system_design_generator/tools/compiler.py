"""LaTeX compilation with log parsing.

Reuses the same patterns as research_article_generator/tools/compiler.py.
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
    """Find the latexmk executable."""
    path = shutil.which("latexmk")
    if path:
        return path
    path = shutil.which("latexmk.exe")
    return path


def _find_engine(engine: str) -> str | None:
    """Find the LaTeX engine executable."""
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

_ERROR_RE = re.compile(r"^!\s*(.*)", re.MULTILINE)
_LINE_RE = re.compile(r"^l\.(\d+)\s*(.*)", re.MULTILINE)
_WARNING_RE = re.compile(
    r"(?:LaTeX|Package|Class)\s+(?:\w+\s+)?Warning[:\s]*(.*?)(?:\n(?!\s)|$)",
    re.MULTILINE | re.DOTALL,
)
_UNDEF_REF_RE = re.compile(r"LaTeX Warning: Reference `([^']+)' on page", re.MULTILINE)
_UNDEF_CIT_RE = re.compile(r"LaTeX Warning: Citation `([^']+)' on page", re.MULTILINE)
_FILE_OPEN_RE = re.compile(r"\((?:\./)?([^\s()]+\.tex)\b")


def _is_absolute_path(path: str) -> bool:
    if len(path) >= 3 and path[1] == ":" and path[2] in ("/", "\\"):
        return True
    if path.startswith("/"):
        return True
    return False


def _find_current_file(log_text: str, error_pos: int) -> str:
    """Determine which .tex file is active at error_pos in the log."""
    stack: list[str] = []
    i = 0
    text = log_text[:error_pos]

    while i < len(text):
        ch = text[i]
        if ch == "(":
            m = _FILE_OPEN_RE.match(text, i)
            if m:
                fname = m.group(1)
                if _is_absolute_path(fname):
                    stack.append("")
                    i = m.end()
                    continue
                fname = fname.lstrip("./")
                stack.append(fname)
                i = m.end()
                continue
            stack.append("")
            i += 1
        elif ch == ")":
            if stack:
                stack.pop()
            i += 1
        else:
            i += 1

    for name in reversed(stack):
        if name:
            return name
    return "main.tex"


def _extract_context(tex_content: str, line_num: int, window: int = 5) -> str:
    """Extract +-window lines around a line number."""
    lines = tex_content.split("\n")
    start = max(0, line_num - 1 - window)
    end = min(len(lines), line_num + window)
    context_lines: list[str] = []
    for i in range(start, end):
        marker = ">>>" if i == line_num - 1 else "   "
        context_lines.append(f"{marker} {i + 1:4d} | {lines[i]}")
    return "\n".join(context_lines)


def parse_log(
    log_path: str | Path,
    tex_content: str = "",
) -> tuple[list[CompilationWarning], list[CompilationWarning], list[str]]:
    """Parse a LaTeX .log file for errors, warnings, and unresolved refs."""
    log = Path(log_path)
    if not log.exists():
        return [], [], []

    log_text = log.read_text(encoding="utf-8", errors="replace")
    errors: list[CompilationWarning] = []
    warnings: list[CompilationWarning] = []
    unresolved: list[str] = []

    error_matches = list(_ERROR_RE.finditer(log_text))
    for em in error_matches:
        error_msg = em.group(1).strip()
        line_num = None
        context = ""

        after_error = log_text[em.end():em.end() + 500]
        line_match = _LINE_RE.search(after_error)
        if line_match:
            line_num = int(line_match.group(1))

        err_file = _find_current_file(log_text, em.start())

        if line_num and tex_content and err_file == "main.tex":
            context = _extract_context(tex_content, line_num)

        errors.append(CompilationWarning(
            file=err_file,
            line=line_num,
            message=error_msg,
            severity=Severity.ERROR,
            context=context,
        ))

    for wm in _WARNING_RE.finditer(log_text):
        msg = wm.group(1).strip().replace("\n", " ")
        if msg:
            warnings.append(CompilationWarning(
                file=_find_current_file(log_text, wm.start()),
                message=msg,
                severity=Severity.WARNING,
            ))

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
    """Build a CompilationResult from a completed subprocess."""
    tex_path = out / main_file
    tex_content = tex_path.read_text(encoding="utf-8", errors="replace")

    log_path = out / main_file.replace(".tex", ".log")
    errors, warnings, unresolved = parse_log(log_path, tex_content)

    for err in errors:
        if "sections/" in (err.file or "") and err.line:
            section_path = out / err.file
            if section_path.exists():
                section_content = section_path.read_text(encoding="utf-8", errors="replace")
                err.context = _extract_context(section_content, err.line)

    pdf_name = main_file.replace(".tex", ".pdf")
    pdf_path = out / pdf_name
    success = pdf_path.exists()

    logger.info(
        "%s finished: returncode=%d, pdf_exists=%s, errors=%d, cwd=%s",
        label, proc.returncode, pdf_path.exists(), len(errors), out,
    )

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
    """Compile by calling the engine directly (fallback)."""
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

    pdf_path = out / f"{base}.pdf"
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except PermissionError:
            logger.warning("Cannot delete stale PDF %s", pdf_path)

    proc = None
    for pass_num, cmd in enumerate(
        [
            engine_args,
            [bibtex_cmd, base] if bibtex_cmd else None,
            engine_args,
            engine_args,
        ],
        1,
    ):
        if cmd is None:
            continue
        logger.info("Direct compile pass %d: %s (in %s)", pass_num, " ".join(cmd), out)
        try:
            proc = subprocess.run(
                cmd, cwd=str(out), capture_output=True, text=True, timeout=per_pass_timeout,
            )
        except subprocess.TimeoutExpired:
            return CompilationResult(
                success=False,
                errors=[CompilationWarning(
                    message=f"Compilation timed out after {per_pass_timeout}s (pass {pass_num})",
                    severity=Severity.ERROR,
                )],
            )

    assert proc is not None
    return _build_result(proc, out, main_file, engine)


_LATEXMK_ENV_ERRORS = ("script engine", "perl", "not succeed")


def run_latexmk(
    output_dir: str | Path,
    engine: str = "pdflatex",
    *,
    main_file: str = "main.tex",
    timeout: int = 120,
) -> CompilationResult:
    """Run latexmk in the output directory and return structured results."""
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

    cmd = [latexmk_cmd, engine_flag, "-interaction=nonstopmode", main_file]

    pdf_name = main_file.replace(".tex", ".pdf")
    pdf_path = out / pdf_name
    if pdf_path.exists():
        try:
            pdf_path.unlink()
        except PermissionError:
            logger.warning("Cannot delete stale PDF %s", pdf_path)

    logger.info("Running: %s (in %s)", " ".join(cmd), out)

    try:
        proc = subprocess.run(
            cmd, cwd=str(out), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CompilationResult(
            success=False,
            errors=[CompilationWarning(message=f"Compilation timed out after {timeout}s", severity=Severity.ERROR)],
        )

    stderr_lower = (proc.stderr or "").lower()
    if proc.returncode != 0 and not pdf_path.exists():
        if any(pat in stderr_lower for pat in _LATEXMK_ENV_ERRORS):
            logger.warning("latexmk failed, falling back to direct %s", engine)
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
    """Format compilation errors with source context for LLM fix attempts."""
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
