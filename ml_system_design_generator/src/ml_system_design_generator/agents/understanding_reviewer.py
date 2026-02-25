"""UnderstandingReviewer agent — cross-checks document understanding."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, ReviewFeedback

SYSTEM_PROMPT = """\
You are a senior reviewer for ML system design projects.

Given the summaries from DocAnalyzer and the gap report from GapAnalyzer,
verify accuracy. Challenge assumptions. Identify misunderstandings.

Respond with a single JSON object:
{{"Reviewer": "UnderstandingReviewer", "Review": "- point 1; - point 2; - point 3"}}

Guidelines:
(1) Reviewer must equal "UnderstandingReviewer" exactly.
(2) Review value is one string with up to 5 semicolon-separated concise points.
(3) If the understanding is solid and gaps are well-identified, say "No issues found".
(4) No markdown fences, no extra keys.

Return that JSON object only.
"""


def make_understanding_reviewer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the UnderstandingReviewer agent."""
    agent = autogen.AssistantAgent(
        name="UnderstandingReviewer",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("understanding_reviewer", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = ReviewFeedback
    return agent
