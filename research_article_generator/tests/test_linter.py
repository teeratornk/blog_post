"""Tests for tools/linter.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from research_article_generator.tools.linter import (
    LintResult,
    chktex_available,
    run_chktex,
    run_lint,
)


class TestLintResult:
    def test_empty(self):
        r = LintResult()
        assert r.total == 0
        assert r.warnings == []

    def test_totals(self):
        r = LintResult(error_count=2, warning_count=3, info_count=1)
        assert r.total == 6


class TestRunChktex:
    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            run_chktex("nonexistent.tex")

    def test_unavailable_returns_empty(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}")
        with patch("research_article_generator.tools.linter.chktex_available", return_value=False):
            result = run_chktex(tex)
            assert result.total == 0

    @pytest.mark.skipif(not chktex_available(), reason="chktex not installed")
    def test_real_chktex(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n")
        result = run_chktex(tex)
        # Should at least run without error
        assert isinstance(result, LintResult)


class TestRunLint:
    def test_no_tools_available(self, tmp_path):
        tex = tmp_path / "test.tex"
        tex.write_text("\\documentclass{article}\n")
        with patch("research_article_generator.tools.linter.chktex_available", return_value=False):
            with patch("research_article_generator.tools.linter.lacheck_available", return_value=False):
                result = run_lint(tex)
                assert result.total == 0
