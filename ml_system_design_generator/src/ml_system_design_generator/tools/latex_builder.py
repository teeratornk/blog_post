"""LaTeX document assembly: preamble generation, multi-file output.

Outputs a multi-file project::

    output/
    +-- main.tex              # skeleton: preamble + \\input{} calls
    +-- sections/
    |   +-- situation.tex
    |   +-- approach.tex
    |   +-- ...
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "preamble_templates"


def _load_preamble_template(template_file: str | None = None) -> str:
    """Load the design doc preamble template."""
    if template_file:
        p = Path(template_file)
        if p.exists():
            return p.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Custom template not found: {p}")

    default = TEMPLATES_DIR / "design_doc.tex"
    if default.exists():
        return default.read_text(encoding="utf-8")

    raise FileNotFoundError(f"Preamble template not found: {default}")


def generate_preamble(
    title: str = "",
    author: str = "",
    template_file: str | None = None,
) -> str:
    """Generate the document preamble from template.

    Replaces ``{{TITLE}}`` and ``{{AUTHOR}}`` placeholders.
    """
    raw = _load_preamble_template(template_file)
    if title:
        raw = raw.replace("{{TITLE}}", title)
    raw = raw.replace("{{AUTHOR}}", author or "ML System Design Generator")
    return raw


def assemble_main_tex(
    preamble: str,
    section_ids: list[str],
    *,
    title: str = "",
    appendix_ids: list[str] | None = None,
) -> str:
    """Assemble the main.tex skeleton with preamble and \\input{} calls.

    Parameters
    ----------
    appendix_ids : list[str] | None
        Section IDs to include after ``\\appendix``.  These are excluded
        from the main body even if they also appear in *section_ids*.
    """
    appendix_set = set(appendix_ids or [])
    main_ids = [s for s in section_ids if s not in appendix_set]

    parts: list[str] = [preamble]

    parts.append("")
    parts.append("\\begin{document}")
    parts.append("")

    if title:
        parts.append("\\maketitle")
        parts.append("\\thispagestyle{fancy}")
        parts.append("")

    for section_id in main_ids:
        parts.append(f"\\input{{sections/{section_id}}}")

    if appendix_ids:
        parts.append("")
        parts.append("\\appendix")
        for section_id in appendix_ids:
            parts.append(f"\\input{{sections/{section_id}}}")

    parts.append("")
    parts.append("\\end{document}")
    parts.append("")

    return "\n".join(parts)


def assemble_supplementary_tex(
    preamble: str,
    section_ids: list[str],
    project_name: str = "",
) -> str:
    """Assemble a standalone supplementary materials document."""
    parts: list[str] = [preamble]

    parts.append("")
    parts.append("\\begin{document}")
    parts.append("")

    supp_title = f"Supplementary Materials: {project_name}" if project_name else "Supplementary Materials"
    parts.append(f"\\title{{{supp_title}}}")
    parts.append("\\maketitle")
    parts.append("")

    for section_id in section_ids:
        parts.append(f"\\input{{sections/{section_id}}}")

    parts.append("")
    parts.append("\\end{document}")
    parts.append("")

    return "\n".join(parts)


def write_supplementary_tex(content: str, output_dir: Path) -> None:
    """Write supplementary.tex to output_dir."""
    path = output_dir / "supplementary.tex"
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", path)


def _strip_safe_zone_markers(latex: str) -> str:
    """Remove SAFE_ZONE annotation markers from final output."""
    lines = []
    for line in latex.splitlines():
        stripped = line.strip()
        if stripped in ("%% SAFE_ZONE_START", "%% SAFE_ZONE_END"):
            continue
        lines.append(line)
    return "\n".join(lines)


def write_section_files(section_latex: dict[str, str], output_dir: Path) -> None:
    """Write individual section .tex files to output_dir/sections/."""
    sections_dir = output_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    for section_id, latex in section_latex.items():
        path = sections_dir / f"{section_id}.tex"
        path.write_text(_strip_safe_zone_markers(latex), encoding="utf-8")
        logger.info("Wrote %s", path)


def write_main_tex(content: str, output_dir: Path) -> None:
    """Write main.tex to output_dir."""
    path = output_dir / "main.tex"
    path.write_text(content, encoding="utf-8")
    logger.info("Wrote %s", path)
