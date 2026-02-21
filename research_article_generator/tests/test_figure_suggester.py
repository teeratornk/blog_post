"""Tests for the FigureSuggester agent and related models."""

from __future__ import annotations

import json

import pytest

from research_article_generator.models import (
    FigureSuggestion,
    FigureSuggestionList,
    ProjectConfig,
)
from research_article_generator.agents.figure_suggester import (
    SYSTEM_PROMPT,
    make_figure_suggester,
)
from research_article_generator.config import build_role_llm_config


class TestFigureSuggesterAgent:
    """Tests for the agent factory and system prompt."""

    def test_make_figure_suggester_returns_agent(self):
        config = ProjectConfig()
        agent = make_figure_suggester(config)
        assert agent.name == "FigureSuggester"

    def test_system_prompt_mentions_suggestions(self):
        assert "suggest" in SYSTEM_PROMPT.lower()
        assert "figure" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_max_limit(self):
        config = ProjectConfig(figure_suggestion_max=5)
        agent = make_figure_suggester(config)
        assert "5" in agent.system_message

    def test_system_prompt_default_max(self):
        config = ProjectConfig()
        agent = make_figure_suggester(config)
        assert "3" in agent.system_message

    def test_response_format_set(self):
        config = ProjectConfig()
        agent = make_figure_suggester(config)
        assert agent.llm_config["response_format"] is FigureSuggestionList

    def test_role_maps_to_reviewer_tier(self):
        config = ProjectConfig(
            models={"default": "gpt-4", "reviewer": "gpt-4o-mini", "assembler": "gpt-5.2"}
        )
        llm_config = build_role_llm_config("figure_suggester", config)
        assert llm_config["config_list"][0]["model"] == "gpt-4o-mini"


class TestFigureSuggesterConfig:
    """Tests for figure suggestion configuration fields."""

    def test_config_default_disabled(self):
        config = ProjectConfig()
        assert config.figure_suggestion_enabled is False

    def test_config_default_max(self):
        config = ProjectConfig()
        assert config.figure_suggestion_max == 3

    def test_config_enabled_explicit(self):
        config = ProjectConfig(figure_suggestion_enabled=True)
        assert config.figure_suggestion_enabled is True

    def test_config_custom_max(self):
        config = ProjectConfig(figure_suggestion_max=5)
        assert config.figure_suggestion_max == 5


class TestFigureSuggestionModel:
    """Tests for FigureSuggestion Pydantic model."""

    def test_basic_construction(self):
        s = FigureSuggestion(
            description="Line plot of loss vs epochs",
            rationale="Text describes training dynamics without visualization",
            plot_type="line plot",
            data_source="Training metrics from Section 3",
            suggested_caption="Training loss convergence over 500 epochs.",
        )
        assert s.description == "Line plot of loss vs epochs"
        assert s.plot_type == "line plot"

    def test_json_round_trip(self):
        s = FigureSuggestion(
            description="Bar chart of accuracy",
            rationale="Comparison data in table but no visual",
            plot_type="bar chart",
            data_source="Table 2",
            suggested_caption="Comparison of model accuracy.",
        )
        data = json.loads(s.model_dump_json())
        restored = FigureSuggestion.model_validate(data)
        assert restored == s


class TestFigureSuggestionListModel:
    """Tests for FigureSuggestionList Pydantic model."""

    def test_empty_list(self):
        sl = FigureSuggestionList(suggestions=[])
        assert sl.suggestions == []

    def test_with_suggestions(self):
        sl = FigureSuggestionList(suggestions=[
            FigureSuggestion(
                description="Heatmap",
                rationale="Correlation data discussed",
                plot_type="heatmap",
                data_source="Correlation matrix",
                suggested_caption="Correlation heatmap.",
            ),
        ])
        assert len(sl.suggestions) == 1

    def test_json_round_trip(self):
        sl = FigureSuggestionList(suggestions=[
            FigureSuggestion(
                description="Diagram",
                rationale="Architecture described in text",
                plot_type="diagram",
                data_source="Section 2 description",
                suggested_caption="System architecture.",
            ),
        ])
        data = json.loads(sl.model_dump_json())
        restored = FigureSuggestionList.model_validate(data)
        assert len(restored.suggestions) == 1
        assert restored.suggestions[0].description == "Diagram"

    def test_default_factory(self):
        sl = FigureSuggestionList()
        assert sl.suggestions == []
