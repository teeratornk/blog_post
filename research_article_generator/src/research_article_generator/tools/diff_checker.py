"""Faithfulness checking: deterministic layers 1-4.

Layer 1: Structural check — section headings, figure/table/equation counts.
Layer 2: Math exact-match — extract all math environments, verify identical.
Layer 3: Citation key check — all \\cite{} keys match source references.
Layer 4: Plain-text diff — convert both source and output to plain text via
         pandoc, then sentence-level diff.
"""

from __future__ import annotations

import difflib
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..models import FaithfulnessReport, FaithfulnessViolation, Severity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def to_plain_text(content: str, fmt: str = "markdown") -> str:
    """Convert content to plain text using pandoc.

    Parameters
    ----------
    content : str
        Content string (markdown or LaTeX).
    fmt : str
        Input format: ``"markdown"`` or ``"latex"``.

    Falls back to simple regex-based stripping if pandoc is unavailable.
    """
    if shutil.which("pandoc"):
        try:
            result = subprocess.run(
                ["pandoc", "-f", fmt, "-t", "plain", "--wrap=none"],
                input=content,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback: simple stripping
    text = content
    if fmt == "latex":
        # Remove LaTeX commands
        text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
        text = re.sub(r"\\[a-zA-Z]+\[[^\]]*\]\{([^}]*)\}", r"\1", text)
        text = re.sub(r"\\[a-zA-Z]+", "", text)
        text = re.sub(r"[{}]", "", text)
    elif fmt == "markdown":
        # Remove markdown formatting
        text = re.sub(r"#{1,6}\s+", "", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    return text


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences (simple heuristic)."""
    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in sentences if s.strip()]


# ---------------------------------------------------------------------------
# Layer 1: Structural check
# ---------------------------------------------------------------------------

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_TEX_HEADING_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph)\{([^}]+)\}",
)
_MD_FIGURE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_TEX_FIGURE_RE = re.compile(r"\\includegraphics")
_MD_TABLE_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
_TEX_TABLE_RE = re.compile(r"\\begin\{tabular")
_MD_EQUATION_RE = re.compile(r"\$\$[^$]+\$\$", re.DOTALL)
_TEX_EQUATION_RE = re.compile(r"\\begin\{(equation|align|gather|multline)\*?\}")


def check_structure(
    source_md: str, output_latex: str,
) -> list[FaithfulnessViolation]:
    """Layer 1: Compare structural elements between source and output."""
    violations: list[FaithfulnessViolation] = []

    # Section headings
    md_headings = [m.group(2).strip() for m in _MD_HEADING_RE.finditer(source_md)]
    tex_headings = [m.group(2).strip() for m in _TEX_HEADING_RE.finditer(output_latex)]

    if len(md_headings) != len(tex_headings):
        violations.append(FaithfulnessViolation(
            severity=Severity.WARNING,
            source_text=f"Source has {len(md_headings)} headings",
            output_text=f"Output has {len(tex_headings)} headings",
            issue="Section heading count mismatch",
            recommendation="Check if any sections were added or removed",
        ))

    # Figure count
    md_figs = len(_MD_FIGURE_RE.findall(source_md))
    tex_figs = len(_TEX_FIGURE_RE.findall(output_latex))
    if md_figs != tex_figs:
        violations.append(FaithfulnessViolation(
            severity=Severity.WARNING,
            source_text=f"Source has {md_figs} figures",
            output_text=f"Output has {tex_figs} figures",
            issue="Figure count mismatch",
            recommendation="Verify all figures are included",
        ))

    # Equation count (approximate)
    md_eqs = len(_MD_EQUATION_RE.findall(source_md))
    tex_eqs = len(_TEX_EQUATION_RE.findall(output_latex))
    if md_eqs > 0 and tex_eqs == 0:
        violations.append(FaithfulnessViolation(
            severity=Severity.ERROR,
            source_text=f"Source has {md_eqs} display equations",
            output_text="Output has 0 equation environments",
            issue="Equations appear to be missing",
            recommendation="Check equation conversion",
        ))

    return violations


# ---------------------------------------------------------------------------
# Layer 2: Math exact-match
# ---------------------------------------------------------------------------

_MATH_ENV_RE = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}(.*?)\\end\{\1\*?\}",
    re.DOTALL,
)
_INLINE_MATH_RE = re.compile(r"(?<![\\])\$([^$]+)\$")


def extract_math(latex: str) -> list[str]:
    """Extract all math content from LaTeX (display + inline)."""
    math: list[str] = []
    for m in _MATH_ENV_RE.finditer(latex):
        math.append(m.group(2).strip())
    for m in _INLINE_MATH_RE.finditer(latex):
        math.append(m.group(1).strip())
    return math


def check_math_preservation(
    source_latex: str, output_latex: str,
) -> list[FaithfulnessViolation]:
    """Layer 2: Verify math environments are preserved exactly."""
    source_math = extract_math(source_latex)
    output_math = extract_math(output_latex)
    violations: list[FaithfulnessViolation] = []

    # Check that every source math expression appears in output
    for i, sm in enumerate(source_math):
        normalized_sm = re.sub(r"\s+", " ", sm)
        found = False
        for om in output_math:
            normalized_om = re.sub(r"\s+", " ", om)
            if normalized_sm == normalized_om:
                found = True
                break
        if not found:
            violations.append(FaithfulnessViolation(
                severity=Severity.CRITICAL,
                source_text=sm[:200],
                output_text="(not found or modified)",
                issue=f"Math expression {i + 1} was altered or removed",
                recommendation="Restore the original math expression exactly",
            ))

    return violations


# ---------------------------------------------------------------------------
# Layer 3: Citation key check
# ---------------------------------------------------------------------------

_CITE_RE = re.compile(r"\\cite[tp]?\{([^}]+)\}")


def extract_citation_keys(latex: str) -> set[str]:
    """Extract all citation keys from LaTeX content."""
    keys: set[str] = set()
    for m in _CITE_RE.finditer(latex):
        for key in m.group(1).split(","):
            keys.add(key.strip())
    return keys


def check_citation_keys(
    source_latex: str, output_latex: str,
) -> list[FaithfulnessViolation]:
    """Layer 3: Verify citation keys match between source and output."""
    source_keys = extract_citation_keys(source_latex)
    output_keys = extract_citation_keys(output_latex)
    violations: list[FaithfulnessViolation] = []

    missing = source_keys - output_keys
    added = output_keys - source_keys

    for key in missing:
        violations.append(FaithfulnessViolation(
            severity=Severity.ERROR,
            source_text=f"\\cite{{{key}}}",
            output_text="(missing)",
            issue=f"Citation key '{key}' removed from output",
            recommendation="Restore the citation",
        ))

    for key in added:
        violations.append(FaithfulnessViolation(
            severity=Severity.WARNING,
            source_text="(not in source)",
            output_text=f"\\cite{{{key}}}",
            issue=f"Citation key '{key}' added but not in source",
            recommendation="Verify this citation is correct",
        ))

    return violations


# ---------------------------------------------------------------------------
# Layer 4: Plain-text sentence diff
# ---------------------------------------------------------------------------


def compare_plain_text(
    source_md: str,
    output_latex: str,
    *,
    similarity_threshold: float = 0.8,
) -> list[FaithfulnessViolation]:
    """Layer 4: Convert both to plain text and compare at sentence level.

    Uses difflib.SequenceMatcher to find significantly different sentences.
    """
    source_plain = to_plain_text(source_md, "markdown")
    output_plain = to_plain_text(output_latex, "latex")

    source_sentences = _split_sentences(source_plain)
    output_sentences = _split_sentences(output_plain)

    violations: list[FaithfulnessViolation] = []

    # Use SequenceMatcher on sentence lists
    matcher = difflib.SequenceMatcher(None, source_sentences, output_sentences)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        if tag == "replace":
            for idx in range(i1, i2):
                src = source_sentences[idx] if idx < len(source_sentences) else ""
                out_idx = j1 + (idx - i1)
                out = output_sentences[out_idx] if out_idx < len(output_sentences) else ""

                ratio = difflib.SequenceMatcher(None, src, out).ratio()
                if ratio < similarity_threshold:
                    violations.append(FaithfulnessViolation(
                        severity=Severity.WARNING,
                        source_text=src[:200],
                        output_text=out[:200],
                        issue=f"Sentence significantly changed (similarity: {ratio:.0%})",
                        recommendation="Verify this change preserves original meaning",
                    ))

        elif tag == "delete":
            for idx in range(i1, i2):
                violations.append(FaithfulnessViolation(
                    severity=Severity.WARNING,
                    source_text=source_sentences[idx][:200],
                    output_text="(deleted)",
                    issue="Sentence removed from output",
                    recommendation="Verify this deletion is intentional",
                ))

        elif tag == "insert":
            for idx in range(j1, j2):
                violations.append(FaithfulnessViolation(
                    severity=Severity.INFO,
                    source_text="(not in source)",
                    output_text=output_sentences[idx][:200],
                    issue="New sentence added in output",
                    recommendation="Verify this addition is appropriate",
                ))

    return violations


# ---------------------------------------------------------------------------
# Full faithfulness check (layers 1-4)
# ---------------------------------------------------------------------------


def run_faithfulness_check(
    source_md: str,
    source_latex_from_pandoc: str,
    output_latex: str,
) -> FaithfulnessReport:
    """Run all deterministic faithfulness checks (layers 1-4).

    Parameters
    ----------
    source_md : str
        Original markdown source.
    source_latex_from_pandoc : str
        Pandoc-converted LaTeX (before LLM polishing) — used for math/cite comparison.
    output_latex : str
        Final LLM-polished LaTeX output.
    """
    all_violations: list[FaithfulnessViolation] = []

    # Layer 1: Structure
    struct_violations = check_structure(source_md, output_latex)
    all_violations.extend(struct_violations)
    section_match = not any(v.issue.startswith("Section heading") for v in struct_violations)

    # Layer 2: Math preservation (compare pandoc output to final output)
    math_violations = check_math_preservation(source_latex_from_pandoc, output_latex)
    all_violations.extend(math_violations)
    math_match = len(math_violations) == 0

    # Layer 3: Citation keys (compare pandoc output to final output)
    cite_violations = check_citation_keys(source_latex_from_pandoc, output_latex)
    all_violations.extend(cite_violations)
    citation_match = not any(v.severity in (Severity.ERROR, Severity.CRITICAL) for v in cite_violations)

    # Layer 4: Plain text diff
    text_violations = compare_plain_text(source_md, output_latex)
    all_violations.extend(text_violations)

    # Figure match from layer 1
    figure_match = not any("Figure count" in v.issue for v in struct_violations)

    # Overall pass: no CRITICAL or ERROR violations
    passed = not any(
        v.severity in (Severity.CRITICAL, Severity.ERROR)
        for v in all_violations
    )

    return FaithfulnessReport(
        passed=passed,
        violations=all_violations,
        section_match=section_match,
        math_match=math_match,
        citation_match=citation_match,
        figure_match=figure_match,
    )
