"""Pipeline — 6-phase orchestration for research article generation.

Phase 1: PLANNING         — StructurePlanner analyzes inputs
Phase 2: CONVERSION       — Pandoc + LaTeXAssembler per section
Phase 3: POST-PROCESSING  — Equations, figures, citations
Phase 4: COMPILATION + REVIEW — latexmk, ChkTeX, nested reviewer chats
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
from .agents.latex_assembler import make_assembler
from .agents.page_budget_manager import make_page_budget_manager
from .agents.reviewers import make_meta_reviewer, make_reviewers, reflection_message, build_summary_args
from .agents.structure_planner import make_structure_planner
from .logging_config import PipelineCallbacks, RichCallbacks, logger
from .models import (
    BuildManifest,
    CompilationResult,
    FaithfulnessReport,
    PipelinePhase,
    PipelineResult,
    ProjectConfig,
    SplitDecision,
    StructurePlan,
    SectionPlan,
)
from .tools.compiler import extract_error_context, run_latexmk
from .tools.diff_checker import run_faithfulness_check
from .tools.latex_builder import (
    assemble_document,
    generate_makefile,
    generate_preamble,
    write_main_tex,
    write_makefile,
)
from .tools.linter import run_lint
from .tools.page_counter import count_pages
from .tools.pandoc_converter import convert_markdown_to_latex

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class Pipeline:
    """Orchestrates the 6-phase research article generation pipeline."""

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

        # State
        self.structure_plan: StructurePlan | None = None
        self.section_latex: dict[str, str] = {}  # section_id → polished LaTeX
        self.pandoc_latex: dict[str, str] = {}    # section_id → raw pandoc LaTeX
        self.source_md: dict[str, str] = {}       # section_id → raw markdown
        self.full_latex: str = ""
        self.compilation_result: CompilationResult | None = None
        self.faithfulness_report: FaithfulnessReport | None = None
        self.split_decision: SplitDecision | None = None
        self.manifest: BuildManifest | None = None

    # -----------------------------------------------------------------------
    # Phase 1: Planning
    # -----------------------------------------------------------------------

    def run_planning(self) -> StructurePlan:
        """Phase 1: Analyze inputs and produce a structure plan."""
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
        for f in draft_files:
            content = f.read_text(encoding="utf-8")
            self.source_md[f.stem] = content
            # Show first few lines for context
            preview = "\n".join(content.splitlines()[:10])
            input_desc += f"\n--- {f.name} ---\n{preview}\n...\n"

        if figure_files:
            input_desc += f"\nFigure files ({len(figure_files)}):\n"
            for f in figure_files:
                input_desc += f"  - {f.name}\n"

        if self.bib_file and self.bib_file.exists():
            input_desc += f"\nBibliography: {self.bib_file.name}\n"

        # Use AG2 agent
        planner = make_structure_planner(self.config)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        response = orchestrator.initiate_chat(
            planner,
            message=f"Create a structure plan for this research article:\n\n{input_desc}",
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
        self.callbacks.on_phase_end("PLANNING", True)
        return plan

    # -----------------------------------------------------------------------
    # Phase 2: Conversion
    # -----------------------------------------------------------------------

    def run_conversion(self) -> dict[str, str]:
        """Phase 2: Convert each section via Pandoc + LLM polish."""
        if not self.structure_plan:
            raise RuntimeError("Must run planning phase first")

        self.callbacks.on_phase_start("CONVERSION", "Converting sections to LaTeX")

        assembler = make_assembler(self.config)
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
                # Fallback: try matching by section_id stem
                candidates = list(self.draft_dir.glob(f"*{section.section_id}*"))
                if candidates:
                    source_path = candidates[0]
            if not source_path.exists():
                logger.warning("Source file not found: %s, skipping", source_path)
                self.callbacks.on_warning(f"Skipping {section.section_id}: source file not found")
                continue

            # Step 1: Pandoc conversion (deterministic)
            pandoc_latex = convert_markdown_to_latex(source_path, annotate=True)
            self.pandoc_latex[section.section_id] = pandoc_latex

            # Step 2: LLM polish
            prompt = (
                f"Polish this Pandoc-converted LaTeX for the section '{section.title}'. "
                f"Template: {self.config.template}. "
                f"Only modify text between SAFE_ZONE markers.\n\n"
                f"{pandoc_latex}"
            )

            response = orchestrator.initiate_chat(
                assembler,
                message=prompt,
                max_turns=1,
            )

            polished = _extract_latex(response)
            self.section_latex[section.section_id] = polished
            self.callbacks.on_section_end(section.section_id)

        self.callbacks.on_phase_end("CONVERSION", len(self.section_latex) > 0)
        return self.section_latex

    # -----------------------------------------------------------------------
    # Phase 3: Post-processing
    # -----------------------------------------------------------------------

    def run_post_processing(self) -> str:
        """Phase 3: Equation, figure, and citation passes + assembly."""
        self.callbacks.on_phase_start("POST_PROCESSING", "Equation, figure, and citation passes")

        # Assemble full document first
        preamble = generate_preamble(self.config)
        sections = [
            (sid, latex)
            for sid, latex in self.section_latex.items()
        ]

        # Handle abstract if present
        abstract = None
        if self.structure_plan and self.structure_plan.abstract_file:
            abs_path = self.config_dir / self.structure_plan.abstract_file
            if abs_path.exists():
                abstract = convert_markdown_to_latex(abs_path, annotate=False)

        bib_name = None
        if self.bib_file:
            bib_name = self.bib_file.stem

        self.full_latex = assemble_document(
            preamble,
            sections,
            abstract=abstract,
            bibliography=bib_name,
            bib_style=self.config.bib_style,
        )

        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        # Equation formatting pass
        eq_formatter = make_equation_formatter(self.config)
        response = orchestrator.initiate_chat(
            eq_formatter,
            message=f"Check and fix equation consistency:\n\n{self.full_latex}",
            max_turns=1,
        )
        self.full_latex = _extract_latex(response)

        # Figure integration pass
        fig_integrator = make_figure_integrator(self.config)
        response = orchestrator.initiate_chat(
            fig_integrator,
            message=f"Optimize figure placement and sizing:\n\n{self.full_latex}",
            max_turns=1,
        )
        self.full_latex = _extract_latex(response)

        # Citation validation
        if self.bib_file and self.bib_file.exists():
            bib_content = self.bib_file.read_text(encoding="utf-8")
            citation_agent = make_citation_agent(self.config)
            response = orchestrator.initiate_chat(
                citation_agent,
                message=(
                    f"Validate citations in this LaTeX against the .bib file.\n\n"
                    f"LaTeX:\n{self.full_latex}\n\n"
                    f".bib contents:\n{bib_content}"
                ),
                max_turns=1,
            )
            # Citation agent only reports — doesn't modify

        self.callbacks.on_phase_end("POST_PROCESSING", True)
        return self.full_latex

    # -----------------------------------------------------------------------
    # Phase 4: Compilation + Review
    # -----------------------------------------------------------------------

    def run_compilation_review(self) -> CompilationResult:
        """Phase 4: Compile, lint, review, fix loop."""
        self.callbacks.on_phase_start("COMPILATION_REVIEW", "Compiling and reviewing")

        # Prepare output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Copy figures
        if self.figure_dir.exists():
            for fig in _list_figure_files(self.figure_dir):
                dest = self.output_dir / fig.name
                if not dest.exists():
                    shutil.copy2(fig, dest)

        # Copy .bib file
        if self.bib_file and self.bib_file.exists():
            dest = self.output_dir / self.bib_file.name
            if not dest.exists():
                shutil.copy2(self.bib_file, dest)

        # Write Makefile
        write_makefile(generate_makefile(self.config), self.output_dir)

        # Compile-fix loop
        assembler = make_assembler(self.config)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        latex_content = self.full_latex
        result = CompilationResult(success=False, errors=[], warnings=[])

        for attempt in range(1, self.config.compile_max_attempts + 1):
            self.callbacks.on_compile_attempt(attempt, self.config.compile_max_attempts)

            write_main_tex(latex_content, self.output_dir)
            result = run_latexmk(self.output_dir, self.config.latex_engine)

            if result.success and not result.unresolved_refs:
                break

            if attempt < self.config.compile_max_attempts:
                # Extract error context and ask LLM to fix
                error_ctx = extract_error_context(result, latex_content)
                response = orchestrator.initiate_chat(
                    assembler,
                    message=(
                        f"The LaTeX compilation failed. Fix the errors below and return "
                        f"the COMPLETE corrected LaTeX document.\n\n{error_ctx}\n\n"
                        f"Current document:\n{latex_content}"
                    ),
                    max_turns=1,
                )
                latex_content = _extract_latex(response)

        self.full_latex = latex_content
        self.compilation_result = result

        # Run linter
        tex_path = self.output_dir / "main.tex"
        if tex_path.exists():
            lint_result = run_lint(tex_path)
            if lint_result.total > 0:
                self.callbacks.on_warning(f"Lint: {lint_result.warning_count} warnings, {lint_result.error_count} errors")

        # Run faithfulness check (deterministic layers 1-4)
        all_source_md = "\n\n".join(self.source_md.values())
        all_pandoc_latex = "\n\n".join(self.pandoc_latex.values())
        self.faithfulness_report = run_faithfulness_check(
            all_source_md, all_pandoc_latex, latex_content,
        )

        if not self.faithfulness_report.passed:
            self.callbacks.on_warning(
                f"Faithfulness check: {len(self.faithfulness_report.violations)} violations"
            )

        # Review round (nested chats with reviewers)
        for round_num in range(1, self.config.review_max_rounds + 1):
            self.callbacks.on_review_round(round_num, self.config.review_max_rounds)

            reviewers = make_reviewers(self.config)
            meta = make_meta_reviewer(self.config)
            summary_args = build_summary_args()

            review_chats: list[dict] = []
            for name, agent in reviewers.items():
                if agent is not None:
                    review_chats.append({
                        "recipient": agent,
                        "message": reflection_message,
                        "summary_method": "reflection_with_llm",
                        "summary_args": summary_args,
                        "max_turns": self.config.review_max_turns,
                    })
            review_chats.append({
                "recipient": meta,
                "message": "Aggregate all reviewer feedback. Prioritize faithfulness issues.",
                "max_turns": self.config.review_max_turns,
            })

            # Use assembler as trigger for nested reviews
            review_agent = make_assembler(self.config)
            review_agent.register_nested_chats(review_chats, trigger=orchestrator)

            response = orchestrator.initiate_chat(
                review_agent,
                message=f"Review and improve this LaTeX:\n\n{latex_content}",
                max_turns=2,
            )

            new_latex = _extract_latex(response)
            if new_latex and new_latex != latex_content:
                latex_content = new_latex
                self.full_latex = latex_content

                # Recompile after fixes
                write_main_tex(latex_content, self.output_dir)
                result = run_latexmk(self.output_dir, self.config.latex_engine)
                self.compilation_result = result

                if result.success:
                    break

        self.callbacks.on_phase_end("COMPILATION_REVIEW", result.success)
        return result

    # -----------------------------------------------------------------------
    # Phase 5: Page Budget
    # -----------------------------------------------------------------------

    def run_page_budget(self) -> SplitDecision | None:
        """Phase 5: Advisory page budget analysis."""
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

        # Over budget — ask LLM for advisory
        budget_mgr = make_page_budget_manager(self.config)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        sections_info = ""
        if self.structure_plan:
            for s in self.structure_plan.sections:
                sections_info += f"  - {s.section_id}: ~{s.estimated_pages} pages (priority {s.priority})\n"

        response = orchestrator.initiate_chat(
            budget_mgr,
            message=(
                f"The document is {page_count} pages but the budget is {self.config.page_budget} pages.\n"
                f"Sections:\n{sections_info}\n"
                f"Recommend which sections/figures to move to supplementary materials."
            ),
            max_turns=1,
        )

        decision = _extract_json(response, SplitDecision)
        if decision is None:
            decision = SplitDecision(
                action="warn_over",
                current_pages=page_count,
                budget_pages=self.config.page_budget,
                recommendations=f"Document is {page_count} pages, over budget of {self.config.page_budget}.",
            )

        self.split_decision = decision
        if decision.action != "ok":
            self.callbacks.on_warning(decision.recommendations)

        self.callbacks.on_phase_end("PAGE_BUDGET", True)
        return decision

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

        self.manifest = BuildManifest(
            project_name=self.config.project_name,
            output_dir=str(self.output_dir),
            pdf_file=self.compilation_result.pdf_path if self.compilation_result else None,
            source_files=[s.source_file for s in (self.structure_plan.sections if self.structure_plan else [])],
            figure_files=[str(f) for f in _list_figure_files(self.figure_dir)],
            bibliography_file=str(self.bib_file) if self.bib_file else None,
            template_used=self.config.template,
            compilation_attempts=self.config.compile_max_attempts,
            faithfulness_passed=self.faithfulness_report.passed if self.faithfulness_report else False,
            page_count=self.compilation_result.page_count if self.compilation_result else None,
            warnings=warnings,
        )

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

            self.run_conversion()
            phases.append(PipelinePhase.CONVERSION)

            self.run_post_processing()
            phases.append(PipelinePhase.POST_PROCESSING)

            self.run_compilation_review()
            phases.append(PipelinePhase.COMPILATION_REVIEW)

            self.run_page_budget()
            phases.append(PipelinePhase.PAGE_BUDGET)

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

        assembler = make_assembler(self.config)
        orchestrator = autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        response = orchestrator.initiate_chat(
            assembler,
            message=(
                f"Polish this Pandoc-converted LaTeX. Template: {self.config.template}. "
                f"Only modify text between SAFE_ZONE markers.\n\n{pandoc_latex}"
            ),
            max_turns=1,
        )

        return _extract_latex(response)

    def run_compile_only(self) -> CompilationResult:
        """Compile existing output directory (no LLM)."""
        return run_latexmk(self.output_dir, self.config.latex_engine)

    def run_validate_only(self) -> FaithfulnessReport:
        """Run faithfulness validation on existing output."""
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
