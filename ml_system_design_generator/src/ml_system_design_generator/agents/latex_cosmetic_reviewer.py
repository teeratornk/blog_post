"""LaTeXCosmeticReviewer agent — reviews assembled LaTeX for formatting issues."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, ReviewFeedback


_SYSTEM_PROMPT = (
    "You are a LaTeX formatting reviewer for ML system design documents. "
    "Review the assembled LaTeX for cosmetic and structural issues:\n"
    "- Section hierarchy consistency (\\section → \\subsection → \\subsubsection)\n"
    "- Table formatting: booktabs rules (\\toprule/\\midrule/\\bottomrule), "
    "caption placement (above tabular), column width (avoid page overflow)\n"
    "- Float placement: avoid large whitespace gaps between floats\n"
    "- Typography consistency: consistent use of \\textbf, \\emph, list styles\n"
    "- Page overflow risks: tables or figures wider than \\textwidth\n\n"
    "Respond with a single JSON object: "
    '{"Reviewer": "LaTeXCosmeticReviewer", "Review": "- issue 1; - issue 2; - issue 3"}. '
    "Guidelines: (1) Reviewer must equal your agent name exactly; "
    "(2) Review value is one string containing up to 5 semicolon-separated concise actionable points; "
    "(3) If the LaTeX looks clean, respond with Review = 'No issues found.'; "
    "(4) Focus on ERROR-level issues that affect readability — ignore minor style preferences; "
    "(5) No markdown fences, no lists/arrays, no extra keys. Return that JSON object only."
)


def make_latex_cosmetic_reviewer(
    config: ProjectConfig,
) -> autogen.AssistantAgent | None:
    """Create the LaTeXCosmeticReviewer agent if enabled."""
    if not config.enabled_reviewers.get("LaTeXCosmeticReviewer", False):
        return None
    agent = autogen.AssistantAgent(
        name="LaTeXCosmeticReviewer",
        llm_config=build_role_llm_config("latex_cosmetic_reviewer", config),
        system_message=_SYSTEM_PROMPT,
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = ReviewFeedback
    return agent
