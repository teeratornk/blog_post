"""Tests for models.py — Pydantic model validation."""

from __future__ import annotations

import json

import pytest

from research_article_generator.models import (
    BuildManifest,
    CompilationResult,
    CompilationWarning,
    FaithfulnessReport,
    FaithfulnessViolation,
    PipelinePhase,
    PipelineResult,
    ProjectConfig,
    ReviewFeedback,
    SectionPlan,
    Severity,
    SplitDecision,
    StructurePlan,
    SupplementaryClassification,
    SupplementaryPlan,
)


class TestSectionPlan:
    def test_minimal(self):
        s = SectionPlan(section_id="01_intro", title="Introduction", source_file="drafts/01.md")
        assert s.latex_command == "\\section"
        assert s.figures == []

    def test_full(self):
        s = SectionPlan(
            section_id="02_method",
            title="Methodology",
            source_file="drafts/02.md",
            latex_command="\\section",
            figures=["fig1.png", "fig2.png"],
            tables=2,
            equations=5,
            estimated_pages=3.5,
            priority=1,
        )
        assert len(s.figures) == 2
        assert s.estimated_pages == 3.5


class TestStructurePlan:
    def test_roundtrip_json(self):
        plan = StructurePlan(
            title="Test Article",
            sections=[
                SectionPlan(section_id="01", title="Intro", source_file="01.md"),
            ],
            page_budget=15,
            budget_status="ok",
        )
        j = plan.model_dump_json()
        restored = StructurePlan.model_validate_json(j)
        assert restored.title == "Test Article"
        assert len(restored.sections) == 1


class TestCompilationResult:
    def test_success(self):
        r = CompilationResult(success=True, pdf_path="output/main.pdf", page_count=12)
        assert r.success
        assert r.errors == []

    def test_failure_with_errors(self):
        r = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(message="Undefined control sequence", line=42, severity=Severity.ERROR),
            ],
        )
        assert not r.success
        assert len(r.errors) == 1


class TestReviewFeedback:
    def test_parse_json(self):
        raw = '{"Reviewer": "LaTeXLinter", "Review": "- fix spacing; - add labels"}'
        rf = ReviewFeedback.model_validate_json(raw)
        assert rf.Reviewer == "LaTeXLinter"
        assert "fix spacing" in rf.Review


class TestFaithfulnessReport:
    def test_passed(self):
        r = FaithfulnessReport(passed=True)
        assert r.violations == []

    def test_failed_with_violations(self):
        r = FaithfulnessReport(
            passed=False,
            violations=[
                FaithfulnessViolation(
                    severity=Severity.CRITICAL,
                    issue="Math expression altered",
                ),
            ],
            math_match=False,
        )
        assert not r.passed
        assert not r.math_match


class TestProjectConfig:
    def test_defaults(self):
        c = ProjectConfig()
        assert c.template == "elsarticle"
        assert c.latex_engine == "pdflatex"
        assert c.compile_max_attempts == 3
        assert "LaTeXLinter" in c.enabled_reviewers

    def test_custom(self):
        c = ProjectConfig(
            project_name="Custom",
            template="ieeetran",
            page_budget=10,
        )
        assert c.project_name == "Custom"
        assert c.page_budget == 10


class TestPipelinePhase:
    def test_values(self):
        assert PipelinePhase.PLANNING == "planning"
        assert PipelinePhase.SUPPLEMENTARY == "supplementary"
        assert PipelinePhase.FINALIZATION == "finalization"


class TestSupplementaryClassification:
    def test_roundtrip(self):
        c = SupplementaryClassification(
            section_id="06_proofs",
            placement="supplementary",
            reasoning="Extended proofs",
            priority=5,
            estimated_pages=3.0,
        )
        j = c.model_dump_json()
        restored = SupplementaryClassification.model_validate_json(j)
        assert restored.section_id == "06_proofs"
        assert restored.placement == "supplementary"
        assert restored.estimated_pages == 3.0

    def test_defaults(self):
        c = SupplementaryClassification(
            section_id="01_intro",
            placement="main",
            reasoning="Core contribution",
        )
        assert c.priority == 1
        assert c.estimated_pages == 0.0


