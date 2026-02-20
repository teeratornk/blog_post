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
Your job is to polish this LaTeX for publication quality:
- Improve academic phrasing and transitions between paragraphs.
- Adjust style to match {journal_name} conventions.
- Select appropriate environments (e.g., prefer \\texttt{{align}} over \\texttt{{equation}} for multi-line math if appropriate).
- Add template-specific commands where needed.

Read-only zones — preserve these exactly (do not modify, reorder, or remove):
- All math environments (equation, align, gather, etc.) and inline math ($...$).
- All \\cite{{}} keys.
- All \\label{{}} and \\ref{{}} commands.
- All \\includegraphics paths and options.
- All table data cells.

You may only modify text between %% SAFE_ZONE_START and %% SAFE_ZONE_END markers.
Everything outside those markers must be preserved character-for-character.

{template_context_block}\
Return the polished LaTeX only, without explanations or markdown fences.
"""


def make_assembler(
    config: ProjectConfig,
    *,
    template_context: str = "",
) -> autogen.AssistantAgent:
    """Create the LaTeXAssembler agent."""
    journal = config.journal_name or config.template
    if template_context:
        block = (
            "The target template is shown below. Use ONLY packages and commands\n"
            "available in this template. Follow its conventions for title,\n"
            "abstract placement, and citation commands.\n\n"
            f"{template_context}\n\n"
        )
    else:
        block = ""

    return autogen.AssistantAgent(
        name="LaTeXAssembler",
        system_message=SYSTEM_PROMPT_TEMPLATE.format(
            journal_name=journal,
            template_context_block=block,
        ),
        llm_config=build_role_llm_config("assembler", config),
    )
