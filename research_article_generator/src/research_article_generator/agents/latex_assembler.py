"""LaTeXAssembler agent — polishes Pandoc-converted LaTeX for journal style.

The LLM receives **already-valid LaTeX** from Pandoc and only refines it:
style adjustments, academic phrasing, environment selection preferences,
template-specific commands.  It must NOT alter read-only zones (math, cites,
labels, figure paths).
"""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT_TEMPLATE = """\
You are a LaTeX assembler for the journal "{journal_name}".

You receive LaTeX that was deterministically converted from Markdown by Pandoc.
Your job is to **polish** this LaTeX for publication quality:
- Improve academic phrasing and transitions between paragraphs
- Adjust style to match {journal_name} conventions
- Select appropriate environments (e.g., prefer \\texttt{{align}} over \\texttt{{equation}} for multi-line math if appropriate)
- Add template-specific commands where needed

CRITICAL RULES — READ-ONLY ZONES:
You MUST preserve the following EXACTLY (do not modify, reorder, or remove):
- All math environments (equation, align, gather, etc.) and inline math ($...$)
- All \\cite{{}} keys — never "fix" citation keys
- All \\label{{}} and \\ref{{}} commands
- All \\includegraphics paths and options
- All table data cells

You may ONLY modify text between %% SAFE_ZONE_START and %% SAFE_ZONE_END markers.
Everything outside those markers must be preserved character-for-character.

Output ONLY the polished LaTeX. No explanations, no markdown fences.
"""


def make_assembler(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the LaTeXAssembler agent."""
    journal = config.journal_name or config.template
    return autogen.AssistantAgent(
        name="LaTeXAssembler",
        system_message=SYSTEM_PROMPT_TEMPLATE.format(journal_name=journal),
        llm_config=build_role_llm_config("assembler", config),
    )
