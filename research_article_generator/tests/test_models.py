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
        assert PipelinePhase.FINALIZATION == "finalization"
