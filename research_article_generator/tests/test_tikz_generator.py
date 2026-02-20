"""Tests for the TikZ diagram generator agent and related integration."""

from __future__ import annotations

import json

import pytest

from research_article_generator.models import (
    ProjectConfig,
    Severity,
    TikZIssue,
    TikZReviewResult,
)
from research_article_generator.agents.tikz_generator import (
    REVIEWER_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    make_tikz_generator,
    make_tikz_reviewer,
    validate_tikz_review,
)
from research_article_generator.config import build_role_llm_config
from research_article_generator.tools.latex_builder import generate_preamble
from research_article_generator.tools.pandoc_converter import _annotate_safe_zones


class TestTikzGeneratorAgent:
    """Tests for the agent factory and system prompt."""

    def test_make_tikz_generator_returns_agent(self):
        config = ProjectConfig()
        agent = make_tikz_generator(config)
        assert agent.name == "TikZGenerator"

    def test_system_prompt_mentions_tikz(self):
        assert "TikZ" in SYSTEM_PROMPT or "tikz" in SYSTEM_PROMPT.lower()

    def test_system_prompt_forbids_pgfplots(self):
        assert "pgfplots" in SYSTEM_PROMPT.lower()

    def test_system_prompt_mentions_figure_environment(self):
        assert "\\begin{figure}" in SYSTEM_PROMPT

    def test_system_prompt_mentions_tikzpicture(self):
        assert "tikzpicture" in SYSTEM_PROMPT

    def test_system_prompt_lists_allowed_libraries(self):
        for lib in ["arrows.meta", "positioning", "shapes.geometric", "calc", "fit", "backgrounds"]:
            assert lib in SYSTEM_PROMPT

    def test_system_prompt_preserves_existing_content(self):
        assert "unchanged" in SYSTEM_PROMPT.lower() or "preserve" in SYSTEM_PROMPT.lower()


class TestTikzReviewerAgent:
    """Tests for the TikZ reviewer agent factory and system prompt."""

    def test_make_tikz_reviewer_returns_agent(self):
        config = ProjectConfig()
        agent = make_tikz_reviewer(config)
        assert agent.name == "TikZReviewer"

    def test_reviewer_prompt_checks_syntax(self):
        assert "syntax" in REVIEWER_SYSTEM_PROMPT.lower()

    def test_reviewer_prompt_checks_spacing(self):
        assert "1.5cm" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prompt_checks_libraries(self):
        for lib in ["arrows.meta", "positioning", "shapes.geometric"]:
            assert lib in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prompt_forbids_pgfplots(self):
        assert "pgfplots" in REVIEWER_SYSTEM_PROMPT.lower()

    def test_reviewer_prompt_mentions_pass(self):
        assert "PASS" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prompt_no_latex_return(self):
        assert "Do NOT return modified LaTeX" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prompt_checks_figure_integration(self):
        assert "\\caption" in REVIEWER_SYSTEM_PROMPT
        assert "\\label" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prompt_has_concrete_thresholds(self):
        """New prescriptive prompt has concrete thresholds for node sizing and arrow style."""
        assert "minimum width=2cm" in REVIEWER_SYSTEM_PROMPT
        assert "minimum height=0.8cm" in REVIEWER_SYSTEM_PROMPT
        assert "-Stealth" in REVIEWER_SYSTEM_PROMPT
        assert "text width" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_prompt_requires_json_output(self):
        assert "verdict" in REVIEWER_SYSTEM_PROMPT
        assert "FAIL" in REVIEWER_SYSTEM_PROMPT
        assert "issues" in REVIEWER_SYSTEM_PROMPT
        assert "category" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_role_maps_to_assembler_tier(self):
        """tikz_reviewer now maps to assembler tier, not reviewer tier."""
        config = ProjectConfig(models={"default": "gpt-4", "assembler": "gpt-5.2", "reviewer": "gpt-4o-mini"})
        llm_config = build_role_llm_config("tikz_reviewer", config)
        assert llm_config["config_list"][0]["model"] == "gpt-5.2"


