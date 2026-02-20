"""LaTeX document assembly: preamble generation, multi-file output, Makefile.

Outputs a multi-file project::

    output/
    ├── main.tex              # skeleton: preamble + \\input{} calls
    ├── sections/
    │   ├── 01_introduction.tex
    │   ├── 02_methodology.tex
    │   └── ...
    ├── figures/
    ├── references.bib
    └── Makefile
"""

from __future__ import annotations

import logging
import re
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


def summarize_template(config: ProjectConfig) -> str:
    """Return a human-readable summary of the LaTeX template for LLM agents.

    Extracts document class, packages, frontmatter presence, citation style,
    and title mechanism via regex.  Appends the full raw template so the LLM
    can read it directly.  Returns a short fallback when no template is found.
    """
    try:
        raw = _load_template(config.template, config.template_file)
    except FileNotFoundError:
        path_hint = f" (custom: {config.template_file})" if config.template_file else ""
        return f"(No template file found for '{config.template}'{path_hint}; using minimal preamble.)"

    parts: list[str] = [f"=== LaTeX Template: {config.template} ==="]

    # Document class + options
    doc_class = ""
    m = re.search(r"\\documentclass\s*(\[[^\]]*\])?\s*\{([^}]+)\}", raw)
    if m:
        opts = m.group(1) or ""
        doc_class = m.group(2)
        parts.append(f"Document class: {doc_class} {opts}".strip())

    # Packages
    pkgs: list[str] = []
    for pm in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", raw):
        pkgs.extend(p.strip() for p in pm.group(1).split(","))
    if pkgs:
        parts.append(f"Packages: {', '.join(pkgs)}")

    # Frontmatter / title mechanism detection
    has_frontmatter = r"\begin{frontmatter}" in raw
    is_revtex = "revtex" in doc_class.lower()
    if has_frontmatter:
        parts.append(
            r"Title/structure: \begin{frontmatter}...\end{frontmatter} "
            "(abstract goes inside frontmatter)"
        )
    elif is_revtex:
        parts.append(
            r"Title/structure: revtex (\title{} and \author{} after "
            r"\begin{document}; title rendered automatically, no \maketitle)"
        )
    else:
        parts.append(r"Title/structure: \maketitle (standard)")

    # Citation style hint
    if "natbib" in raw:
        parts.append(r"Citations: natbib (prefer \citep{} and \citet{} over \cite{})")
    elif "biblatex" in raw:
        parts.append(r"Citations: biblatex (use \autocite{})")
    elif "cite" in pkgs:
        parts.append(r"Citations: cite package (use \cite{})")
    elif is_revtex:
        parts.append(r"Citations: built-in BibTeX support (use \cite{})")
    else:
        parts.append(r"Citations: default (use \cite{})")

    # Frontmatter warning
    if has_frontmatter:
        parts.append(r"NOTE: This template uses frontmatter. Do NOT use \maketitle.")

    # Raw content
    parts.append("")
    parts.append("Full template content:")
    parts.append(raw.rstrip())

    return "\n".join(parts)


_TIKZ_PACKAGES = (
    "\\usepackage{tikz}\n"
    "\\usetikzlibrary{arrows.meta,positioning,shapes.geometric,calc,fit,backgrounds,decorations.pathreplacing}\n"
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

    # Inject TikZ packages when enabled
    if config.tikz_enabled:
        preamble = _inject_tikz_packages(preamble)

    return preamble


def _inject_tikz_packages(preamble: str) -> str:
    """Insert TikZ package declarations into a template-based preamble.

    Inserts before ``\\begin{frontmatter}`` when present (elsarticle),
    otherwise before ``\\begin{document}`` if present, otherwise appends.
    """
    for marker in ("\\begin{frontmatter}", "\\begin{document}"):
        if marker in preamble:
            idx = preamble.index(marker)
            return preamble[:idx] + _TIKZ_PACKAGES + "\n" + preamble[idx:]
    return preamble.rstrip() + "\n" + _TIKZ_PACKAGES


def _generate_minimal_preamble(config: ProjectConfig) -> str:
    """Generate a minimal preamble when no template is found."""
    engine = config.latex_engine
    font_pkg = ""
    if engine in ("xelatex", "lualatex"):
        font_pkg = "\\usepackage{fontspec}\n"

    tikz_pkg = ""
    if config.tikz_enabled:
        tikz_pkg = _TIKZ_PACKAGES

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
        f"{tikz_pkg}"
        f"\n"
        f"\\title{{{config.project_name}}}\n"
        f"\\date{{\\today}}\n"
    )


# ---------------------------------------------------------------------------
# Document Assembly (multi-file: main.tex + sections/*.tex)
# ---------------------------------------------------------------------------

