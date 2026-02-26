"""OpportunityAnalyzer agent — proposes ML solution directions from source docs."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import OpportunityReport, ProjectConfig

SYSTEM_PROMPT = """\
You are an ML solutions architect. Given document summaries, gap analysis, and \
project context, propose up to {max_opportunities} concrete ML solution directions.

Each opportunity should be:
- A distinct, actionable ML approach grounded in the source evidence
- Categorised (e.g. classification, anomaly_detection, forecasting, agentic_ai, \
optimisation, recommendation, nlp, computer_vision, etc.)
- Rated for estimated complexity (low | medium | high) and potential impact \
(low | medium | high)

Return ONLY valid JSON matching the OpportunityReport schema:
{{
  "opportunities": [
    {{
      "opportunity_id": "slug_id",
      "title": "Human-Readable Title",
      "category": "category_slug",
      "description": "2-3 sentence description of the approach.",
      "source_evidence": ["Doc Title 1", "Doc Title 2"],
      "estimated_complexity": "medium",
      "potential_impact": "high"
    }}
  ],
  "summary": "Brief overall summary of discovered opportunities."
}}

No markdown fences or explanations.
"""


def make_opportunity_analyzer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the OpportunityAnalyzer agent."""
    prompt = SYSTEM_PROMPT.format(max_opportunities=config.max_opportunities)
    agent = autogen.AssistantAgent(
        name="OpportunityAnalyzer",
        system_message=prompt,
        llm_config=build_role_llm_config("opportunity_analyzer", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = OpportunityReport
    return agent
