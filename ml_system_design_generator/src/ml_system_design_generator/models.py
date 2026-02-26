"""Pydantic models for the ML system design generator pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PipelinePhase(str, Enum):
    CONFIGURATION = "configuration"
    UNDERSTANDING = "understanding"
    DESIGN = "design"
    PLAN_APPROVAL = "plan_approval"
    PAGE_BUDGET = "page_budget"
    SUPPLEMENTARY = "supplementary"
    USER_REVIEW = "user_review"


class PlanAction(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    ABORT = "abort"


# ---------------------------------------------------------------------------
# Azure & Model Configuration
# ---------------------------------------------------------------------------

class AzureConfig(BaseModel):
    """Azure OpenAI connection settings."""
    api_key: str = Field(default="", description="Azure OpenAI API key")
    api_version: str = Field(default="", description="API version")
    endpoint: str = Field(default="", description="Azure endpoint URL")


class ModelConfig(BaseModel):
    """LLM model configuration per role."""
    default: str = Field(default="gpt-5.2", description="Default model")
    analyzer: str | None = Field(default=None)
    writer: str | None = Field(default=None)
    reviewer: str | None = Field(default=None)
    planner: str | None = Field(default=None)
    advisor: str | None = Field(default=None)


class InfrastructureConfig(BaseModel):
    """Target infrastructure for the ML system."""
    provider: str = Field(default="", description="azure | aws | gcp | on_prem | hybrid | local")
    compute: list[str] = Field(default_factory=list, description="e.g. gpu_a100, cpu_cluster")
    storage: list[str] = Field(default_factory=list, description="e.g. blob_storage, s3")
    services: list[str] = Field(default_factory=list, description="e.g. kubernetes, databricks")


# ---------------------------------------------------------------------------
# Phase 1: Configuration & Validation
# ---------------------------------------------------------------------------

class ConfigValidationResult(BaseModel):
    """Result of configuration validation."""
    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    resolved_config: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Phase 2: Document Understanding
# ---------------------------------------------------------------------------

class DocumentSummary(BaseModel):
    """Summary of a single source document."""
    file_path: str
    title: str
    key_topics: list[str]
    personas: list[str] = Field(default_factory=list)
    word_count: int = 0
    summary: str = ""


class GapItem(BaseModel):
    """A single gap identified in source material."""
    area: str
    description: str
    severity: Severity = Severity.WARNING
    suggestion: str = ""


class GapReport(BaseModel):
    """Gaps identified in source material."""
    gaps: list[GapItem] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, description="0-1 how well agents understand the docs")


class UnderstandingReport(BaseModel):
    """Phase 2 output: full understanding of source documents."""
    documents: list[DocumentSummary] = Field(default_factory=list)
    cross_references: list[str] = Field(default_factory=list)
    gap_report: GapReport = Field(default_factory=GapReport)
    vector_db_created: bool = False
    total_chunks: int = 0


# ---------------------------------------------------------------------------
# Phase 3: Design Generation
# ---------------------------------------------------------------------------

class DesignSection(BaseModel):
    """Plan for a single section of the design document."""
    section_id: str
    title: str
    content_guidance: str = Field(default="", description="What this section should cover")
    estimated_pages: float = 1.0
    depends_on: list[str] = Field(default_factory=list, description="Other section_ids")
    priority: int = Field(default=1, description="1=highest priority, higher=lower priority")
    target_word_count: int | None = Field(default=None, description="Target word count for this section")


class DesignPlan(BaseModel):
    """Phase 3 output: document structure plan."""
    title: str
    style: str = ""
    sections: list[DesignSection] = Field(default_factory=list)
    total_estimated_pages: float = 0.0
    page_budget: int | None = None


class ReviewFeedback(BaseModel):
    """Structured review output from a reviewer agent."""
    Reviewer: str = Field(..., description="Name of the reviewer agent")
    Review: str = Field(..., description="Semicolon-separated feedback points")
    severity: Severity = Field(default=Severity.WARNING, description="Overall severity")
    affected_sections: list[str] = Field(default_factory=list)


class CompilationWarning(BaseModel):
    """A single warning or error from LaTeX compilation."""
    file: str = Field(default="", description="Source file")
    line: int | None = Field(default=None, description="Line number")
    message: str = Field(..., description="Warning/error message")
    severity: Severity = Field(default=Severity.WARNING)
    context: str = Field(default="", description="+-5 line window around the error")


class CompilationResult(BaseModel):
    """Result of a LaTeX compilation attempt."""
    success: bool = Field(..., description="Whether compilation succeeded")
    pdf_path: str | None = Field(default=None, description="Path to generated PDF")
    errors: list[CompilationWarning] = Field(default_factory=list)
    warnings: list[CompilationWarning] = Field(default_factory=list)
    page_count: int | None = Field(default=None, description="PDF page count")
    unresolved_refs: list[str] = Field(default_factory=list)
    log_excerpt: str = Field(default="", description="Relevant log excerpt")


# ---------------------------------------------------------------------------
# Plan Review
# ---------------------------------------------------------------------------

class PlanReviewResult(BaseModel):
    """Result of user reviewing the design plan before writing begins."""
    action: PlanAction = PlanAction.APPROVE
    feedback: str = ""


# ---------------------------------------------------------------------------
# Page Budget & Supplementary
# ---------------------------------------------------------------------------

class SupplementaryClassification(BaseModel):
    """Classification of a single section as main or supplementary."""
    section_id: str
    placement: str = Field(description="'main' or 'supplementary'")
    reasoning: str = ""
    priority: int = 1
    estimated_pages: float = 0.0


class SupplementaryPlan(BaseModel):
    """Plan for splitting content between main and supplementary documents."""
    mode: str = Field(default="appendix", description="'appendix' or 'standalone'")
    main_sections: list[str] = Field(default_factory=list)
    supplementary_sections: list[str] = Field(default_factory=list)
    classifications: list[SupplementaryClassification] = Field(default_factory=list)
    estimated_main_pages: float = 0.0
    estimated_supp_pages: float = 0.0
    cross_reference_note: str = "See Appendix for additional details."


class SplitDecision(BaseModel):
    """Decision from the PageBudgetManager agent."""
    action: str = Field(description="'ok', 'warn_over', or 'split'")
    current_pages: int = 0
    budget_pages: int | None = None
    sections_to_move: list[str] = Field(default_factory=list)
    estimated_savings: float = 0.0
    recommendations: str = ""
    supplementary_plan: SupplementaryPlan | None = None


# ---------------------------------------------------------------------------
# Phase 4: User Review
# ---------------------------------------------------------------------------

class UserFeedback(BaseModel):
    """User feedback on the generated design document."""
    action: str = Field(..., description="approve | revise | abort")
    comments: str = ""
    section_comments: dict[str, str] = Field(default_factory=dict, description="section_id -> comment")


# ---------------------------------------------------------------------------
# Build Manifest
# ---------------------------------------------------------------------------

class BuildManifest(BaseModel):
    """Provenance record for the final output."""
    project_name: str
    output_dir: str
    main_tex: str = Field(default="main.tex")
    section_files: list[str] = Field(default_factory=list)
    pdf_file: str | None = None
    source_files: list[str] = Field(default_factory=list)
    style_used: str = ""
    compilation_attempts: int = 0
    review_rounds: int = 0
    page_count: int | None = None
    warnings: list[str] = Field(default_factory=list)
    supplementary_tex: str | None = None
    supplementary_pdf: str | None = None
    supplementary_sections: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level Pipeline Result
# ---------------------------------------------------------------------------

class PipelineResult(BaseModel):
    """Top-level result of the full pipeline run."""
    success: bool
    understanding_report: UnderstandingReport | None = None
    design_plan: DesignPlan | None = None
    compilation_result: CompilationResult | None = None
    output_dir: str | None = None
    errors: list[str] = Field(default_factory=list)
    phases_completed: list[PipelinePhase] = Field(default_factory=list)
    split_decision: SplitDecision | None = None


# ---------------------------------------------------------------------------
# Project Configuration (loaded from YAML / Hydra)
# ---------------------------------------------------------------------------

class ProjectConfig(BaseModel):
    """Full project configuration."""
    project_name: str = Field(default="ml-system-design")
    style: str = Field(default="amazon_6page", description="Design doc style template")
    max_pages: int | None = Field(default=None, description="Target page count")
    docs_dir: str = Field(default="docs/", description="Directory containing source markdown docs")
    output_dir: str = Field(default="output/", description="Output directory")

    # Infrastructure & tech
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    tech_stack: list[str] = Field(default_factory=list)
    team_size: int | None = None
    timeline: str | None = None
    constraints: list[str] = Field(default_factory=list)
    target_audience: str = Field(default="engineering", description="engineering | leadership | mixed")

    # Azure OpenAI
    azure: AzureConfig = Field(default_factory=AzureConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)

    # Pipeline tuning
    understanding_max_rounds: int = Field(default=3)
    design_review_max_turns: int = Field(default=3)
    design_revision_max_rounds: int = Field(default=3)
    compile_max_attempts: int = Field(default=3)
    vector_db_enabled: bool = Field(default=True)
    vector_db_threshold_kb: int = Field(default=50)
    timeout: int = Field(default=120)
    seed: int = Field(default=42)

    # Page budget & supplementary
    supplementary_mode: str = Field(
        default="disabled",
        description="disabled | auto | appendix | standalone",
    )
    supplementary_threshold: float = Field(
        default=1.3,
        description="Ratio of actual/budget pages that triggers supplementary (for auto mode)",
    )
    max_plan_revisions: int = Field(default=3, description="Max plan revision rounds")
    words_per_page: int = Field(default=500, description="Estimated words per page for budget")

    # Enabled reviewers
    enabled_reviewers: dict[str, bool] = Field(
        default_factory=lambda: {
            "DesignReviewer": True,
            "ConsistencyChecker": True,
            "InfraAdvisor": True,
        }
    )
