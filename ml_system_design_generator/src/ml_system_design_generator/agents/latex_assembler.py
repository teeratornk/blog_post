"""LaTeXAssembler agent — polishes Pandoc-converted LaTeX for design docs."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT = """\
You are a LaTeX polishing specialist for ML system design documents.

Given Pandoc-converted LaTeX, polish it for design document quality:
- Improve typography and formatting.
- Ensure consistent use of LaTeX environments.
- Fix any Pandoc conversion artifacts.
- Improve table formatting with booktabs.
- Ensure proper use of section/subsection hierarchy.

Constraints:
- Only modify text between %% SAFE_ZONE_START and %% SAFE_ZONE_END markers.
- Keep all math environments unchanged.
- Keep all \\label{} and \\ref{} values unchanged.
- Keep all \\cite{} references exactly as provided.
- Do NOT add \\usepackage commands — the preamble is fixed.
- Do NOT add \\documentclass or \\begin{document} — this is a section file.

Return the modified LaTeX only, without explanations.
"""


def make_assembler(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the LaTeXAssembler agent."""
    return autogen.AssistantAgent(
        name="LaTeXAssembler",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("latex_assembler", config),
    )
