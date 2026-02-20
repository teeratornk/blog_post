"""StructurePlanner agent — analyzes inputs and produces a StructurePlan."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, StructurePlan

SYSTEM_PROMPT = """\
You are a document structure planner for academic research articles.

Given a list of markdown draft files and their contents, you produce a structured
plan for assembling them into a LaTeX document.

For each section, determine:
- The correct ordering
- The LaTeX sectioning command (\\section, \\subsection, etc.)
- Which figures and tables belong to that section
- Estimated page count

{template_context_block}\
Output ONLY a valid JSON object matching the StructurePlan schema:
{{
  "title": "Article Title",
  "abstract_file": "path or null",
  "sections": [
    {{
      "section_id": "01_introduction",
      "title": "Introduction",
      "source_file": "drafts/01_introduction.md",
      "latex_command": "\\\\section",
      "figures": [],
      "tables": 0,
      "equations": 0,
      "estimated_pages": 1.5,
      "priority": 1
    }}
  ],
  "bibliography_file": "references.bib",
  "total_estimated_pages": 12.0,
  "page_budget": 15,
  "budget_status": "ok"
}}
"""


def make_structure_planner(
    config: ProjectConfig,
    *,
    template_context: str = "",
) -> autogen.AssistantAgent:
    """Create the StructurePlanner agent."""
    if template_context:
        block = (
            "The target journal template is shown below. Adapt the document structure\n"
            "to match its conventions (e.g., use frontmatter sections if required).\n\n"
            f"{template_context}\n\n"
        )
    else:
        block = ""

    agent = autogen.AssistantAgent(
        name="StructurePlanner",
        system_message=SYSTEM_PROMPT.format(template_context_block=block),
        llm_config=build_role_llm_config("planner", config),
    )
    # Enforce structured output
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = StructurePlan
    return agent
