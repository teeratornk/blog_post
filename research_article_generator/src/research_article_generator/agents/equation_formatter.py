"""EquationFormatter agent — ensures equation consistency across the document."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT = """\
You are an equation formatting specialist for LaTeX research articles.

Given a LaTeX section, ensure equation consistency:
- All display equations use consistent environments (equation vs align vs gather).
- Equation numbering is correct and sequential.
- Cross-references (\\eqref, \\ref) point to valid labels.
- Notation is consistent throughout (same symbol for same quantity).
- Spacing and formatting follow journal conventions.

Constraints:
- Keep the mathematical content of every equation unchanged.
- Keep existing \\label{} values unchanged (you may add missing ones).
- Only adjust formatting, environments, and spacing.
- Keep all \\cite{} references exactly as provided.

Return the modified LaTeX only, without explanations.
"""


def make_equation_formatter(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the EquationFormatter agent."""
    return autogen.AssistantAgent(
        name="EquationFormatter",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("equation_formatter", config),
    )
