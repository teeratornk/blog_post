"""Tests for compiler tool."""

import pytest
from pathlib import Path

from ml_system_design_generator.models import CompilationResult, CompilationWarning, Severity
from ml_system_design_generator.tools.compiler import (
    _extract_context,
    extract_error_context,
    latexmk_available,
    parse_log,
)


class TestExtractContext:
    def test_basic_context(self):
        tex = "\n".join(f"Line {i}" for i in range(1, 21))
        ctx = _extract_context(tex, 10, window=2)
        assert ">>> " in ctx
        assert "Line 10" in ctx
        assert "Line 8" in ctx
        assert "Line 12" in ctx

    def test_edge_case_first_line(self):
        tex = "First line\nSecond line\nThird line"
        ctx = _extract_context(tex, 1, window=1)
        assert "First line" in ctx

    def test_edge_case_last_line(self):
        tex = "First line\nSecond line\nThird line"
        ctx = _extract_context(tex, 3, window=1)
        assert "Third line" in ctx


class TestExtractErrorContext:
    def test_no_errors(self):
        result = CompilationResult(success=True)
        ctx = extract_error_context(result, "some tex")
        assert "No errors found" in ctx

    def test_with_errors(self):
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="Undefined control sequence",
                    severity=Severity.ERROR,
                    line=5,
                )
            ],
        )
        tex = "\n".join(f"Line {i}" for i in range(1, 11))
        ctx = extract_error_context(result, tex)
        assert "Undefined control sequence" in ctx


class TestParseLog:
    def test_no_log_file(self, tmp_path: Path):
        errors, warnings, unresolved = parse_log(tmp_path / "nonexistent.log")
        assert errors == []
        assert warnings == []
        assert unresolved == []

    def test_log_with_error(self, tmp_path: Path):
        log_content = """\
This is TeX output.
! Undefined control sequence.
l.42 \\badcommand
"""
        log_path = tmp_path / "main.log"
        log_path.write_text(log_content)

        errors, warnings, unresolved = parse_log(log_path)
        assert len(errors) >= 1
        assert any("Undefined" in e.message for e in errors)
