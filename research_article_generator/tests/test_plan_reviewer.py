"""Tests for the PlanReviewer agent — factory, review flow, and notes display."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from research_article_generator.models import (
    ProjectConfig,
    ReviewFeedback,
    SectionPlan,
    StructurePlan,
)
from research_article_generator.agents.reviewers import make_plan_reviewer
from research_article_generator.pipeline import Pipeline


@pytest.fixture
def config():
    return ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")


@pytest.fixture
def pipeline(tmp_path, config):
    return Pipeline(config, config_dir=tmp_path)


def _make_plan():
    return StructurePlan(
        title="Test Article",
        sections=[
            SectionPlan(
                section_id="01_intro",
                title="Introduction",
                source_file="drafts/01_intro.md",
                priority=1,
                estimated_pages=2.0,
            ),
            SectionPlan(
                section_id="02_methods",
                title="Methods",
                source_file="drafts/02_methods.md",
                priority=2,
                estimated_pages=3.0,
            ),
        ],
        total_estimated_pages=5.0,
        page_budget=15,
    )


# ---------------------------------------------------------------------------
# Agent factory tests
# ---------------------------------------------------------------------------


class TestPlanReviewerAgent:
    def test_returns_agent_when_enabled(self, config):
        config.enabled_reviewers["PlanReviewer"] = True
        agent = make_plan_reviewer(config)
        assert agent is not None
        assert agent.name == "PlanReviewer"

    def test_returns_none_when_disabled(self, config):
        config.enabled_reviewers["PlanReviewer"] = False
        agent = make_plan_reviewer(config)
        assert agent is None

    def test_returns_none_when_key_missing(self, config):
        config.enabled_reviewers.pop("PlanReviewer", None)
        agent = make_plan_reviewer(config)
        assert agent is None

    def test_system_prompt_content(self, config):
        config.enabled_reviewers["PlanReviewer"] = True
        agent = make_plan_reviewer(config)
        msg = agent.system_message if hasattr(agent, "system_message") else ""
        assert "structure plan reviewer" in msg.lower() or "PlanReviewer" in msg

    def test_llm_config_set(self, config):
        config.enabled_reviewers["PlanReviewer"] = True
        agent = make_plan_reviewer(config)
        # Agent should have a valid llm_config with config_list
        llm_cfg = agent.llm_config
        if isinstance(llm_cfg, dict):
            assert "config_list" in llm_cfg
        else:
            # LLMConfig object
            assert hasattr(llm_cfg, "config_list")

    def test_role_mapping(self, config):
        """plan_reviewer role maps to reviewer model tier."""
        from research_article_generator.config import build_role_llm_config

        llm_config = build_role_llm_config("plan_reviewer", config)
        assert "config_list" in llm_config
        model = llm_config["config_list"][0]["model"]
        # Should use reviewer model or default
        expected = config.models.reviewer or config.models.default
        assert model == expected


# ---------------------------------------------------------------------------
# Review flow tests
# ---------------------------------------------------------------------------


class TestPlanReviewFlow:
    def test_reviewer_disabled_returns_unchanged(self, pipeline, tmp_path):
        pipeline.config.enabled_reviewers["PlanReviewer"] = False
        plan = _make_plan()
        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir(exist_ok=True)

        result_plan, notes = pipeline._review_plan(plan, [])
        assert result_plan is plan
        assert notes is None

    def test_no_issues_returns_unchanged(self, pipeline, tmp_path):
        pipeline.config.enabled_reviewers["PlanReviewer"] = True
        plan = _make_plan()

        no_issues_response = MagicMock(
            summary='{"Reviewer": "PlanReviewer", "Review": "No issues found"}'
        )

        with patch("research_article_generator.pipeline.make_plan_reviewer") as mock_factory, \
             patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_factory.return_value = MagicMock(name="PlanReviewer")
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = no_issues_response

            result_plan, notes = pipeline._review_plan(plan, [])

        assert result_plan is plan
        assert notes is None

    def test_issues_trigger_auto_revision(self, pipeline, tmp_path):
        pipeline.config.enabled_reviewers["PlanReviewer"] = True
        plan = _make_plan()

        review_response = MagicMock(
            summary='{"Reviewer": "PlanReviewer", "Review": "- Methods should come after Introduction; - Missing conclusion section"}'
        )

        revised_plan = _make_plan()
        revised_plan.title = "Revised Article"

        with patch("research_article_generator.pipeline.make_plan_reviewer") as mock_factory, \
             patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline._extract_json", return_value=revised_plan):
            mock_factory.return_value = MagicMock(name="PlanReviewer")
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = review_response

            result_plan, notes = pipeline._review_plan(plan, [])

        assert result_plan.title == "Revised Article"
        assert notes is not None
        assert "Methods should come after Introduction" in notes

    def test_revision_failure_returns_original_with_notes(self, pipeline, tmp_path):
        pipeline.config.enabled_reviewers["PlanReviewer"] = True
        plan = _make_plan()

        review_response = MagicMock(
            summary='{"Reviewer": "PlanReviewer", "Review": "- Missing conclusion section"}'
        )

        with patch("research_article_generator.pipeline.make_plan_reviewer") as mock_factory, \
             patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline._extract_json", return_value=None):
            mock_factory.return_value = MagicMock(name="PlanReviewer")
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = review_response

            result_plan, notes = pipeline._review_plan(plan, [])

        # Original plan kept, but notes still returned
        assert result_plan is plan
        assert notes is not None
        assert "Missing conclusion section" in notes

    def test_reviewer_exception_returns_unchanged(self, pipeline, tmp_path):
        pipeline.config.enabled_reviewers["PlanReviewer"] = True
        plan = _make_plan()

        with patch("research_article_generator.pipeline.make_plan_reviewer") as mock_factory, \
             patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_factory.return_value = MagicMock(name="PlanReviewer")
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("LLM timeout")

            result_plan, notes = pipeline._review_plan(plan, [])

        assert result_plan is plan
        assert notes is None


# ---------------------------------------------------------------------------
# Plan review notes field tests
# ---------------------------------------------------------------------------


class TestPlanReviewNotes:
    def test_field_defaults_to_none(self):
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01", title="Intro", source_file="01.md"),
            ],
        )
        assert plan.plan_review_notes is None

    def test_field_set(self):
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01", title="Intro", source_file="01.md"),
            ],
            plan_review_notes="- Missing conclusion; - Reorder methods",
        )
        assert "Missing conclusion" in plan.plan_review_notes

    def test_json_roundtrip(self):
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01", title="Intro", source_file="01.md"),
            ],
            plan_review_notes="- Issue one; - Issue two",
        )
        j = plan.model_dump_json()
        restored = StructurePlan.model_validate_json(j)
        assert restored.plan_review_notes == "- Issue one; - Issue two"

    def test_json_roundtrip_none(self):
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01", title="Intro", source_file="01.md"),
            ],
        )
        j = plan.model_dump_json()
        restored = StructurePlan.model_validate_json(j)
        assert restored.plan_review_notes is None
