"""ChkTeX and lacheck integration for LaTeX linting.

Wraps ``chktex`` and parses output into structured warnings.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LintWarning:
    """A single lint warning from ChkTeX or lacheck."""
    file: str
    line: int | None
    column: int | None
    code: str
    message: str
    severity: str = "warning"


@dataclass
class LintResult:
    """Aggregated lint results."""
    warnings: list[LintWarning] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    @property
    def total(self) -> int:
        return self.error_count + self.warning_count + self.info_count


# ---------------------------------------------------------------------------
# Tool availability
# ---------------------------------------------------------------------------


def chktex_available() -> bool:
    return shutil.which("chktex") is not None


def lacheck_available() -> bool:
    return shutil.which("lacheck") is not None


# ---------------------------------------------------------------------------
# ChkTeX
# ---------------------------------------------------------------------------

# ChkTeX output format: file:line:col:code:severity:message
_CHKTEX_RE = re.compile(
    r"^(.+?):(\d+):(\d+):(\d+):(.*?):(.*?)$",
    re.MULTILINE,
)

# Alternative format: Warning N in file.tex line N: message
_CHKTEX_ALT_RE = re.compile(
    r"^Warning\s+(\d+)\s+in\s+(.+?)\s+line\s+(\d+):\s*(.*?)$",
    re.MULTILINE,
)


def run_chktex(
    tex_path: str | Path,
    *,
    quiet_flags: list[int] | None = None,
    timeout: int = 30,
) -> LintResult:
    """Run ChkTeX on a .tex file and return structured results.

    Parameters
    ----------
    tex_path : str | Path
        Path to the .tex file.
    quiet_flags : list[int], optional
        ChkTeX warning numbers to suppress (e.g., ``[1, 24]``).
    """
    path = Path(tex_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not chktex_available():
        logger.warning("chktex not found on PATH, skipping lint")
        return LintResult()

    cmd = ["chktex", "-v0", "-q"]
    if quiet_flags:
        for flag in quiet_flags:
            cmd.extend(["-n", str(flag)])
    cmd.append(str(path))

    logger.info("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error("chktex timed out after %ds", timeout)
        return LintResult()

    output = proc.stdout + proc.stderr
    result = LintResult()

    # Parse structured output
    for m in _CHKTEX_RE.finditer(output):
        sev = m.group(5).strip().lower()
        w = LintWarning(
            file=m.group(1),
            line=int(m.group(2)),
            column=int(m.group(3)),
            code=f"chktex:{m.group(4)}",
            message=m.group(6).strip(),
            severity=sev,
        )
        result.warnings.append(w)
        if sev == "error":
            result.error_count += 1
        else:
            result.warning_count += 1

    # Also parse alternative format
    for m in _CHKTEX_ALT_RE.finditer(output):
        w = LintWarning(
            file=m.group(2),
            line=int(m.group(3)),
            column=None,
            code=f"chktex:{m.group(1)}",
            message=m.group(4).strip(),
        )
        result.warnings.append(w)
        result.warning_count += 1

    return result


# ---------------------------------------------------------------------------
# lacheck
# ---------------------------------------------------------------------------

_LACHECK_RE = re.compile(
    r'^"(.+?)",\s*line\s+(\d+):\s*(.*?)$',
    re.MULTILINE,
)


def run_lacheck(tex_path: str | Path, *, timeout: int = 30) -> LintResult:
    """Run lacheck on a .tex file and return structured results."""
    path = Path(tex_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not lacheck_available():
        logger.warning("lacheck not found on PATH, skipping lint")
        return LintResult()

    cmd = ["lacheck", str(path)]

    logger.info("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.error("lacheck timed out after %ds", timeout)
        return LintResult()

    output = proc.stdout + proc.stderr
    result = LintResult()

    for m in _LACHECK_RE.finditer(output):
        w = LintWarning(
            file=m.group(1),
            line=int(m.group(2)),
            column=None,
            code="lacheck",
            message=m.group(3).strip(),
        )
        result.warnings.append(w)
        result.warning_count += 1

    return result


# ---------------------------------------------------------------------------
# Combined lint
# ---------------------------------------------------------------------------


def run_lint(tex_path: str | Path) -> LintResult:
    """Run all available linters and combine results."""
    combined = LintResult()

    if chktex_available():
        chk = run_chktex(tex_path)
        combined.warnings.extend(chk.warnings)
        combined.error_count += chk.error_count
        combined.warning_count += chk.warning_count

    if lacheck_available():
        la = run_lacheck(tex_path)
        combined.warnings.extend(la.warnings)
        combined.error_count += la.error_count
        combined.warning_count += la.warning_count

    return combined
