"""DesignPlanner agent — plans the design document structure."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import DesignPlan, ProjectConfig

SYSTEM_PROMPT = """\
You are a design document planner for ML system designs.

Given the template style, understanding report, and project config, produce a
DesignPlan with concrete sections adapted to the specific domain.

{style_context_block}\
Output ONLY a valid JSON object matching the DesignPlan schema:
{{
  "title": "ML System Design: Project Title",
  "style": "amazon_6page",
  "sections": [
    {{
      "section_id": "situation",
      "title": "Situation / Problem Statement",
      "content_guidance": "Describe the current operational challenges...",
      "estimated_pages": 0.5,
      "depends_on": []
    }}
  ],
  "total_estimated_pages": 6.0,
  "page_budget": 6
}}

Adapt the template sections to the specific domain described in the source
documents. Add domain-specific guidance in content_guidance.
"""


def make_design_planner(
    config: ProjectConfig,
    *,
    style_context: str = "",
) -> autogen.AssistantAgent:
    """Create the DesignPlanner agent."""
    if style_context:
        block = (
            "The target design document style is shown below. Adapt the sections\n"
            "to match this template while incorporating domain-specific content.\n\n"
            f"{style_context}\n\n"
        )
    else:
        block = ""

    agent = autogen.AssistantAgent(
        name="DesignPlanner",
        system_message=SYSTEM_PROMPT.format(style_context_block=block),
        llm_config=build_role_llm_config("design_planner", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = DesignPlan
    return agent
