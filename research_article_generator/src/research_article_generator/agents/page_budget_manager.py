"""PageBudgetManager agent — advisory page budget analysis.

MVP: advisory only — reports page count, flags over-budget, recommends which
sections to move, but does NOT auto-split. User decides.
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


def make_page_budget_manager(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the PageBudgetManager agent."""
    agent = autogen.AssistantAgent(
        name="PageBudgetManager",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("page_budget", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = SplitDecision
    return agent
