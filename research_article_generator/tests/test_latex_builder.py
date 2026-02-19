"""Tests for tools/latex_builder.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from research_article_generator.models import ProjectConfig
from research_article_generator.tools.latex_builder import (
    assemble_document,
    generate_makefile,
    generate_preamble,
    write_main_tex,
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
