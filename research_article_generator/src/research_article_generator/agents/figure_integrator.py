"""FigureIntegrator agent — handles figure placement, sizing, and cross-refs."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT = """\
You are a figure integration specialist for LaTeX research articles.

You receive the full LaTeX document and optimize figure handling:
- Ensure \\begin{figure} environments have appropriate placement specifiers ([htbp])
- Set appropriate \\includegraphics width/height for the journal template
- Verify all \\label{} and \\ref{} pairs for figures are correct
- Ensure captions are well-formatted and positioned correctly
- Add \\centering where appropriate

CRITICAL RULES:
- NEVER change \\includegraphics file paths
- NEVER alter figure captions' semantic content (only formatting)
- NEVER remove or rename \\label{} values
- Preserve all other content exactly

Output ONLY the modified LaTeX. No explanations.
"""


def make_figure_integrator(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the FigureIntegrator agent."""
    return autogen.AssistantAgent(
        name="FigureIntegrator",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("figure_integrator", config),
    )
