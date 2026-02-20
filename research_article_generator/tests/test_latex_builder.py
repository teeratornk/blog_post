"""Tests for tools/latex_builder.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_article_generator.models import ProjectConfig
from research_article_generator.tools.latex_builder import (
    assemble_document,
    assemble_main_tex,
    assemble_supplementary_tex,
    generate_makefile,
    generate_preamble,
    summarize_template,
    write_main_tex,
    write_section_file,
    write_section_files,
    write_supplementary_tex,
)


class TestGeneratePreamble:
    def test_minimal_preamble(self):
        config = ProjectConfig(project_name="Test Paper", template="nonexistent_template")
        preamble = generate_preamble(config)
        assert "\\documentclass" in preamble
        assert "Test Paper" in preamble
        assert "amsmath" in preamble

    def test_elsarticle_template(self):
        config = ProjectConfig(
            project_name="My Article",
            template="elsarticle",
            journal_name="CMAME",
        )
        preamble = generate_preamble(config)
        assert "elsarticle" in preamble
        assert "My Article" in preamble

    def test_xelatex_includes_fontspec(self):
        config = ProjectConfig(project_name="Test", template="none", latex_engine="xelatex")
        preamble = generate_preamble(config)
        assert "fontspec" in preamble


class TestAssembleDocument:
    def test_basic_assembly(self):
        preamble = "\\documentclass{article}\n\\title{Test}"
        sections = [
            ("intro", "\\section{Introduction}\nHello world."),
            ("method", "\\section{Methods}\nWe did things."),
        ]
        doc = assemble_document(preamble, sections)
        assert "\\begin{document}" in doc
        assert "\\end{document}" in doc
        assert "\\maketitle" in doc
        assert "Hello world." in doc
        assert "We did things." in doc

    def test_with_abstract(self):
        doc = assemble_document(
            "\\documentclass{article}",
            [("s1", "content")],
            abstract="This is the abstract.",
        )
        assert "\\begin{abstract}" in doc
        assert "This is the abstract." in doc

    def test_with_bibliography(self):
        doc = assemble_document(
            "\\documentclass{article}",
            [("s1", "content")],
            bibliography="references.bib",
            bib_style="plain",
        )
        assert "\\bibliographystyle{plain}" in doc
        assert "\\bibliography{references}" in doc
        # .bib extension should be stripped
        assert ".bib" not in doc.split("\\bibliography{")[1].split("}")[0]

    def test_with_appendices(self):
        doc = assemble_document(
            "\\documentclass{article}",
            [("s1", "main content")],
            appendices=[("a1", "appendix content")],
        )
        assert "\\appendix" in doc
        assert "appendix content" in doc

    def test_section_comments(self):
        doc = assemble_document(
            "\\documentclass{article}",
            [("my_section", "content")],
        )
        assert "% --- Section: my_section ---" in doc


class TestWriteMainTex:
    def test_write(self, tmp_output_dir):
        path = write_main_tex("\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}", tmp_output_dir)
        assert path.exists()
        assert path.name == "main.tex"
        content = path.read_text()
        assert "Hello" in content

    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new_subdir"
        path = write_main_tex("content", new_dir)
        assert path.exists()


class TestAssembleMainTex:
    def test_frontmatter_moved_inside_document(self):
        preamble = (
            "\\documentclass{elsarticle}\n"
            "\\usepackage{amsmath}\n"
            "\\begin{frontmatter}\n"
            "\\title{Test}\n"
            "\\end{frontmatter}"
        )
        doc = assemble_main_tex(preamble, ["s1"])
        # frontmatter must be AFTER \begin{document}
        doc_start = doc.index("\\begin{document}")
        fm_start = doc.index("\\begin{frontmatter}")
        assert fm_start > doc_start
        # \maketitle should NOT appear when frontmatter is used
        assert "\\maketitle" not in doc

    def test_frontmatter_with_abstract(self):
        preamble = (
            "\\documentclass{elsarticle}\n"
            "\\begin{frontmatter}\n"
            "\\title{Test}\n"
            "\\end{frontmatter}"
        )
        doc = assemble_main_tex(preamble, ["s1"], abstract="My abstract.")
        assert "\\begin{abstract}" in doc
        assert "My abstract." in doc
        # Abstract should be inside frontmatter
        abs_pos = doc.index("\\begin{abstract}")
        fm_end = doc.index("\\end{frontmatter}")
        assert abs_pos < fm_end

    def test_basic_skeleton(self):
        preamble = "\\documentclass{article}\n\\title{Test}"
        section_ids = ["01_introduction", "02_methodology"]
        doc = assemble_main_tex(preamble, section_ids)
        assert "\\begin{document}" in doc
        assert "\\end{document}" in doc
        assert "\\maketitle" in doc
        assert "\\input{sections/01_introduction}" in doc
        assert "\\input{sections/02_methodology}" in doc
        # Should NOT contain inline content
        assert "Hello world" not in doc

    def test_with_abstract(self):
        doc = assemble_main_tex(
            "\\documentclass{article}",
            ["s1"],
            abstract="This is the abstract.",
        )
        assert "\\begin{abstract}" in doc
        assert "This is the abstract." in doc

    def test_with_bibliography(self):
        doc = assemble_main_tex(
            "\\documentclass{article}",
            ["s1"],
            bibliography="references.bib",
            bib_style="plain",
        )
        assert "\\bibliographystyle{plain}" in doc
        assert "\\bibliography{references}" in doc
        assert ".bib" not in doc.split("\\bibliography{")[1].split("}")[0]

    def test_with_appendices(self):
        doc = assemble_main_tex(
            "\\documentclass{article}",
            ["s1"],
            appendix_ids=["a1_appendix"],
        )
        assert "\\appendix" in doc
        assert "\\input{sections/a1_appendix}" in doc

    def test_empty_sections(self):
        doc = assemble_main_tex("\\documentclass{article}", [])
        assert "\\begin{document}" in doc
        assert "\\end{document}" in doc


class TestWriteSectionFiles:
    def test_write_single(self, tmp_output_dir):
        path = write_section_file("01_intro", "\\section{Intro}\nHello.", tmp_output_dir)
        assert path.exists()
        assert path.name == "01_intro.tex"
        assert path.parent.name == "sections"
        assert "Hello." in path.read_text()

    def test_write_multiple(self, tmp_output_dir):
        sections = {
            "01_intro": "\\section{Introduction}\nHello.",
            "02_methods": "\\section{Methods}\nWe did things.",
        }
        paths = write_section_files(sections, tmp_output_dir)
        assert len(paths) == 2
        for p in paths:
            assert p.exists()
        # Verify content
        assert "Hello." in (tmp_output_dir / "sections" / "01_intro.tex").read_text()
        assert "We did things." in (tmp_output_dir / "sections" / "02_methods.tex").read_text()

    def test_creates_sections_dir(self, tmp_path):
        new_dir = tmp_path / "new_output"
        path = write_section_file("test", "content", new_dir)
        assert path.exists()
        assert (new_dir / "sections").is_dir()

    def test_empty_dict(self, tmp_output_dir):
        paths = write_section_files({}, tmp_output_dir)
        assert paths == []


class TestGenerateMakefile:
    def test_pdflatex(self):
        config = ProjectConfig(project_name="Test", latex_engine="pdflatex")
        mk = generate_makefile(config)
        assert "-pdf" in mk
        assert "latexmk" in mk

    def test_xelatex(self):
        config = ProjectConfig(project_name="Test", latex_engine="xelatex")
        mk = generate_makefile(config)
        assert "-xelatex" in mk

    def test_with_supplementary(self):
        config = ProjectConfig(project_name="Test", latex_engine="pdflatex")
        mk = generate_makefile(config, has_supplementary=True)
        assert "SUPP = supplementary" in mk
        assert "$(SUPP).pdf" in mk
        assert "$(SUPP).tex" in mk

    def test_without_supplementary(self):
        config = ProjectConfig(project_name="Test", latex_engine="pdflatex")
        mk = generate_makefile(config, has_supplementary=False)
        assert "SUPP" not in mk
        assert "supplementary" not in mk


class TestAssembleSupplementaryTex:
    def test_basic_assembly(self):
        preamble = "\\documentclass{article}\n\\usepackage{amsmath}\n\\title{Original}"
        doc = assemble_supplementary_tex(
            preamble,
            ["06_proofs", "07_tables"],
            project_name="My Paper",
        )
        assert "\\begin{document}" in doc
        assert "\\end{document}" in doc
        assert "\\input{sections/06_proofs}" in doc
        assert "\\input{sections/07_tables}" in doc
        assert "xr-hyper" in doc
        assert "\\externaldocument{main}" in doc
        assert "Supplementary Materials: My Paper" in doc

    def test_frontmatter_stripped(self):
        preamble = (
            "\\documentclass{elsarticle}\n"
            "\\usepackage{amsmath}\n"
            "\\begin{frontmatter}\n"
            "\\title{Original Title}\n"
            "\\author{Author}\n"
            "\\end{frontmatter}"
        )
        doc = assemble_supplementary_tex(preamble, ["06_proofs"])
        assert "\\begin{frontmatter}" not in doc
        assert "\\end{frontmatter}" not in doc
        assert "\\author{Author}" not in doc
        assert "Supplementary Materials" in doc

    def test_with_bibliography(self):
        preamble = "\\documentclass{article}"
        doc = assemble_supplementary_tex(
            preamble,
            ["06_proofs"],
            bibliography="references.bib",
            bib_style="plain",
        )
        assert "\\bibliographystyle{plain}" in doc
        assert "\\bibliography{references}" in doc

    def test_custom_main_doc(self):
        preamble = "\\documentclass{article}"
        doc = assemble_supplementary_tex(
            preamble,
            ["06_proofs"],
            main_doc="paper",
        )
        assert "\\externaldocument{paper}" in doc

    def test_maketitle_present(self):
        preamble = "\\documentclass{article}"
        doc = assemble_supplementary_tex(preamble, ["06_proofs"])
        assert "\\maketitle" in doc

    def test_empty_sections(self):
        preamble = "\\documentclass{article}"
        doc = assemble_supplementary_tex(preamble, [])
        assert "\\begin{document}" in doc
        assert "\\end{document}" in doc


class TestWriteSupplementaryTex:
    def test_write(self, tmp_output_dir):
        path = write_supplementary_tex(
            "\\documentclass{article}\n\\begin{document}\nSupp\n\\end{document}",
            tmp_output_dir,
        )
        assert path.exists()
        assert path.name == "supplementary.tex"
        content = path.read_text()
        assert "Supp" in content

    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new_subdir"
        path = write_supplementary_tex("content", new_dir)
        assert path.exists()


class TestSummarizeTemplate:
    def test_elsarticle_summary(self):
        config = ProjectConfig(project_name="Test", template="elsarticle")
        summary = summarize_template(config)
        assert "elsarticle" in summary
        assert "frontmatter" in summary.lower()
        assert "natbib" in summary
        assert "Document class:" in summary

    def test_ieeetran_summary(self):
        config = ProjectConfig(project_name="Test", template="ieeetran")
        summary = summarize_template(config)
        assert "IEEEtran" in summary
        assert "cite" in summary
        assert "maketitle" in summary.lower()
        # IEEEtran has no frontmatter
        assert "frontmatter" not in summary.split("Full template content:")[0].lower()

    def test_revtex4_summary(self):
        config = ProjectConfig(project_name="Test", template="revtex4")
        summary = summarize_template(config)
        assert "revtex4-2" in summary

    def test_revtex4_title_mechanism(self):
        config = ProjectConfig(project_name="Test", template="revtex4")
        summary = summarize_template(config)
        # Should detect revtex-specific title mechanism, not \maketitle
        header = summary.split("Full template content:")[0]
        assert "revtex" in header.lower()
        assert r"no \maketitle" in header

    def test_revtex4_citation_hint(self):
        config = ProjectConfig(project_name="Test", template="revtex4")
        summary = summarize_template(config)
        header = summary.split("Full template content:")[0]
        # revtex4 has no citation package — should still get a citation hint
        assert "Citations:" in header
        assert r"\cite{}" in header

    def test_nonexistent_template_fallback(self):
        config = ProjectConfig(project_name="Test", template="nonexistent_xyz")
        summary = summarize_template(config)
        assert "No template file found" in summary
        assert isinstance(summary, str)

    def test_nonexistent_custom_template_shows_path(self):
        config = ProjectConfig(
            project_name="Test",
            template="custom",
            template_file="/nonexistent/path/custom.tex",
        )
        summary = summarize_template(config)
        assert "No template file found" in summary
        assert "/nonexistent/path/custom.tex" in summary

    def test_every_template_has_citation_hint(self):
        """All built-in templates should produce a citation hint."""
        for tpl in ("elsarticle", "ieeetran", "revtex4"):
            config = ProjectConfig(project_name="Test", template=tpl)
            summary = summarize_template(config)
            header = summary.split("Full template content:")[0]
            assert "Citations:" in header, f"No citation hint for {tpl}"

    def test_includes_raw_content(self):
        config = ProjectConfig(project_name="Test", template="elsarticle")
        summary = summarize_template(config)
        assert "Full template content:" in summary
        assert r"\documentclass" in summary

    def test_detects_packages(self):
        config = ProjectConfig(project_name="Test", template="elsarticle")
        summary = summarize_template(config)
        assert "Packages:" in summary
        assert "amsmath" in summary
        assert "graphicx" in summary