class TestSupplementaryPlan:
    def test_defaults(self):
        plan = SupplementaryPlan()
        assert plan.mode == "standalone"
        assert plan.main_sections == []
        assert plan.supplementary_sections == []
        assert plan.estimated_main_pages == 0.0
        assert "Supplementary Materials" in plan.cross_reference_note

    def test_full_construction(self):
        plan = SupplementaryPlan(
            mode="appendix",
            main_sections=["01_intro", "02_methods"],
            supplementary_sections=["06_proofs"],
            supplementary_figures=["fig_detailed.png"],
            classifications=[
                SupplementaryClassification(
                    section_id="06_proofs",
                    placement="supplementary",
                    reasoning="Extended proofs",
                ),
            ],
            estimated_main_pages=14.0,
            estimated_supp_pages=3.5,
            cross_reference_note="See Appendix for proofs.",
        )
        assert plan.mode == "appendix"
        assert len(plan.supplementary_sections) == 1
        assert len(plan.classifications) == 1
        assert plan.estimated_supp_pages == 3.5

    def test_roundtrip(self):
        plan = SupplementaryPlan(
            mode="standalone",
            main_sections=["01_intro"],
            supplementary_sections=["06_proofs"],
        )
        j = plan.model_dump_json()
        restored = SupplementaryPlan.model_validate_json(j)
        assert restored.mode == "standalone"
        assert restored.supplementary_sections == ["06_proofs"]


class TestSplitDecisionWithPlan:
    def test_with_supplementary_plan(self):
        plan = SupplementaryPlan(
            mode="standalone",
            main_sections=["01_intro"],
            supplementary_sections=["06_proofs"],
        )
        decision = SplitDecision(
            action="split",
            current_pages=18,
            budget_pages=15,
            sections_to_move=["06_proofs"],
            supplementary_plan=plan,
        )
        assert decision.action == "split"
        assert decision.supplementary_plan is not None
        assert decision.supplementary_plan.supplementary_sections == ["06_proofs"]

    def test_without_supplementary_plan(self):
        decision = SplitDecision(action="warn_over", current_pages=18, budget_pages=15)
        assert decision.supplementary_plan is None

    def test_roundtrip_with_plan(self):
        plan = SupplementaryPlan(mode="appendix", supplementary_sections=["06_proofs"])
        decision = SplitDecision(
            action="split",
            current_pages=18,
            budget_pages=15,
            supplementary_plan=plan,
        )
        j = decision.model_dump_json()
        restored = SplitDecision.model_validate_json(j)
        assert restored.supplementary_plan is not None
        assert restored.supplementary_plan.mode == "appendix"


class TestProjectConfigSupplementary:
    def test_supplementary_defaults(self):
        c = ProjectConfig()
        assert c.supplementary_mode == "disabled"
        assert c.supplementary_threshold == 1.2

    def test_supplementary_custom(self):
        c = ProjectConfig(supplementary_mode="auto", supplementary_threshold=1.5)
        assert c.supplementary_mode == "auto"
        assert c.supplementary_threshold == 1.5


class TestBuildManifestSupplementary:
    def test_supplementary_fields_default(self):
        m = BuildManifest(project_name="Test", output_dir="output/")
        assert m.supplementary_tex is None
        assert m.supplementary_pdf is None
        assert m.supplementary_sections == []

    def test_supplementary_fields_set(self):
        m = BuildManifest(
            project_name="Test",
            output_dir="output/",
            supplementary_tex="supplementary.tex",
            supplementary_pdf="output/supplementary.pdf",
            supplementary_sections=["06_proofs"],
        )
        assert m.supplementary_tex == "supplementary.tex"
        assert m.supplementary_sections == ["06_proofs"]
