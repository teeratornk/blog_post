"""LaTeX document assembly: preamble generation, section assembly, Makefile.

Combines converted sections with a template preamble into a complete
``main.tex`` document ready for compilation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..models import ProjectConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Preamble Templates
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "preamble_templates"


def _load_template(template_name: str, template_file: str | None = None) -> str:
    """Load a preamble template by name or from a custom file path."""
    if template_file:
        p = Path(template_file)
        if p.exists():
            return p.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Custom template not found: {p}")

    # Look in built-in templates
    candidates = [
        TEMPLATES_DIR / f"{template_name}.tex",
        TEMPLATES_DIR / f"{template_name.lower()}.tex",
    ]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Template '{template_name}' not found. Available: {list(TEMPLATES_DIR.glob('*.tex'))}"
    )


def generate_preamble(config: ProjectConfig) -> str:
    """Generate a LaTeX preamble from config settings.

    If a template file exists, loads it. Otherwise generates a minimal preamble.
    Template placeholders ``{{TITLE}}``, ``{{JOURNAL}}``, ``{{BIB_STYLE}}``
    are substituted.
    """
    try:
        preamble = _load_template(config.template, config.template_file)
    except FileNotFoundError:
        logger.info("No template found for '%s', generating minimal preamble", config.template)
        preamble = _generate_minimal_preamble(config)
        return preamble

    # Substitute placeholders
    preamble = preamble.replace("{{TITLE}}", config.project_name)
    preamble = preamble.replace("{{JOURNAL}}", config.journal_name)
    preamble = preamble.replace("{{BIB_STYLE}}", config.bib_style)

    return preamble


def _generate_minimal_preamble(config: ProjectConfig) -> str:
    """Generate a minimal preamble when no template is found."""
    engine = config.latex_engine
    font_pkg = ""
    if engine in ("xelatex", "lualatex"):
        font_pkg = "\\usepackage{fontspec}\n"

    return (
        f"\\documentclass[12pt]{{article}}\n"
        f"\\usepackage[utf8]{{inputenc}}\n"
        f"{font_pkg}"
        f"\\usepackage{{amsmath,amssymb,amsfonts}}\n"
        f"\\usepackage{{graphicx}}\n"
        f"\\usepackage{{hyperref}}\n"
        f"\\usepackage{{natbib}}\n"
        f"\\usepackage{{booktabs}}\n"
        f"\\usepackage{{caption}}\n"
        f"\n"
        f"\\title{{{config.project_name}}}\n"
        f"\\date{{\\today}}\n"
    )


# ---------------------------------------------------------------------------
# Document Assembly
# ---------------------------------------------------------------------------

def assemble_document(
    preamble: str,
    sections: list[tuple[str, str]],
    *,
    abstract: str | None = None,
    bibliography: str | None = None,
    bib_style: str = "elsarticle-num",
    appendices: list[tuple[str, str]] | None = None,
) -> str:
    """Assemble a complete LaTeX document from preamble + sections.

    Parameters
    ----------
    preamble : str
        LaTeX preamble (everything before ``\\begin{document}``).
    sections : list[tuple[str, str]]
        Ordered list of (section_id, latex_content) tuples.
    abstract : str, optional
        Abstract content (already in LaTeX).
    bibliography : str, optional
        Path to .bib file (without extension).
    bib_style : str
        Bibliography style name.
    appendices : list[tuple[str, str]], optional
        Appendix sections.
    """
    parts: list[str] = []

    # Preamble
    parts.append(preamble.rstrip())
    parts.append("")

    # Begin document
    parts.append("\\begin{document}")
    parts.append("\\maketitle")
    parts.append("")

    # Abstract
    if abstract:
        parts.append("\\begin{abstract}")
        parts.append(abstract.strip())
        parts.append("\\end{abstract}")
        parts.append("")

    # Sections
    for section_id, content in sections:
        parts.append(f"% --- Section: {section_id} ---")
        parts.append(content.strip())
        parts.append("")

    # Appendices
    if appendices:
        parts.append("\\appendix")
        parts.append("")
        for section_id, content in appendices:
            parts.append(f"% --- Appendix: {section_id} ---")
            parts.append(content.strip())
            parts.append("")

    # Bibliography
    if bibliography:
        bib_name = bibliography
        if bib_name.endswith(".bib"):
            bib_name = bib_name[:-4]
        parts.append(f"\\bibliographystyle{{{bib_style}}}")
        parts.append(f"\\bibliography{{{bib_name}}}")
        parts.append("")

    parts.append("\\end{document}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Makefile Generation
# ---------------------------------------------------------------------------

def generate_makefile(config: ProjectConfig) -> str:
    """Generate a Makefile for building the LaTeX project."""
    engine = config.latex_engine
    engine_flag = {
        "pdflatex": "-pdf",
        "xelatex": "-xelatex",
        "lualatex": "-lualatex",
    }.get(engine, "-pdf")

    return (
        f"# Auto-generated Makefile for {config.project_name}\n"
        f"LATEXMK = latexmk\n"
        f"ENGINE_FLAG = {engine_flag}\n"
        f"MAIN = main\n"
        f"\n"
        f".PHONY: all clean\n"
        f"\n"
        f"all: $(MAIN).pdf\n"
        f"\n"
        f"$(MAIN).pdf: $(MAIN).tex\n"
        f"\t$(LATEXMK) $(ENGINE_FLAG) -interaction=nonstopmode $(MAIN).tex\n"
        f"\n"
        f"clean:\n"
        f"\t$(LATEXMK) -C\n"
    )


# ---------------------------------------------------------------------------
# File writing helpers
# ---------------------------------------------------------------------------

def write_main_tex(content: str, output_dir: str | Path) -> Path:
    """Write ``main.tex`` to the output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tex_path = out / "main.tex"
    tex_path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", tex_path)
    return tex_path


def write_makefile(content: str, output_dir: str | Path) -> Path:
    """Write ``Makefile`` to the output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    makefile_path = out / "Makefile"
    makefile_path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", makefile_path)
    return makefile_path
