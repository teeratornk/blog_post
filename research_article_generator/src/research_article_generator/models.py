"""Pydantic models for the research article generator pipeline."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
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
    PLANNING = "planning"
    CONVERSION = "conversion"
    POST_PROCESSING = "post_processing"
    COMPILATION_REVIEW = "compilation_review"
    PAGE_BUDGET = "page_budget"
    FINALIZATION = "finalization"


# ---------------------------------------------------------------------------
# Phase 1: Structure Planning
# ---------------------------------------------------------------------------

class SectionPlan(BaseModel):
    """Plan for a single section of the article."""
    section_id: str = Field(..., description="Unique section identifier, e.g. '02_methodology'")
    title: str = Field(..., description="Section title")
    source_file: str = Field(..., description="Path to source markdown file")
    latex_command: str = Field(default="\\section", description="LaTeX sectioning command")
    figures: list[str] = Field(default_factory=list, description="Figure files referenced")
    tables: int = Field(default=0, description="Number of tables")
    equations: int = Field(default=0, description="Estimated number of equations")
    estimated_pages: float = Field(default=1.0, description="Estimated page count")
    priority: int = Field(default=1, description="Priority for page budget (1=highest)")


class StructurePlan(BaseModel):
    """Phase 1 output: full document structure plan."""
    title: str = Field(..., description="Article title")
    abstract_file: str | None = Field(default=None, description="Path to abstract markdown")
    sections: list[SectionPlan] = Field(..., description="Ordered list of section plans")
    bibliography_file: str | None = Field(default=None, description="Path to .bib file")
    total_estimated_pages: float = Field(default=0.0, description="Total estimated pages")
    page_budget: int | None = Field(default=None, description="Target page count")
    budget_status: str = Field(default="ok", description="'ok', 'over', or 'under'")


# ---------------------------------------------------------------------------
# Phase 4: Compilation
# ---------------------------------------------------------------------------

class CompilationWarning(BaseModel):
    """A single warning or error from LaTeX compilation."""
    file: str = Field(default="", description="Source file")
    line: int | None = Field(default=None, description="Line number")
    message: str = Field(..., description="Warning/error message")
    severity: Severity = Field(default=Severity.WARNING)
    context: str = Field(default="", description="±5 line window around the error")


class CompilationResult(BaseModel):
    """Result of a LaTeX compilation attempt."""
    success: bool = Field(..., description="Whether compilation succeeded")
    pdf_path: str | None = Field(default=None, description="Path to generated PDF")
    errors: list[CompilationWarning] = Field(default_factory=list)
    warnings: list[CompilationWarning] = Field(default_factory=list)
    page_count: int | None = Field(default=None, description="PDF page count")
    unresolved_refs: list[str] = Field(default_factory=list, description="Unresolved references")
    log_excerpt: str = Field(default="", description="Relevant log excerpt")


# ---------------------------------------------------------------------------
# Phase 4: Review
# ---------------------------------------------------------------------------

class ReviewFeedback(BaseModel):
    """Structured review output from a reviewer agent."""
    Reviewer: str = Field(..., description="Name of the reviewer agent")
    Review: str = Field(..., description="Semicolon-separated feedback points")
    severity: Severity = Field(default=Severity.WARNING, description="Overall severity")


# ---------------------------------------------------------------------------
# Faithfulness Checking
# ---------------------------------------------------------------------------

class FaithfulnessViolation(BaseModel):
    """A single faithfulness violation."""
    severity: Severity = Field(...)
    source_text: str = Field(default="", description="Original text from source")
    output_text: str = Field(default="", description="Text in generated output")
    issue: str = Field(..., description="Description of the violation")
    recommendation: str = Field(default="", description="How to fix")


class FaithfulnessReport(BaseModel):
    """Result of faithfulness checking (deterministic + LLM)."""
    passed: bool = Field(..., description="Whether faithfulness check passed")
    violations: list[FaithfulnessViolation] = Field(default_factory=list)
    section_match: bool = Field(default=True, description="Section headings match")
    math_match: bool = Field(default=True, description="Math environments preserved")
    citation_match: bool = Field(default=True, description="Citation keys match")
    figure_match: bool = Field(default=True, description="Figure references match")


# ---------------------------------------------------------------------------
# Phase 5: Page Budget
# ---------------------------------------------------------------------------

class SplitDecision(BaseModel):
    """Advisory output from PageBudgetManager."""
    action: str = Field(..., description="'ok', 'warn_over', or 'warn_under'")
    current_pages: int = Field(default=0)
    budget_pages: int | None = Field(default=None)
    sections_to_move: list[str] = Field(default_factory=list, description="Sections to consider moving to appendix/supplementary")
    figures_to_move: list[str] = Field(default_factory=list, description="Figures to consider moving")
    estimated_savings: float = Field(default=0.0, description="Estimated page savings")
    recommendations: str = Field(default="", description="Human-readable recommendations")


# ---------------------------------------------------------------------------
# Phase 6: Finalization
# ---------------------------------------------------------------------------

class BuildManifest(BaseModel):
    """Provenance record for the final output."""
    project_name: str = Field(...)
    output_dir: str = Field(...)
    main_tex: str = Field(default="main.tex")
    pdf_file: str | None = Field(default=None)
    source_files: list[str] = Field(default_factory=list)
    figure_files: list[str] = Field(default_factory=list)
    bibliography_file: str | None = Field(default=None)
    template_used: str = Field(default="")
    compilation_attempts: int = Field(default=0)
    review_rounds: int = Field(default=0)
    faithfulness_passed: bool = Field(default=False)
    page_count: int | None = Field(default=None)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level Pipeline Result
# ---------------------------------------------------------------------------

class PipelineResult(BaseModel):
    """Top-level result of the full pipeline run."""
    success: bool = Field(...)
    structure_plan: StructurePlan | None = Field(default=None)
    compilation_result: CompilationResult | None = Field(default=None)
    faithfulness_report: FaithfulnessReport | None = Field(default=None)
    split_decision: SplitDecision | None = Field(default=None)
    manifest: BuildManifest | None = Field(default=None)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    phases_completed: list[PipelinePhase] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Project Configuration (loaded from YAML)
# ---------------------------------------------------------------------------

class ModelConfig(BaseModel):
    """LLM model configuration per role."""
    default: str = Field(default="gpt-5.2", description="Default model")
    assembler: str | None = Field(default=None)
    planner: str | None = Field(default=None)
    reviewer: str | None = Field(default=None)
    editor: str | None = Field(default=None)


class AzureConfig(BaseModel):
    """Azure OpenAI connection settings."""
    api_key: str = Field(default="", description="Azure OpenAI API key (or ${ENV_VAR})")
    api_version: str = Field(default="", description="API version")
    endpoint: str = Field(default="", description="Azure endpoint URL")


class ProjectConfig(BaseModel):
    """Full project configuration loaded from config.yaml."""
    project_name: str = Field(default="research-article")
    template: str = Field(default="elsarticle", description="LaTeX template name")
    template_file: str | None = Field(default=None, description="Path to custom template .tex")
    journal_name: str = Field(default="", description="Target journal name")
    page_budget: int | None = Field(default=None, description="Target page count")
    latex_engine: str = Field(default="pdflatex", description="pdflatex, xelatex, or lualatex")
    bib_style: str = Field(default="elsarticle-num", description="Bibliography style")

    # File paths
    draft_dir: str = Field(default="drafts/", description="Directory containing markdown drafts")
    figure_dir: str = Field(default="figures/", description="Directory containing figures")
    bibliography: str | None = Field(default=None, description="Path to .bib file")
    output_dir: str = Field(default="output/", description="Output directory")

    # Azure OpenAI
    azure: AzureConfig = Field(default_factory=AzureConfig)

    # Models
    models: ModelConfig = Field(default_factory=ModelConfig)

    # Pipeline settings
    compile_max_attempts: int = Field(default=3, description="Max compile-fix loop attempts")
    review_max_turns: int = Field(default=2, description="Max turns per reviewer")
    review_max_rounds: int = Field(default=2, description="Max review-fix-recompile rounds")
    timeout: int = Field(default=120, description="LLM call timeout in seconds")
    seed: int = Field(default=42, description="LLM seed for reproducibility")

    # Enabled reviewers
    enabled_reviewers: dict[str, bool] = Field(
        default_factory=lambda: {
            "LaTeXLinter": True,
            "StyleChecker": True,
            "FaithfulnessChecker": True,
            "MetaReviewer": True,
        }
    )