class TestTikzConfig:
    """Tests for tikz_enabled configuration field."""

    def test_tikz_disabled_by_default(self):
        config = ProjectConfig()
        assert config.tikz_enabled is False

    def test_tikz_enabled_explicit(self):
        config = ProjectConfig(tikz_enabled=True)
        assert config.tikz_enabled is True

    def test_role_mapping_exists(self):
        config = ProjectConfig()
        llm_config = build_role_llm_config("tikz_generator", config)
        assert "config_list" in llm_config
        assert len(llm_config["config_list"]) == 1

    def test_role_maps_to_assembler_tier(self):
        config = ProjectConfig(models={"default": "gpt-4", "assembler": "gpt-5.2"})
        llm_config = build_role_llm_config("tikz_generator", config)
        assert llm_config["config_list"][0]["model"] == "gpt-5.2"

    def test_tikz_review_max_turns_default(self):
        config = ProjectConfig()
        assert config.tikz_review_max_turns == 3

    def test_tikz_review_max_turns_custom(self):
        config = ProjectConfig(tikz_review_max_turns=5)
        assert config.tikz_review_max_turns == 5


class TestTikZIssueModel:
    """Tests for TikZIssue Pydantic model."""

    def test_basic_construction(self):
        issue = TikZIssue(category="syntax", severity=Severity.ERROR, description="Missing semicolon")
        assert issue.category == "syntax"
        assert issue.severity == Severity.ERROR
        assert issue.description == "Missing semicolon"

    def test_json_round_trip(self):
        issue = TikZIssue(category="spacing", severity=Severity.WARNING, description="Nodes too close")
        data = json.loads(issue.model_dump_json())
        restored = TikZIssue.model_validate(data)
        assert restored == issue


class TestTikZReviewResultModel:
    """Tests for TikZReviewResult Pydantic model."""

    def test_pass_result(self):
        result = TikZReviewResult(verdict="PASS", issues=[])
        assert result.verdict == "PASS"
        assert result.issues == []

    def test_fail_result_with_issues(self):
        issues = [
            TikZIssue(category="spacing", severity=Severity.ERROR, description="Overlap"),
            TikZIssue(category="layout", severity=Severity.WARNING, description="Mixed arrows"),
        ]
        result = TikZReviewResult(verdict="FAIL", issues=issues)
        assert result.verdict == "FAIL"
        assert len(result.issues) == 2

    def test_json_round_trip(self):
        result = TikZReviewResult(
            verdict="FAIL",
            issues=[TikZIssue(category="syntax", severity=Severity.ERROR, description="Test")],
        )
        data = json.loads(result.model_dump_json())
        restored = TikZReviewResult.model_validate(data)
        assert restored.verdict == result.verdict
        assert len(restored.issues) == 1


