"""FigureSuggestionAgent — suggests figures/plots the author should create."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import FigureSuggestionList, ProjectConfig

SYSTEM_PROMPT = """\
You are a figure suggestion specialist for LaTeX research articles.

Given a LaTeX section, identify opportunities for figures or plots that would \
improve the presentation. Focus on data, results, or methods described in text \
that lack visualization.

For each suggestion, provide:
- description: What to plot or show (be specific).
- rationale: Why this figure would improve the section.
- plot_type: The type of visualization (line plot, bar chart, heatmap, schematic, diagram, etc.).
- data_source: What data to use for the figure.
- suggested_caption: A draft caption.

Constraints:
- Only suggest figures for content that lacks adequate visualization.
- Do not suggest figures for purely textual sections with no data or results \
(e.g. abstract-only sections, acknowledgements).
- Do not duplicate existing figures in the section.
- Respect the maximum number of suggestions specified in the prompt.

Return a JSON object matching the FigureSuggestionList schema:
{"suggestions": [{"description": "...", "rationale": "...", "plot_type": "...", "data_source": "...", "suggested_caption": "..."}]}

If no figures are needed, return: {"suggestions": []}
"""


def make_figure_suggester(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the FigureSuggester agent."""
    max_n = config.figure_suggestion_max
    prompt = SYSTEM_PROMPT + f"\nSuggest at most {max_n} figures per section.\n"

    agent = autogen.AssistantAgent(
        name="FigureSuggester",
        system_message=prompt,
        llm_config=build_role_llm_config("figure_suggester", config),
    )
    agent.llm_config["response_format"] = FigureSuggestionList
    return agent
