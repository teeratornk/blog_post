"""Tests for tools/pandoc_converter.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from research_article_generator.tools.pandoc_converter import (
    _annotate_safe_zones,
    convert_markdown_to_latex,
    pandoc_available,
)


class TestAnnotateSafeZones:
    def test_text_gets_safe_zones(self):
        latex = r"""
\section{Introduction}
This is a paragraph of text.
Another sentence here.

\begin{equation}
E = mc^2
\end{equation}

More text after the equation.
"""
        result = _annotate_safe_zones(latex)
        assert "%% SAFE_ZONE_START" in result
        assert "%% SAFE_ZONE_END" in result

    def test_equations_not_in_safe_zone(self):
        latex = r"""
\begin{equation}
E = mc^2
\end{equation}
"""
        result = _annotate_safe_zones(latex)
        lines = result.split("\n")
        in_safe = False
        for line in lines:
            if "%% SAFE_ZONE_START" in line:
                in_safe = True
            if "%% SAFE_ZONE_END" in line:
                in_safe = False
            if "E = mc^2" in line:
                assert not in_safe, "Math should not be inside a SAFE_ZONE"

    def test_structural_commands_not_in_safe_zone(self):
        latex = r"""
\section{Title}
Some text.
\subsection{Subtitle}
More text.
"""
        result = _annotate_safe_zones(latex)
        lines = result.split("\n")
        in_safe = False
        for line in lines:
            if "%% SAFE_ZONE_START" in line:
                in_safe = True
            if "%% SAFE_ZONE_END" in line:
                in_safe = False
            if r"\section{Title}" in line:
                assert not in_safe
            if r"\subsection{Subtitle}" in line:
                assert not in_safe


class TestConvertMarkdownToLatex:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            convert_markdown_to_latex("nonexistent.md")

    def test_pandoc_fallback(self, sample_drafts_dir):
        """When pandoc is not available, returns raw markdown."""
        md_file = sample_drafts_dir / "01_introduction.md"
        with patch("research_article_generator.tools.pandoc_converter.pandoc_available", return_value=False):
            result = convert_markdown_to_latex(md_file)
            assert "Introduction" in result
            # Should be raw markdown, not LaTeX
            assert "\\section" not in result

    @pytest.mark.skipif(not pandoc_available(), reason="pandoc not installed")
    def test_real_pandoc_conversion(self, sample_drafts_dir):
        md_file = sample_drafts_dir / "01_introduction.md"
        result = convert_markdown_to_latex(md_file)
        assert "\\section" in result or "\\hypertarget" in result
        assert "%% SAFE_ZONE" in result