def assemble_main_tex(
    preamble: str,
    section_ids: list[str],
    *,
    abstract: str | None = None,
    bibliography: str | None = None,
    bib_style: str = "elsarticle-num",
    appendix_ids: list[str] | None = None,
) -> str:
    """Assemble the ``main.tex`` skeleton with ``\\input{}`` calls.

    Individual section content lives in ``sections/<section_id>.tex``.

    Handles elsarticle-style templates that include
    ``\\begin{frontmatter}...\\end{frontmatter}`` — the frontmatter block
    is moved inside ``\\begin{document}`` and ``\\maketitle`` is omitted.
    """
    parts: list[str] = []

    # Check if preamble contains \begin{frontmatter} (elsarticle pattern).
    # If so, split: everything before frontmatter is the true preamble,
    # and the frontmatter block goes inside \begin{document}.
    frontmatter_block = ""
    actual_preamble = preamble
    if "\\begin{frontmatter}" in preamble:
        idx_start = preamble.index("\\begin{frontmatter}")
        idx_end = preamble.index("\\end{frontmatter}") + len("\\end{frontmatter}")
        frontmatter_block = preamble[idx_start:idx_end].strip()
        actual_preamble = (preamble[:idx_start] + preamble[idx_end:]).strip()

    # Preamble (packages, documentclass, etc.)
    parts.append(actual_preamble.rstrip())
    parts.append("")

    # Begin document
    parts.append("\\begin{document}")

    if frontmatter_block:
        # Insert abstract into frontmatter if provided
        if abstract:
            # Insert abstract before \end{frontmatter}
            fm_end = frontmatter_block.index("\\end{frontmatter}")
            frontmatter_block = (
                frontmatter_block[:fm_end]
                + "\\begin{abstract}\n"
                + abstract.strip() + "\n"
                + "\\end{abstract}\n\n"
                + frontmatter_block[fm_end:]
            )
        parts.append(frontmatter_block)
        parts.append("")
    else:
        parts.append("\\maketitle")
        parts.append("")
        # Abstract (non-frontmatter templates)
        if abstract:
            parts.append("\\begin{abstract}")
            parts.append(abstract.strip())
            parts.append("\\end{abstract}")
            parts.append("")

    # Section inputs
    for section_id in section_ids:
        parts.append(f"\\input{{sections/{section_id}}}")
    parts.append("")

    # Appendices
    if appendix_ids:
        parts.append("\\appendix")
        for section_id in appendix_ids:
            parts.append(f"\\input{{sections/{section_id}}}")
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


def assemble_supplementary_tex(
    preamble: str,
    supplementary_section_ids: list[str],
    *,
    project_name: str = "",
    bibliography: str | None = None,
    bib_style: str = "elsarticle-num",
    main_doc: str = "main",
) -> str:
    """Assemble ``supplementary.tex`` for standalone supplementary materials.

    Uses the same document class and packages as the main document but strips
    frontmatter and adds ``xr-hyper`` cross-references back to ``main.tex``.

    Parameters
    ----------
    preamble : str
        The preamble (from ``generate_preamble``).
    supplementary_section_ids : list[str]
        Section IDs to include in the supplementary document.
    project_name : str
        Project name for the title.
    bibliography : str | None
        Bibliography file stem (without .bib).
    bib_style : str
        Bibliography style.
    main_doc : str
        Name of the main document (without extension) for cross-refs.
    """
    parts: list[str] = []

    # Strip frontmatter from preamble if present (elsarticle pattern)
    actual_preamble = preamble
    if "\\begin{frontmatter}" in preamble:
        idx_start = preamble.index("\\begin{frontmatter}")
        idx_end = preamble.index("\\end{frontmatter}") + len("\\end{frontmatter}")
        actual_preamble = (preamble[:idx_start] + preamble[idx_end:]).strip()

    parts.append(actual_preamble.rstrip())

    # Add xr-hyper for cross-referencing back to main document
    parts.append("\\usepackage{xr-hyper}")
    parts.append(f"\\externaldocument{{{main_doc}}}")
    parts.append("")

    # Override title for supplementary
    title = f"Supplementary Materials: {project_name}" if project_name else "Supplementary Materials"
    parts.append(f"\\title{{{title}}}")
    parts.append("")

    # Begin document
    parts.append("\\begin{document}")
    parts.append("\\maketitle")
    parts.append("")

    # Section inputs
    for section_id in supplementary_section_ids:
        parts.append(f"\\input{{sections/{section_id}}}")
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


