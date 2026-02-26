"""Tests for LaTeX builder utilities."""

from ml_system_design_generator.tools.latex_builder import (
    _strip_safe_zone_markers,
    assemble_main_tex,
    generate_preamble,
)


class TestStripSafeZoneMarkers:
    def test_strips_markers(self):
        latex = (
            "%% SAFE_ZONE_START\n"
            "Some text here.\n"
            "%% SAFE_ZONE_END\n"
        )
        result = _strip_safe_zone_markers(latex)
        assert "%% SAFE_ZONE" not in result
        assert "Some text here." in result

    def test_preserves_other_comments(self):
        latex = "% Normal comment\nText"
        assert _strip_safe_zone_markers(latex) == latex

    def test_empty_string(self):
        assert _strip_safe_zone_markers("") == ""

    def test_no_markers(self):
        latex = "\\section{Hello}\nSome text."
        assert _strip_safe_zone_markers(latex) == latex


class TestGeneratePreamble:
    def test_title_replaced(self):
        result = generate_preamble(title="Test Project")
        assert "Test Project" in result
        assert "{{TITLE}}" not in result

    def test_author_replaced(self):
        result = generate_preamble(title="Test", author="My Team")
        assert "My Team" in result
        assert "{{AUTHOR}}" not in result

    def test_author_default_fallback(self):
        result = generate_preamble(title="Test")
        assert "ML System Design Generator" in result

    def test_compact_formatting_present(self):
        result = generate_preamble(title="Test")
        assert "headheight=14pt" in result
        assert "\\titlespacing" in result
        assert "\\setlist{nosep" in result
        assert "\\small ML System Design Document" in result


class TestAssembleMainTex:
    def test_thispagestyle_fancy(self):
        preamble = "\\documentclass{article}"
        result = assemble_main_tex(preamble, ["situation"], title="Test")
        assert "\\thispagestyle{fancy}" in result

    def test_thispagestyle_after_maketitle(self):
        preamble = "\\documentclass{article}"
        result = assemble_main_tex(preamble, ["situation"], title="Test")
        lines = result.splitlines()
        maketitle_idx = next(i for i, l in enumerate(lines) if "\\maketitle" in l)
        fancy_idx = next(i for i, l in enumerate(lines) if "\\thispagestyle{fancy}" in l)
        assert fancy_idx == maketitle_idx + 1
