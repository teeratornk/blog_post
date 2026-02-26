"""Pipeline — 6-phase orchestration for research article generation.

Phase 1: PLANNING         — StructurePlanner analyzes inputs
Phase 2: CONVERSION       — Pandoc + LLM polish + per-section review
Phase 3: POST-PROCESSING  — Per-section equation/figure/citation + multi-file assembly
Phase 4: COMPILATION + META-REVIEW — compile, meta-review on summaries, fix affected sections
Phase 5: PAGE BUDGET      — Advisory page count analysis
Phase 6: FINALIZATION     — Manifest, output copy, final verify
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import autogen

from .agents.citation_agent import make_citation_agent
from .agents.equation_formatter import make_equation_formatter
from .agents.figure_integrator import make_figure_integrator
from .agents.figure_suggester import make_figure_suggester
from .agents.tikz_generator import make_tikz_generator, make_tikz_reviewer, validate_tikz_review
from .agents.latex_assembler import make_assembler
from .agents.page_budget_manager import make_page_budget_manager
from .agents.reviewers import make_meta_reviewer, make_plan_reviewer, make_reviewers, reflection_message, build_summary_args, validate_review
from .agents.structure_planner import make_structure_planner
from .config import build_role_llm_config
from .logging_config import PipelineCallbacks, RichCallbacks, logger
from .models import (
    BuildManifest,
    CompilationResult,
    FaithfulnessReport,
    FaithfulnessViolation,
    FigureSuggestionList,
    PipelinePhase,
    PipelineResult,
    PlanAction,
    ProjectConfig,
    ReviewFeedback,
    SectionReviewResult,
    Severity,
    SplitDecision,
    StructurePlan,
    SectionPlan,
    SupplementaryPlan,
)
from .tools.compiler import extract_error_context, run_latexmk
from .tools.diff_checker import run_faithfulness_check
from .tools.latex_builder import (
    assemble_document,
    assemble_main_tex,
    assemble_supplementary_tex,
    generate_makefile,
    generate_preamble,
    summarize_template,
    write_main_tex,
    write_makefile,
    write_section_files,
    write_supplementary_tex,
)
from .tools.linter import run_lint
from .tools.page_counter import count_pages
from .tools.pandoc_converter import convert_markdown_to_latex

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _looks_like_latex(text: str) -> bool:
    """Heuristic check that text is LaTeX, not reviewer JSON or garbage."""
    latex_markers = ["\\begin{", "\\section", "\\documentclass", "\\usepackage", "\\end{"]
    return any(m in text for m in latex_markers)


def _extract_latex(response: Any) -> str:
    """Extract LaTeX string from an AG2 chat response."""
    if hasattr(response, "summary") and response.summary:
        text = str(response.summary)
    elif hasattr(response, "chat_history") and response.chat_history:
        last = response.chat_history[-1]
        text = last.get("content", "") if isinstance(last, dict) else str(last)
    else:
        text = str(response)

    # Strip markdown fences if present
    text = re.sub(r"```(?:latex|tex)?\n?", "", text)
    text = re.sub(r"```\s*$", "", text)
    return text.strip()


def _extract_json(response: Any, model_cls: type) -> Any:
    """Extract and validate a Pydantic model from an AG2 response."""
    text = _extract_latex(response)
    # Try to find JSON in the response
    if "{" in text:
        json_str = text[text.find("{"):text.rfind("}") + 1]
        try:
            return model_cls.model_validate_json(json_str)
        except Exception:
            pass
    # Try the full text
    try:
        return model_cls.model_validate_json(text)
    except Exception as e:
        logger.warning("Failed to parse %s from response: %s", model_cls.__name__, e)
        return None


def _list_draft_files(draft_dir: str | Path) -> list[Path]:
    """List markdown files in the drafts directory, sorted by name."""
    d = Path(draft_dir)
    if not d.exists():
        return []
    files = sorted(d.glob("*.md"))
    return files


def _list_figure_files(figure_dir: str | Path) -> list[Path]:
    """List figure files in the figures directory."""
    d = Path(figure_dir)
    if not d.exists():
        return []
    exts = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
    return sorted(f for f in d.iterdir() if f.suffix.lower() in exts)


# Regex to match \includegraphics[...]{path} or \includegraphics{path}
_INCLUDEGRAPHICS_RE = re.compile(
    r"(\\includegraphics\s*(?:\[[^\]]*\])?\s*\{)([^}]+)(\})"
)

# Regex to match a complete figure environment containing a missing graphic
_FIGURE_ENV_RE = re.compile(
    r"(\\begin\{figure\}.*?\\end\{figure\})",
    re.DOTALL,
)


def _comment_missing_figures(latex: str, output_dir: Path) -> tuple[str, list[str]]:
    """Comment out figure environments that reference non-existent image files.

    Returns (modified_latex, list_of_commented_paths).
    """
    commented: list[str] = []

    def _fig_path_exists(path_str: str) -> bool:
        """Check if a figure file exists in the output directory."""
        p = Path(path_str)
        # Check relative to output_dir
        if (output_dir / p).exists():
            return True
        # Check just the filename in figures/
        if (output_dir / "figures" / p.name).exists():
            return True
        return False

    # Find all \includegraphics references and check which are missing
    # (skip already-commented lines to ensure idempotency)
    missing_paths: set[str] = set()
    for m in _INCLUDEGRAPHICS_RE.finditer(latex):
        # Check if this match is on a commented line
        line_start = latex.rfind("\n", 0, m.start()) + 1
        line_prefix = latex[line_start:m.start()].lstrip()
        if line_prefix.startswith("%"):
            continue
        fig_path = m.group(2).strip()
        if not _fig_path_exists(fig_path):
            missing_paths.add(fig_path)

    if not missing_paths:
        return latex, []

    # Comment out entire figure environments that contain missing graphics
    def _comment_figure_env(match: re.Match) -> str:
        env_text = match.group(1)
        for mp in missing_paths:
            if mp in env_text:
                commented.append(mp)
                # Comment out each line of the figure environment
                lines = env_text.split("\n")
                return "\n".join(f"% [missing figure] {line}" for line in lines)
        return env_text

    result = _FIGURE_ENV_RE.sub(_comment_figure_env, latex)

    # Also handle bare \includegraphics not inside a figure environment
    for mp in missing_paths:
        if mp not in commented:
            result = result.replace(
                f"\\includegraphics",
                f"% [missing figure] \\includegraphics",
            )
            commented.append(mp)

    return result, commented


# ---------------------------------------------------------------------------
# Figure suggestion helpers
# ---------------------------------------------------------------------------

def _parse_figure_suggestions(response: Any) -> list[dict]:
    """Extract a list of figure suggestion dicts from an AG2 response.

    Attempts structured JSON parsing first, then falls back to extracting
    any JSON object containing a ``suggestions`` key.
    """
    text = _extract_latex(response)

    # Try full text as FigureSuggestionList
    try:
        parsed = FigureSuggestionList.model_validate_json(text)
        return [s.model_dump() for s in parsed.suggestions]
    except Exception:
        pass

    # Try to find JSON substring
    if "{" in text:
        json_str = text[text.find("{"):text.rfind("}") + 1]
        try:
            parsed = FigureSuggestionList.model_validate_json(json_str)
            return [s.model_dump() for s in parsed.suggestions]
        except Exception:
            pass

        # Last resort: try raw json.loads and look for suggestions key
        try:
            raw = json.loads(json_str)
            if isinstance(raw, dict) and "suggestions" in raw:
                return raw["suggestions"]
        except Exception:
            pass

    return []


def _insert_suggestion_comments(latex: str, suggestions: list[dict]) -> str:
    """Append ``%% FIGURE_SUGGESTION`` LaTeX comments at the end of section content."""
    if not suggestions:
        return latex

    lines = [
        "",
        "%% === FIGURE SUGGESTIONS (auto-generated) ===",
    ]
    for s in suggestions:
        lines.append(f"%% FIGURE_SUGGESTION: {s.get('description', '')}")
        lines.append(f"%%   Rationale: {s.get('rationale', '')}")
        lines.append(f"%%   Plot type: {s.get('plot_type', '')}")
        lines.append(f"%%   Data source: {s.get('data_source', '')}")
        lines.append(f"%%   Suggested caption: {s.get('suggested_caption', '')}")
    lines.append("")

    return latex.rstrip() + "\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """Orchestrates the 6-phase research article generation pipeline.

    .. note:: ``_sanitize_missing_figures`` is called at multiple points to
       prevent LLM fixes from reintroducing references to non-existent images.
    """

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
        self.draft_dir = self.config_dir / config.draft_dir
        self.figure_dir = self.config_dir / config.figure_dir
        self.output_dir = self.config_dir / config.output_dir
        self.bib_file = (self.config_dir / config.bibliography) if config.bibliography else None

        # Template context (loaded once, passed to planner + assembler agents)
        self.template_context: str = summarize_template(self.config)

        # State
        self.structure_plan: StructurePlan | None = None
        self.section_latex: dict[str, str] = {}  # section_id -> polished LaTeX
        self.pandoc_latex: dict[str, str] = {}    # section_id -> raw pandoc LaTeX
        self.source_md: dict[str, str] = {}       # section_id -> raw markdown
        self.section_reviews: dict[str, SectionReviewResult] = {}  # section_id -> review result
        self.compilation_result: CompilationResult | None = None
        self.faithfulness_report: FaithfulnessReport | None = None
        self.split_decision: SplitDecision | None = None
        self.supplementary_plan: SupplementaryPlan | None = None
        self.supplementary_compilation: CompilationResult | None = None
        self.figure_suggestions: dict[str, list[dict]] = {}
        self.manifest: BuildManifest | None = None

    # -----------------------------------------------------------------------
    # Phase 1: Planning
    # -----------------------------------------------------------------------

    def run_planning(self, revision_feedback: str | None = None) -> StructurePlan:
        """Phase 1: Analyze inputs and produce a structure plan.

        Args:
            revision_feedback: If provided, the previous plan is sent back to the
                planner along with this feedback text so it can produce a revised plan.
        """
        self.callbacks.on_phase_start("PLANNING", "Analyzing inputs and creating structure plan")

        draft_files = _list_draft_files(self.draft_dir)
        figure_files = _list_figure_files(self.figure_dir)

        if not draft_files:
            raise FileNotFoundError(f"No .md files found in {self.draft_dir}")

        # Build input description for the planner
        input_desc = f"Project: {self.config.project_name}\n"
        input_desc += f"Template: {self.config.template}\n"
        if self.config.page_budget:
            input_desc += f"Page budget: {self.config.page_budget}\n"
        input_desc += f"\nDraft files ({len(draft_files)}):\n"
        input_desc += (
            "Every file below MUST appear as the source_file of at least one section.\n"
            "A file MAY be split across multiple sections (e.g. a long methodology file "
            "can become 'Problem Statement' + 'Numerical Method'), but no content should "
            "be duplicated across sections.\n"
        )
        for f in draft_files:
            input_desc += f"  - {f.name}\n"
        input_desc += "\n"
        for f in draft_files:
            content = f.read_text(encoding="utf-8")
            self.source_md[f.stem] = content
            # Show first 40 lines for context (full file if shorter)
            preview = "\n".join(content.splitlines()[:40])
            input_desc += f"\n--- {f.name} ---\n{preview}\n...\n"

        if figure_files:
            input_desc += f"\nFigure files ({len(figure_files)}):\n"
            for f in figure_files:
                input_desc += f"  - {f.name}\n"

        if self.bib_file and self.bib_file.exists():
            input_desc += f"\nBibliography: {self.bib_file.name}\n"

        # Build the planner message, optionally prepending revision context
        message = ""
        if revision_feedback and self.structure_plan:
            message += (
                "The following structure plan was proposed but the user requested changes:\n\n"
                f"{self.structure_plan.model_dump_json(indent=2)}\n\n"
                f"User feedback: \"{revision_feedback}\"\n\n"
                "Please produce a revised structure plan that addresses this feedback.\n\n"
            )
        message += f"Create a structure plan for this research article:\n\n{input_desc}"

        # Use AG2 agent
        planner = make_structure_planner(self.config, template_context=self.template_context)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        response = orchestrator.initiate_chat(
            planner,
            message=message,
            max_turns=1,
        )

        plan = _extract_json(response, StructurePlan)
        if plan is None:
            # Fallback: create plan from file listing
            logger.warning("LLM planning failed, creating plan from file listing")
            sections = []
            for i, f in enumerate(draft_files):
                sections.append(SectionPlan(
                    section_id=f.stem,
                    title=f.stem.replace("_", " ").title(),
                    source_file=str(f.relative_to(self.config_dir)),
                    priority=i + 1,
                ))
            plan = StructurePlan(
                title=self.config.project_name,
                sections=sections,
                bibliography_file=str(self.bib_file) if self.bib_file else None,
                page_budget=self.config.page_budget,
            )

        self.structure_plan = plan

        # Auto-append any draft files not covered by the plan
        planned_sources = {Path(s.source_file).stem for s in plan.sections}
        next_priority = max((s.priority for s in plan.sections), default=0) + 1
        for f in draft_files:
            if f.stem not in planned_sources:
                self.callbacks.on_warning(
                    f"Draft file '{f.name}' was not in the plan — appending as new section"
                )
                plan.sections.append(SectionPlan(
                    section_id=f.stem,
                    title=f.stem.replace("_", " ").title(),
                    source_file=str(f.relative_to(self.config_dir)),
                    priority=next_priority,
                ))
                next_priority += 1

        # PlanReviewer: automated quality check + optional auto-revision
        plan, review_notes = self._review_plan(plan, draft_files)

        # Re-run auto-append after possible revision
        if review_notes is not None:
            planned_sources = {Path(s.source_file).stem for s in plan.sections}
            next_priority = max((s.priority for s in plan.sections), default=0) + 1
            for f in draft_files:
                if f.stem not in planned_sources:
                    self.callbacks.on_warning(
                        f"Draft file '{f.name}' was not in the revised plan — appending as new section"
                    )
                    plan.sections.append(SectionPlan(
                        section_id=f.stem,
                        title=f.stem.replace("_", " ").title(),
                        source_file=str(f.relative_to(self.config_dir)),
                        priority=next_priority,
                    ))
                    next_priority += 1

        # Add standard sections mentioned in review notes but missing from plan
        added_ids = self._add_sections_from_review_notes(plan, review_notes)
        if added_ids:
            self.callbacks.on_warning(
                f"Added {len(added_ids)} section(s) from review notes: {', '.join(added_ids)}"
            )

        # Generate placeholder drafts for sections without source files
        created = self._generate_placeholder_drafts(plan, draft_files)
        if created:
            self.callbacks.on_warning(
                f"Generated {len(created)} placeholder draft(s): {', '.join(p.name for p in created)}"
            )

        plan.plan_review_notes = review_notes
        self.structure_plan = plan

        self.callbacks.on_phase_end("PLANNING", True)
        return plan

    def _review_plan(
        self,
        plan: StructurePlan,
        draft_files: list[Path],
    ) -> tuple[StructurePlan, str | None]:
        """Run PlanReviewer on the structure plan and optionally auto-revise.

        Returns ``(plan, review_notes)`` where *review_notes* is ``None`` when
        the reviewer is disabled or finds no issues.
        """
        try:
            reviewer = make_plan_reviewer(self.config)
        except Exception as e:
            logger.warning("PlanReviewer creation failed: %s", e)
            return plan, None

        if reviewer is None:
            return plan, None

        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        draft_names = [f.name for f in draft_files]

        try:
            review_response = orchestrator.initiate_chat(
                reviewer,
                message=(
                    "Review this structure plan for a research article.\n\n"
                    f"Plan JSON:\n{plan.model_dump_json(indent=2)}\n\n"
                    f"Draft files available: {draft_names}"
                ),
                max_turns=1,
            )

            raw_text = _extract_latex(review_response)
            feedback, err = validate_review(raw_text)

            if feedback is None:
                logger.warning("Could not parse PlanReviewer response: %s", err)
                return plan, None

            review_text = feedback.Review

            # Check if no issues were found
            no_issue_phrases = ("no issues", "looks good", "no problems", "plan is sound")
            if any(phrase in review_text.lower() for phrase in no_issue_phrases):
                return plan, None

            # Issues found — attempt one auto-revision round
            self.callbacks.on_warning(f"PlanReviewer found issues, attempting auto-revision")
            try:
                planner = make_structure_planner(self.config, template_context=self.template_context)
                revision_orchestrator = autogen.UserProxyAgent(
                    name="Orchestrator",
                    human_input_mode="NEVER",
                    code_execution_config=False,
                )

                revision_response = revision_orchestrator.initiate_chat(
                    planner,
                    message=(
                        "The following structure plan was reviewed and issues were found.\n\n"
                        f"Original plan:\n{plan.model_dump_json(indent=2)}\n\n"
                        f"PlanReviewer feedback:\n{review_text}\n\n"
                        f"Draft files available: {draft_names}\n\n"
                        "Please produce a REVISED StructurePlan JSON that addresses this feedback. "
                        "Return ONLY valid JSON matching the StructurePlan schema."
                    ),
                    max_turns=1,
                )

                revised = _extract_json(revision_response, StructurePlan)
                if revised is not None:
                    self.callbacks.on_warning("PlanReviewer auto-revision applied successfully")
                    return revised, review_text
                else:
                    logger.warning("Auto-revision failed to produce valid plan, keeping original")
                    return plan, review_text

            except Exception as e:
                logger.warning("Auto-revision failed: %s", e)
                return plan, review_text

        except Exception as e:
            logger.warning("PlanReviewer failed: %s", e)
            return plan, None

    # -----------------------------------------------------------------------
    # Phase 2: Conversion (with per-section review)
    # -----------------------------------------------------------------------

    def _review_section(
        self,
        section_id: str,
        section_latex: str,
        orchestrator: autogen.UserProxyAgent,
    ) -> list[ReviewFeedback]:
        """Run 3 reviewers on a single section via direct chat."""
        reviewers = make_reviewers(self.config)
        collected: list[ReviewFeedback] = []

        for name, agent in reviewers.items():
            if agent is None:
                continue
            self.callbacks.on_section_review(section_id, name)
            try:
                response = orchestrator.initiate_chat(
                    agent,
                    message=(
                        f"Review this LaTeX section (section_id: {section_id}):\n\n"
                        f"{section_latex}"
                    ),
                    max_turns=1,
                )
                text = _extract_latex(response)
                # Try to parse as ReviewFeedback
                from .agents.reviewers import validate_review
                feedback, err = validate_review(text)
                if feedback:
                    collected.append(feedback)
                elif err:
                    logger.warning("Could not parse review from %s: %s", name, err)
            except Exception as e:
                self.callbacks.on_warning(f"Reviewer {name} skipped for {section_id}: {e}")

        return collected

    def run_conversion(self) -> dict[str, str]:
        """Phase 2: Convert each section via Pandoc + LLM polish + per-section review."""
        if not self.structure_plan:
            raise RuntimeError("Must run planning phase first")

        self.callbacks.on_phase_start("CONVERSION", "Converting sections to LaTeX (with per-section review)")

        assembler = make_assembler(self.config, template_context=self.template_context)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        for section in self.structure_plan.sections:
            self.callbacks.on_section_start(section.section_id)

            # Resolve source file — try multiple locations
            source_path = self.config_dir / section.source_file
            if not source_path.exists():
                # Fallback: try relative to draft_dir (LLM often omits the drafts/ prefix)
                source_path = self.draft_dir / Path(section.source_file).name
            if not source_path.exists():
                # Fallback 3: try matching by section_id glob
                candidates = list(self.draft_dir.glob(f"*{section.section_id}*"))
                if candidates:
                    source_path = candidates[0]
            if not source_path.exists():
                # Fallback 4: find best match by stem substring overlap
                sec_stem = section.section_id.lower()
                for draft_file in sorted(self.draft_dir.glob("*.md")):
                    draft_stem = draft_file.stem.lower()
                    if sec_stem in draft_stem or draft_stem in sec_stem:
                        source_path = draft_file
                        break
            if not source_path.exists():
                logger.warning("Source file not found: %s, skipping", source_path)
                self.callbacks.on_warning(f"Skipping {section.section_id}: source file not found")
                continue

            # Step 1: Pandoc conversion (deterministic)
            pandoc_latex = convert_markdown_to_latex(source_path, annotate=True)
            self.pandoc_latex[section.section_id] = pandoc_latex

            # Read source markdown for faithfulness
            if section.section_id not in self.source_md:
                self.source_md[section.section_id] = source_path.read_text(encoding="utf-8")

            # Step 2: LLM polish
            prompt = (
                f"Polish this Pandoc-converted LaTeX for the section '{section.title}'. "
                f"Only modify text between SAFE_ZONE markers.\n\n"
                f"{pandoc_latex}"
            )

            response = orchestrator.initiate_chat(
                assembler,
                message=prompt,
                max_turns=1,
            )

            polished = _extract_latex(response)

            # Step 3: Per-section review (3 reviewers)
            reviews = self._review_section(section.section_id, polished, orchestrator)

            # Step 4: If reviews found issues, ask a fresh assembler to fix
            fix_applied = False
            has_issues = any(
                r.severity in (Severity.ERROR, Severity.CRITICAL) or "fix" in r.Review.lower()
                for r in reviews
            )
            if reviews and has_issues:
                feedback_text = "\n".join(
                    f"[{r.Reviewer}]: {r.Review}" for r in reviews
                )
                fix_assembler = make_assembler(self.config, template_context=self.template_context)
                fix_response = orchestrator.initiate_chat(
                    fix_assembler,
                    message=(
                        f"Apply the following reviewer feedback to improve this LaTeX section. "
                        f"Return the COMPLETE corrected section.\n\n"
                        f"FEEDBACK:\n{feedback_text}\n\n"
                        f"SECTION:\n{polished}"
                    ),
                    max_turns=1,
                )
                new_latex = _extract_latex(fix_response)
                if new_latex and _looks_like_latex(new_latex):
                    polished = new_latex
                    fix_applied = True

            # Step 5: Per-section faithfulness check (deterministic)
            section_faith = run_faithfulness_check(
                self.source_md[section.section_id],
                pandoc_latex,
                polished,
            )

            # Store results
            self.section_latex[section.section_id] = polished
            self.section_reviews[section.section_id] = SectionReviewResult(
                section_id=section.section_id,
                reviews=reviews,
                faithfulness=section_faith,
                fix_applied=fix_applied,
            )

            self.callbacks.on_section_end(section.section_id)

        # Aggregate faithfulness across all sections
        self.faithfulness_report = self._aggregate_faithfulness()

        self.callbacks.on_phase_end("CONVERSION", len(self.section_latex) > 0)
        return self.section_latex

    # -----------------------------------------------------------------------
    # Phase 3: Post-processing (per-section + multi-file assembly)
    # -----------------------------------------------------------------------

    def run_post_processing(self) -> dict[str, str]:
        """Phase 3: Per-section equation/figure/citation passes + multi-file assembly."""
        self.callbacks.on_phase_start("POST_PROCESSING", "Per-section post-processing + multi-file assembly")

        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        bib_content = ""
        if self.bib_file and self.bib_file.exists():
            bib_content = self.bib_file.read_text(encoding="utf-8")

        for section_id, latex in list(self.section_latex.items()):
            self.callbacks.on_section_start(section_id)

            # TikZ diagram generation + review pass (before equation/figure passes)
            if self.config.tikz_enabled:
                latex = self._tikz_generate_and_review(section_id, latex, orchestrator)

            # Equation formatting pass
            try:
                eq_formatter = make_equation_formatter(self.config)
                response = orchestrator.initiate_chat(
                    eq_formatter,
                    message=f"Check and fix equation consistency in this section:\n\n{latex}",
                    max_turns=1,
                )
                updated = _extract_latex(response)
                if updated and _looks_like_latex(updated):
                    latex = updated
            except Exception as e:
                self.callbacks.on_warning(f"EquationFormatter skipped for {section_id}: {e}")

            # Figure integration pass
            try:
                fig_integrator = make_figure_integrator(self.config)
                response = orchestrator.initiate_chat(
                    fig_integrator,
                    message=f"Optimize figure placement and sizing in this section:\n\n{latex}",
                    max_turns=1,
                )
                updated = _extract_latex(response)
                if updated and _looks_like_latex(updated):
                    latex = updated
            except Exception as e:
                self.callbacks.on_warning(f"FigureIntegrator skipped for {section_id}: {e}")

            # Figure suggestion pass (advisory, inserts LaTeX comments)
            if self.config.figure_suggestion_enabled:
                try:
                    suggester = make_figure_suggester(self.config)
                    response = orchestrator.initiate_chat(
                        suggester,
                        message=(
                            f"Analyze this LaTeX section '{section_id}' and suggest up to "
                            f"{self.config.figure_suggestion_max} figures/plots that should be "
                            f"created. Only suggest figures where the text discusses data, "
                            f"results, or methods without adequate visualization.\n\n{latex}"
                        ),
                        max_turns=1,
                    )
                    suggestions = _parse_figure_suggestions(response)
                    if suggestions:
                        self.figure_suggestions[section_id] = suggestions
                        latex = _insert_suggestion_comments(latex, suggestions)
                except Exception as e:
                    self.callbacks.on_warning(f"FigureSuggester skipped for {section_id}: {e}")

            # Citation validation (report only, per section)
            if bib_content:
                try:
                    citation_agent = make_citation_agent(self.config)
                    orchestrator.initiate_chat(
                        citation_agent,
                        message=(
                            f"Validate citations in this LaTeX section against the .bib file.\n\n"
                            f"LaTeX:\n{latex}\n\n"
                            f".bib contents:\n{bib_content}"
                        ),
                        max_turns=1,
                    )
                except Exception as e:
                    self.callbacks.on_warning(f"CitationAgent skipped for {section_id}: {e}")

            self.section_latex[section_id] = latex
            self.callbacks.on_section_end(section_id)

        # Multi-file assembly: write sections/*.tex + main.tex skeleton
        self.output_dir.mkdir(parents=True, exist_ok=True)
        write_section_files(self.section_latex, self.output_dir)

        # Build main.tex skeleton
        section_ids = list(self.section_latex.keys())

        abstract = None
        if self.structure_plan and self.structure_plan.abstract_file:
            abs_path = self.config_dir / self.structure_plan.abstract_file
            if abs_path.exists():
                abstract = convert_markdown_to_latex(abs_path, annotate=False)

        bib_name = None
        if self.bib_file:
            bib_name = self.bib_file.stem

        preamble = generate_preamble(self.config)
        main_tex_content = assemble_main_tex(
            preamble,
            section_ids,
            abstract=abstract,
            bibliography=bib_name,
            bib_style=self.config.bib_style,
        )
        write_main_tex(main_tex_content, self.output_dir)

        self.callbacks.on_phase_end("POST_PROCESSING", True)
        return self.section_latex

    # -----------------------------------------------------------------------
    # Phase 4: Compilation + Meta-Review
    # -----------------------------------------------------------------------

    def run_compilation_review(self) -> CompilationResult:
        """Phase 4: Compile, meta-review on summaries, fix affected sections."""
        self.callbacks.on_phase_start("COMPILATION_REVIEW", "Compiling and meta-reviewing")

        # Prepare output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Copy figures
        if self.figure_dir.exists():
            fig_dest = self.output_dir / "figures"
            fig_dest.mkdir(parents=True, exist_ok=True)
            for fig in _list_figure_files(self.figure_dir):
                dest = fig_dest / fig.name
                if not dest.exists():
                    shutil.copy2(fig, dest)
                # Also copy to output root for backward compat
                root_dest = self.output_dir / fig.name
                if not root_dest.exists():
                    shutil.copy2(fig, root_dest)

        # Copy .bib file
        if self.bib_file and self.bib_file.exists():
            dest = self.output_dir / self.bib_file.name
            if not dest.exists():
                shutil.copy2(self.bib_file, dest)

        # Write Makefile
        write_makefile(generate_makefile(self.config), self.output_dir)

        # Pre-compilation: comment out references to missing figure files
        if self._sanitize_missing_figures():
            write_section_files(self.section_latex, self.output_dir)

        # Compile-fix loop
        assembler = make_assembler(self.config, template_context=self.template_context)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        result = CompilationResult(success=False, errors=[], warnings=[])

        for attempt in range(1, self.config.compile_max_attempts + 1):
            self.callbacks.on_compile_attempt(attempt, self.config.compile_max_attempts)

            result = run_latexmk(self.output_dir, self.config.latex_engine)
            logger.info(
                "[compile-fix] attempt %d/%d: success=%s, errors=%d, unresolved=%d",
                attempt, self.config.compile_max_attempts,
                result.success, len(result.errors), len(result.unresolved_refs),
            )
            if result.errors:
                for err in result.errors:
                    logger.info("  error: %s (file=%s, line=%s)", err.message, err.file, err.line)

            if result.success:
                if result.unresolved_refs:
                    self.callbacks.on_warning(
                        f"Unresolved references (will not block): {', '.join(result.unresolved_refs)}"
                    )
                break

            # Don't try LLM fixes for environment/tooling errors
            _unfixable = {"latexmk not found", "not found on PATH", "timed out"}
            if any(
                any(u in err.message for u in _unfixable)
                for err in result.errors
            ):
                self.callbacks.on_warning(
                    "Compilation failed due to environment issue (not a LaTeX content error), skipping fix attempts"
                )
                break

            if attempt < self.config.compile_max_attempts:
                # Identify which section files are affected by errors
                affected = self._identify_affected_sections(result)
                if not affected:
                    # Can't identify — try fixing all sections
                    affected = list(self.section_latex.keys())

                for section_id in affected:
                    if section_id not in self.section_latex:
                        continue
                    section_content = self.section_latex[section_id]
                    error_ctx = extract_error_context(
                        result, section_content,
                        section_file=f"sections/{section_id}.tex",
                    )
                    try:
                        fix_response = orchestrator.initiate_chat(
                            assembler,
                            message=(
                                f"The LaTeX compilation failed. Fix the errors in this section "
                                f"and return the COMPLETE corrected section.\n"
                                f"Do NOT add \\usepackage commands — the preamble is fixed.\n\n"
                                f"Section: {section_id}\n"
                                f"Errors:\n{error_ctx}\n\n"
                                f"Section content:\n{section_content}"
                            ),
                            max_turns=1,
                        )
                        new_latex = _extract_latex(fix_response)
                        if new_latex and _looks_like_latex(new_latex):
                            self.section_latex[section_id] = new_latex
                    except Exception as e:
                        self.callbacks.on_warning(f"Compile-fix skipped for {section_id}: {e}")

                # Re-sanitize: LLM fixes may reintroduce missing figures
                self._sanitize_missing_figures()

                # Rewrite fixed sections and recompile
                write_section_files(self.section_latex, self.output_dir)

        self.compilation_result = result

        # Run linter
        tex_path = self.output_dir / "main.tex"
        if tex_path.exists():
            lint_result = run_lint(tex_path)
            if lint_result.total > 0:
                self.callbacks.on_warning(f"Lint: {lint_result.warning_count} warnings, {lint_result.error_count} errors")

        # Meta-review round: review SUMMARIES, not full doc.
        # Snapshot the working state so we can revert if meta-review
        # changes break compilation.
        pre_meta_sections: dict[str, str] = {}
        pre_meta_result = result  # from compile-fix loop

        for round_num in range(1, self.config.review_max_rounds + 1):
            self.callbacks.on_review_round(round_num, self.config.review_max_rounds)

            # Build section summaries for meta-reviewer
            summaries = self._build_section_summaries()

            try:
                meta = make_meta_reviewer(self.config)
                review_response = orchestrator.initiate_chat(
                    meta,
                    message=(
                        f"Review these section summaries for cross-section issues "
                        f"(narrative flow, notation consistency, bibliography coherence, redundancy).\n\n"
                        f"Prior per-section review results are included.\n\n"
                        f"{summaries}"
                    ),
                    max_turns=1,
                )

                feedback = _extract_latex(review_response)
            except Exception as e:
                self.callbacks.on_warning(f"Meta-review skipped: {e}")
                break

            # Parse affected sections from meta-reviewer feedback
            affected = self._parse_affected_sections(feedback)
            if not affected:
                # No cross-section issues found
                break

            # Save snapshot before applying meta-review changes
            pre_meta_sections = {k: v for k, v in self.section_latex.items()}

            # Fix affected sections
            for section_id in affected:
                if section_id not in self.section_latex:
                    continue
                try:
                    fix_assembler = make_assembler(self.config, template_context=self.template_context)
                    fix_response = orchestrator.initiate_chat(
                        fix_assembler,
                        message=(
                            f"Apply the following meta-reviewer feedback to improve this section. "
                            f"Return the COMPLETE corrected section.\n\n"
                            f"FEEDBACK:\n{feedback}\n\n"
                            f"SECTION ({section_id}):\n{self.section_latex[section_id]}"
                        ),
                        max_turns=1,
                    )
                    new_latex = _extract_latex(fix_response)
                    if new_latex and _looks_like_latex(new_latex):
                        self.section_latex[section_id] = new_latex
                except Exception as e:
                    self.callbacks.on_warning(f"Meta-review fix skipped for {section_id}: {e}")

            # Re-sanitize: LLM meta-review fixes may reintroduce missing figures
            self._sanitize_missing_figures()

            # Rewrite and recompile
            write_section_files(self.section_latex, self.output_dir)
            result = run_latexmk(self.output_dir, self.config.latex_engine)
            self.compilation_result = result
            logger.info(
                "[meta-review] round %d recompile: success=%s, errors=%d",
                round_num, result.success, len(result.errors),
            )

            if result.success:
                break

            # Meta-review broke compilation — revert to pre-meta-review state
            if pre_meta_result.success and pre_meta_sections:
                self.callbacks.on_warning(
                    "Meta-review changes broke compilation; reverting to working state"
                )
                self.section_latex = pre_meta_sections
                write_section_files(self.section_latex, self.output_dir)
                result = pre_meta_result
                self.compilation_result = result
                break

        logger.info(
            "[COMPILATION_REVIEW] final result: success=%s, errors=%d, pdf=%s",
            result.success, len(result.errors), result.pdf_path,
        )
        self.callbacks.on_phase_end("COMPILATION_REVIEW", result.success)
        return result

    # -----------------------------------------------------------------------
    # Phase 5: Page Budget
    # -----------------------------------------------------------------------

    def _is_supplementary_enabled(self, page_count: int) -> bool:
        """Determine whether supplementary generation should be activated."""
        mode = self.config.supplementary_mode
        if mode == "disabled":
            return False
        if mode in ("appendix", "standalone"):
            return True
        if mode == "auto" and self.config.page_budget:
            ratio = page_count / self.config.page_budget if self.config.page_budget else 0
            return ratio > self.config.supplementary_threshold
        return False

    def run_page_budget(self) -> SplitDecision | None:
        """Phase 5: Advisory page budget analysis (with optional supplementary split)."""
        self.callbacks.on_phase_start("PAGE_BUDGET", "Checking page budget")

        if not self.config.page_budget:
            decision = SplitDecision(action="ok", recommendations="No page budget set")
            self.split_decision = decision
            self.callbacks.on_phase_end("PAGE_BUDGET", True)
            return decision

        page_count = 0
        if self.compilation_result and self.compilation_result.page_count:
            page_count = self.compilation_result.page_count
        elif self.compilation_result and self.compilation_result.pdf_path:
            page_count = count_pages(self.compilation_result.pdf_path) or 0

        if page_count <= self.config.page_budget:
            decision = SplitDecision(
                action="ok",
                current_pages=page_count,
                budget_pages=self.config.page_budget,
                recommendations=f"Document is {page_count} pages, within budget of {self.config.page_budget}.",
            )
            self.split_decision = decision
            self.callbacks.on_phase_end("PAGE_BUDGET", True)
            return decision

        # Over budget — decide if supplementary mode is active
        supplementary_enabled = self._is_supplementary_enabled(page_count)

        budget_mgr = make_page_budget_manager(
            self.config,
            supplementary_enabled=supplementary_enabled,
        )
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        sections_info = ""
        if self.structure_plan:
            for s in self.structure_plan.sections:
                sections_info += f"  - {s.section_id}: ~{s.estimated_pages} pages (priority {s.priority})\n"

        supp_note = ""
        if supplementary_enabled:
            mode = self.config.supplementary_mode
            if mode == "auto":
                mode = "standalone"
            supp_note = (
                f"\nSupplementary mode: {mode}. "
                f"Classify each section and produce a supplementary_plan."
            )

        response = orchestrator.initiate_chat(
            budget_mgr,
            message=(
                f"The document is {page_count} pages but the budget is {self.config.page_budget} pages.\n"
                f"Sections:\n{sections_info}\n"
                f"Recommend which sections/figures to move to supplementary materials."
                f"{supp_note}"
            ),
            max_turns=1,
        )

        decision = _extract_json(response, SplitDecision)
        if decision is None:
            action = "warn_over"
            decision = SplitDecision(
                action=action,
                current_pages=page_count,
                budget_pages=self.config.page_budget,
                recommendations=f"Document is {page_count} pages, over budget of {self.config.page_budget}.",
            )

        # Store supplementary plan if the decision includes one
        if decision.supplementary_plan and decision.action == "split":
            # Override mode from config if explicit (not auto)
            if self.config.supplementary_mode in ("appendix", "standalone"):
                decision.supplementary_plan.mode = self.config.supplementary_mode
            self.supplementary_plan = decision.supplementary_plan

        self.split_decision = decision
        if decision.action != "ok":
            self.callbacks.on_warning(decision.recommendations)

        self.callbacks.on_phase_end("PAGE_BUDGET", True)
        return decision

    # -----------------------------------------------------------------------
    # Phase 5b: Supplementary Materials
    # -----------------------------------------------------------------------

    def run_supplementary(self) -> SupplementaryPlan | None:
        """Phase 5b: Generate supplementary materials if a plan exists."""
        if self.supplementary_plan is None:
            return None

        self.callbacks.on_phase_start("SUPPLEMENTARY", "Generating supplementary materials")
        plan = self.supplementary_plan

        if plan.mode == "appendix":
            self._rebuild_main_with_appendix(plan)
        else:
            self._generate_standalone_supplementary(plan)

        # Insert cross-reference note in last main section
        self._insert_supplementary_note(plan)

        # Rewrite all section files
        write_section_files(self.section_latex, self.output_dir)

        # Recompile main.tex
        result = run_latexmk(self.output_dir, self.config.latex_engine)
        self.compilation_result = result

        # Compile supplementary.tex if standalone
        if plan.mode == "standalone":
            supp_result = self._compile_fix_supplementary()
            self.supplementary_compilation = supp_result

        self.callbacks.on_phase_end("SUPPLEMENTARY", True)
        return plan

    def _rebuild_main_with_appendix(self, plan: SupplementaryPlan) -> None:
        """Rebuild main.tex with supplementary sections as appendices."""
        main_ids = [
            sid for sid in self.section_latex
            if sid not in plan.supplementary_sections
        ]

        abstract = None
        if self.structure_plan and self.structure_plan.abstract_file:
            abs_path = self.config_dir / self.structure_plan.abstract_file
            if abs_path.exists():
                abstract = convert_markdown_to_latex(abs_path, annotate=False)

        bib_name = self.bib_file.stem if self.bib_file else None

        preamble = generate_preamble(self.config)
        main_tex_content = assemble_main_tex(
            preamble,
            main_ids,
            abstract=abstract,
            bibliography=bib_name,
            bib_style=self.config.bib_style,
            appendix_ids=plan.supplementary_sections,
        )
        write_main_tex(main_tex_content, self.output_dir)

    def _generate_standalone_supplementary(self, plan: SupplementaryPlan) -> None:
        """Rebuild main.tex without supp sections and generate supplementary.tex."""
        main_ids = [
            sid for sid in self.section_latex
            if sid not in plan.supplementary_sections
        ]

        abstract = None
        if self.structure_plan and self.structure_plan.abstract_file:
            abs_path = self.config_dir / self.structure_plan.abstract_file
            if abs_path.exists():
                abstract = convert_markdown_to_latex(abs_path, annotate=False)

        bib_name = self.bib_file.stem if self.bib_file else None

        # Rebuild main.tex (without supplementary sections)
        preamble = generate_preamble(self.config)
        main_tex_content = assemble_main_tex(
            preamble,
            main_ids,
            abstract=abstract,
            bibliography=bib_name,
            bib_style=self.config.bib_style,
        )
        write_main_tex(main_tex_content, self.output_dir)

        # Generate supplementary.tex
        supp_content = assemble_supplementary_tex(
            preamble,
            plan.supplementary_sections,
            project_name=self.config.project_name,
            bibliography=bib_name,
            bib_style=self.config.bib_style,
        )
        write_supplementary_tex(supp_content, self.output_dir)

    def _insert_supplementary_note(self, plan: SupplementaryPlan) -> None:
        """Append a supplementary materials note to the last main section."""
        main_ids = [
            sid for sid in self.section_latex
            if sid not in plan.supplementary_sections
        ]
        if not main_ids:
            return

        last_main_id = main_ids[-1]
        note = (
            f"\n\n\\paragraph{{Supplementary Materials.}}\n"
            f"{plan.cross_reference_note}\n"
        )
        self.section_latex[last_main_id] += note

    def _compile_fix_supplementary(self) -> CompilationResult:
        """Compile supplementary.tex with a simple compile-fix loop."""
        result = run_latexmk(
            self.output_dir,
            self.config.latex_engine,
            main_file="supplementary.tex",
        )

        if not result.success:
            # One retry: try to fix errors via LLM
            assembler = make_assembler(self.config, template_context=self.template_context)
            orchestrator = autogen.UserProxyAgent(
                name="Orchestrator",
                human_input_mode="NEVER",
                code_execution_config=False,
            )

            supp_path = self.output_dir / "supplementary.tex"
            if supp_path.exists():
                supp_content = supp_path.read_text(encoding="utf-8")
                error_ctx = extract_error_context(result, supp_content)
                try:
                    fix_response = orchestrator.initiate_chat(
                        assembler,
                        message=(
                            f"The supplementary LaTeX compilation failed. "
                            f"Fix the errors and return the COMPLETE corrected document.\n\n"
                            f"Errors:\n{error_ctx}\n\n"
                            f"Document:\n{supp_content}"
                        ),
                        max_turns=1,
                    )
                    new_latex = _extract_latex(fix_response)
                    if new_latex and _looks_like_latex(new_latex):
                        supp_path.write_text(new_latex, encoding="utf-8")
                        result = run_latexmk(
                            self.output_dir,
                            self.config.latex_engine,
                            main_file="supplementary.tex",
                        )
                except Exception as e:
                    self.callbacks.on_warning(f"Supplementary compile-fix skipped: {e}")

        return result

    # -----------------------------------------------------------------------
    # Phase 6: Finalization
    # -----------------------------------------------------------------------

    def run_finalization(self) -> BuildManifest:
        """Phase 6: Generate manifest, final verification."""
        self.callbacks.on_phase_start("FINALIZATION", "Generating manifest and final verification")

        warnings: list[str] = []
        if self.faithfulness_report and not self.faithfulness_report.passed:
            warnings.append("Faithfulness check had violations — review output carefully")
        if self.split_decision and self.split_decision.action != "ok":
            warnings.append(f"Page budget: {self.split_decision.recommendations}")

        section_file_list = [f"sections/{sid}.tex" for sid in self.section_latex]

        # Supplementary fields
        supp_tex = None
        supp_pdf = None
        supp_sections: list[str] = []
        has_supplementary = False
        if self.supplementary_plan:
            supp_sections = self.supplementary_plan.supplementary_sections
            has_supplementary = True
            if self.supplementary_plan.mode == "standalone":
                supp_tex = "supplementary.tex"
                if (
                    self.supplementary_compilation
                    and self.supplementary_compilation.success
                    and self.supplementary_compilation.pdf_path
                ):
                    supp_pdf = self.supplementary_compilation.pdf_path

        self.manifest = BuildManifest(
            project_name=self.config.project_name,
            output_dir=str(self.output_dir),
            section_files=section_file_list,
            pdf_file=self.compilation_result.pdf_path if self.compilation_result else None,
            source_files=[s.source_file for s in (self.structure_plan.sections if self.structure_plan else [])],
            figure_files=[str(f) for f in _list_figure_files(self.figure_dir)],
            bibliography_file=str(self.bib_file) if self.bib_file else None,
            template_used=self.config.template,
            compilation_attempts=self.config.compile_max_attempts,
            faithfulness_passed=self.faithfulness_report.passed if self.faithfulness_report else False,
            page_count=self.compilation_result.page_count if self.compilation_result else None,
            warnings=warnings,
            supplementary_tex=supp_tex,
            supplementary_pdf=supp_pdf,
            supplementary_sections=supp_sections,
        )

        # Update Makefile with supplementary target if needed
        write_makefile(
            generate_makefile(self.config, has_supplementary=has_supplementary),
            self.output_dir,
        )

        # Write figure suggestions JSON
        if self.figure_suggestions:
            sugg_path = self.output_dir / "figure_suggestions.json"
            sugg_path.write_text(
                json.dumps(self.figure_suggestions, indent=2),
                encoding="utf-8",
            )
            self.manifest.figure_suggestions_file = "figure_suggestions.json"
            logger.info("Wrote %s", sugg_path)

        # Write manifest
        manifest_path = self.output_dir / "manifest.json"
        manifest_path.write_text(
            self.manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info("Wrote %s", manifest_path)

        self.callbacks.on_phase_end("FINALIZATION", True)
        return self.manifest

    # -----------------------------------------------------------------------
    # Full pipeline
    # -----------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """Run the full 6-phase pipeline."""
        errors: list[str] = []
        warnings: list[str] = []
        phases: list[PipelinePhase] = []

        try:
            self.run_planning()
            phases.append(PipelinePhase.PLANNING)

            # Plan approval gate
            for _ in range(self.config.max_plan_revisions):
                review = self.callbacks.on_plan_review(self.structure_plan)
                if review.action == PlanAction.APPROVE:
                    break
                elif review.action == PlanAction.ABORT:
                    return PipelineResult(
                        success=False,
                        structure_plan=self.structure_plan,
                        errors=["Pipeline aborted by user during plan review"],
                        phases_completed=phases,
                    )
                else:  # REVISE
                    self.run_planning(revision_feedback=review.feedback)

            self.run_conversion()
            phases.append(PipelinePhase.CONVERSION)

            self.run_post_processing()
            phases.append(PipelinePhase.POST_PROCESSING)

            self.run_compilation_review()
            phases.append(PipelinePhase.COMPILATION_REVIEW)

            self.run_page_budget()
            phases.append(PipelinePhase.PAGE_BUDGET)

            self.run_supplementary()
            phases.append(PipelinePhase.SUPPLEMENTARY)

            self.run_finalization()
            phases.append(PipelinePhase.FINALIZATION)

        except Exception as e:
            logger.exception("Pipeline failed")
            errors.append(str(e))

        success = (
            PipelinePhase.FINALIZATION in phases
            and self.compilation_result is not None
            and self.compilation_result.success
        )

        return PipelineResult(
            success=success,
            structure_plan=self.structure_plan,
            compilation_result=self.compilation_result,
            faithfulness_report=self.faithfulness_report,
            split_decision=self.split_decision,
            manifest=self.manifest,
            errors=errors,
            warnings=warnings,
            phases_completed=phases,
        )

    # -----------------------------------------------------------------------
    # Partial runs (for CLI subcommands)
    # -----------------------------------------------------------------------

    def run_plan_only(self) -> StructurePlan:
        """Run only the planning phase (dry run)."""
        return self.run_planning()

    def run_convert_section(self, section_path: str | Path) -> str:
        """Convert a single section (for testing)."""
        path = Path(section_path)
        pandoc_latex = convert_markdown_to_latex(path, annotate=True)

        assembler = make_assembler(self.config, template_context=self.template_context)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        response = orchestrator.initiate_chat(
            assembler,
            message=(
                f"Polish this Pandoc-converted LaTeX. "
                f"Only modify text between SAFE_ZONE markers.\n\n{pandoc_latex}"
            ),
            max_turns=1,
        )

        return _extract_latex(response)

    def run_compile_only(self) -> CompilationResult:
        """Compile existing output directory (no LLM)."""
        return run_latexmk(self.output_dir, self.config.latex_engine)

    def run_validate_only(self) -> FaithfulnessReport:
        """Run faithfulness validation on existing output.

        Reads individual section files from sections/*.tex when available,
        falling back to monolithic main.tex.
        """
        sections_dir = self.output_dir / "sections"

        if sections_dir.exists() and list(sections_dir.glob("*.tex")):
            # Multi-file: read each section individually
            output_latex = ""
            for tex_file in sorted(sections_dir.glob("*.tex")):
                output_latex += tex_file.read_text(encoding="utf-8") + "\n\n"
        else:
            # Fallback: monolithic main.tex
            tex_path = self.output_dir / "main.tex"
            if not tex_path.exists():
                raise FileNotFoundError(f"main.tex not found in {self.output_dir}")
            output_latex = tex_path.read_text(encoding="utf-8")

        # Load source files
        all_source_md = ""
        all_pandoc_latex = ""
        for md_file in _list_draft_files(self.draft_dir):
            all_source_md += md_file.read_text(encoding="utf-8") + "\n\n"
            pandoc_latex = convert_markdown_to_latex(md_file, annotate=False)
            all_pandoc_latex += pandoc_latex + "\n\n"

        return run_faithfulness_check(all_source_md, all_pandoc_latex, output_latex)

    # -----------------------------------------------------------------------
    # Helper methods
    # -----------------------------------------------------------------------

    def _tikz_generate_and_review(
        self,
        section_id: str,
        latex: str,
        orchestrator: autogen.UserProxyAgent,
    ) -> str:
        """Generate TikZ diagrams and run a structured review-fix loop.

        1. Generate TikZ via the generator agent.
        2. If no ``\\begin{tikzpicture}`` in output → return as-is.
        3. Review-fix loop (up to ``tikz_review_max_turns`` rounds):
           - Reviewer examines section → returns structured JSON.
           - Parse via ``validate_tikz_review()``.
           - On verdict ``PASS`` → break.
           - On ``FAIL`` → build severity-sorted fix prompt with
             accumulated issue history → fresh generator fixes → loop.
        4. Graceful fallback: return original *latex* on any failure.
        """
        original = latex

        # Step 1: Generate
        try:
            tikz_gen = make_tikz_generator(self.config)
            response = orchestrator.initiate_chat(
                tikz_gen,
                message=f"Analyze this section and generate TikZ diagrams where appropriate:\n\n{latex}",
                max_turns=1,
            )
            updated = _extract_latex(response)
            if updated and _looks_like_latex(updated):
                latex = updated
            else:
                return original
        except Exception as e:
            self.callbacks.on_warning(f"TikZGenerator skipped for {section_id}: {e}")
            return original

        # Step 2: Short-circuit if no diagrams were produced
        if r"\begin{tikzpicture}" not in latex:
            return latex

        # Step 3: Structured review-fix loop
        issue_history: list[list[dict[str, str]]] = []  # per-round issue lists

        for turn in range(self.config.tikz_review_max_turns):
            try:
                reviewer = make_tikz_reviewer(self.config)
                review_response = orchestrator.initiate_chat(
                    reviewer,
                    message=f"Review the TikZ diagrams in this LaTeX section:\n\n{latex}",
                    max_turns=1,
                )
                raw_verdict = _extract_latex(review_response).strip()
            except Exception as e:
                self.callbacks.on_warning(f"TikZReviewer skipped for {section_id}: {e}")
                break

            # Parse structured result
            result = validate_tikz_review(raw_verdict)
            if result is None:
                # Unparseable — treat as PASS to avoid infinite loop
                logger.warning("TikZ review unparseable for %s, treating as PASS", section_id)
                break

            self.callbacks.on_warning(
                f"TikZ review {section_id} round {turn + 1}: "
                f"verdict={result.verdict}, issues={len(result.issues)}"
            )

            if result.verdict == "PASS":
                break

            # Accumulate issues for history
            round_issues = [
                {"category": iss.category, "severity": iss.severity.value, "description": iss.description}
                for iss in result.issues
            ]
            issue_history.append(round_issues)

            # Build severity-sorted fix prompt
            fix_prompt = self._build_tikz_fix_prompt(latex, result.issues, issue_history)

            # Fix
            try:
                fixer = make_tikz_generator(self.config)
                fix_response = orchestrator.initiate_chat(
                    fixer,
                    message=fix_prompt,
                    max_turns=1,
                )
                fixed = _extract_latex(fix_response)
                if fixed and _looks_like_latex(fixed):
                    latex = fixed
                else:
                    break
            except Exception as e:
                self.callbacks.on_warning(f"TikZ fix skipped for {section_id}: {e}")
                break

        return latex

    @staticmethod
    def _build_tikz_fix_prompt(
        latex: str,
        current_issues: list,
        issue_history: list[list[dict[str, str]]],
    ) -> str:
        """Build a severity-sorted fix prompt with accumulated issue history."""
        from .models import Severity

        # Sort current issues: ERROR first, then WARNING, then INFO
        severity_order = {Severity.CRITICAL: 0, Severity.ERROR: 1, Severity.WARNING: 2, Severity.INFO: 3}
        sorted_issues = sorted(current_issues, key=lambda i: severity_order.get(i.severity, 3))

        parts = [
            "Fix the following TikZ issues in this LaTeX section. "
            "Return the COMPLETE section with corrected diagrams.\n"
        ]

        # Current issues grouped by severity
        parts.append("CURRENT ISSUES (fix these now):")
        for iss in sorted_issues:
            parts.append(f"  [{iss.severity.value.upper()}] [{iss.category}] {iss.description}")

        # Prior round history (so fixer knows what was already tried)
        if len(issue_history) > 1:
            parts.append("\nPRIOR ROUND ISSUES (already attempted — avoid repeating these mistakes):")
            for round_num, round_issues in enumerate(issue_history[:-1], 1):
                parts.append(f"  Round {round_num}:")
                for iss in round_issues:
                    parts.append(f"    [{iss['severity'].upper()}] [{iss['category']}] {iss['description']}")

        parts.append(f"\nSECTION:\n{latex}")
        return "\n".join(parts)

    def _sanitize_missing_figures(self) -> bool:
        """Comment out missing-figure references across all sections.

        Iterates ``self.section_latex``, applies ``_comment_missing_figures``
        on each, and updates in-place.  Does **not** write files — callers
        handle that.

        Returns ``True`` if any section was modified.
        """
        changed = False
        for section_id, latex in list(self.section_latex.items()):
            fixed, commented_paths = _comment_missing_figures(latex, self.output_dir)
            if commented_paths:
                self.callbacks.on_warning(
                    f"Section {section_id}: commented out missing figure(s): {', '.join(commented_paths)}"
                )
                self.section_latex[section_id] = fixed
                changed = True
        return changed

    def _aggregate_faithfulness(self) -> FaithfulnessReport:
        """Combine per-section faithfulness reports into one aggregate report."""
        all_violations: list[FaithfulnessViolation] = []
        section_match = True
        math_match = True
        citation_match = True
        figure_match = True

        for sid, review in self.section_reviews.items():
            if review.faithfulness is None:
                continue
            all_violations.extend(review.faithfulness.violations)
            if not review.faithfulness.section_match:
                section_match = False
            if not review.faithfulness.math_match:
                math_match = False
            if not review.faithfulness.citation_match:
                citation_match = False
            if not review.faithfulness.figure_match:
                figure_match = False

        passed = not any(
            v.severity in (Severity.CRITICAL, Severity.ERROR)
            for v in all_violations
        )

        return FaithfulnessReport(
            passed=passed,
            violations=all_violations,
            section_match=section_match,
            math_match=math_match,
            citation_match=citation_match,
            figure_match=figure_match,
        )

    def _build_section_summaries(self) -> str:
        """Build truncated summaries of each section for the meta-reviewer.

        Each summary includes: first 20 lines, last 10 lines, stats, and
        prior review results.
        """
        parts: list[str] = []

        for section_id, latex in self.section_latex.items():
            lines = latex.splitlines()
            total_lines = len(lines)

            # First 20 + last 10 lines
            head = "\n".join(lines[:20])
            tail = "\n".join(lines[-10:]) if total_lines > 30 else ""

            # Stats
            eq_count = latex.count("\\begin{equation")
            fig_count = latex.count("\\includegraphics")
            cite_count = len(re.findall(r"\\cite[tp]?\{", latex))

            summary = f"=== Section: {section_id} ({total_lines} lines) ===\n"
            summary += f"Stats: {eq_count} equations, {fig_count} figures, {cite_count} citations\n"

            # Prior review results
            if section_id in self.section_reviews:
                sr = self.section_reviews[section_id]
                for r in sr.reviews:
                    summary += f"  [{r.Reviewer}]: {r.Review}\n"
                if sr.faithfulness and not sr.faithfulness.passed:
                    summary += f"  [Faithfulness]: FAILED ({len(sr.faithfulness.violations)} violations)\n"
                if sr.fix_applied:
                    summary += "  [Fix]: Applied after review\n"

            summary += f"\n--- Head (first 20 lines) ---\n{head}\n"
            if tail:
                summary += f"\n--- Tail (last 10 lines) ---\n{tail}\n"

            parts.append(summary)

        return "\n\n".join(parts)

    @staticmethod
    def _parse_affected_sections(feedback: str) -> list[str]:
        """Extract section_ids from meta-reviewer feedback text.

        Looks for patterns like: "section_id": "02_methodology" or
        "section_id": "02_methodology, 03_results" (comma-separated) or
        section_id: 02_methodology (plain text).
        """
        affected: list[str] = []

        def _add(sid: str) -> None:
            sid = sid.strip().strip('",')
            if sid and sid not in affected:
                affected.append(sid)

        # Pattern 1: JSON-like "section_id": "value" (may be comma-separated)
        for m in re.finditer(r'"section_id"\s*:\s*"([^"]+)"', feedback):
            for part in m.group(1).split(","):
                _add(part)

        # Pattern 2: section_id: value (plain text)
        for m in re.finditer(r'section_id\s*:\s*(\S+)', feedback, re.IGNORECASE):
            for part in m.group(1).split(","):
                _add(part)

        return affected

    # -----------------------------------------------------------------------
    # Placeholder draft generation for missing sections
    # -----------------------------------------------------------------------

    # Standard sections that PlanReviewer commonly recommends.
    # Maps keyword → (section_id, title, position).
    # position: "start" inserts before all sections, "end" appends after all.
    _REVIEW_SECTION_KEYWORDS: dict[str, tuple[str, str, str]] = {
        "abstract": ("abstract", "Abstract", "start"),
        "conclusion": ("conclusion", "Conclusion", "end"),
        "discussion": ("discussion", "Discussion", "end"),
        "results": ("results", "Results", "end"),
        "acknowledgement": ("acknowledgements", "Acknowledgements", "end"),
        "acknowledgment": ("acknowledgements", "Acknowledgements", "end"),
    }

    def _add_sections_from_review_notes(
        self,
        plan: StructurePlan,
        review_notes: str | None,
    ) -> list[str]:
        """Add standard sections mentioned in review notes but missing from the plan.

        Sections are inserted at natural positions (e.g. Abstract at the start,
        Conclusion at the end) rather than blindly appended.

        Returns list of section_ids that were added.
        """
        if not review_notes:
            return []

        notes_lower = review_notes.lower()
        existing_titles_lower = {s.title.lower() for s in plan.sections}
        existing_ids = {s.section_id for s in plan.sections}
        added: list[str] = []

        # Collect sections to insert, grouped by position
        to_prepend: list[SectionPlan] = []
        to_append: list[SectionPlan] = []

        for keyword, (section_id, title, position) in self._REVIEW_SECTION_KEYWORDS.items():
            if section_id in existing_ids or section_id in added:
                continue
            if keyword not in notes_lower:
                continue
            # Check if a section with this type already exists by title keyword
            if any(keyword in t for t in existing_titles_lower):
                continue

            new_section = SectionPlan(
                section_id=section_id,
                title=title,
                source_file=f"drafts/{section_id}.md",
                priority=0,  # re-numbered below
            )
            if position == "start":
                to_prepend.append(new_section)
            else:
                to_append.append(new_section)
            added.append(section_id)

        if not added:
            return []

        # Rebuild sections list with correct ordering
        plan.sections = to_prepend + plan.sections + to_append

        # Re-number priorities to match new list order
        for i, section in enumerate(plan.sections):
            section.priority = i + 1

        return added

    @staticmethod
    def _placeholder_content(title: str, section_id: str) -> str:
        """Return section-type-aware deterministic placeholder markdown."""
        key = section_id.lower() + " " + title.lower()

        if "abstract" in key:
            guidance = "Summarize the research problem, methodology, key results, and conclusions."
        elif "conclusion" in key:
            guidance = "Summarize the key findings from previous sections. Discuss implications and future work."
        elif "discussion" in key:
            guidance = "Interpret the results. Compare with existing literature. Discuss limitations."
        elif "result" in key:
            guidance = "Present the main findings. Reference figures and tables."
        elif "acknowledgement" in key or "acknowledgment" in key:
            guidance = "Acknowledge funding sources, collaborators, and institutional support."
        else:
            guidance = f"Write the {title} section content."

        return (
            f"# {title}\n"
            f"\n"
            f"<!-- TODO: {guidance} -->\n"
            f"<!-- This section was added by PlanReviewer but no draft file exists. -->\n"
        )

    def _generate_placeholder_drafts(
        self,
        plan: StructurePlan,
        draft_files: list[Path],
    ) -> list[Path]:
        """Generate placeholder .md files for plan sections without source files.

        Uses a single LLM call to derive placeholder content from existing drafts.
        Falls back to deterministic templates on any failure.

        Returns a list of created file paths.
        """
        existing_stems = {f.stem for f in draft_files}
        missing_sections: list[SectionPlan] = []

        for section in plan.sections:
            source_path = self.config_dir / section.source_file
            # Also check draft_dir fallback (same as run_conversion)
            alt_path = self.draft_dir / Path(section.source_file).name
            if not source_path.exists() and not alt_path.exists():
                stem = Path(section.source_file).stem
                if stem not in existing_stems:
                    missing_sections.append(section)

        # Detect duplicate source file assignments: when the auto-revision
        # maps multiple sections to the same existing file, the duplicates
        # need their own placeholder files.
        source_usage: dict[str, list[SectionPlan]] = {}
        for section in plan.sections:
            key = Path(section.source_file).name
            source_usage.setdefault(key, []).append(section)
        for filename, sections in source_usage.items():
            if len(sections) > 1:
                for dup in sections[1:]:
                    if dup not in missing_sections:
                        dup.source_file = f"drafts/{dup.section_id}.md"
                        missing_sections.append(dup)

        if not missing_sections:
            return []

        self.draft_dir.mkdir(parents=True, exist_ok=True)
        created: list[Path] = []

        # Try a single LLM call for all missing sections
        llm_content: dict[str, str] = {}
        try:
            planner = make_structure_planner(self.config, template_context=self.template_context)
            orchestrator = autogen.UserProxyAgent(
                name="Orchestrator",
                human_input_mode="NEVER",
                code_execution_config=False,
            )

            # Build summaries of existing drafts (first 30 lines each)
            draft_summaries = ""
            for sid, content in self.source_md.items():
                preview = "\n".join(content.splitlines()[:30])
                draft_summaries += f"\n--- {sid} ---\n{preview}\n...\n"

            missing_desc = "\n".join(
                f"- {s.section_id}: {s.title}" for s in missing_sections
            )

            response = orchestrator.initiate_chat(
                planner,
                message=(
                    "The following sections were added to the structure plan but have no "
                    "draft files. For each missing section, generate a brief markdown draft "
                    "skeleton. Derive what you can from the existing drafts. Use "
                    "`<!-- TODO: ... -->` comments for content the user must write.\n\n"
                    "Return a JSON object mapping section_id to markdown content.\n"
                    "Example: {\"conclusion\": \"# Conclusion\\n\\n<!-- TODO: ... -->\"}\n\n"
                    f"Missing sections:\n{missing_desc}\n\n"
                    f"Existing draft summaries:\n{draft_summaries}"
                ),
                max_turns=1,
            )

            raw = _extract_latex(response)
            if "{" in raw:
                json_str = raw[raw.find("{"):raw.rfind("}") + 1]
                llm_content = json.loads(json_str)
                if not isinstance(llm_content, dict):
                    llm_content = {}
        except Exception as e:
            logger.warning("LLM placeholder generation failed, using deterministic fallback: %s", e)
            llm_content = {}

        # Write placeholder files
        for section in missing_sections:
            content = llm_content.get(section.section_id)
            if not content or not isinstance(content, str):
                content = self._placeholder_content(section.title, section.section_id)

            # Ensure TODO marker exists
            if "TODO" not in content:
                content += f"\n\n<!-- TODO: Review and complete this section. -->\n"

            out_path = self.draft_dir / f"{section.section_id}.md"
            if not out_path.exists():
                out_path.write_text(content, encoding="utf-8")
                # Update source_file in the plan to point to the new file
                section.source_file = str(out_path.relative_to(self.config_dir))
                # Also add to source_md so faithfulness checks can reference it
                self.source_md[section.section_id] = content
                created.append(out_path)

        return created

    def _identify_affected_sections(self, result: CompilationResult) -> list[str]:
        """Map compilation errors to section files by matching error context/message."""
        affected: list[str] = []

        for err in result.errors:
            # Check if error mentions a section file
            if err.file and "sections/" in err.file:
                sid = err.file.replace("sections/", "").replace(".tex", "")
                if sid in self.section_latex and sid not in affected:
                    affected.append(sid)
                continue

            # Try matching error context lines against section content
            ctx = err.context or ""
            if ctx:
                for section_id, latex in self.section_latex.items():
                    for line in ctx.splitlines():
                        cleaned = re.sub(r"^[>\s]*\d*\s*\|\s*", "", line).strip()
                        if cleaned and len(cleaned) > 10 and cleaned in latex:
                            if section_id not in affected:
                                affected.append(section_id)
                            break

            # Also try matching key tokens from the error message (e.g. filenames,
            # command names) against section content
            msg = err.message
            if not msg:
                continue
            # Extract quoted/backticked tokens from the error message
            tokens = re.findall(r"[`']([^`']+)[`']", msg)
            for token in tokens:
                token = token.strip()
                if len(token) < 4:
                    continue
                for section_id, latex in self.section_latex.items():
                    if token in latex and section_id not in affected:
                        affected.append(section_id)

        return affected
