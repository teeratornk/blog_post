"""Tests for the deterministic LaTeX linter."""

from ml_system_design_generator.tools.latex_linter import (
    autofix_section,
    fix_heading_hierarchy,
    fix_hline_to_booktabs,
    lint_section_latex,
)


# ---------------------------------------------------------------------------
# fix_heading_hierarchy
# ---------------------------------------------------------------------------


class TestFixHeadingHierarchy:
    def test_promotes_subsection_to_section(self):
        latex = "\\subsection{Introduction}\nSome text."
        result = fix_heading_hierarchy(latex)
        assert "\\section{Introduction}" in result
        assert "\\subsection{Introduction}" not in result

    def test_promotes_subsection_star(self):
        latex = "\\subsection*{Overview}\nDetails here."
        result = fix_heading_hierarchy(latex)
        assert "\\section*{Overview}" in result
        assert "\\subsection*{Overview}" not in result

    def test_no_change_when_section_exists(self):
        latex = "\\section{Title}\n\\subsection{Sub}\nText."
        result = fix_heading_hierarchy(latex)
        assert result == latex

    def test_no_change_when_no_headings(self):
        latex = "Just some text without any headings."
        result = fix_heading_hierarchy(latex)
        assert result == latex

    def test_only_promotes_first_subsection(self):
        latex = "\\subsection{First}\nText.\n\\subsection{Second}\nMore."
        result = fix_heading_hierarchy(latex)
        assert result.startswith("\\section{First}")
        assert "\\subsection{Second}" in result

    def test_leaves_subsubsection_unchanged(self):
        latex = "\\subsection{Main}\n\\subsubsection{Detail}\nText."
        result = fix_heading_hierarchy(latex)
        assert "\\section{Main}" in result
        assert "\\subsubsection{Detail}" in result


# ---------------------------------------------------------------------------
# lint_section_latex
# ---------------------------------------------------------------------------


class TestLintSectionLatex:
    def test_detects_subsection_as_first_heading(self):
        latex = "\\subsection{Title}\nContent."
        issues = lint_section_latex("sec1", latex)
        assert any("\\subsection" in i for i in issues)

    def test_no_heading_issue_when_section_present(self):
        latex = "\\section{Title}\n\\subsection{Sub}\nContent."
        issues = lint_section_latex("sec1", latex)
        assert not any("\\subsection" in i and "should be" in i for i in issues)

    def test_detects_hline_without_booktabs(self):
        latex = "\\begin{tabular}{ll}\n\\hline\na & b \\\\\n\\hline\n\\end{tabular}"
        issues = lint_section_latex("sec1", latex)
        assert any("\\hline" in i for i in issues)

    def test_no_hline_issue_when_booktabs_present(self):
        latex = "\\begin{tabular}{ll}\n\\toprule\na & b \\\\\n\\bottomrule\n\\end{tabular}"
        issues = lint_section_latex("sec1", latex)
        assert not any("\\hline" in i for i in issues)

    def test_detects_unbalanced_braces(self):
        latex = "\\section{Title\nMissing closing brace."
        issues = lint_section_latex("sec1", latex)
        assert any("unbalanced" in i for i in issues)

    def test_no_brace_issue_when_balanced(self):
        latex = "\\section{Title}\nText with {nested} braces."
        issues = lint_section_latex("sec1", latex)
        assert not any("unbalanced" in i for i in issues)

    def test_detects_tabularx_without_textwidth(self):
        latex = "\\begin{tabularx}{10cm}{lXr}\ncontent\n\\end{tabularx}"
        issues = lint_section_latex("sec1", latex)
        assert any("tabularx" in i and "textwidth" in i for i in issues)

    def test_no_tabularx_issue_with_textwidth(self):
        latex = "\\begin{tabularx}{\\textwidth}{lXr}\ncontent\n\\end{tabularx}"
        issues = lint_section_latex("sec1", latex)
        assert not any("tabularx" in i for i in issues)

    def test_clean_latex_no_issues(self):
        latex = (
            "\\section{Title}\n"
            "Some text.\n"
            "\\begin{tabular}{ll}\n"
            "\\toprule\na & b \\\\\n"
            "\\bottomrule\n"
            "\\end{tabular}"
        )
        issues = lint_section_latex("sec1", latex)
        assert issues == []


# ---------------------------------------------------------------------------
# fix_hline_to_booktabs
# ---------------------------------------------------------------------------


class TestFixHlineToBooktabs:
    def test_single_hline_becomes_toprule(self):
        latex = "\\begin{tabular}{ll}\n\\hline\na & b\n\\end{tabular}"
        result = fix_hline_to_booktabs(latex)
        assert "\\toprule" in result
        assert "\\hline" not in result

    def test_two_hlines(self):
        latex = (
            "\\begin{tabular}{ll}\n"
            "\\hline\n"
            "a & b \\\\\n"
            "\\hline\n"
            "\\end{tabular}"
        )
        result = fix_hline_to_booktabs(latex)
        assert "\\toprule" in result
        assert "\\bottomrule" in result
        assert "\\hline" not in result

    def test_three_hlines(self):
        latex = (
            "\\begin{tabular}{ll}\n"
            "\\hline\n"
            "Header & Header \\\\\n"
            "\\hline\n"
            "a & b \\\\\n"
            "\\hline\n"
            "\\end{tabular}"
        )
        result = fix_hline_to_booktabs(latex)
        assert "\\toprule" in result
        assert "\\midrule" in result
        assert "\\bottomrule" in result
        assert "\\hline" not in result

    def test_no_hline_unchanged(self):
        latex = "\\begin{tabular}{ll}\n\\toprule\na & b\n\\bottomrule\n\\end{tabular}"
        result = fix_hline_to_booktabs(latex)
        assert result == latex

    def test_tabularx_also_fixed(self):
        latex = (
            "\\begin{tabularx}{\\textwidth}{lX}\n"
            "\\hline\n"
            "a & b \\\\\n"
            "\\hline\n"
            "\\end{tabularx}"
        )
        result = fix_hline_to_booktabs(latex)
        assert "\\toprule" in result
        assert "\\hline" not in result


# ---------------------------------------------------------------------------
# autofix_section
# ---------------------------------------------------------------------------


class TestAutofixSection:
    def test_returns_fixed_latex_and_issues(self):
        latex = "\\subsection{Title}\n\\begin{tabular}{ll}\n\\hline\na & b\n\\hline\n\\end{tabular}"
        fixed, issues = autofix_section("sec1", latex)
        # Should have promoted heading and reported issues
        assert "\\section{Title}" in fixed
        assert len(issues) > 0

    def test_clean_latex_returns_no_issues(self):
        latex = "\\section{Title}\nClean content."
        fixed, issues = autofix_section("sec1", latex)
        assert fixed == latex
        assert issues == []
