"""Pipeline — 4-phase orchestration for ML system design generation.

Phase 1: CONFIGURATION   — Validate config, interactive fill-in
Phase 2: UNDERSTANDING   — Read & summarize docs, gap analysis, vector DB
Phase 3: DESIGN          — Plan structure, write sections, review, compile
Phase 4: USER_REVIEW     — Present draft, collect feedback, revise
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import autogen

from .agents.consistency_checker import make_consistency_checker
from .agents.design_planner import make_design_planner
from .agents.design_reviewer import make_design_reviewer, validate_review
from .agents.design_writer import make_design_writer
from .agents.doc_analyzer import make_doc_analyzer
from .agents.feasibility_assessor import make_feasibility_assessor
from .agents.gap_analyzer import make_gap_analyzer
from .agents.infra_advisor import make_infra_advisor
from .agents.latex_assembler import make_assembler
from .agents.latex_cosmetic_reviewer import make_latex_cosmetic_reviewer
from .agents.opportunity_analyzer import make_opportunity_analyzer
from .agents.page_budget_manager import make_page_budget_manager
from .agents.quality_reviewer import make_quality_reviewer
from .agents.understanding_reviewer import make_understanding_reviewer
from .config import build_role_llm_config
from .logging_config import PipelineCallbacks, RichCallbacks, logger
from .models import (
    BuildManifest,
    CompilationResult,
    ConfigValidationResult,
    DesignPlan,
    DesignSection,
    DocumentSummary,
    FeasibilityReport,
    GapReport,
    Opportunity,
    OpportunityReport,
    OpportunitySelection,
    OpportunitySelectionAction,
    PipelinePhase,
    PipelineResult,
    PlanAction,
    ProjectConfig,
    ReviewFeedback,
    Severity,
    SplitDecision,
    UnderstandingReport,
    UserFeedback,
)
from .tools.compiler import extract_error_context, run_latexmk
from .tools.latex_linter import autofix_section
from .tools.doc_reader import chunk_all_documents, list_doc_files, read_document, total_size_kb
from .tools.latex_builder import (
    assemble_main_tex,
    assemble_supplementary_tex,
    generate_preamble,
    write_main_tex,
    write_section_files,
    write_supplementary_tex,
)
from .tools.page_counter import count_pages
from .tools.pandoc_converter import convert_markdown_string_to_latex
from .tools.template_loader import get_style_max_pages, load_style_template, summarize_style

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _looks_like_latex(text: str) -> bool:
    """Heuristic check that text is LaTeX."""
    latex_markers = ["\\begin{", "\\section", "\\documentclass", "\\usepackage", "\\end{"]
    return any(m in text for m in latex_markers)


def _extract_text(response: Any) -> str:
    """Extract text string from an AG2 chat response."""
    if hasattr(response, "summary") and response.summary:
        text = str(response.summary)
    elif hasattr(response, "chat_history") and response.chat_history:
        last = response.chat_history[-1]
        text = last.get("content", "") if isinstance(last, dict) else str(last)
    else:
        text = str(response)

    text = re.sub(r"```(?:latex|tex|json|markdown|md)?\n?", "", text)
    text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _extract_json(response: Any, model_cls: type) -> Any:
    """Extract and validate a Pydantic model from an AG2 response."""
    text = _extract_text(response)
    if "{" in text:
        json_str = text[text.find("{"):text.rfind("}") + 1]
        try:
            return model_cls.model_validate_json(json_str)
        except Exception:
            pass
    try:
        return model_cls.model_validate_json(text)
    except Exception as e:
        logger.warning("Failed to parse %s from response: %s", model_cls.__name__, e)
        return None


_TODO_RE = re.compile(r"<!--\s*TODO:?\s*.*?-->", re.DOTALL)


def _strip_todo_markers(text: str) -> str:
    """Remove <!-- TODO: ... --> markers from text."""
    return _TODO_RE.sub("", text)


def _find_todos(text: str) -> list[str]:
    """Return all TODO markers found in text."""
    return _TODO_RE.findall(text)


def _count_words(text: str) -> int:
    """Count words in markdown text, excluding code blocks and HTML comments."""
    cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
    return len(cleaned.split())


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    for char, escaped in [("&", r"\&"), ("%", r"\%"), ("$", r"\$"),
                          ("#", r"\#"), ("_", r"\_"), ("{", r"\{"), ("}", r"\}")]:
        text = text.replace(char, escaped)
    return text


def _make_orchestrator() -> autogen.UserProxyAgent:
    """Create a standard orchestrator agent."""
    return autogen.UserProxyAgent(
        name="Orchestrator",
        human_input_mode="NEVER",
        code_execution_config=False,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """Orchestrates the 4-phase ML system design generation pipeline."""

    def __init__(
        self,
        config: ProjectConfig,
        config_dir: Path | None = None,
        callbacks: PipelineCallbacks | None = None,
    ) -> None:
        self.config = config
        self.config_dir = config_dir or Path(".")
        self.callbacks = callbacks or RichCallbacks()

        # Resolve paths relative to config dir
        self.docs_dir = self.config_dir / config.docs_dir
        self.output_dir = self.config_dir / config.output_dir

        # Style template context
        self.style_context: str = summarize_style(self.config.style)

        # State
        self.understanding_report: UnderstandingReport | None = None
        self.opportunity_report: OpportunityReport | None = None
        self.opportunity_selection: OpportunitySelection | None = None
        self.feasibility_report: FeasibilityReport | None = None
        self.design_plan: DesignPlan | None = None
        self.section_markdown: dict[str, str] = {}   # section_id -> markdown
        self.section_latex: dict[str, str] = {}       # section_id -> polished LaTeX
        self.compilation_result: CompilationResult | None = None
        self.split_decision: SplitDecision | None = None
        self.manifest: BuildManifest | None = None
        self.vector_db_dir: Path | None = None

    # -----------------------------------------------------------------------
    # Phase 1: Configuration & Validation
    # -----------------------------------------------------------------------

    def run_configuration(self) -> ConfigValidationResult:
        """Phase 1: Validate config and fill missing fields."""
        self.callbacks.on_phase_start("CONFIGURATION", "Validating configuration")

        missing: list[str] = []
        warnings: list[str] = []

        if not self.config.project_name:
            missing.append("project_name")

        if not self.docs_dir.exists():
            missing.append(f"docs_dir ({self.docs_dir} does not exist)")
        elif not list_doc_files(self.docs_dir):
            missing.append(f"No .md files found in {self.docs_dir}")

        if not self.config.azure.api_key:
            warnings.append("Azure API key not set — LLM calls will fail")

        if self.config.max_pages is None:
            default_pages = get_style_max_pages(self.config.style)
            if default_pages:
                self.config.max_pages = default_pages
                warnings.append(f"max_pages defaulted to {default_pages} from style template")

        valid = len(missing) == 0
        result = ConfigValidationResult(
            valid=valid,
            missing_fields=missing,
            warnings=warnings,
        )

        self.callbacks.on_phase_end("CONFIGURATION", valid)
        return result

    # -----------------------------------------------------------------------
    # Phase 2: Document Understanding
    # -----------------------------------------------------------------------

    def run_understanding(self) -> UnderstandingReport:
        """Phase 2: Read, summarize, gap-analyze source documents."""
        self.callbacks.on_phase_start("UNDERSTANDING", "Analyzing source documents")

        doc_files = list_doc_files(self.docs_dir)
        if not doc_files:
            raise FileNotFoundError(f"No .md files found in {self.docs_dir}")

        # Vector DB creation if docs are large enough
        vector_db_created = False
        total_chunks = 0
        if self.config.vector_db_enabled:
            size_kb = total_size_kb(self.docs_dir)
            if size_kb > self.config.vector_db_threshold_kb:
                self.callbacks.on_warning(
                    f"Docs total {size_kb:.1f}KB > threshold {self.config.vector_db_threshold_kb}KB, "
                    f"creating vector store"
                )
                self.vector_db_dir = self.output_dir / ".vectordb"
                chunks = chunk_all_documents(self.docs_dir)
                if chunks:
                    from .tools.vector_store import create_vector_store
                    total_chunks = create_vector_store(chunks, self.vector_db_dir)
                    vector_db_created = True

        # DocAnalyzer: summarize each document
        orchestrator = _make_orchestrator()
        doc_analyzer = make_doc_analyzer(self.config)
        summaries: list[DocumentSummary] = []

        for doc_file in doc_files:
            self.callbacks.on_section_start(doc_file.name)
            content = read_document(doc_file)

            response = orchestrator.initiate_chat(
                doc_analyzer,
                message=f"Analyze this document:\n\nFile: {doc_file.name}\n\n{content}",
                max_turns=1,
            )

            summary = _extract_json(response, DocumentSummary)
            if summary is None:
                # Fallback
                summary = DocumentSummary(
                    file_path=str(doc_file),
                    title=doc_file.stem.replace("_", " ").title(),
                    key_topics=[],
                    word_count=len(content.split()),
                    summary=content[:200],
                )
            summaries.append(summary)
            self.callbacks.on_section_end(doc_file.name)

        # GapAnalyzer: identify gaps
        gap_analyzer = make_gap_analyzer(self.config)
        summaries_text = "\n\n".join(
            f"=== {s.title} ===\n{s.summary}\nTopics: {', '.join(s.key_topics)}"
            for s in summaries
        )

        style_info = f"Design style: {self.config.style}\n"
        if self.config.infrastructure.provider:
            style_info += f"Infrastructure: {self.config.infrastructure.provider}\n"
        if self.config.tech_stack:
            style_info += f"Tech stack: {', '.join(self.config.tech_stack)}\n"

        response = orchestrator.initiate_chat(
            gap_analyzer,
            message=(
                f"Analyze gaps in source material for an ML system design document.\n\n"
                f"{style_info}\n"
                f"Document summaries:\n{summaries_text}"
            ),
            max_turns=1,
        )

        gap_report = _extract_json(response, GapReport)
        if gap_report is None:
            gap_report = GapReport(confidence_score=0.5)

        # UnderstandingReviewer: cross-check
        understanding_reviewer = make_understanding_reviewer(self.config)
        for round_num in range(self.config.understanding_max_rounds):
            response = orchestrator.initiate_chat(
                understanding_reviewer,
                message=(
                    f"Cross-check the document understanding (round {round_num + 1}).\n\n"
                    f"Summaries:\n{summaries_text}\n\n"
                    f"Gap report:\n{gap_report.model_dump_json(indent=2)}"
                ),
                max_turns=1,
            )

            raw_text = _extract_text(response)
            feedback, _err = validate_review(raw_text)

            if feedback is None or "no issues" in (feedback.Review or "").lower():
                break

            self.callbacks.on_warning(
                f"UnderstandingReviewer round {round_num + 1}: {feedback.Review[:100]}..."
            )

        # Build cross-references from summaries
        all_topics: list[str] = []
        for s in summaries:
            all_topics.extend(s.key_topics)
        # Find topics that appear in multiple docs
        from collections import Counter
        topic_counts = Counter(all_topics)
        cross_refs = [t for t, c in topic_counts.items() if c > 1]

        self.understanding_report = UnderstandingReport(
            documents=summaries,
            cross_references=cross_refs,
            gap_report=gap_report,
            vector_db_created=vector_db_created,
            total_chunks=total_chunks,
        )

        self.callbacks.on_phase_end("UNDERSTANDING", True)
        return self.understanding_report

    # -----------------------------------------------------------------------
    # Phase 2b: Opportunity Discovery
    # -----------------------------------------------------------------------

    def run_opportunity_discovery(self) -> OpportunityReport:
        """Propose ML solution directions from the understanding report."""
        if not self.understanding_report:
            raise RuntimeError("Must run understanding phase first")

        self.callbacks.on_phase_start(
            "OPPORTUNITY_DISCOVERY", "Discovering ML opportunities"
        )
        orchestrator = _make_orchestrator()
        analyzer = make_opportunity_analyzer(self.config)

        # Build prompt from understanding report
        summaries_text = "\n".join(
            f"- {doc.title}: {doc.summary}" for doc in self.understanding_report.documents
        )
        gaps_text = "\n".join(
            f"- [{g.severity.value}] {g.area}: {g.description}"
            for g in self.understanding_report.gap_report.gaps
        )

        context_parts: list[str] = [
            f"Project: {self.config.project_name}",
            f"Target audience: {self.config.target_audience}",
        ]
        if self.config.infrastructure.provider:
            context_parts.append(f"Infrastructure: {self.config.infrastructure.provider}")
        if self.config.tech_stack:
            context_parts.append(f"Tech stack: {', '.join(self.config.tech_stack)}")
        if self.config.constraints:
            context_parts.append(f"Constraints: {', '.join(self.config.constraints)}")
        if self.config.team_size:
            context_parts.append(f"Team size: {self.config.team_size}")
        if self.config.timeline:
            context_parts.append(f"Timeline: {self.config.timeline}")

        prompt = (
            f"Analyze the following source documents and propose up to "
            f"{self.config.max_opportunities} ML solution directions.\n\n"
            f"PROJECT CONTEXT:\n" + "\n".join(context_parts) + "\n\n"
            f"DOCUMENT SUMMARIES:\n{summaries_text}\n\n"
            f"GAP ANALYSIS:\n{gaps_text or 'No gaps identified.'}\n\n"
            f"Cross-references: {', '.join(self.understanding_report.cross_references) or 'none'}"
        )

        response = orchestrator.initiate_chat(analyzer, message=prompt, max_turns=1)
        report = _extract_json(response, OpportunityReport)

        if report is None:
            # Fallback: generic opportunity
            logger.warning("OpportunityAnalyzer failed, creating generic opportunity")
            report = OpportunityReport(
                opportunities=[
                    Opportunity(
                        opportunity_id="ml_system_design",
                        title="ML System Design",
                        category="general",
                        description="General ML system design based on source documents.",
                        estimated_complexity="medium",
                        potential_impact="medium",
                    )
                ],
                summary="Fallback: could not parse LLM response.",
            )

        self.opportunity_report = report
        self.callbacks.on_phase_end("OPPORTUNITY_DISCOVERY", True)
        return report

    # -----------------------------------------------------------------------
    # Phase 2c: Feasibility Check
    # -----------------------------------------------------------------------

    def run_feasibility_check(self) -> FeasibilityReport:
        """Assess feasibility of selected ML opportunities."""
        if not self.opportunity_selection:
            raise RuntimeError("Must select opportunities first")

        self.callbacks.on_phase_start(
            "FEASIBILITY_CHECK", "Assessing feasibility"
        )
        orchestrator = _make_orchestrator()
        assessor = make_feasibility_assessor(self.config)

        # Build description of selected opportunities
        selected_desc = ""
        if (
            self.opportunity_selection.action == OpportunitySelectionAction.CUSTOM
            and self.opportunity_selection.custom_opportunity
        ):
            selected_desc = f"Custom direction: {self.opportunity_selection.custom_opportunity}"
            selected_ids = ["custom"]
        elif self.opportunity_report:
            selected_ids = self.opportunity_selection.selected_ids
            by_id = {o.opportunity_id: o for o in self.opportunity_report.opportunities}
            parts: list[str] = []
            for oid in selected_ids:
                opp = by_id.get(oid)
                if opp:
                    parts.append(f"- {opp.title} ({opp.opportunity_id}): {opp.description}")
            selected_desc = "\n".join(parts)
        else:
            selected_ids = self.opportunity_selection.selected_ids
            selected_desc = f"Selected IDs: {', '.join(selected_ids)}"

        if self.opportunity_selection.combination_note:
            selected_desc += f"\nCombination guidance: {self.opportunity_selection.combination_note}"

        context_parts: list[str] = [
            f"Project: {self.config.project_name}",
        ]
        if self.config.infrastructure.provider:
            ctx = f"Infrastructure: {self.config.infrastructure.provider}"
            if self.config.infrastructure.compute:
                ctx += f", Compute: {', '.join(self.config.infrastructure.compute)}"
            if self.config.infrastructure.storage:
                ctx += f", Storage: {', '.join(self.config.infrastructure.storage)}"
            if self.config.infrastructure.services:
                ctx += f", Services: {', '.join(self.config.infrastructure.services)}"
            context_parts.append(ctx)
        if self.config.tech_stack:
            context_parts.append(f"Tech stack: {', '.join(self.config.tech_stack)}")
        if self.config.team_size:
            context_parts.append(f"Team size: {self.config.team_size}")
        if self.config.timeline:
            context_parts.append(f"Timeline: {self.config.timeline}")
        if self.config.constraints:
            context_parts.append(f"Constraints: {', '.join(self.config.constraints)}")

        prompt = (
            f"Assess the feasibility of the following ML direction(s).\n\n"
            f"SELECTED OPPORTUNITIES:\n{selected_desc}\n\n"
            f"PROJECT CONTEXT:\n" + "\n".join(context_parts)
        )

        report: FeasibilityReport | None = None
        for attempt in range(self.config.feasibility_max_rounds):
            response = orchestrator.initiate_chat(assessor, message=prompt, max_turns=1)
            report = _extract_json(response, FeasibilityReport)
            if report is not None:
                break
            logger.warning(
                "Feasibility parse attempt %d/%d failed",
                attempt + 1,
                self.config.feasibility_max_rounds,
            )

        if report is None:
            logger.warning("FeasibilityAssessor failed, creating inconclusive report")
            report = FeasibilityReport(
                selected_opportunities=selected_ids,
                overall_feasible=True,
                overall_summary="Feasibility assessment inconclusive — proceeding with caution.",
            )

        self.feasibility_report = report
        self.callbacks.on_phase_end("FEASIBILITY_CHECK", True)
        return report

    # -----------------------------------------------------------------------
    # Phase 3: Design Generation
    # -----------------------------------------------------------------------

    def run_plan(self, revision_feedback: str | None = None) -> DesignPlan:
        """Create (or revise) the design plan without writing sections.

        Parameters
        ----------
        revision_feedback : str | None
            If provided, the prior plan and this feedback are included in the
            prompt so the planner can revise.
        """
        if not self.understanding_report:
            raise RuntimeError("Must run understanding phase first")

        self.callbacks.on_phase_start("PLAN", "Creating design plan")
        orchestrator = _make_orchestrator()

        planner = make_design_planner(self.config, style_context=self.style_context)

        understanding_summary = ""
        for doc in self.understanding_report.documents:
            understanding_summary += f"- {doc.title}: {doc.summary}\n"

        prompt = (
            f"Create a design plan for: {self.config.project_name}\n\n"
            f"Style: {self.config.style}\n"
            f"Max pages: {self.config.max_pages or 'unset'}\n"
            f"Target audience: {self.config.target_audience}\n"
            f"Tech stack: {', '.join(self.config.tech_stack) or 'unspecified'}\n"
            f"Infrastructure: {self.config.infrastructure.provider or 'unspecified'}\n"
            f"Constraints: {', '.join(self.config.constraints) or 'none'}\n\n"
            f"Source document summaries:\n{understanding_summary}\n\n"
            f"Gap report confidence: {self.understanding_report.gap_report.confidence_score}\n"
            f"Cross-references: {', '.join(self.understanding_report.cross_references)}"
        )

        # Inject opportunity & feasibility context if available
        if self.opportunity_selection and self.opportunity_report:
            direction_lines: list[str] = []
            if self.opportunity_selection.action == OpportunitySelectionAction.CUSTOM:
                direction_lines.append(
                    f"- Custom: {self.opportunity_selection.custom_opportunity}"
                )
            else:
                by_id = {
                    o.opportunity_id: o
                    for o in self.opportunity_report.opportunities
                }
                for oid in self.opportunity_selection.selected_ids:
                    opp = by_id.get(oid)
                    if opp:
                        direction_lines.append(f"- {opp.title}: {opp.description}")
            if self.opportunity_selection.combination_note:
                direction_lines.append(
                    f"Combination guidance: {self.opportunity_selection.combination_note}"
                )
            prompt += (
                f"\n\nSELECTED ML DIRECTION(S):\n" + "\n".join(direction_lines)
            )

        if self.feasibility_report:
            fr = self.feasibility_report
            risk_lines = [
                f"  - [{item.risk_level}] {item.area}: {item.assessment}"
                for item in fr.items
                if item.risk_level in ("medium", "high", "critical")
            ]
            prompt += (
                f"\n\nFEASIBILITY ASSESSMENT:\n"
                f"Overall feasible: {fr.overall_feasible}\n"
                f"Summary: {fr.overall_summary}\n"
            )
            if risk_lines:
                prompt += "Key risks to address in design:\n" + "\n".join(risk_lines)

        if revision_feedback and self.design_plan:
            prompt += (
                f"\n\nPREVIOUS PLAN (needs revision):\n"
                f"{self.design_plan.model_dump_json(indent=2)}\n\n"
                f"USER FEEDBACK:\n{revision_feedback}\n\n"
                f"Please revise the plan based on the feedback above."
            )

        response = orchestrator.initiate_chat(planner, message=prompt, max_turns=1)

        plan = _extract_json(response, DesignPlan)
        if plan is None:
            logger.warning("LLM planning failed, creating plan from style template")
            template = load_style_template(self.config.style)
            sections = []
            for s in template.get("sections", []):
                sections.append(DesignSection(
                    section_id=s["id"],
                    title=s["title"],
                    content_guidance=s.get("guidance", ""),
                    estimated_pages=s.get("estimated_pages", 1.0),
                ))
            plan = DesignPlan(
                title=self.config.project_name,
                style=self.config.style,
                sections=sections,
                total_estimated_pages=sum(s.estimated_pages for s in sections),
                page_budget=self.config.max_pages,
            )

        # Assign word limits based on page budget
        self._assign_word_limits(plan)
        self.design_plan = plan

        self.callbacks.on_phase_end("PLAN", True)
        return plan

    def _assign_word_limits(self, plan: DesignPlan) -> None:
        """Compute per-section word limits from page budget."""
        max_pages = self.config.max_pages
        if not max_pages:
            return

        total_words = max_pages * self.config.words_per_page
        total_estimated = plan.total_estimated_pages or sum(
            s.estimated_pages for s in plan.sections
        )
        if total_estimated <= 0:
            return

        for section in plan.sections:
            ratio = section.estimated_pages / total_estimated
            section.target_word_count = int(ratio * total_words)

    def run_writing(self) -> DesignPlan:
        """Write, review, convert, and compile all sections.

        Assumes ``run_plan()`` has already been called and ``self.design_plan``
        is populated.

        The flow is::

            Phase A — Initial Write (once):
                For each section: draft → resolve TODOs → condense

            Phase B — Outer Review Loop (up to writing_review_max_rounds):
                Section review: review all sections, revise if ERROR/CRITICAL
                Meta review: cross-review loop (up to _META_REVIEW_MAX)
                Convergence: break early if nothing was revised

            Phase C — Convert & Compile (once)
        """
        if not self.design_plan:
            raise RuntimeError("Must run plan phase first")

        self.callbacks.on_phase_start("WRITING", "Writing design document")
        orchestrator = _make_orchestrator()
        plan = self.design_plan

        # ---- Phase A: Initial Write (once) --------------------------------
        writer = make_design_writer(self.config)

        for section in plan.sections:
            self.callbacks.on_section_start(section.section_id)

            context = self._build_section_context(section)

            # Inject word limit if assigned
            word_limit_note = ""
            if section.target_word_count:
                target = section.target_word_count
                pages = section.estimated_pages
                word_limit_note = (
                    f"\nHARD WORD LIMIT: {target} words maximum (~{pages:.1f} pages). "
                    f"Aim for {int(target * 0.8)} words on your first draft. "
                    f"Going over this limit will trigger automatic condensation.\n"
                )

            response = orchestrator.initiate_chat(
                writer,
                message=(
                    f"Write the '{section.title}' section for the ML system design document.\n\n"
                    f"Content guidance: {section.content_guidance}\n"
                    f"Estimated pages: {section.estimated_pages}\n"
                    f"Target audience: {self.config.target_audience}\n"
                    f"{word_limit_note}\n"
                    f"Context from source documents:\n{context}"
                ),
                max_turns=1,
            )

            markdown = _extract_text(response)

            # Resolve any TODO markers by asking the writer to address them
            markdown = self._resolve_todos(section, markdown, orchestrator)
            self.section_markdown[section.section_id] = markdown

            # Word budget enforcement
            if section.target_word_count:
                markdown = self._condense_section(section, markdown, orchestrator)
                self.section_markdown[section.section_id] = markdown

            self.callbacks.on_section_end(section.section_id)

        # ---- Phase B: Outer Review Loop -----------------------------------
        _META_REVIEW_MAX = 2

        for outer_round in range(1, self.config.writing_review_max_rounds + 1):
            self.callbacks.on_review_round(outer_round, self.config.writing_review_max_rounds)
            any_revised = False

            # -- Section review: all sections every pass --
            for section in plan.sections:
                markdown = self.section_markdown[section.section_id]
                review_feedback = self._review_section(
                    section.section_id, markdown, orchestrator,
                )

                if review_feedback and any(
                    r.severity in (Severity.ERROR, Severity.CRITICAL)
                    for r in review_feedback
                ):
                    feedback_text = "\n".join(
                        f"[{r.Reviewer}]: {r.Review}" for r in review_feedback
                    )
                    word_budget_note = ""
                    if section.target_word_count:
                        word_budget_note = (
                            f"\nHARD WORD LIMIT: {section.target_word_count} words maximum. "
                            f"Do NOT expand the section while fixing issues.\n"
                        )
                    fix_writer = make_design_writer(self.config)
                    fix_response = orchestrator.initiate_chat(
                        fix_writer,
                        message=(
                            f"Revise the '{section.title}' section based on reviewer feedback.\n\n"
                            f"{word_budget_note}"
                            f"FEEDBACK:\n{feedback_text}\n\n"
                            f"ORIGINAL SECTION:\n{markdown}"
                        ),
                        max_turns=1,
                    )
                    revised = _extract_text(fix_response)
                    if revised:
                        revised = self._resolve_todos(section, revised, orchestrator)
                        self.section_markdown[section.section_id] = revised
                        any_revised = True

                    # Re-enforce word budget after revision
                    if section.target_word_count:
                        md = self.section_markdown[section.section_id]
                        md = self._condense_section(section, md, orchestrator)
                        self.section_markdown[section.section_id] = md

            # -- Meta review: loop until clean (up to _META_REVIEW_MAX) --
            for _meta_round in range(_META_REVIEW_MAX):
                meta_issues = self._cross_review(orchestrator)
                if meta_issues:
                    any_revised = True
                if not meta_issues:
                    break

            # -- Convergence check --
            if not any_revised:
                break

        # ---- Phase C: Convert & Compile (once) ----------------------------
        self._convert_and_compile(orchestrator)

        self.callbacks.on_phase_end("WRITING", True)
        return plan

    def run_design(self) -> DesignPlan:
        """Phase 3: Plan, write, review, compile the design document.

        Legacy method that combines ``run_plan()`` + ``run_writing()``.
        """
        self.run_plan()
        return self.run_writing()

    def _build_section_context(self, section: DesignSection) -> str:
        """Build context for section writing from understanding report + vector DB."""
        parts: list[str] = []

        # Include relevant document summaries
        if self.understanding_report:
            for doc in self.understanding_report.documents:
                parts.append(f"--- {doc.title} ---\n{doc.summary}")

        # Query vector DB for relevant chunks
        if self.vector_db_dir:
            try:
                from .tools.vector_store import query_vector_store
                query = f"{section.title} {section.content_guidance}"
                results = query_vector_store(query, self.vector_db_dir, n_results=3)
                if results:
                    parts.append("\n--- Relevant source excerpts ---")
                    for r in results:
                        parts.append(f"[{r['file_path']}]\n{r['text'][:500]}")
            except Exception as e:
                logger.warning("Vector DB query failed: %s", e)

        # Include infrastructure and tech context
        if self.config.infrastructure.provider:
            parts.append(
                f"\nInfrastructure: {self.config.infrastructure.provider}\n"
                f"Compute: {', '.join(self.config.infrastructure.compute)}\n"
                f"Storage: {', '.join(self.config.infrastructure.storage)}\n"
                f"Services: {', '.join(self.config.infrastructure.services)}"
            )
        if self.config.tech_stack:
            parts.append(f"Tech stack: {', '.join(self.config.tech_stack)}")
        if self.config.constraints:
            parts.append(f"Constraints: {', '.join(self.config.constraints)}")

        return "\n\n".join(parts) if parts else "(No additional context available)"

    def _resolve_todos(
        self,
        section: DesignSection,
        markdown: str,
        orchestrator: autogen.UserProxyAgent,
    ) -> str:
        """Resolve TODO markers by asking the writer to address each one.

        Returns the updated markdown with TODOs replaced by real content.
        If no TODOs exist, returns the original text unchanged.
        Any TODOs that the agent fails to resolve are stripped as a fallback.
        """
        todos = _find_todos(markdown)
        if not todos:
            return markdown

        self.callbacks.on_warning(
            f"{section.section_id}: resolving {len(todos)} TODO marker(s)"
        )

        context = self._build_section_context(section)
        todo_list = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(todos))

        writer = make_design_writer(self.config)
        response = orchestrator.initiate_chat(
            writer,
            message=(
                f"The following section contains TODO placeholders that must be resolved.\n"
                f"Address EVERY TODO below using the source context provided. Replace each\n"
                f"TODO marker with concrete, grounded content. If a TODO truly cannot be\n"
                f"addressed from the sources, replace it with a brief factual note.\n"
                f"Do NOT leave any <!-- TODO --> markers in the output.\n\n"
                f"TODOs to resolve:\n{todo_list}\n\n"
                f"CONTEXT FROM SOURCES:\n{context}\n\n"
                f"FULL SECTION (return the complete revised section):\n{markdown}"
            ),
            max_turns=1,
        )

        resolved = _extract_text(response)
        if not resolved:
            return _strip_todo_markers(markdown)

        # Safety net: strip any remaining TODOs the agent missed
        return _strip_todo_markers(resolved)

    def _condense_section(
        self,
        section: DesignSection,
        markdown: str,
        orchestrator: autogen.UserProxyAgent,
        max_attempts: int = 3,
    ) -> str:
        """Condense a section to fit its word budget. Returns (possibly condensed) markdown."""
        if not section.target_word_count:
            return markdown
        word_count = _count_words(markdown)
        threshold = int(section.target_word_count * 1.05)
        for attempt in range(max_attempts):
            if word_count <= threshold:
                break
            if attempt == 0:
                condense_msg = (
                    f"This section is {word_count} words but the STRICT budget is "
                    f"{section.target_word_count} words. Condense it to ~{section.target_word_count} words.\n"
                    f"Cut low-priority content, use tables/bullets, remove redundancy.\n"
                    f"Return ONLY the condensed markdown.\n\n"
                    f"SECTION:\n{markdown}"
                )
            else:
                condense_msg = (
                    f"You are at {word_count} words. The HARD LIMIT is "
                    f"{section.target_word_count} words. Cut aggressively — "
                    f"remove entire sub-sections if needed, merge tables, "
                    f"eliminate examples. Return ONLY the condensed markdown.\n\n"
                    f"SECTION:\n{markdown}"
                )
            self.callbacks.on_warning(
                f"{section.section_id}: {word_count} words vs "
                f"{section.target_word_count} target — condensing "
                f"(attempt {attempt + 1})"
            )
            condense_writer = make_design_writer(self.config)
            condense_response = orchestrator.initiate_chat(
                condense_writer,
                message=condense_msg,
                max_turns=1,
            )
            condensed = _strip_todo_markers(_extract_text(condense_response))
            new_count = _count_words(condensed) if condensed else word_count
            if condensed and new_count < word_count:
                markdown = condensed
                word_count = new_count
            else:
                break  # no improvement, stop retrying

        section.actual_word_count = _count_words(markdown)
        return markdown

    def _review_section(
        self,
        section_id: str,
        markdown: str,
        orchestrator: autogen.UserProxyAgent,
    ) -> list[ReviewFeedback]:
        """Run DesignReviewer on a section."""
        collected: list[ReviewFeedback] = []

        reviewer = make_design_reviewer(self.config)
        if reviewer is not None:
            self.callbacks.on_section_review(section_id, "DesignReviewer")
            try:
                response = orchestrator.initiate_chat(
                    reviewer,
                    message=(
                        f"Review this design section (section_id: {section_id}):\n\n{markdown}"
                    ),
                    max_turns=1,
                )
                raw = _extract_text(response)
                feedback, _err = validate_review(raw)
                if feedback:
                    collected.append(feedback)
            except Exception as e:
                self.callbacks.on_warning(f"DesignReviewer skipped for {section_id}: {e}")

        quality_reviewer = make_quality_reviewer(self.config)
        if quality_reviewer is not None:
            self.callbacks.on_section_review(section_id, "QualityReviewer")
            try:
                response = orchestrator.initiate_chat(
                    quality_reviewer,
                    message=(
                        f"Quality-check this design section (section_id: {section_id}):\n\n{markdown}"
                    ),
                    max_turns=1,
                )
                raw = _extract_text(response)
                feedback, _err = validate_review(raw)
                if feedback:
                    collected.append(feedback)
            except Exception as e:
                self.callbacks.on_warning(f"QualityReviewer skipped for {section_id}: {e}")

        return collected

    def _cross_review(self, orchestrator: autogen.UserProxyAgent) -> bool:
        """Run ConsistencyChecker and InfraAdvisor across all sections.

        Returns ``True`` if any issues were found and fixes applied.
        """
        issues_found = False

        # Build section summaries
        summaries = "\n\n".join(
            f"=== {sid} ===\n{md[:300]}..."
            for sid, md in self.section_markdown.items()
        )

        # ConsistencyChecker
        checker = make_consistency_checker(self.config)
        if checker:
            self.callbacks.on_section_review("all", "ConsistencyChecker")
            try:
                response = orchestrator.initiate_chat(
                    checker,
                    message=f"Review all section summaries for consistency:\n\n{summaries}",
                    max_turns=1,
                )
                raw = _extract_text(response)
                feedback, _err = validate_review(raw)
                if feedback and "no issues" not in (feedback.Review or "").lower():
                    self.callbacks.on_warning(f"ConsistencyChecker: {feedback.Review[:150]}")
                    self._apply_cross_review_fixes(feedback, orchestrator)
                    issues_found = True
            except Exception as e:
                self.callbacks.on_warning(f"ConsistencyChecker skipped: {e}")

        # InfraAdvisor
        advisor = make_infra_advisor(self.config)
        if advisor:
            self.callbacks.on_section_review("all", "InfraAdvisor")
            try:
                infra_context = (
                    f"Infrastructure: {self.config.infrastructure.provider}\n"
                    f"Compute: {', '.join(self.config.infrastructure.compute)}\n"
                    f"Tech stack: {', '.join(self.config.tech_stack)}\n\n"
                )
                response = orchestrator.initiate_chat(
                    advisor,
                    message=(
                        f"Review design for infrastructure feasibility:\n\n"
                        f"{infra_context}{summaries}"
                    ),
                    max_turns=1,
                )
                raw = _extract_text(response)
                feedback, _err = validate_review(raw)
                if feedback and "no issues" not in (feedback.Review or "").lower():
                    self.callbacks.on_warning(f"InfraAdvisor: {feedback.Review[:150]}")
                    self._apply_cross_review_fixes(feedback, orchestrator)
                    issues_found = True
            except Exception as e:
                self.callbacks.on_warning(f"InfraAdvisor skipped: {e}")

        return issues_found

    def _apply_cross_review_fixes(
        self,
        feedback: ReviewFeedback,
        orchestrator: autogen.UserProxyAgent,
    ) -> None:
        """Apply fixes from cross-review feedback to affected sections."""
        affected = feedback.affected_sections
        if not affected:
            # Try to extract section IDs from the review text
            for sid in self.section_markdown:
                if sid in feedback.Review:
                    affected.append(sid)

        # Look up section word budgets
        section_by_id: dict[str, DesignSection] = {}
        if self.design_plan:
            section_by_id = {s.section_id: s for s in self.design_plan.sections}

        for sid in affected:
            if sid not in self.section_markdown:
                continue
            try:
                word_budget_note = ""
                sec = section_by_id.get(sid)
                if sec and sec.target_word_count:
                    word_budget_note = (
                        f"\nHARD WORD LIMIT: {sec.target_word_count} words maximum. "
                        f"Do NOT expand the section while fixing issues.\n"
                    )
                fix_writer = make_design_writer(self.config)
                response = orchestrator.initiate_chat(
                    fix_writer,
                    message=(
                        f"Revise this section based on cross-review feedback.\n\n"
                        f"{word_budget_note}"
                        f"FEEDBACK: {feedback.Review}\n\n"
                        f"SECTION ({sid}):\n{self.section_markdown[sid]}"
                    ),
                    max_turns=1,
                )
                revised = _strip_todo_markers(_extract_text(response))
                if revised:
                    self.section_markdown[sid] = revised
            except Exception as e:
                self.callbacks.on_warning(f"Cross-review fix skipped for {sid}: {e}")

        # Re-enforce word budget after cross-review fixes
        for sid in affected:
            sec = section_by_id.get(sid)
            if sec and sec.target_word_count and sid in self.section_markdown:
                self.section_markdown[sid] = self._condense_section(
                    sec, self.section_markdown[sid], orchestrator
                )

    def _convert_and_compile(self, orchestrator: autogen.UserProxyAgent) -> None:
        """Convert markdown sections to LaTeX and compile."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Convert each section: markdown -> LaTeX via Pandoc -> LLM polish
        assembler = make_assembler(self.config)

        for section_id, markdown in self.section_markdown.items():
            self.callbacks.on_section_start(f"convert:{section_id}")

            # Pandoc conversion
            pandoc_latex = convert_markdown_string_to_latex(markdown, annotate=True)

            # LLM polish
            try:
                response = orchestrator.initiate_chat(
                    assembler,
                    message=(
                        f"Polish this Pandoc-converted LaTeX for the section '{section_id}'. "
                        f"Only modify text between SAFE_ZONE markers.\n\n{pandoc_latex}"
                    ),
                    max_turns=1,
                )
                polished = _extract_text(response)
                if polished and _looks_like_latex(polished):
                    self.section_latex[section_id] = polished
                else:
                    self.section_latex[section_id] = pandoc_latex
            except Exception as e:
                self.callbacks.on_warning(f"LaTeX polish skipped for {section_id}: {e}")
                self.section_latex[section_id] = pandoc_latex

            self.callbacks.on_section_end(f"convert:{section_id}")

        # Deterministic lint + auto-fix each section
        for section_id in list(self.section_latex):
            fixed, issues = autofix_section(section_id, self.section_latex[section_id])
            if issues:
                for issue in issues:
                    self.callbacks.on_warning(f"Lint: {issue}")
            self.section_latex[section_id] = fixed

        # LLM cosmetic review (single pass over all sections)
        self._cosmetic_review(orchestrator, assembler)

        # Assemble main.tex
        section_ids = list(self.section_latex.keys())
        preamble = generate_preamble(title=self.config.project_name, author=self.config.author)
        main_tex = assemble_main_tex(preamble, section_ids, title=self.config.project_name)
        write_main_tex(main_tex, self.output_dir)
        write_section_files(self.section_latex, self.output_dir)

        # Compile-fix loop
        for attempt in range(1, self.config.compile_max_attempts + 1):
            self.callbacks.on_compile_attempt(attempt, self.config.compile_max_attempts)

            result = run_latexmk(self.output_dir)
            if result.success:
                self.compilation_result = result
                break

            # Don't try LLM fixes for environment errors
            _unfixable = {"latexmk not found", "not found on PATH", "timed out"}
            if any(any(u in err.message for u in _unfixable) for err in result.errors):
                self.compilation_result = result
                break

            if attempt < self.config.compile_max_attempts:
                for section_id in list(self.section_latex.keys()):
                    section_content = self.section_latex[section_id]
                    error_ctx = extract_error_context(
                        result, section_content,
                        section_file=f"sections/{section_id}.tex",
                    )
                    if "No errors found" in error_ctx:
                        continue
                    try:
                        fix_response = orchestrator.initiate_chat(
                            assembler,
                            message=(
                                f"Fix LaTeX compilation errors in section {section_id}. "
                                f"Return the COMPLETE corrected section.\n"
                                f"Do NOT add \\usepackage commands.\n\n"
                                f"Errors:\n{error_ctx}\n\n"
                                f"Section content:\n{section_content}"
                            ),
                            max_turns=1,
                        )
                        new_latex = _extract_text(fix_response)
                        if new_latex and _looks_like_latex(new_latex):
                            self.section_latex[section_id] = new_latex
                    except Exception as e:
                        self.callbacks.on_warning(f"Compile-fix skipped for {section_id}: {e}")

                write_section_files(self.section_latex, self.output_dir)

            self.compilation_result = result

    def _cosmetic_review(
        self,
        orchestrator: autogen.UserProxyAgent,
        assembler: autogen.AssistantAgent,
    ) -> None:
        """Run LLM cosmetic review on assembled LaTeX (single pass).

        If the reviewer finds ERROR/CRITICAL issues, affected sections are
        re-polished by the LaTeXAssembler with the cosmetic feedback.
        """
        reviewer = make_latex_cosmetic_reviewer(self.config)
        if reviewer is None:
            return

        # Concatenate all sections for a holistic review
        combined = "\n\n".join(
            f"%%% Section: {sid} %%%\n{latex}"
            for sid, latex in self.section_latex.items()
        )

        try:
            self.callbacks.on_section_review("all", "LaTeXCosmeticReviewer")
            response = orchestrator.initiate_chat(
                reviewer,
                message=(
                    "Review the following assembled LaTeX sections for cosmetic "
                    "and structural issues.\n\n" + combined
                ),
                max_turns=1,
            )
            raw = _extract_text(response)
            feedback, _err = validate_review(raw)

            if feedback is None:
                return
            if "no issues" in (feedback.Review or "").lower():
                return
            if feedback.severity not in (Severity.ERROR, Severity.CRITICAL):
                self.callbacks.on_warning(
                    f"LaTeXCosmeticReviewer ({feedback.severity.value}): "
                    f"{feedback.Review[:150]}"
                )
                return

            # Re-polish affected sections with cosmetic feedback
            self.callbacks.on_warning(
                f"LaTeXCosmeticReviewer ({feedback.severity.value}): "
                f"{feedback.Review[:150]}"
            )
            affected = feedback.affected_sections
            if not affected:
                # Infer from review text
                affected = [
                    sid for sid in self.section_latex if sid in feedback.Review
                ]
            if not affected:
                # If no sections identified, re-polish all
                affected = list(self.section_latex.keys())

            for sid in affected:
                if sid not in self.section_latex:
                    continue
                try:
                    fix_response = orchestrator.initiate_chat(
                        assembler,
                        message=(
                            f"Fix the cosmetic issues in section '{sid}' "
                            f"identified by the reviewer.\n\n"
                            f"COSMETIC FEEDBACK:\n{feedback.Review}\n\n"
                            f"SECTION CONTENT:\n{self.section_latex[sid]}"
                        ),
                        max_turns=1,
                    )
                    fixed = _extract_text(fix_response)
                    if fixed and _looks_like_latex(fixed):
                        self.section_latex[sid] = fixed
                except Exception as e:
                    self.callbacks.on_warning(
                        f"Cosmetic fix skipped for {sid}: {e}"
                    )
        except Exception as e:
            self.callbacks.on_warning(f"LaTeXCosmeticReviewer skipped: {e}")

    # -----------------------------------------------------------------------
    # Page Budget Enforcement
    # -----------------------------------------------------------------------

    def _is_supplementary_enabled(self, page_count: int) -> bool:
        """Decide whether supplementary material generation should activate."""
        mode = self.config.supplementary_mode
        if mode in ("appendix", "standalone"):
            return True
        if mode == "auto" and self.config.max_pages:
            ratio = page_count / self.config.max_pages
            return ratio > self.config.supplementary_threshold
        return False

    def run_page_budget(self) -> SplitDecision:
        """Check compiled page count against budget, optionally plan a split."""
        self.callbacks.on_phase_start("PAGE_BUDGET", "Checking page budget")

        if not self.config.max_pages:
            decision = SplitDecision(action="ok")
            self.split_decision = decision
            self.callbacks.on_phase_end("PAGE_BUDGET", True)
            return decision

        page_count = 0
        if self.compilation_result and self.compilation_result.page_count:
            page_count = self.compilation_result.page_count

        if page_count <= self.config.max_pages:
            decision = SplitDecision(
                action="ok",
                current_pages=page_count,
                budget_pages=self.config.max_pages,
            )
            self.split_decision = decision
            self.callbacks.on_phase_end("PAGE_BUDGET", True)
            return decision

        # Over budget — call PageBudgetManager
        supplementary = self._is_supplementary_enabled(page_count)
        orchestrator = _make_orchestrator()
        agent = make_page_budget_manager(
            self.config, supplementary_enabled=supplementary,
        )

        sections_info = ""
        if self.design_plan:
            for s in self.design_plan.sections:
                actual_words = _count_words(self.section_markdown.get(s.section_id, ""))
                actual_pages_est = actual_words / self.config.words_per_page
                budget_words = s.target_word_count or 0
                over_flag = ""
                if budget_words and actual_words > budget_words:
                    pct = int((actual_words - budget_words) / budget_words * 100)
                    over_flag = f" [OVER BUDGET by {pct}%]"
                sections_info += (
                    f"- {s.section_id}: {s.title} "
                    f"(actual ~{actual_words}w / ~{actual_pages_est:.1f}p, "
                    f"budget ~{budget_words}w / {s.estimated_pages:.1f}p, "
                    f"priority={s.priority}){over_flag}\n"
                )

        response = orchestrator.initiate_chat(
            agent,
            message=(
                f"The compiled document is {page_count} pages but the budget is "
                f"{self.config.max_pages} pages.\n\n"
                f"Sections:\n{sections_info}\n"
                f"Please recommend how to bring this within budget."
            ),
            max_turns=1,
        )

        decision = _extract_json(response, SplitDecision)
        if decision is None:
            decision = SplitDecision(
                action="warn_over",
                current_pages=page_count,
                budget_pages=self.config.max_pages,
                recommendations="PageBudgetManager could not produce a plan.",
            )

        self.split_decision = decision
        self.callbacks.on_phase_end("PAGE_BUDGET", True)
        return decision

    def _condense_main_sections(self) -> None:
        """Condense main-body sections to their budgets after split decision."""
        if not self.split_decision or not self.split_decision.supplementary_plan:
            return
        plan = self.split_decision.supplementary_plan
        main_ids = set(plan.main_sections)
        if not self.design_plan:
            return

        orchestrator = _make_orchestrator()
        condensed_any = False
        for section in self.design_plan.sections:
            if section.section_id not in main_ids:
                continue
            if not section.target_word_count:
                continue
            md = self.section_markdown.get(section.section_id, "")
            word_count = _count_words(md)
            if word_count <= section.target_word_count:
                continue
            self.callbacks.on_warning(
                f"Post-split condense {section.section_id}: "
                f"{word_count} → {section.target_word_count} words"
            )
            writer = make_design_writer(self.config)
            response = orchestrator.initiate_chat(
                writer,
                message=(
                    f"You are at {word_count} words. The HARD LIMIT is "
                    f"{section.target_word_count} words. Cut aggressively — "
                    f"remove entire sub-sections if needed, merge tables, "
                    f"eliminate examples. Return ONLY the condensed markdown.\n\n"
                    f"SECTION:\n{md}"
                ),
                max_turns=1,
            )
            condensed = _strip_todo_markers(_extract_text(response))
            if condensed and _count_words(condensed) < word_count:
                self.section_markdown[section.section_id] = condensed
                condensed_any = True

        if condensed_any:
            # Re-convert condensed markdown to LaTeX
            self._convert_and_compile(orchestrator)

    def run_supplementary(self) -> CompilationResult | None:
        """Move overflow sections to appendix/standalone and recompile."""
        if not self.split_decision or self.split_decision.action != "split":
            return None
        plan = self.split_decision.supplementary_plan
        if not plan:
            return None

        self.callbacks.on_phase_start("SUPPLEMENTARY", "Building supplementary materials")

        preamble = generate_preamble(title=self.config.project_name, author=self.config.author)

        if plan.mode == "appendix":
            # Rebuild main.tex with appendix sections
            all_ids = list(self.section_latex.keys())
            main_tex = assemble_main_tex(
                preamble,
                all_ids,
                title=self.config.project_name,
                appendix_ids=plan.supplementary_sections,
            )
            write_main_tex(main_tex, self.output_dir)
        else:
            # Standalone mode: main without supplementary, separate doc
            main_ids = [s for s in self.section_latex if s not in set(plan.supplementary_sections)]
            main_tex = assemble_main_tex(
                preamble, main_ids, title=self.config.project_name,
            )
            write_main_tex(main_tex, self.output_dir)

            supp_tex = assemble_supplementary_tex(
                preamble, plan.supplementary_sections,
                project_name=self.config.project_name,
            )
            write_supplementary_tex(supp_tex, self.output_dir)

        # Insert cross-reference note in last main section
        main_section_ids = plan.main_sections
        if main_section_ids:
            last_main = main_section_ids[-1]
            if last_main in self.section_latex:
                safe_note = _escape_latex(plan.cross_reference_note)
                note = f"\n\n\\paragraph{{Supplementary Materials.}} {safe_note}\n"
                self.section_latex[last_main] += note
                write_section_files(
                    {last_main: self.section_latex[last_main]}, self.output_dir,
                )

        # Recompile main
        result = run_latexmk(self.output_dir)
        self.compilation_result = result

        self.callbacks.on_phase_end("SUPPLEMENTARY", result.success)
        return result

    # -----------------------------------------------------------------------
    # Phase 4: User Review
    # -----------------------------------------------------------------------

    def run_user_review(self) -> UserFeedback:
        """Phase 4: Present draft to user and collect feedback."""
        self.callbacks.on_phase_start("USER_REVIEW", "Presenting draft for review")

        if not self.design_plan:
            raise RuntimeError("Must run design phase first")

        feedback = self.callbacks.on_plan_review(self.design_plan)

        if feedback.action == "revise" and feedback.comments:
            self._apply_user_revisions(feedback)

        self.callbacks.on_phase_end("USER_REVIEW", feedback.action != "abort")
        return feedback

    def _apply_user_revisions(self, feedback: UserFeedback) -> None:
        """Apply user revision feedback to affected sections."""
        orchestrator = _make_orchestrator()

        # Section-specific comments
        for sid, comment in feedback.section_comments.items():
            if sid in self.section_markdown:
                writer = make_design_writer(self.config)
                try:
                    response = orchestrator.initiate_chat(
                        writer,
                        message=(
                            f"Revise this section based on user feedback.\n\n"
                            f"USER FEEDBACK: {comment}\n\n"
                            f"SECTION ({sid}):\n{self.section_markdown[sid]}"
                        ),
                        max_turns=1,
                    )
                    revised = _strip_todo_markers(_extract_text(response))
                    if revised:
                        self.section_markdown[sid] = revised
                except Exception as e:
                    self.callbacks.on_warning(f"Revision skipped for {sid}: {e}")

        # General comments: apply to all sections
        if feedback.comments and not feedback.section_comments:
            for sid in list(self.section_markdown.keys()):
                writer = make_design_writer(self.config)
                try:
                    response = orchestrator.initiate_chat(
                        writer,
                        message=(
                            f"Revise this section based on general user feedback.\n\n"
                            f"USER FEEDBACK: {feedback.comments}\n\n"
                            f"SECTION ({sid}):\n{self.section_markdown[sid]}"
                        ),
                        max_turns=1,
                    )
                    revised = _strip_todo_markers(_extract_text(response))
                    if revised:
                        self.section_markdown[sid] = revised
                except Exception as e:
                    self.callbacks.on_warning(f"Revision skipped for {sid}: {e}")

        # Re-convert and re-compile
        self._convert_and_compile(orchestrator)

    # -----------------------------------------------------------------------
    # Finalization
    # -----------------------------------------------------------------------

    def run_finalization(self) -> BuildManifest:
        """Generate manifest and final verification."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        warnings: list[str] = []
        if self.compilation_result and not self.compilation_result.success:
            warnings.append("Compilation did not succeed — review output carefully")

        section_file_list = [f"sections/{sid}.tex" for sid in self.section_latex]

        # Supplementary info
        supp_tex: str | None = None
        supp_pdf: str | None = None
        supp_sections: list[str] = []
        if (
            self.split_decision
            and self.split_decision.supplementary_plan
            and self.split_decision.action == "split"
        ):
            sp = self.split_decision.supplementary_plan
            supp_sections = sp.supplementary_sections
            if sp.mode == "standalone":
                supp_tex = "supplementary.tex"
                supp_pdf_path = self.output_dir / "supplementary.pdf"
                if supp_pdf_path.exists():
                    supp_pdf = str(supp_pdf_path)

        page_count = self.compilation_result.page_count if self.compilation_result else None

        # Estimate main body pages
        main_page_count: int | None = page_count  # default: total
        if supp_sections and self.design_plan and page_count:
            supp_est = sum(
                s.estimated_pages for s in self.design_plan.sections
                if s.section_id in set(supp_sections)
            )
            total_est = self.design_plan.total_estimated_pages or sum(
                s.estimated_pages for s in self.design_plan.sections
            )
            if total_est > 0:
                supp_pages = int(round(supp_est / total_est * page_count))
                main_page_count = page_count - supp_pages

        self.manifest = BuildManifest(
            project_name=self.config.project_name,
            output_dir=str(self.output_dir),
            section_files=section_file_list,
            pdf_file=self.compilation_result.pdf_path if self.compilation_result else None,
            source_files=[str(f) for f in list_doc_files(self.docs_dir)],
            style_used=self.config.style,
            compilation_attempts=self.config.compile_max_attempts,
            page_count=page_count,
            main_page_count=main_page_count,
            warnings=warnings,
            supplementary_tex=supp_tex,
            supplementary_pdf=supp_pdf,
            supplementary_sections=supp_sections,
        )

        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(
            self.manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Wrote %s", manifest_path)

        return self.manifest

    # -----------------------------------------------------------------------
    # Full pipeline
    # -----------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """Run the full pipeline with plan-first workflow.

        Flow::

            CONFIGURATION → UNDERSTANDING → PLAN → [PLAN APPROVAL] →
            WRITING+REVIEW → COMPILE → PAGE_BUDGET → SUPPLEMENTARY →
            USER REVIEW → FINALIZE
        """
        errors: list[str] = []
        phases: list[PipelinePhase] = []

        try:
            # Phase 1: Configuration
            validation = self.run_configuration()
            phases.append(PipelinePhase.CONFIGURATION)
            if not validation.valid:
                return PipelineResult(
                    success=False,
                    errors=[f"Config validation failed: {', '.join(validation.missing_fields)}"],
                    phases_completed=phases,
                )

            # Phase 2: Understanding
            self.run_understanding()
            phases.append(PipelinePhase.UNDERSTANDING)

            # Phase 2b: Opportunity Discovery
            self.run_opportunity_discovery()
            phases.append(PipelinePhase.OPPORTUNITY_DISCOVERY)

            # Phase 2c: Opportunity selection + feasibility loop
            for _ in range(self.config.max_plan_revisions):
                selection = self.callbacks.on_opportunity_review(self.opportunity_report)
                self.opportunity_selection = selection

                if selection.action == OpportunitySelectionAction.ABORT:
                    return PipelineResult(
                        success=False,
                        understanding_report=self.understanding_report,
                        opportunity_report=self.opportunity_report,
                        errors=["Pipeline aborted by user during opportunity selection"],
                        phases_completed=phases,
                    )

                self.run_feasibility_check()
                phases.append(PipelinePhase.FEASIBILITY_CHECK)

                feasibility_review = self.callbacks.on_feasibility_review(
                    self.feasibility_report
                )

                if feasibility_review.action == PlanAction.APPROVE:
                    break
                elif feasibility_review.action == PlanAction.ABORT:
                    return PipelineResult(
                        success=False,
                        understanding_report=self.understanding_report,
                        opportunity_report=self.opportunity_report,
                        opportunity_selection=self.opportunity_selection,
                        feasibility_report=self.feasibility_report,
                        errors=["Pipeline aborted by user during feasibility review"],
                        phases_completed=phases,
                    )
                # PlanAction.REVISE → loop back to re-select opportunities

            # Phase 3a: Plan
            self.run_plan()

            # Plan approval loop
            for _ in range(self.config.max_plan_revisions):
                review = self.callbacks.on_plan_approval(self.design_plan)
                phases.append(PipelinePhase.PLAN_APPROVAL)

                if review.action == PlanAction.APPROVE:
                    break
                elif review.action == PlanAction.ABORT:
                    return PipelineResult(
                        success=False,
                        understanding_report=self.understanding_report,
                        opportunity_report=self.opportunity_report,
                        opportunity_selection=self.opportunity_selection,
                        feasibility_report=self.feasibility_report,
                        design_plan=self.design_plan,
                        errors=["Pipeline aborted by user during plan approval"],
                        phases_completed=phases,
                    )
                elif review.action == PlanAction.REVISE:
                    self.run_plan(revision_feedback=review.feedback)

            # Phase 3b: Writing + review + compile
            self.run_writing()
            phases.append(PipelinePhase.DESIGN)

            # Phase 4: Page budget check
            self.run_page_budget()
            phases.append(PipelinePhase.PAGE_BUDGET)

            # Condense main-body sections after split decision
            self._condense_main_sections()

            # Phase 5: Supplementary material (if split was decided)
            self.run_supplementary()
            if self.split_decision and self.split_decision.action == "split":
                phases.append(PipelinePhase.SUPPLEMENTARY)

            # Phase 6: User review loop (on compiled document)
            for _ in range(self.config.design_revision_max_rounds):
                feedback = self.run_user_review()
                phases.append(PipelinePhase.USER_REVIEW)

                if feedback.action == "approve":
                    break
                elif feedback.action == "abort":
                    return PipelineResult(
                        success=False,
                        understanding_report=self.understanding_report,
                        opportunity_report=self.opportunity_report,
                        opportunity_selection=self.opportunity_selection,
                        feasibility_report=self.feasibility_report,
                        design_plan=self.design_plan,
                        compilation_result=self.compilation_result,
                        split_decision=self.split_decision,
                        errors=["Pipeline aborted by user during review"],
                        phases_completed=phases,
                    )

            # Phase 7: Finalization
            self.run_finalization()

        except Exception as e:
            logger.exception("Pipeline failed")
            errors.append(str(e))

        success = (
            self.compilation_result is not None
            and self.compilation_result.success
        )

        return PipelineResult(
            success=success,
            understanding_report=self.understanding_report,
            opportunity_report=self.opportunity_report,
            opportunity_selection=self.opportunity_selection,
            feasibility_report=self.feasibility_report,
            design_plan=self.design_plan,
            compilation_result=self.compilation_result,
            output_dir=str(self.output_dir),
            errors=errors,
            phases_completed=phases,
            split_decision=self.split_decision,
        )

    # -----------------------------------------------------------------------
    # Partial runs (for CLI subcommands)
    # -----------------------------------------------------------------------

    def run_understand_only(self) -> UnderstandingReport:
        """Run only Phase 1 + 2 (config + understanding)."""
        self.run_configuration()
        return self.run_understanding()

    def run_opportunity_only(self) -> tuple[UnderstandingReport, OpportunityReport]:
        """Run Phase 1 + 2 + opportunity discovery (no feasibility/plan)."""
        self.run_configuration()
        report = self.run_understanding()
        opp_report = self.run_opportunity_discovery()
        return report, opp_report

    def run_plan_only(self) -> tuple[UnderstandingReport, DesignPlan]:
        """Run Phase 1 + 2 + plan step (no writing)."""
        self.run_configuration()
        report = self.run_understanding()
        plan = self.run_plan()
        return report, plan
