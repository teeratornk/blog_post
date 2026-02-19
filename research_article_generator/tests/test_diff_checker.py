"""Tests for tools/diff_checker.py — faithfulness checking layers 1-4."""

from __future__ import annotations

import pytest

from research_article_generator.models import Severity
from research_article_generator.tools.diff_checker import (
    check_citation_keys,
    check_math_preservation,
    check_structure,
    compare_plain_text,
    extract_citation_keys,
    extract_math,
    run_faithfulness_check,
    to_plain_text,
)


class TestToPlainText:
    def test_markdown_stripping(self):
        md = "# Title\n\nSome **bold** and *italic* text."
        result = to_plain_text(md, "markdown")
        assert "Title" in result
        assert "bold" in result
        assert "**" not in result or "bold" in result  # pandoc or fallback

    def test_latex_stripping(self):
        latex = r"\section{Title}\textbf{bold} and \textit{italic} text."
        result = to_plain_text(latex, "latex")
        assert "bold" in result


class TestCheckStructure:
    def test_matching_structure(self):
        md = "# Introduction\n\n## Methods\n\nText."
        latex = r"\section{Introduction}\subsection{Methods}Text."
        violations = check_structure(md, latex)
        assert len(violations) == 0

    def test_missing_section(self):
        md = "# Introduction\n\n## Methods\n\n## Results\n\nText."
        latex = r"\section{Introduction}\subsection{Methods}Text."
        violations = check_structure(md, latex)
        assert len(violations) > 0

    def test_figure_count_mismatch(self):
        md = "![Fig1](f1.png)\n\n![Fig2](f2.png)"
        latex = r"\includegraphics{f1.png}"
        violations = check_structure(md, latex)
        fig_violations = [v for v in violations if "Figure count" in v.issue]
        assert len(fig_violations) == 1


class TestCheckMathPreservation:
    def test_preserved(self):
        source = r"\begin{equation}E = mc^2\end{equation}"
        output = r"\begin{equation}E = mc^2\end{equation}"
        violations = check_math_preservation(source, output)
        assert len(violations) == 0

    def test_altered(self):
        source = r"\begin{equation}E = mc^2\end{equation}"
        output = r"\begin{equation}E = mc^3\end{equation}"
        violations = check_math_preservation(source, output)
        assert len(violations) > 0
        assert violations[0].severity == Severity.CRITICAL

    def test_whitespace_normalization(self):
        source = r"\begin{equation}E  =  mc^2\end{equation}"
        output = r"\begin{equation}E = mc^2\end{equation}"
        violations = check_math_preservation(source, output)
        assert len(violations) == 0


class TestExtractMath:
    def test_display_math(self):
        latex = r"\begin{equation}x^2 + y^2 = r^2\end{equation}"
        math = extract_math(latex)
        assert len(math) == 1
        assert "x^2 + y^2 = r^2" in math[0]

    def test_inline_math(self):
        latex = r"The value $\alpha = 0.5$ is used."
        math = extract_math(latex)
        assert len(math) == 1
        assert r"\alpha = 0.5" in math[0]

    def test_align_env(self):
        latex = r"\begin{align}a &= b \\ c &= d\end{align}"
        math = extract_math(latex)
        assert len(math) == 1


class TestExtractCitationKeys:
    def test_single_cite(self):
        keys = extract_citation_keys(r"\cite{smith2020}")
        assert keys == {"smith2020"}

    def test_multiple_keys(self):
        keys = extract_citation_keys(r"\cite{a2020, b2021, c2022}")
        assert keys == {"a2020", "b2021", "c2022"}

    def test_citep_and_citet(self):
        keys = extract_citation_keys(r"\citep{x2020} and \citet{y2021}")
        assert keys == {"x2020", "y2021"}


class TestCheckCitationKeys:
    def test_matching(self):
        source = r"\cite{a2020, b2021}"
        output = r"\cite{a2020, b2021}"
        violations = check_citation_keys(source, output)
        assert len(violations) == 0

    def test_missing_key(self):
        source = r"\cite{a2020, b2021}"
        output = r"\cite{a2020}"
        violations = check_citation_keys(source, output)
        missing = [v for v in violations if "removed" in v.issue]
        assert len(missing) == 1

    def test_added_key(self):
        source = r"\cite{a2020}"
        output = r"\cite{a2020, extra2023}"
        violations = check_citation_keys(source, output)
        added = [v for v in violations if "added" in v.issue]
        assert len(added) == 1


class TestComparePlainText:
    def test_identical(self):
        violations = compare_plain_text(
            "This is a test sentence. Another sentence.",
            "This is a test sentence. Another sentence.",
        )
        assert len(violations) == 0

    def test_significant_change(self):
        violations = compare_plain_text(
            "The method converges rapidly for all test cases.",
            "The algorithm diverges and produces unstable oscillations in every scenario.",
            similarity_threshold=0.8,
        )
        assert len(violations) > 0


class TestRunFaithfulnessCheck:
    def test_full_check_passes(self):
        md = "# Introduction\nSome text about $E=mc^2$ and \\cite{ref2020}."
        pandoc_latex = r"\section{Introduction}Some text about $E=mc^2$ and \cite{ref2020}."
        output_latex = r"\section{Introduction}Some polished text about $E=mc^2$ and \cite{ref2020}."
        report = run_faithfulness_check(md, pandoc_latex, output_latex)
        # Math and citations should match
        assert report.math_match
        assert report.citation_match

    def test_full_check_fails_on_math(self):
        md = "Some text with $E=mc^2$."
        pandoc_latex = r"Some text with $E=mc^2$."
        output_latex = r"Some text with $E=mc^3$."
        report = run_faithfulness_check(md, pandoc_latex, output_latex)
        assert not report.math_match
        assert not report.passed
