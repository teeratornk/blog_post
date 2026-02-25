"""Tests for Pydantic models."""

import pytest

from ml_system_design_generator.models import (
    AzureConfig,
    BuildManifest,
    CompilationResult,
    CompilationWarning,
    ConfigValidationResult,
    DesignPlan,
    DesignSection,
    DocumentSummary,
    GapItem,
    GapReport,
    InfrastructureConfig,
    ModelConfig,
    PipelinePhase,
    PipelineResult,
    ProjectConfig,
    ReviewFeedback,
    Severity,
    UnderstandingReport,
    UserFeedback,
)


class TestSeverity:
    def test_values(self):
        assert Severity.INFO == "info"
        assert Severity.WARNING == "warning"
        assert Severity.ERROR == "error"
        assert Severity.CRITICAL == "critical"


class TestProjectConfig:
    def test_defaults(self):
        config = ProjectConfig()
        assert config.project_name == "ml-system-design"
        assert config.style == "amazon_6page"
        assert config.max_pages is None
        assert config.docs_dir == "docs/"
        assert config.output_dir == "output/"
        assert config.timeout == 120
        assert config.seed == 42

    def test_custom_values(self):
        config = ProjectConfig(
            project_name="test-project",
            style="google_design",
            max_pages=8,
            tech_stack=["python", "pytorch"],
        )
        assert config.project_name == "test-project"
        assert config.style == "google_design"
        assert config.max_pages == 8
        assert config.tech_stack == ["python", "pytorch"]

    def test_enabled_reviewers_default(self):
        config = ProjectConfig()
        assert config.enabled_reviewers["DesignReviewer"] is True
        assert config.enabled_reviewers["ConsistencyChecker"] is True
        assert config.enabled_reviewers["InfraAdvisor"] is True

    def test_infrastructure_config(self):
        config = ProjectConfig(
            infrastructure=InfrastructureConfig(
                provider="azure",
                compute=["gpu_a100"],
                storage=["blob_storage"],
                services=["kubernetes"],
            )
        )
        assert config.infrastructure.provider == "azure"
        assert "gpu_a100" in config.infrastructure.compute


class TestDocumentSummary:
    def test_creation(self):
        summary = DocumentSummary(
            file_path="docs/test.md",
            title="Test Document",
            key_topics=["ml", "systems"],
            word_count=1000,
            summary="A test document about ML systems.",
        )
        assert summary.file_path == "docs/test.md"
        assert len(summary.key_topics) == 2

    def test_json_roundtrip(self):
        summary = DocumentSummary(
            file_path="docs/test.md",
            title="Test",
            key_topics=["ml"],
            word_count=100,
            summary="Test summary.",
        )
        json_str = summary.model_dump_json()
        parsed = DocumentSummary.model_validate_json(json_str)
        assert parsed.title == "Test"


class TestDesignPlan:
    def test_creation(self):
        plan = DesignPlan(
            title="Test Design",
            style="amazon_6page",
            sections=[
                DesignSection(
                    section_id="situation",
                    title="Situation",
                    content_guidance="Describe the problem",
                    estimated_pages=0.5,
                ),
            ],
            total_estimated_pages=0.5,
        )
        assert len(plan.sections) == 1
        assert plan.sections[0].section_id == "situation"


class TestReviewFeedback:
    def test_creation(self):
        feedback = ReviewFeedback(
            Reviewer="DesignReviewer",
            Review="- Fix architecture diagram; - Add latency numbers",
        )
        assert feedback.Reviewer == "DesignReviewer"
        assert feedback.severity == Severity.WARNING

    def test_json_roundtrip(self):
        feedback = ReviewFeedback(
            Reviewer="TestReviewer",
            Review="- point 1; - point 2",
            severity=Severity.ERROR,
            affected_sections=["approach"],
        )
        json_str = feedback.model_dump_json()
        parsed = ReviewFeedback.model_validate_json(json_str)
        assert parsed.Reviewer == "TestReviewer"
        assert parsed.severity == Severity.ERROR
        assert "approach" in parsed.affected_sections


class TestCompilationResult:
    def test_success(self):
        result = CompilationResult(
            success=True,
            pdf_path="/output/main.pdf",
            page_count=6,
        )
        assert result.success
        assert result.page_count == 6

    def test_failure(self):
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="Undefined control sequence",
                    severity=Severity.ERROR,
                    line=42,
                )
            ],
        )
        assert not result.success
        assert len(result.errors) == 1


class TestPipelineResult:
    def test_success(self):
        result = PipelineResult(
            success=True,
            phases_completed=[PipelinePhase.CONFIGURATION, PipelinePhase.UNDERSTANDING],
        )
        assert result.success
        assert len(result.phases_completed) == 2

    def test_failure(self):
        result = PipelineResult(
            success=False,
            errors=["Config validation failed"],
        )
        assert not result.success
        assert len(result.errors) == 1
