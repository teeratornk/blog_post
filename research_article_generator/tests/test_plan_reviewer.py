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


# ---------------------------------------------------------------------------
# Placeholder draft generation tests
# ---------------------------------------------------------------------------


class TestPlaceholderDrafts:
    """Tests for Pipeline._generate_placeholder_drafts()."""

    def _make_pipeline_with_drafts(self, tmp_path, config):
        """Set up a pipeline with real draft files and source_md populated."""
        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        intro = draft_dir / "01_intro.md"
        intro.write_text("# Introduction\n\nSome intro content.\n", encoding="utf-8")
        config.draft_dir = "drafts/"
        pipe = Pipeline(config, config_dir=tmp_path)
        pipe.source_md["01_intro"] = intro.read_text(encoding="utf-8")
        return pipe, [intro]

    def test_placeholder_created_for_missing_section(self, tmp_path, config):
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="conclusion", title="Conclusion", source_file="drafts/conclusion.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("no LLM")

            created = pipe._generate_placeholder_drafts(plan, drafts)

        assert len(created) == 1
        assert created[0].name == "conclusion.md"
        assert created[0].exists()

    def test_placeholder_content_has_todo(self, tmp_path, config):
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="conclusion", title="Conclusion", source_file="drafts/conclusion.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("no LLM")

            pipe._generate_placeholder_drafts(plan, drafts)

        content = (tmp_path / "drafts" / "conclusion.md").read_text(encoding="utf-8")
        assert "TODO" in content

    def test_no_placeholder_for_existing_files(self, tmp_path, config):
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("no LLM")

            created = pipe._generate_placeholder_drafts(plan, drafts)

        assert len(created) == 0

    def test_plan_source_file_updated(self, tmp_path, config):
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="discussion", title="Discussion", source_file="drafts/discussion.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("no LLM")

            pipe._generate_placeholder_drafts(plan, drafts)

        # The section's source_file should now point to the created file
        discussion = [s for s in plan.sections if s.section_id == "discussion"][0]
        assert discussion.source_file == "drafts/discussion.md"
        assert (tmp_path / discussion.source_file).exists()

    def test_deterministic_fallback_on_llm_failure(self, tmp_path, config):
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="abstract", title="Abstract", source_file="drafts/abstract.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("LLM unavailable")

            created = pipe._generate_placeholder_drafts(plan, drafts)

        assert len(created) == 1
        content = created[0].read_text(encoding="utf-8")
        assert "TODO" in content
        assert "# Abstract" in content

    def test_section_type_guidance(self, tmp_path, config):
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="conclusion", title="Conclusion", source_file="drafts/conclusion.md"),
                SectionPlan(section_id="abstract", title="Abstract", source_file="drafts/abstract.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("no LLM")

            pipe._generate_placeholder_drafts(plan, drafts)

        conclusion_content = (tmp_path / "drafts" / "conclusion.md").read_text(encoding="utf-8")
        abstract_content = (tmp_path / "drafts" / "abstract.md").read_text(encoding="utf-8")

        assert "key findings" in conclusion_content.lower()
        assert "summarize" in abstract_content.lower()

    def test_sections_added_from_review_notes(self, tmp_path, config):
        """Sections mentioned in review notes but missing from the plan are added."""
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
            ],
        )
        review_notes = "- Add a conclusion/discussion section to complete standard structure"

        added = pipe._add_sections_from_review_notes(plan, review_notes)

        assert "conclusion" in added
        assert "discussion" in added
        section_ids = [s.section_id for s in plan.sections]
        assert "conclusion" in section_ids
        assert "discussion" in section_ids
        # Conclusion/discussion are "end" sections, so they come after intro
        assert section_ids.index("01_intro") < section_ids.index("conclusion")

    def test_abstract_inserted_before_other_sections(self, tmp_path, config):
        """Abstract from review notes is placed at the start of the plan."""
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="02_methods", title="Methods", source_file="drafts/02_methods.md"),
            ],
        )
        review_notes = "- Add an abstract section"

        pipe._add_sections_from_review_notes(plan, review_notes)

        section_ids = [s.section_id for s in plan.sections]
        assert section_ids[0] == "abstract"
        # Priorities re-numbered to match new order
        assert plan.sections[0].priority == 1
        assert plan.sections[1].priority == 2

    def test_review_notes_skip_existing_sections(self, tmp_path, config):
        """Sections already in the plan are not duplicated from review notes."""
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="conclusion", title="Conclusion", source_file="drafts/conclusion.md"),
            ],
        )
        review_notes = "- Add a conclusion section"

        added = pipe._add_sections_from_review_notes(plan, review_notes)

        assert len(added) == 0
        assert len(plan.sections) == 2

    def test_duplicate_source_file_gets_placeholder(self, tmp_path, config):
        """When multiple sections share the same source file, duplicates get placeholders."""
        pipe, drafts = self._make_pipeline_with_drafts(tmp_path, config)
        plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01_intro.md"),
                SectionPlan(section_id="01_abstract", title="Abstract", source_file="drafts/01_intro.md"),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_ag:
            mock_proxy = MagicMock()
            mock_ag.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = RuntimeError("no LLM")

            created = pipe._generate_placeholder_drafts(plan, drafts)

        assert len(created) == 1
        assert created[0].name == "01_abstract.md"
        abstract_section = [s for s in plan.sections if s.section_id == "01_abstract"][0]
        assert abstract_section.source_file == "drafts/01_abstract.md"
        assert (tmp_path / "drafts" / "01_abstract.md").exists()
