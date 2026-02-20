"""Tests for tools/compiler.py — log parsing and compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_article_generator.tools.compiler import (
    _extract_context,
    _find_current_file,
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

    def test_unresolved_refs_without_errors(self):
        """Unresolved refs should be included even when there are no errors."""
        result = CompilationResult(
            success=True,
            unresolved_refs=["ref:sec:missing", "cite:nonexistent2023"],
        )
        ctx = extract_error_context(result, "")
        assert "No LaTeX errors" in ctx
        assert "sec:missing" in ctx
        assert "nonexistent2023" in ctx

    def test_section_file_filter(self):
        """When section_file is set, only errors from that file are included."""
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    file="sections/01_intro.tex",
                    message="Error in intro",
                    line=5,
                    severity=Severity.ERROR,
                ),
                CompilationWarning(
                    file="sections/02_methods.tex",
                    message="Error in methods",
                    line=10,
                    severity=Severity.ERROR,
                ),
                CompilationWarning(
                    message="Generic error",
                    severity=Severity.ERROR,
                ),
            ],
        )
        tex = "\n".join(f"line {i+1}" for i in range(20))
        ctx = extract_error_context(
            result, tex, section_file="sections/02_methods.tex"
        )
        assert "Error in methods" in ctx
        assert "Error in intro" not in ctx
        # Generic errors (no file) should also be included
        assert "Generic error" in ctx

    def test_section_file_context_from_tex_content(self):
        """When section_file matches an error, context is extracted from tex_content."""
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    file="sections/02_methods.tex",
                    message="Undefined control sequence",
                    line=3,
                    severity=Severity.ERROR,
                    context="",  # empty stale context
                ),
            ],
        )
        tex = "line A\nline B\nline C with \\badcommand\nline D\n"
        ctx = extract_error_context(
            result, tex, section_file="sections/02_methods.tex"
        )
        assert "\\badcommand" in ctx


class TestFindCurrentFile:
    def test_main_file_when_no_nesting(self):
        log = "Some log text without file opens"
        assert _find_current_file(log, len(log)) == "main.tex"

    def test_section_file(self):
        log = "(./main.tex\nsome text\n(./sections/02_methods.tex\n! Error here"
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "sections/02_methods.tex"

    def test_after_section_closed(self):
        log = (
            "(./main.tex\n"
            "(./sections/02_methods.tex\nstuff\n)\n"
            "! Error in main after section closed"
        )
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "main.tex"

    def test_nested_sections(self):
        log = (
            "(./main.tex\n"
            "(./sections/01_intro.tex\nok\n)\n"
            "(./sections/03_results.tex\n"
            "! Error in results"
        )
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "sections/03_results.tex"

    def test_empty_log(self):
        assert _find_current_file("", 0) == "main.tex"

    def test_miktex_no_dot_slash(self):
        """MiKTeX logs omit the ./ prefix — files should still be matched."""
        log = (
            "(main.tex\n"
            "(sections/02_methodology.tex\n"
            "! Error here"
        )
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "sections/02_methodology.tex"

    def test_miktex_main_without_dot_slash(self):
        """MiKTeX: (main.tex without ./ still tracks as main."""
        log = "(main.tex\nsome text\n! Error"
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "main.tex"

    def test_skips_absolute_windows_paths(self):
        """Absolute Windows paths (e.g. .cls files) should not enter the stack."""
        log = (
            "(main.tex\n"
            r"(C:\Users\test\MiKTeX\tex\latex\elsarticle\elsarticle.tex" "\n"
            ")\n"
            "! Error here"
        )
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "main.tex"

    def test_skips_absolute_unix_paths(self):
        """Absolute Unix paths should not enter the stack."""
        log = (
            "(./main.tex\n"
            "(/usr/share/texlive/texmf-dist/tex/latex/base/article.tex\n"
            ")\n"
            "! Error here"
        )
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "main.tex"


class TestParseLogMultiFile:
    def test_errors_attributed_to_section_files(self, error_multifile_log_path):
        tex_content = "\n".join(f"line {i+1}" for i in range(200))
        errors, warnings, unresolved = parse_log(error_multifile_log_path, tex_content)

        assert len(errors) >= 2

        # First error should be in 02_methods
        methods_errors = [e for e in errors if e.file == "sections/02_methods.tex"]
        assert len(methods_errors) >= 1
        assert any("Undefined control sequence" in e.message for e in methods_errors)

        # Second error should be in 03_results
        results_errors = [e for e in errors if e.file == "sections/03_results.tex"]
        assert len(results_errors) >= 1
        assert any("not found" in e.message for e in results_errors)

    def test_no_context_for_section_errors(self, error_multifile_log_path):
        """Section errors should NOT get context from main.tex content."""
        tex_content = "\n".join(f"main line {i+1}" for i in range(200))
        errors, _, _ = parse_log(error_multifile_log_path, tex_content)

        section_errors = [e for e in errors if "sections/" in (e.file or "")]
        for err in section_errors:
            # Context should be empty — it will be filled later by run_latexmk
            assert err.context == ""

    def test_unresolved_refs_still_found(self, error_multifile_log_path):
        errors, warnings, unresolved = parse_log(error_multifile_log_path)
        assert any("sec:method" in u for u in unresolved)

    def test_existing_error_log_still_works(self, error_log_path):
        """Existing test fixture without file nesting falls back to main.tex."""
        tex_content = "\n".join(f"line {i+1}" for i in range(200))
        errors, _, _ = parse_log(error_log_path, tex_content)
        assert len(errors) >= 1
        # All errors should be attributed to main.tex (no file nesting in this log)
        for err in errors:
            assert err.file == "main.tex"


class TestParseLogMiKTeX:
    """Tests using MiKTeX-style log (no ./ prefix on file opens)."""

    def test_miktex_log_attribution(self, error_miktex_log_path):
        """Errors are correctly attributed when logs lack ./ prefix."""
        tex_content = "\n".join(f"line {i+1}" for i in range(200))
        errors, warnings, unresolved = parse_log(error_miktex_log_path, tex_content)

        assert len(errors) >= 2

        # First error should be in 02_methodology
        methodology_errors = [e for e in errors if e.file == "sections/02_methodology.tex"]
        assert len(methodology_errors) >= 1
        assert any("not found" in e.message for e in methodology_errors)

        # Second error should be in 03_results
        results_errors = [e for e in errors if e.file == "sections/03_results.tex"]
        assert len(results_errors) >= 1
        assert any("Undefined control sequence" in e.message for e in results_errors)

    def test_miktex_unresolved_refs(self, error_miktex_log_path):
        """Unresolved refs are still found in MiKTeX logs."""
        _, _, unresolved = parse_log(error_miktex_log_path)
        assert any("sec:methodology" in u for u in unresolved)

    def test_miktex_no_context_for_section_errors(self, error_miktex_log_path):
        """Section errors should NOT get context from main.tex content."""
        tex_content = "\n".join(f"main line {i+1}" for i in range(200))
        errors, _, _ = parse_log(error_miktex_log_path, tex_content)

        section_errors = [e for e in errors if "sections/" in (e.file or "")]
        for err in section_errors:
            assert err.context == ""
