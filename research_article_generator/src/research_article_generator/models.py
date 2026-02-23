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
    SUPPLEMENTARY = "supplementary"
    FINALIZATION = "finalization"


class PlanAction(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    ABORT = "abort"


class PlanReviewResult(BaseModel):
    """Result of a human plan review: approve, revise (with feedback), or abort."""
    action: PlanAction = PlanAction.APPROVE
    feedback: str = ""


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
    plan_review_notes: str | None = Field(default=None, description="Notes from PlanReviewer agent")


# ---------------------------------------------------------------------------
# Phase 4: Compilation
# ---------------------------------------------------------------------------

class TikZIssue(BaseModel):
    """A single issue found during TikZ diagram review."""
    category: str = Field(..., description="Issue category: syntax, spacing, labels, libraries, layout, or integration")
    severity: Severity = Field(..., description="Issue severity")
    description: str = Field(..., description="Human-readable description of the issue")


class TikZReviewResult(BaseModel):
    """Structured result from the TikZ reviewer agent."""
    verdict: str = Field(..., description="'PASS' or 'FAIL'")
    issues: list[TikZIssue] = Field(default_factory=list, description="List of issues found")


class FigureSuggestion(BaseModel):
    """A single figure/plot suggestion for a section."""
    description: str = Field(..., description="What to plot/show (e.g. 'Line plot of training loss vs epochs')")
    rationale: str = Field(..., description="Why this figure would improve the section")
    plot_type: str = Field(..., description="'line plot', 'bar chart', 'heatmap', 'schematic', 'diagram', etc.")
    data_source: str = Field(..., description="What data to use (e.g. 'Table 2 results', 'Section 3 convergence data')")
    suggested_caption: str = Field(..., description="Draft caption for the figure")


class FigureSuggestionList(BaseModel):
    """Structured output from the FigureSuggester agent."""
    suggestions: list[FigureSuggestion] = Field(default_factory=list)


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


class SectionReviewResult(BaseModel):
    """Per-section review outcome from Phase 2 review loop."""
    section_id: str = Field(..., description="Section identifier")
    reviews: list[ReviewFeedback] = Field(default_factory=list, description="Reviews collected")
    faithfulness: "FaithfulnessReport | None" = Field(default=None, description="Per-section faithfulness check")
    fix_applied: bool = Field(default=False, description="Whether a fix was applied after review")


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

class SupplementaryClassification(BaseModel):
    """Per-section classification for supplementary placement."""
    section_id: str = Field(..., description="Section identifier")
    placement: str = Field(..., description="'main' or 'supplementary'")
    reasoning: str = Field(..., description="Why this section belongs there")
    priority: int = Field(default=1, description="Priority (1=highest)")
    estimated_pages: float = Field(default=0.0, description="Estimated page count")


class SupplementaryPlan(BaseModel):
    """Complete plan for supplementary material generation."""
    mode: str = Field(default="standalone", description="'appendix' or 'standalone'")
    main_sections: list[str] = Field(default_factory=list, description="Sections staying in main document")
    supplementary_sections: list[str] = Field(default_factory=list, description="Sections moving to supplementary")
    supplementary_figures: list[str] = Field(default_factory=list, description="Figures moving to supplementary")
    classifications: list[SupplementaryClassification] = Field(default_factory=list, description="Per-section classifications")
    estimated_main_pages: float = Field(default=0.0, description="Estimated main document pages after split")
    estimated_supp_pages: float = Field(default=0.0, description="Estimated supplementary pages")
    cross_reference_note: str = Field(
        default="See Supplementary Materials for additional details.",
        description="Note to insert in main document",
    )


class SplitDecision(BaseModel):
    """Advisory output from PageBudgetManager."""
    action: str = Field(..., description="'ok', 'warn_over', 'warn_under', or 'split'")
    current_pages: int = Field(default=0)
    budget_pages: int | None = Field(default=None)
    sections_to_move: list[str] = Field(default_factory=list, description="Sections to consider moving to appendix/supplementary")
    figures_to_move: list[str] = Field(default_factory=list, description="Figures to consider moving")
    estimated_savings: float = Field(default=0.0, description="Estimated page savings")
    recommendations: str = Field(default="", description="Human-readable recommendations")
    supplementary_plan: SupplementaryPlan | None = Field(default=None, description="Detailed supplementary plan when action is 'split'")


# ---------------------------------------------------------------------------
# Phase 6: Finalization
# ---------------------------------------------------------------------------

class BuildManifest(BaseModel):
    """Provenance record for the final output."""
    project_name: str = Field(...)
    output_dir: str = Field(...)
    main_tex: str = Field(default="main.tex")
    section_files: list[str] = Field(default_factory=list, description="Section .tex files under sections/")
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
    supplementary_tex: str | None = Field(default=None, description="Path to supplementary .tex file")
    supplementary_pdf: str | None = Field(default=None, description="Path to supplementary .pdf file")
    supplementary_sections: list[str] = Field(default_factory=list, description="Sections moved to supplementary")
    figure_suggestions_file: str | None = Field(default=None, description="Path to figure_suggestions.json")


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
    max_plan_revisions: int = Field(default=3, description="Max plan revision rounds before auto-approving")
    timeout: int = Field(default=120, description="LLM call timeout in seconds")
    seed: int = Field(default=42, description="LLM seed for reproducibility")

    # Supplementary materials
    supplementary_mode: str = Field(
        default="disabled",
        description="'disabled', 'appendix', 'standalone', or 'auto'",
    )
    supplementary_threshold: float = Field(
        default=1.2,
        description="Page ratio threshold for auto mode (page_count / page_budget)",
    )

    # Enabled reviewers
    enabled_reviewers: dict[str, bool] = Field(
        default_factory=lambda: {
            "LaTeXLinter": True,
            "StyleChecker": True,
            "FaithfulnessChecker": True,
            "MetaReviewer": True,
            "PlanReviewer": True,
        }
    )

    # TikZ diagram generation
    tikz_enabled: bool = Field(default=False, description="Enable TikZ diagram generation from text")
    tikz_review_max_turns: int = Field(default=3, description="Max TikZ review-fix rounds")

    # Figure suggestion
    figure_suggestion_enabled: bool = Field(default=False, description="Enable figure suggestion agent")
    figure_suggestion_max: int = Field(default=3, description="Max suggestions per section")
