"""Deterministic LaTeX linter — fast regex-based checks and auto-fixes.

Runs per-section after LLM polish, before file assembly.  No LLM calls.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Heading hierarchy fixer
# ---------------------------------------------------------------------------

_SUBSECTION_STAR_RE = re.compile(r"^(\\subsection)\*(\{)", re.MULTILINE)
_SUBSECTION_RE = re.compile(r"^(\\subsection)(\{)", re.MULTILINE)
_SECTION_RE = re.compile(r"^\\section[\*{]", re.MULTILINE)


def fix_heading_hierarchy(latex: str) -> str:
    r"""Promote first ``\subsection`` to ``\section`` if no ``\section`` exists.

    If the first heading command in the section file is ``\subsection{…}`` or
    ``\subsection*{…}``, it is promoted to ``\section{…}`` / ``\section*{…}``.
    Deeper headings (``\subsubsection``) are left unchanged.
    """
    if _SECTION_RE.search(latex):
        return latex  # already has a \section — nothing to do

    # Promote starred variant first
    promoted, n = _SUBSECTION_STAR_RE.subn(r"\\section*\2", latex, count=1)
    if n:
        return promoted

    promoted, n = _SUBSECTION_RE.subn(r"\\section\2", latex, count=1)
    if n:
        return promoted

    return latex


# ---------------------------------------------------------------------------
# Lint checks
# ---------------------------------------------------------------------------

_HLINE_RE = re.compile(r"\\hline")
_TOPRULE_RE = re.compile(r"\\toprule|\\midrule|\\bottomrule")
_TABULARX_RE = re.compile(r"\\begin\{tabularx\}")
_TABULAR_RE = re.compile(r"\\begin\{tabular\}")
_OPEN_BRACE_RE = re.compile(r"(?<!\\)\{")
_CLOSE_BRACE_RE = re.compile(r"(?<!\\)\}")


def lint_section_latex(section_id: str, latex: str) -> list[str]:
    """Return a list of human-readable issues found in *latex*.

    Checks performed:
    1. First heading should be ``\\section``, not ``\\subsection``
    2. ``\\hline`` used instead of booktabs rules
    3. Unbalanced braces
    4. ``tabularx`` without full-width spec
    """
    issues: list[str] = []

    # 1. Heading hierarchy
    if not _SECTION_RE.search(latex) and (
        _SUBSECTION_RE.search(latex) or _SUBSECTION_STAR_RE.search(latex)
    ):
        issues.append(
            f"{section_id}: first heading is \\subsection — should be \\section"
        )

    # 2. hline instead of booktabs
    if _HLINE_RE.search(latex) and not _TOPRULE_RE.search(latex):
        issues.append(
            f"{section_id}: uses \\hline without booktabs — prefer \\toprule/\\midrule/\\bottomrule"
        )

    # 3. Unbalanced braces (rough check — ignores verbatim/comments)
    opens = len(_OPEN_BRACE_RE.findall(latex))
    closes = len(_CLOSE_BRACE_RE.findall(latex))
    if opens != closes:
        issues.append(
            f"{section_id}: unbalanced braces (opens={opens}, closes={closes})"
        )

    # 4. tabularx without \textwidth
    for m in _TABULARX_RE.finditer(latex):
        # Expect \begin{tabularx}{\textwidth} or similar within 30 chars
        snippet = latex[m.end():m.end() + 40]
        if "\\textwidth" not in snippet and "\\linewidth" not in snippet:
            issues.append(
                f"{section_id}: tabularx without \\textwidth — table may overflow"
            )
            break  # one warning is enough

    return issues


# ---------------------------------------------------------------------------
# hline -> booktabs replacement
# ---------------------------------------------------------------------------

def fix_hline_to_booktabs(latex: str) -> str:
    r"""Replace ``\hline`` with booktabs equivalents in tabular/tabularx.

    Strategy:
    - First ``\hline`` after ``\begin{tabular...}`` → ``\toprule``
    - Last ``\hline`` before ``\end{tabular...}`` → ``\bottomrule``
    - Remaining ``\hline`` → ``\midrule``
    """
    # Work on each table environment separately
    table_env_re = re.compile(
        r"(\\begin\{tabular[x]?\}.*?\n)(.*?)(\\end\{tabular[x]?\})",
        re.DOTALL,
    )

    def _replace_in_table(m: re.Match) -> str:
        begin = m.group(1)
        body = m.group(2)
        end = m.group(3)

        hlines = list(_HLINE_RE.finditer(body))
        if not hlines:
            return m.group(0)

        # Replace from last to first to preserve offsets
        parts = list(body)
        for i, hm in enumerate(reversed(hlines)):
            idx = len(hlines) - 1 - i
            start, stop = hm.start(), hm.end()
            if idx == 0:
                replacement = "\\toprule"
            elif idx == len(hlines) - 1:
                replacement = "\\bottomrule"
            else:
                replacement = "\\midrule"
            parts[start:stop] = list(replacement)

        return begin + "".join(parts) + end

    return table_env_re.sub(_replace_in_table, latex)


# ---------------------------------------------------------------------------
# Convenience: run all auto-fixes
# ---------------------------------------------------------------------------

def autofix_section(section_id: str, latex: str) -> tuple[str, list[str]]:
    """Run all deterministic auto-fixes on a section.

    Returns ``(fixed_latex, issues_found_before_fix)``.
    """
    issues = lint_section_latex(section_id, latex)
    fixed = fix_heading_hierarchy(latex)
    fixed = fix_hline_to_booktabs(fixed)
    return fixed, issues