class TestValidateTikzReview:
    """Tests for the 3-stage validate_tikz_review() parser."""

    def test_valid_pass_json(self):
        raw = '{"verdict": "PASS", "issues": []}'
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "PASS"
        assert result.issues == []

    def test_valid_fail_json(self):
        raw = json.dumps({
            "verdict": "FAIL",
            "issues": [
                {"category": "spacing", "severity": "error", "description": "Nodes overlap at (2,0)"},
                {"category": "layout", "severity": "warning", "description": "Mixed arrow tips"},
            ]
        })
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "FAIL"
        assert len(result.issues) == 2
        assert result.issues[0].severity == Severity.ERROR
        assert result.issues[1].severity == Severity.WARNING

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"verdict": "PASS", "issues": []}\n```'
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "PASS"

    def test_curly_quotes_repair(self):
        raw = '\u201c{"verdict": "PASS", "issues": []}\u201d'
        # The outer curly quotes get replaced; the inner JSON is valid
        raw = '{"verdict": \u201cPASS\u201d, "issues": []}'
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "PASS"

    def test_trailing_comma_repair(self):
        raw = '{"verdict": "FAIL", "issues": [{"category": "syntax", "severity": "error", "description": "test",},],}'
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "FAIL"

    def test_backslash_repair(self):
        raw = '{"verdict": "FAIL", "issues": [{"category": "syntax", "severity": "error", "description": "Missing \\end{tikzpicture}"}]}'
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "FAIL"
        assert len(result.issues) == 1

    def test_freeform_pass(self):
        raw = "All checks pass. The diagram looks correct.\nPASS"
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "PASS"

    def test_freeform_numbered_issues(self):
        raw = (
            "Issues found:\n"
            "1. Nodes encoder and decoder overlap at (2,0).\n"
            "2. Arrow style inconsistent: some use ->, others use -Stealth.\n"
            "3. Missing caption in figure environment.\n"
        )
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "FAIL"
        assert len(result.issues) == 3

    def test_freeform_bullet_issues(self):
        raw = (
            "- Spacing between nodes is less than 1.5cm.\n"
            "- Missing \\label in figure environment.\n"
        )
        result = validate_tikz_review(raw)
        assert result is not None
        assert result.verdict == "FAIL"
        assert len(result.issues) == 2

    def test_garbage_returns_none(self):
        raw = "asdfghjkl random garbage 12345"
        result = validate_tikz_review(raw)
        assert result is None

    def test_empty_returns_none(self):
        result = validate_tikz_review("")
        assert result is None


class TestTikzPreamble:
    """Tests for TikZ package injection in preamble generation."""

    def test_minimal_preamble_no_tikz_when_disabled(self):
        config = ProjectConfig(project_name="Test", template="nonexistent_template")
        preamble = generate_preamble(config)
        assert "tikz" not in preamble.lower()

    def test_minimal_preamble_has_tikz_when_enabled(self):
        config = ProjectConfig(
            project_name="Test",
            template="nonexistent_template",
            tikz_enabled=True,
        )
        preamble = generate_preamble(config)
        assert "\\usepackage{tikz}" in preamble
        assert "\\usetikzlibrary{" in preamble
        assert "arrows.meta" in preamble
        assert "positioning" in preamble

    def test_elsarticle_preamble_no_tikz_when_disabled(self):
        config = ProjectConfig(
            project_name="Test",
            template="elsarticle",
            tikz_enabled=False,
        )
        preamble = generate_preamble(config)
        assert "\\usepackage{tikz}" not in preamble

    def test_elsarticle_preamble_has_tikz_when_enabled(self):
        config = ProjectConfig(
            project_name="Test",
            template="elsarticle",
            tikz_enabled=True,
        )
        preamble = generate_preamble(config)
        assert "\\usepackage{tikz}" in preamble
        assert "\\usetikzlibrary{" in preamble

    def test_tikz_injected_before_frontmatter(self):
        config = ProjectConfig(
            project_name="Test",
            template="elsarticle",
            tikz_enabled=True,
        )
        preamble = generate_preamble(config)
        tikz_pos = preamble.index("\\usepackage{tikz}")
        frontmatter_pos = preamble.index("\\begin{frontmatter}")
        assert tikz_pos < frontmatter_pos


class TestTikzpictureSafeZone:
    """Tests that tikzpicture environments are protected from SAFE_ZONE markers."""

    def test_tikzpicture_not_in_safe_zone(self):
        latex = (
            "\\section{Methods}\n"
            "Some text before.\n"
            "\\begin{tikzpicture}\n"
            "\\draw (0,0) -- (1,1);\n"
            "\\end{tikzpicture}\n"
            "Some text after.\n"
        )
        annotated = _annotate_safe_zones(latex)
        lines = annotated.split("\n")

        # Find the tikzpicture block
        in_tikz = False
        for line in lines:
            if "\\begin{tikzpicture}" in line:
                in_tikz = True
            if in_tikz:
                assert "SAFE_ZONE" not in line, (
                    f"SAFE_ZONE marker found inside tikzpicture block: {line}"
                )
            if "\\end{tikzpicture}" in line:
                in_tikz = False

    def test_text_around_tikzpicture_gets_safe_zone(self):
        latex = (
            "Some text before.\n"
            "\\begin{tikzpicture}\n"
            "\\draw (0,0) -- (1,1);\n"
            "\\end{tikzpicture}\n"
            "Some text after.\n"
        )
        annotated = _annotate_safe_zones(latex)
        assert "SAFE_ZONE_START" in annotated
        assert "SAFE_ZONE_END" in annotated
