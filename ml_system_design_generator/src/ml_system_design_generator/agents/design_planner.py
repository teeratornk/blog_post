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


_AUDIENCE_GUIDANCE = {
    "leadership": (
        "TARGET AUDIENCE: leadership\n"
        "Write for senior leadership. Keep sections brief and outcome-focused.\n"
        "Minimize subsections. Focus on business impact, key decisions, and risks.\n"
        "Omit low-level implementation details — reference a Technical Supplement.\n"
        "Allocate page budgets tightly: the Approach section should be at most 1.5\n"
        "pages (use tables for architecture summaries instead of verbose prose).\n"
        "Prefer fewer, denser pages over splitting content into an appendix.\n\n"
    ),
    "mixed": (
        "TARGET AUDIENCE: mixed\n"
        "Balanced depth suitable for mixed engineering/leadership audience.\n\n"
    ),
    "engineering": (
        "TARGET AUDIENCE: engineering\n"
        "Write for engineering teams. Include comprehensive subsections.\n"
        "Add implementation specifics, edge cases, failure modes, code-level\n"
        "architecture, API contracts, and detailed data schemas.\n\n"
    ),
}


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

    block += _AUDIENCE_GUIDANCE.get(config.target_audience, _AUDIENCE_GUIDANCE["mixed"])

    agent = autogen.AssistantAgent(
        name="DesignPlanner",
        system_message=SYSTEM_PROMPT.format(style_context_block=block),
        llm_config=build_role_llm_config("design_planner", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = DesignPlan
    return agent