def write_supplementary_tex(content: str, output_dir: str | Path) -> Path:
    """Write ``supplementary.tex`` to the output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    tex_path = out / "supplementary.tex"
    tex_path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", tex_path)
    return tex_path


def assemble_document(
    preamble: str,
    sections: list[tuple[str, str]],
    *,
    abstract: str | None = None,
    bibliography: str | None = None,
    bib_style: str = "elsarticle-num",
    appendices: list[tuple[str, str]] | None = None,
) -> str:
    """Assemble a complete single-file LaTeX document (legacy/fallback).

    Prefer :func:`assemble_main_tex` + :func:`write_section_files` for
    multi-file output.
    """
    parts: list[str] = []

    # Handle frontmatter (elsarticle) the same way as assemble_main_tex
    frontmatter_block = ""
    actual_preamble = preamble
    if "\\begin{frontmatter}" in preamble:
        idx_start = preamble.index("\\begin{frontmatter}")
        idx_end = preamble.index("\\end{frontmatter}") + len("\\end{frontmatter}")
        frontmatter_block = preamble[idx_start:idx_end].strip()
        actual_preamble = (preamble[:idx_start] + preamble[idx_end:]).strip()

    parts.append(actual_preamble.rstrip())
    parts.append("")
    parts.append("\\begin{document}")

    if frontmatter_block:
        if abstract:
            fm_end = frontmatter_block.index("\\end{frontmatter}")
            frontmatter_block = (
                frontmatter_block[:fm_end]
                + "\\begin{abstract}\n"
                + abstract.strip() + "\n"
                + "\\end{abstract}\n\n"
                + frontmatter_block[fm_end:]
            )
        parts.append(frontmatter_block)
        parts.append("")
    else:
        parts.append("\\maketitle")
        parts.append("")
        if abstract:
            parts.append("\\begin{abstract}")
            parts.append(abstract.strip())
            parts.append("\\end{abstract}")
            parts.append("")

    for section_id, content in sections:
        parts.append(f"% --- Section: {section_id} ---")
        parts.append(content.strip())
        parts.append("")

    if appendices:
        parts.append("\\appendix")
        parts.append("")
        for section_id, content in appendices:
            parts.append(f"% --- Appendix: {section_id} ---")
            parts.append(content.strip())
            parts.append("")

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

def generate_makefile(config: ProjectConfig, *, has_supplementary: bool = False) -> str:
    """Generate a Makefile for building the LaTeX project.

    Parameters
    ----------
    config : ProjectConfig
        Project configuration.
    has_supplementary : bool
        When True, add a ``supplementary.pdf`` target.
    """
    engine = config.latex_engine
    engine_flag = {
        "pdflatex": "-pdf",
        "xelatex": "-xelatex",
        "lualatex": "-lualatex",
    }.get(engine, "-pdf")

    all_targets = "$(MAIN).pdf"
    supp_block = ""
    if has_supplementary:
        all_targets += " $(SUPP).pdf"
        supp_block = (
            f"SUPP = supplementary\n"
            f"\n"
            f"$(SUPP).pdf: $(SUPP).tex sections/*.tex\n"
            f"\t$(LATEXMK) $(ENGINE_FLAG) -interaction=nonstopmode $(SUPP).tex\n"
            f"\n"
        )

    makefile = (
        f"# Auto-generated Makefile for {config.project_name}\n"
        f"LATEXMK = latexmk\n"
        f"ENGINE_FLAG = {engine_flag}\n"
        f"MAIN = main\n"
    )

    if has_supplementary:
        makefile += f"SUPP = supplementary\n"

    makefile += (
        f"\n"
        f".PHONY: all clean\n"
        f"\n"
        f"all: {all_targets}\n"
        f"\n"
        f"$(MAIN).pdf: $(MAIN).tex sections/*.tex\n"
        f"\t$(LATEXMK) $(ENGINE_FLAG) -interaction=nonstopmode $(MAIN).tex\n"
        f"\n"
    )

    if has_supplementary:
        makefile += (
            f"$(SUPP).pdf: $(SUPP).tex sections/*.tex\n"
            f"\t$(LATEXMK) $(ENGINE_FLAG) -interaction=nonstopmode $(SUPP).tex\n"
            f"\n"
        )

    makefile += (
        f"clean:\n"
        f"\t$(LATEXMK) -C\n"
    )

    return makefile


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


def write_section_file(
    section_id: str,
    content: str,
    output_dir: str | Path,
) -> Path:
    """Write a single section file to ``output_dir/sections/<section_id>.tex``."""
    out = Path(output_dir) / "sections"
    out.mkdir(parents=True, exist_ok=True)
    tex_path = out / f"{section_id}.tex"
    tex_path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", tex_path)
    return tex_path


def write_section_files(
    sections: dict[str, str],
    output_dir: str | Path,
) -> list[Path]:
    """Write all section files to ``output_dir/sections/``."""
    paths: list[Path] = []
    for section_id, content in sections.items():
        paths.append(write_section_file(section_id, content, output_dir))
    return paths


def write_makefile(content: str, output_dir: str | Path) -> Path:
    """Write ``Makefile`` to the output directory."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    makefile_path = out / "Makefile"
    makefile_path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", makefile_path)
    return makefile_path
