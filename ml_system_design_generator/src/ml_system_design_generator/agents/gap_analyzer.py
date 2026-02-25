"""GapAnalyzer agent — identifies gaps in source material."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import GapReport, ProjectConfig

SYSTEM_PROMPT = """\
You are a gap analysis specialist for ML system design documents.

Given document summaries and design document requirements, identify gaps in
the source material. What information is needed but not present? What
assumptions must be made?

Return a JSON object matching the GapReport schema:
{{
  "gaps": [
    {{
      "area": "Data Pipeline",
      "description": "No information about data freshness requirements",
      "severity": "warning",
      "suggestion": "Define SLA for data pipeline latency"
    }}
  ],
  "recommendations": [
    "Gather input on data freshness requirements",
    "Define model retraining frequency"
  ],
  "confidence_score": 0.7
}}

Severity levels: info, warning, error, critical.
confidence_score: 0.0 (no understanding) to 1.0 (complete understanding).

Return ONLY valid JSON. No markdown fences or explanations.
"""


def make_gap_analyzer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the GapAnalyzer agent."""
    agent = autogen.AssistantAgent(
        name="GapAnalyzer",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("gap_analyzer", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = GapReport
    return agent
