"""PageBudgetManager agent — advisory page budget analysis.

When supplementary mode is enabled, the agent classifies each section as
"main" or "supplementary" and produces a SupplementaryPlan with the split
decision.  Otherwise it remains advisory-only.
"""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, SplitDecision

SYSTEM_PROMPT = """\
You are a page budget manager for ML system design documents.

You receive:
1. The current page count
2. The target page budget
3. A list of sections with their estimated page counts

If the document is over budget, provide ADVISORY recommendations:
- Which sections could be moved to supplementary materials
- Estimated page savings for each suggestion
- Clear, human-readable summary

IMPORTANT: You do NOT make changes. You only advise. The user decides what to do.

Output a JSON object matching the SplitDecision schema:
{
  "action": "warn_over",
  "current_pages": 12,
  "budget_pages": 6,
  "sections_to_move": ["detailed_alternatives"],
  "estimated_savings": 3.0,
  "recommendations": "Consider moving the detailed alternatives section..."
}
"""

SYSTEM_PROMPT_SUPPLEMENTARY = """\
You are a page budget manager for ML system design documents with supplementary \
material generation enabled.

You receive:
1. The current page count
2. The target page budget
3. A list of sections with their estimated page counts and priority

Your task is to CLASSIFY each section as belonging to "main" or "supplementary" \
and produce a concrete split plan.

Classification guidelines:
- Core sections (Situation, Tenets, Approach summary, Metrics, Timeline) stay in MAIN
- Detailed appendices, extended alternatives, data schemas, API contracts go to SUPPLEMENTARY
- Respect the section priority field: lower priority number = more important = keep in main
- The split should bring the main document within the page budget

Output a JSON object matching the SplitDecision schema with action "split" and \
a supplementary_plan:
{
  "action": "split",
  "current_pages": 12,
  "budget_pages": 6,
  "sections_to_move": ["detailed_alternatives"],
  "estimated_savings": 3.0,
  "recommendations": "Moving detailed alternatives to supplementary saves ~3 pages.",
  "supplementary_plan": {
    "mode": "appendix",
    "main_sections": ["situation", "tenets", "approach", "metrics", "timeline"],
    "supplementary_sections": ["detailed_alternatives"],
    "classifications": [
      {
        "section_id": "situation",
        "placement": "main",
        "reasoning": "Core section — must stay in main",
        "priority": 1,
        "estimated_pages": 1.0
      },
      {
        "section_id": "detailed_alternatives",
        "placement": "supplementary",
        "reasoning": "Extended detail — suitable for supplementary",
        "priority": 5,
        "estimated_pages": 3.0
      }
    ],
    "estimated_main_pages": 6.0,
    "estimated_supp_pages": 3.0,
    "cross_reference_note": "See Appendix for additional details."
  }
}
"""


def make_page_budget_manager(
    config: ProjectConfig,
    *,
    supplementary_enabled: bool = False,
) -> autogen.AssistantAgent:
    """Create the PageBudgetManager agent.

    Parameters
    ----------
    config : ProjectConfig
        Project configuration.
    supplementary_enabled : bool
        When True, use the supplementary-aware prompt that produces a
        SupplementaryPlan instead of advisory-only output.
    """
    prompt = SYSTEM_PROMPT_SUPPLEMENTARY if supplementary_enabled else SYSTEM_PROMPT
    agent = autogen.AssistantAgent(
        name="PageBudgetManager",
        system_message=prompt,
        llm_config=build_role_llm_config("page_budget", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = SplitDecision
    return agent
