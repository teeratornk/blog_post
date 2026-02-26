"""Tests for tools/compiler.py — log parsing and compilation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from research_article_generator.tools.compiler import (
    _extract_context,
    _find_current_file,
    _is_absolute_path,
    _run_direct_engine,
    extract_error_context,
    parse_log,
    run_latexmk,
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


class TestIsAbsolutePath:
    """Tests for _is_absolute_path helper."""

    def test_windows_drive_backslash(self):
        assert _is_absolute_path(r"C:\Users\test\file.tex") is True

    def test_windows_drive_forward_slash(self):
        assert _is_absolute_path("D:/texlive/file.tex") is True

    def test_unix_absolute(self):
        assert _is_absolute_path("/usr/share/texlive/file.tex") is True

    def test_unix_root(self):
        assert _is_absolute_path("/") is True

    def test_relative_dotslash(self):
        assert _is_absolute_path("./sections/file.tex") is False

    def test_relative_plain(self):
        assert _is_absolute_path("sections/file.tex") is False

    def test_relative_main(self):
        assert _is_absolute_path("main.tex") is False

    def test_empty_string(self):
        assert _is_absolute_path("") is False

    def test_single_char(self):
        assert _is_absolute_path("C") is False

    def test_two_chars(self):
        assert _is_absolute_path("C:") is False

    def test_digit_colon(self):
        assert _is_absolute_path("2:/path") is True  # technically valid format


class TestRunLatexmk:
    """Tests for run_latexmk — subprocess mock-based."""

    def test_missing_main_tex(self, tmp_path):
        """Returns failure when main.tex doesn't exist."""
        result = run_latexmk(tmp_path)
        assert result.success is False
        assert any("not found" in e.message for e in result.errors)

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value=None)
    @patch("research_article_generator.tools.compiler._find_engine", return_value=None)
    def test_latexmk_and_engine_not_on_path(self, mock_engine, mock_find, tmp_path):
        """Returns failure when neither latexmk nor the engine is installed."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        result = run_latexmk(tmp_path)
        assert result.success is False
        assert any("not found" in e.message for e in result.errors)

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_no_halt_on_error_in_command(self, mock_run, mock_find, tmp_path):
        """The latexmk command must NOT include -halt-on-error."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        # Simulate successful run that produces PDF
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        (tmp_path / "main.pdf").write_bytes(b"%PDF-fake")
        (tmp_path / "main.log").write_text("")

        run_latexmk(tmp_path)

        called_cmd = mock_run.call_args[0][0]
        assert "-halt-on-error" not in called_cmd
        assert "-interaction=nonstopmode" in called_cmd

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_success_when_pdf_exists_despite_nonzero_returncode(self, mock_run, mock_find, tmp_path):
        """Success is True when PDF exists, even with non-zero returncode."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        (tmp_path / "main.log").write_text("")

        def side_effect(*args, **kwargs):
            # latexmk produces a PDF despite returning non-zero
            (tmp_path / "main.pdf").write_bytes(b"%PDF-fake")
            return MagicMock(returncode=1, stdout="", stderr="some warning")

        mock_run.side_effect = side_effect

        result = run_latexmk(tmp_path)
        assert result.success is True
        assert result.pdf_path is not None

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_failure_when_no_pdf_despite_zero_returncode(self, mock_run, mock_find, tmp_path):
        """Success is False when PDF doesn't exist, even with returncode 0."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        # No PDF produced
        (tmp_path / "main.log").write_text("")

        result = run_latexmk(tmp_path)
        assert result.success is False
        assert result.pdf_path is None

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_stale_pdf_deleted_before_compilation(self, mock_run, mock_find, tmp_path):
        """A stale PDF from a previous run is deleted before latexmk runs."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        stale_pdf = tmp_path / "main.pdf"
        stale_pdf.write_bytes(b"%PDF-stale")
        assert stale_pdf.exists()

        # Simulate latexmk that does NOT produce a new PDF (failure)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fatal error")
        (tmp_path / "main.log").write_text("! Fatal error\nl.1 bad\n")

        result = run_latexmk(tmp_path)
        # The stale PDF was deleted, latexmk didn't produce a new one → failure
        assert result.success is False
        assert not stale_pdf.exists()

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_stale_pdf_replaced_by_new(self, mock_run, mock_find, tmp_path):
        """Stale PDF is deleted; new PDF from successful compilation means success."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        stale_pdf = tmp_path / "main.pdf"
        stale_pdf.write_bytes(b"%PDF-stale")

        def side_effect(*args, **kwargs):
            # Simulate latexmk writing a fresh PDF
            (tmp_path / "main.pdf").write_bytes(b"%PDF-fresh")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect
        (tmp_path / "main.log").write_text("")

        result = run_latexmk(tmp_path)
        assert result.success is True

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_timeout_returns_failure(self, mock_run, mock_find, tmp_path):
        """Compilation timeout returns a clear error message."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}Hello\end{document}")
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="latexmk", timeout=120)

        result = run_latexmk(tmp_path)
        assert result.success is False
        assert any("timed out" in e.message for e in result.errors)

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_section_error_context_reextracted(self, mock_run, mock_find, tmp_path):
        """Errors in section files get context from the section, not main.tex."""
        main_tex = r"\documentclass{article}\begin{document}\input{sections/02_methods}\end{document}"
        (tmp_path / "main.tex").write_text(main_tex)
        sections_dir = tmp_path / "sections"
        sections_dir.mkdir()
        section_content = "\\section{Methods}\n\\badcommand\nLine 3 ok\n"
        (sections_dir / "02_methods.tex").write_text(section_content)

        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        # Write a log that references the section file with an error on line 2
        log_text = (
            "(./main.tex\n"
            "(./sections/02_methods.tex\n"
            "! Undefined control sequence\n"
            "l.2 \\badcommand\n"
            ")\n)\n"
        )
        (tmp_path / "main.log").write_text(log_text)
        # latexmk failed, no PDF
        result = run_latexmk(tmp_path)

        section_errors = [e for e in result.errors if e.file == "sections/02_methods.tex"]
        assert len(section_errors) >= 1
        # Context should come from the section file, not main.tex
        assert "\\badcommand" in section_errors[0].context

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_engine_flag_mapping(self, mock_run, mock_find, tmp_path):
        """Engine parameter maps to correct latexmk flag."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        (tmp_path / "main.pdf").write_bytes(b"%PDF")
        (tmp_path / "main.log").write_text("")

        for engine, expected_flag in [
            ("pdflatex", "-pdf"),
            ("xelatex", "-xelatex"),
            ("lualatex", "-lualatex"),
            ("unknown", "-pdf"),  # fallback
        ]:
            run_latexmk(tmp_path, engine)
            called_cmd = mock_run.call_args[0][0]
            assert expected_flag in called_cmd, f"Engine {engine} should use {expected_flag}"

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value="/usr/bin/latexmk")
    @patch("research_article_generator.tools.compiler._run_direct_engine")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_falls_back_to_direct_engine_on_perl_missing(self, mock_run, mock_direct, mock_find, tmp_path):
        """When latexmk fails because Perl is missing, falls back to direct engine."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        (tmp_path / "main.log").write_text("")

        # Simulate MiKTeX latexmk failing due to missing Perl
        mock_run.return_value = MagicMock(
            returncode=1, stdout="",
            stderr="latexmk.exe did not succeed: could not find the script engine 'perl'",
        )
        mock_direct.return_value = CompilationResult(success=True, pdf_path="main.pdf")

        result = run_latexmk(tmp_path)
        # Should have fallen back to direct engine
        mock_direct.assert_called_once()
        assert result.success is True

    @patch("research_article_generator.tools.compiler._find_latexmk", return_value=None)
    @patch("research_article_generator.tools.compiler._find_engine", return_value="/usr/bin/pdflatex")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_falls_back_to_direct_engine_when_no_latexmk(self, mock_run, mock_engine, mock_find, tmp_path):
        """When latexmk is not found, falls back to direct engine."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        (tmp_path / "main.log").write_text("")

        def side_effect(*args, **kwargs):
            # Direct engine produces PDF
            (tmp_path / "main.pdf").write_bytes(b"%PDF")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect

        result = run_latexmk(tmp_path)
        assert result.success is True
        # Should have called the engine directly (multiple passes)
        assert mock_run.call_count >= 2  # at least engine pass 1 + pass 2


