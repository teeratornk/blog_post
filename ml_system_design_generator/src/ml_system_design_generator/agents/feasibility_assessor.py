"""FeasibilityAssessor agent — evaluates feasibility of selected ML opportunities."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import FeasibilityReport, ProjectConfig

SYSTEM_PROMPT = """\
You are an ML engineering feasibility analyst. Given selected ML opportunities \
and project context (infrastructure, tech stack, team size, timeline, constraints), \
assess feasibility across these dimensions:

- Data Availability
- Compute Resources
- Team Skills
- Timeline
- Integration
- Cost
- Regulatory
- Technical Risk

For each dimension, assign a risk_level: none | low | medium | high | critical.
Set overall_feasible=false ONLY when there are critical blockers that cannot be \
mitigated. If everything looks achievable, say so clearly.

Return ONLY valid JSON matching the FeasibilityReport schema:
{{
  "selected_opportunities": ["opportunity_id_1"],
  "items": [
    {{
      "area": "Data Availability",
      "assessment": "Sufficient historical data exists in the data lake.",
      "risk_level": "low",
      "mitigation": ""
    }}
  ],
  "overall_feasible": true,
  "overall_summary": "Brief overall feasibility summary.",
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}}

No markdown fences or explanations.
"""


def make_feasibility_assessor(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the FeasibilityAssessor agent."""
    agent = autogen.AssistantAgent(
        name="FeasibilityAssessor",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("feasibility_assessor", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = FeasibilityReport
    return agent
