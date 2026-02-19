"""Tests for tools/compiler.py — log parsing and compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_article_generator.tools.compiler import (
    _extract_context,
    extract_error_context,
    parse_log,
)
from research_article_generator.models import CompilationResult, CompilationWarning, Severity


class TestExtractContext:
    def test_middle_of_file(self):
        tex = "\n".join(f"line {i+1} content" for i in range(20))
        ctx = _extract_context(tex, 10, window=2)
        assert ">>> " in ctx  # Current line marker
        assert "line 10 content" in ctx
        assert "line 8 content" in ctx
        assert "line 12 content" in ctx

    def test_beginning_of_file(self):
        tex = "\n".join(f"line {i+1}" for i in range(10))
        ctx = _extract_context(tex, 1, window=3)
        assert ">>>" in ctx
        assert "line 1" in ctx

    def test_end_of_file(self):
        tex = "\n".join(f"line {i+1}" for i in range(10))
        ctx = _extract_context(tex, 10, window=3)
        assert ">>>" in ctx
        assert "line 10" in ctx


class TestParseLog:
    def test_success_log(self, success_log_path):
        errors, warnings, unresolved = parse_log(success_log_path)
        assert len(errors) == 0
        assert len(unresolved) == 0

    def test_error_log(self, error_log_path):
        tex_content = "\n".join(f"line {i+1}" for i in range(200))
        errors, warnings, unresolved = parse_log(error_log_path, tex_content)

        # Should find errors
        assert len(errors) >= 1
        error_msgs = [e.message for e in errors]
        assert any("Undefined control sequence" in m for m in error_msgs)

        # Should find unresolved references
        assert any("fig:missing" in u for u in unresolved)
        assert any("nonexistent2023" in u for u in unresolved)

    def test_error_has_line_number(self, error_log_path):
        tex_content = "\n".join(f"line {i+1}" for i in range(200))
        errors, _, _ = parse_log(error_log_path, tex_content)
        # At least one error should have a line number
        errors_with_lines = [e for e in errors if e.line is not None]
        assert len(errors_with_lines) > 0

    def test_nonexistent_log(self):
        errors, warnings, unresolved = parse_log("nonexistent.log")
        assert errors == []
        assert warnings == []
        assert unresolved == []


class TestExtractErrorContext:
    def test_format_errors(self):
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="Undefined control sequence",
                    line=42,
                    severity=Severity.ERROR,
                ),
            ],
            unresolved_refs=["ref:fig:missing"],
        )
        tex = "\n".join(f"line {i+1}" for i in range(100))
        ctx = extract_error_context(result, tex)
        assert "Error 1:" in ctx
        assert "Undefined control sequence" in ctx
        assert "Line: 42" in ctx
        assert "fig:missing" in ctx

    def test_no_errors(self):
        result = CompilationResult(success=True)
        ctx = extract_error_context(result, "")
        assert "No errors" in ctx
