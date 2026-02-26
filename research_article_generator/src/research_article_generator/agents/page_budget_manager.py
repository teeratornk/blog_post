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
You are a page budget manager for academic research articles.

You receive:
1. The current page count
2. The target page budget
3. A list of sections with their estimated page counts

If the document is over budget, provide ADVISORY recommendations:
- Which sections could be moved to supplementary materials
- Which figures could be moved to an appendix
- Estimated page savings for each suggestion
- Clear, human-readable summary

IMPORTANT: You do NOT make changes. You only advise. The user decides what to do.

Output a JSON object matching the SplitDecision schema:
{
  "action": "warn_over",
  "current_pages": 18,
  "budget_pages": 15,
  "sections_to_move": ["06_appendix_proofs"],
  "figures_to_move": ["fig_convergence_detailed"],
  "estimated_savings": 3.5,
  "recommendations": "Consider moving the detailed proofs section..."
}
"""

SYSTEM_PROMPT_SUPPLEMENTARY = """\
You are a page budget manager for academic research articles with supplementary \
material generation enabled.

You receive:
1. The current page count
2. The target page budget
3. A list of sections with their estimated page counts and priority

Your task is to CLASSIFY each section as belonging to "main" or "supplementary" \
and produce a concrete split plan.

Classification guidelines:
- Core contributions (introduction, methodology, key results, conclusions) stay in MAIN
- Extended proofs, derivations, and mathematical details go to SUPPLEMENTARY
- Large tables of raw data or extended numerical results go to SUPPLEMENTARY
- Detailed parameter studies and sensitivity analyses go to SUPPLEMENTARY
- Respect the section priority field: lower priority number = more important = keep in main
- The split should bring the main document within the page budget

Output a JSON object matching the SplitDecision schema with action "split" and \
a supplementary_plan:
{
  "action": "split",
  "current_pages": 18,
  "budget_pages": 15,
  "sections_to_move": ["06_appendix_proofs"],
  "figures_to_move": [],
  "estimated_savings": 3.5,
  "recommendations": "Moving proofs to supplementary saves ~3.5 pages.",
  "supplementary_plan": {
    "mode": "standalone",
    "main_sections": ["01_introduction", "02_methodology", "03_results", "04_conclusions"],
    "supplementary_sections": ["06_appendix_proofs"],
    "supplementary_figures": [],
    "classifications": [
      {
        "section_id": "01_introduction",
        "placement": "main",
        "reasoning": "Core contribution — must stay in main",
        "priority": 1,
        "estimated_pages": 2.0
      },
      {
        "section_id": "06_appendix_proofs",
        "placement": "supplementary",
        "reasoning": "Extended proofs — suitable for supplementary",
        "priority": 5,
        "estimated_pages": 3.5
      }
    ],
    "estimated_main_pages": 14.5,
    "estimated_supp_pages": 3.5,
    "cross_reference_note": "See Supplementary Materials for detailed proofs."
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