class TestRunDirectEngine:
    """Tests for _run_direct_engine fallback compilation."""

    @patch("research_article_generator.tools.compiler._find_engine", return_value=None)
    def test_engine_not_found(self, mock_find, tmp_path):
        """Returns failure when engine executable is not found."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        result = _run_direct_engine(tmp_path, "pdflatex", "main.tex", 120)
        assert result.success is False
        assert any("not found" in e.message for e in result.errors)

    @patch("research_article_generator.tools.compiler._find_engine", return_value="/usr/bin/pdflatex")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_multiple_passes_executed(self, mock_run, mock_find, tmp_path):
        """Direct engine runs multiple passes (engine → bibtex → engine → engine)."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        (tmp_path / "main.log").write_text("")

        def side_effect(*args, **kwargs):
            (tmp_path / "main.pdf").write_bytes(b"%PDF")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = side_effect

        result = _run_direct_engine(tmp_path, "pdflatex", "main.tex", 120)
        assert result.success is True
        # Should run: pass 1, bibtex (if found), pass 2, pass 3
        assert mock_run.call_count >= 3

    @patch("research_article_generator.tools.compiler._find_engine", return_value="/usr/bin/pdflatex")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_stale_pdf_deleted(self, mock_run, mock_find, tmp_path):
        """Stale PDF is deleted before direct engine compilation."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        (tmp_path / "main.log").write_text("")
        stale = tmp_path / "main.pdf"
        stale.write_bytes(b"%PDF-stale")

        # Engine fails — no new PDF produced
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        result = _run_direct_engine(tmp_path, "pdflatex", "main.tex", 120)
        assert result.success is False
        assert not stale.exists()

    @patch("research_article_generator.tools.compiler._find_engine", return_value="/usr/bin/pdflatex")
    @patch("research_article_generator.tools.compiler.subprocess.run")
    def test_timeout_during_pass(self, mock_run, mock_find, tmp_path):
        """Timeout during any pass returns a clear error."""
        (tmp_path / "main.tex").write_text(r"\documentclass{article}\begin{document}X\end{document}")
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="pdflatex", timeout=40)

        result = _run_direct_engine(tmp_path, "pdflatex", "main.tex", 120)
        assert result.success is False
        assert any("timed out" in e.message for e in result.errors)


class TestFindCurrentFileEdgeCases:
    """Additional edge cases for _find_current_file."""

    def test_unbalanced_open_parens(self):
        """Unbalanced open parens don't crash; returns deepest real file."""
        log = "(./main.tex\n(((\n! Error"
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "main.tex"

    def test_more_closes_than_opens(self):
        """Extra close parens don't crash."""
        log = "(./main.tex\n))\n! Error"
        error_pos = log.index("! Error")
        # main.tex was popped, extra ) is harmless
        assert _find_current_file(log, error_pos) == "main.tex"

    def test_error_at_position_zero(self):
        """Error at position 0 returns main.tex."""
        assert _find_current_file("! Error at start", 0) == "main.tex"

    def test_non_tex_parens_ignored(self):
        """Parens not followed by .tex files push empty sentinels."""
        log = "(./main.tex\n(some random text)\n! Error"
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "main.tex"

    def test_mixed_sentinels_and_real_files(self):
        """Stack with mixed sentinel '' and real filenames picks innermost real."""
        log = (
            "(./main.tex\n"
            "(something\n"         # sentinel
            "(./sections/01.tex\n"
            "(another\n"           # sentinel
            "! Error"
        )
        error_pos = log.index("! Error")
        assert _find_current_file(log, error_pos) == "sections/01.tex"


class TestExtractErrorContextEdgeCases:
    """Additional edge cases for extract_error_context."""

    def test_no_section_file_includes_all_errors(self):
        """Without section_file filter, all errors are included."""
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(file="sections/01_intro.tex", message="Err A", severity=Severity.ERROR),
                CompilationWarning(file="sections/02_methods.tex", message="Err B", severity=Severity.ERROR),
                CompilationWarning(message="Err C", severity=Severity.ERROR),
            ],
        )
        ctx = extract_error_context(result, "")
        assert "Err A" in ctx
        assert "Err B" in ctx
        assert "Err C" in ctx

    def test_section_file_no_file_included(self):
        """Errors without a file field are included when section_file is set."""
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(message="Global error", severity=Severity.ERROR),
            ],
        )
        ctx = extract_error_context(result, "", section_file="sections/02.tex")
        assert "Global error" in ctx

    def test_error_without_line_has_no_context(self):
        """Error without a line number doesn't attempt context extraction."""
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(message="Some error", severity=Severity.ERROR),
            ],
        )
        ctx = extract_error_context(result, "line1\nline2\nline3")
        assert "Some error" in ctx
        assert "Context" not in ctx

    def test_only_unresolved_refs(self):
        """When there are only unresolved refs and no errors."""
        result = CompilationResult(
            success=True,
            unresolved_refs=["ref:fig:a", "cite:smith2023"],
        )
        ctx = extract_error_context(result, "")
        assert "No LaTeX errors" in ctx
        assert "fig:a" in ctx
        assert "smith2023" in ctx
        # Should NOT say "No errors found." (the default empty message)
        assert ctx != "No errors found."
