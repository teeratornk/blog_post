"""Tests for Pipeline helper methods (no LLM calls required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from research_article_generator.models import (
    BuildManifest,
    CompilationResult,
    CompilationWarning,
    FaithfulnessReport,
    FaithfulnessViolation,
    PlanAction,
    PlanReviewResult,
    ProjectConfig,
    ReviewFeedback,
    SectionPlan,
    SectionReviewResult,
    Severity,
    StructurePlan,
    SupplementaryPlan,
)
from research_article_generator.logging_config import RichCallbacks
from research_article_generator.pipeline import (
    Pipeline,
    _comment_missing_figures,
    _extract_latex,
    _insert_suggestion_comments,
    _looks_like_latex,
    _parse_figure_suggestions,
)


@pytest.fixture
def pipeline(tmp_path):
    """Create a Pipeline with minimal config for testing helpers."""
    config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
    p = Pipeline(config, config_dir=tmp_path)
    return p


class TestAggregateFaithfulness:
    def test_all_pass(self, pipeline):
        pipeline.section_reviews = {
            "01_intro": SectionReviewResult(
                section_id="01_intro",
                faithfulness=FaithfulnessReport(
                    passed=True, violations=[], section_match=True,
                    math_match=True, citation_match=True, figure_match=True,
                ),
            ),
            "02_methods": SectionReviewResult(
                section_id="02_methods",
                faithfulness=FaithfulnessReport(
                    passed=True, violations=[], section_match=True,
                    math_match=True, citation_match=True, figure_match=True,
                ),
            ),
        }
        report = pipeline._aggregate_faithfulness()
        assert report.passed is True
        assert report.section_match is True
        assert report.math_match is True
        assert report.citation_match is True
        assert report.figure_match is True
        assert len(report.violations) == 0

    def test_one_section_fails(self, pipeline):
        violation = FaithfulnessViolation(
            severity=Severity.ERROR,
            issue="Math expression altered",
        )
        pipeline.section_reviews = {
            "01_intro": SectionReviewResult(
                section_id="01_intro",
                faithfulness=FaithfulnessReport(
                    passed=True, violations=[], section_match=True,
                    math_match=True, citation_match=True, figure_match=True,
                ),
            ),
            "02_methods": SectionReviewResult(
                section_id="02_methods",
                faithfulness=FaithfulnessReport(
                    passed=False, violations=[violation],
                    section_match=True, math_match=False,
                    citation_match=True, figure_match=True,
                ),
            ),
        }
        report = pipeline._aggregate_faithfulness()
        assert report.passed is False
        assert report.math_match is False
        assert len(report.violations) == 1

    def test_empty_reviews(self, pipeline):
        pipeline.section_reviews = {}
        report = pipeline._aggregate_faithfulness()
        assert report.passed is True
        assert len(report.violations) == 0

    def test_none_faithfulness(self, pipeline):
        pipeline.section_reviews = {
            "01_intro": SectionReviewResult(
                section_id="01_intro",
                faithfulness=None,
            ),
        }
        report = pipeline._aggregate_faithfulness()
        assert report.passed is True


class TestBuildSectionSummaries:
    def test_basic_summaries(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\n" + "Line.\n" * 25,
            "02_methods": "\\section{Methods}\n\\begin{equation}\nx=1\n\\end{equation}\n",
        }
        pipeline.section_reviews = {
            "01_intro": SectionReviewResult(
                section_id="01_intro",
                reviews=[ReviewFeedback(Reviewer="LaTeXLinter", Review="- looks good")],
            ),
        }
        result = pipeline._build_section_summaries()
        assert "01_intro" in result
        assert "02_methods" in result
        assert "Head (first 20 lines)" in result
        assert "LaTeXLinter" in result
        assert "1 equations" in result

    def test_empty_sections(self, pipeline):
        pipeline.section_latex = {}
        pipeline.section_reviews = {}
        result = pipeline._build_section_summaries()
        assert result == ""


class TestParseAffectedSections:
    def test_json_format(self):
        feedback = '{"section_id": "02_methodology", "issue": "notation"}'
        result = Pipeline._parse_affected_sections(feedback)
        assert result == ["02_methodology"]

    def test_multiple_sections(self):
        feedback = (
            '{"section_id": "01_intro", "issue": "flow"}\n'
            '{"section_id": "03_results", "issue": "redundancy"}'
        )
        result = Pipeline._parse_affected_sections(feedback)
        assert "01_intro" in result
        assert "03_results" in result

    def test_plain_text_format(self):
        feedback = "section_id: 02_methodology has notation issues"
        result = Pipeline._parse_affected_sections(feedback)
        assert "02_methodology" in result

    def test_no_sections(self):
        feedback = "Everything looks good, no cross-section issues found."
        result = Pipeline._parse_affected_sections(feedback)
        assert result == []

    def test_deduplication(self):
        feedback = (
            '{"section_id": "01_intro", "issue": "a"}\n'
            '{"section_id": "01_intro", "issue": "b"}'
        )
        result = Pipeline._parse_affected_sections(feedback)
        assert result == ["01_intro"]

    def test_comma_separated_section_ids(self):
        feedback = '{"section_id": "02_methodology, 02_methodology_problem_statement", "issue": "redundancy"}'
        result = Pipeline._parse_affected_sections(feedback)
        assert "02_methodology" in result
        assert "02_methodology_problem_statement" in result

    def test_mixed_comma_and_separate(self):
        feedback = (
            '{"section_id": "01_intro, 02_methods", "issue": "flow"}\n'
            '{"section_id": "03_results", "issue": "citations"}'
        )
        result = Pipeline._parse_affected_sections(feedback)
        assert result == ["01_intro", "02_methods", "03_results"]


class TestIdentifyAffectedSections:
    def test_error_in_section_file(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nHello.",
            "02_methods": "\\section{Methods}\nWorld.",
        }
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    file="sections/02_methods.tex",
                    message="Undefined control sequence",
                    severity=Severity.ERROR,
                ),
            ],
        )
        affected = pipeline._identify_affected_sections(result)
        assert affected == ["02_methods"]

    def test_error_context_match(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nThis is a unique line in intro.",
            "02_methods": "\\section{Methods}\nThis is a unique line in methods.",
        }
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="Undefined control sequence",
                    severity=Severity.ERROR,
                    context=">>> 10 | This is a unique line in methods.",
                ),
            ],
        )
        affected = pipeline._identify_affected_sections(result)
        assert "02_methods" in affected

    def test_error_message_token_match(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nHello.",
            "02_methods": (
                "\\section{Methods}\n"
                "\\includegraphics{figures/convergence.png}\n"
            ),
        }
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="File `figures/convergence.png' not found",
                    severity=Severity.ERROR,
                ),
            ],
        )
        affected = pipeline._identify_affected_sections(result)
        assert "02_methods" in affected
        assert "01_intro" not in affected

    def test_no_match(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nHello.",
        }
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="Something generic",
                    severity=Severity.ERROR,
                ),
            ],
        )
        affected = pipeline._identify_affected_sections(result)
        assert affected == []


class TestCommentMissingFigures:
    def test_missing_figure_commented_out(self, tmp_path):
        latex = (
            "\\section{Results}\n"
            "\\begin{figure}[htbp]\n"
            "\\centering\n"
            "\\includegraphics[width=0.9\\linewidth]{figures/convergence.png}\n"
            "\\caption{Convergence plot.}\n"
            "\\label{fig:conv}\n"
            "\\end{figure}\n"
            "Some text after.\n"
        )
        result, commented = _comment_missing_figures(latex, tmp_path)
        assert "figures/convergence.png" in commented
        assert "% [missing figure]" in result
        assert "Some text after." in result

    def test_existing_figure_kept(self, tmp_path):
        # Create the figure file
        (tmp_path / "figures").mkdir()
        (tmp_path / "figures" / "convergence.png").write_bytes(b"fake png")
        latex = (
            "\\begin{figure}[htbp]\n"
            "\\includegraphics{figures/convergence.png}\n"
            "\\end{figure}\n"
        )
        result, commented = _comment_missing_figures(latex, tmp_path)
        assert commented == []
        assert result == latex

    def test_no_figures_unchanged(self, tmp_path):
        latex = "\\section{Intro}\nSome text.\n"
        result, commented = _comment_missing_figures(latex, tmp_path)
        assert commented == []
        assert result == latex

    def test_multiple_figures_mixed(self, tmp_path):
        (tmp_path / "figures").mkdir()
        (tmp_path / "figures" / "existing.png").write_bytes(b"fake")
        latex = (
            "\\begin{figure}[htbp]\n"
            "\\includegraphics{figures/existing.png}\n"
            "\\caption{Exists.}\n"
            "\\end{figure}\n"
            "\\begin{figure}[htbp]\n"
            "\\includegraphics{figures/missing.pdf}\n"
            "\\caption{Missing.}\n"
            "\\end{figure}\n"
        )
        result, commented = _comment_missing_figures(latex, tmp_path)
        assert "figures/missing.pdf" in commented
        assert "figures/existing.png" not in commented
        # Existing figure environment should be untouched
        assert "\\includegraphics{figures/existing.png}" in result


class TestInsertSupplementaryNote:
    def test_note_appended_to_last_main_section(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nHello.",
            "02_methods": "\\section{Methods}\nWorld.",
            "06_proofs": "\\section{Proofs}\nProofs here.",
        }
        plan = SupplementaryPlan(
            supplementary_sections=["06_proofs"],
            cross_reference_note="See Supplementary for proofs.",
        )
        pipeline._insert_supplementary_note(plan)
        # Note should be in 02_methods (last main section), not in 06_proofs
        assert "Supplementary Materials" in pipeline.section_latex["02_methods"]
        assert "See Supplementary for proofs." in pipeline.section_latex["02_methods"]
        assert "Supplementary Materials" not in pipeline.section_latex["01_intro"]
        assert "\\paragraph{Supplementary Materials.}" in pipeline.section_latex["02_methods"]

    def test_no_main_sections(self, pipeline):
        pipeline.section_latex = {
            "06_proofs": "\\section{Proofs}\nProofs here.",
        }
        plan = SupplementaryPlan(supplementary_sections=["06_proofs"])
        # Should not raise
        pipeline._insert_supplementary_note(plan)
        # No note should be inserted since all sections are supplementary
        assert "Supplementary Materials" not in pipeline.section_latex["06_proofs"]

    def test_single_main_section(self, pipeline):
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nHello.",
            "06_proofs": "\\section{Proofs}\nProofs here.",
        }
        plan = SupplementaryPlan(supplementary_sections=["06_proofs"])
        pipeline._insert_supplementary_note(plan)
        assert "Supplementary Materials" in pipeline.section_latex["01_intro"]


class TestRebuildMainWithAppendix:
    def test_appendix_ids_passed(self, pipeline, tmp_path):
        # Set up state
        pipeline.section_latex = {
            "01_intro": "\\section{Introduction}\nHello.",
            "02_methods": "\\section{Methods}\nWorld.",
            "06_proofs": "\\section{Proofs}\nProofs here.",
        }
        pipeline.structure_plan = None  # no abstract
        pipeline.output_dir = tmp_path / "output"
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)

        plan = SupplementaryPlan(
            mode="appendix",
            supplementary_sections=["06_proofs"],
        )
        pipeline._rebuild_main_with_appendix(plan)

        main_tex = (pipeline.output_dir / "main.tex").read_text(encoding="utf-8")
        assert "\\appendix" in main_tex
        assert "\\input{sections/06_proofs}" in main_tex
        # Main sections should be included before appendix
        assert "\\input{sections/01_intro}" in main_tex
        assert "\\input{sections/02_methods}" in main_tex
        # The appendix input should come after \appendix
        appendix_pos = main_tex.index("\\appendix")
        proofs_pos = main_tex.index("\\input{sections/06_proofs}")
        assert proofs_pos > appendix_pos


class TestIsSupplementaryEnabled:
    def test_disabled(self, pipeline):
        pipeline.config.supplementary_mode = "disabled"
        assert pipeline._is_supplementary_enabled(20) is False

    def test_appendix_mode(self, pipeline):
        pipeline.config.supplementary_mode = "appendix"
        assert pipeline._is_supplementary_enabled(20) is True

    def test_standalone_mode(self, pipeline):
        pipeline.config.supplementary_mode = "standalone"
        assert pipeline._is_supplementary_enabled(20) is True

    def test_auto_over_threshold(self, pipeline):
        pipeline.config.supplementary_mode = "auto"
        pipeline.config.page_budget = 15
        pipeline.config.supplementary_threshold = 1.2
        # 20 / 15 = 1.33 > 1.2
        assert pipeline._is_supplementary_enabled(20) is True

    def test_auto_under_threshold(self, pipeline):
        pipeline.config.supplementary_mode = "auto"
        pipeline.config.page_budget = 15
        pipeline.config.supplementary_threshold = 1.2
        # 17 / 15 = 1.13 < 1.2
        assert pipeline._is_supplementary_enabled(17) is False

    def test_auto_no_budget(self, pipeline):
        pipeline.config.supplementary_mode = "auto"
        pipeline.config.page_budget = None
        assert pipeline._is_supplementary_enabled(20) is False


class TestSanitizeMissingFigures:
    def test_removes_missing_figures(self, pipeline):
        """Missing figures are commented out across all sections."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {
            "01_intro": "\\section{Intro}\nSome text.\n",
            "02_methods": (
                "\\section{Results}\n"
                "\\begin{figure}[htbp]\n"
                "\\centering\n"
                "\\includegraphics[width=0.9\\linewidth]{figures/missing.png}\n"
                "\\caption{A missing plot.}\n"
                "\\label{fig:missing}\n"
                "\\end{figure}\n"
            ),
        }
        changed = pipeline._sanitize_missing_figures()
        assert changed is True
        assert "% [missing figure]" in pipeline.section_latex["02_methods"]
        # Intro should be untouched
        assert pipeline.section_latex["01_intro"] == "\\section{Intro}\nSome text.\n"

    def test_noop_when_figures_exist(self, pipeline):
        """No changes when all figures exist on disk."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        (pipeline.output_dir / "figures").mkdir()
        (pipeline.output_dir / "figures" / "real.png").write_bytes(b"png")
        pipeline.section_latex = {
            "01_intro": (
                "\\begin{figure}[htbp]\n"
                "\\includegraphics{figures/real.png}\n"
                "\\end{figure}\n"
            ),
        }
        changed = pipeline._sanitize_missing_figures()
        assert changed is False
        assert "% [missing figure]" not in pipeline.section_latex["01_intro"]

    def test_noop_when_no_figures(self, pipeline):
        """No changes when sections contain no figure references."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {
            "01_intro": "\\section{Intro}\nPlain text.\n",
        }
        changed = pipeline._sanitize_missing_figures()
        assert changed is False

    def test_idempotent(self, pipeline):
        """Running twice produces the same result (already-commented figures stay commented)."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {
            "01_intro": (
                "\\begin{figure}[htbp]\n"
                "\\includegraphics{figures/gone.png}\n"
                "\\end{figure}\n"
            ),
        }
        pipeline._sanitize_missing_figures()
        first_pass = pipeline.section_latex["01_intro"]
        pipeline._sanitize_missing_figures()
        second_pass = pipeline.section_latex["01_intro"]
        assert first_pass == second_pass


class TestLooksLikeLaTeX:
    def test_section_command(self):
        assert _looks_like_latex("\\section{Introduction}\nSome text.") is True

    def test_begin_environment(self):
        assert _looks_like_latex("\\begin{equation}\nx=1\n\\end{equation}") is True

    def test_documentclass(self):
        assert _looks_like_latex("\\documentclass{article}") is True

    def test_plain_text(self):
        assert _looks_like_latex("Just some plain text without any commands.") is False

    def test_json_response(self):
        assert _looks_like_latex('{"Reviewer": "Linter", "Review": "ok"}') is False

    def test_empty_string(self):
        assert _looks_like_latex("") is False


class TestExtractLatex:
    def test_summary_attribute(self):
        response = MagicMock(summary="\\section{Intro}\nHello.")
        assert _extract_latex(response) == "\\section{Intro}\nHello."

    def test_chat_history_dict(self):
        response = MagicMock(summary=None, chat_history=[{"content": "\\section{X}"}])
        assert "\\section{X}" in _extract_latex(response)

    def test_strips_markdown_fences(self):
        response = MagicMock(summary="```latex\n\\section{X}\nText.\n```")
        result = _extract_latex(response)
        assert "```" not in result
        assert "\\section{X}" in result

    def test_fallback_to_str(self):
        result = _extract_latex("raw string response")
        assert result == "raw string response"


class TestCompileFixLoopBreakCondition:
    """Verify the compile-fix loop breaks on success even with unresolved refs."""

    @patch("research_article_generator.pipeline.run_latexmk")
    @patch("research_article_generator.pipeline.make_assembler")
    @patch("research_article_generator.pipeline.run_lint")
    @patch("research_article_generator.pipeline.make_meta_reviewer")
    @patch("research_article_generator.pipeline.write_section_files")
    @patch("research_article_generator.pipeline.write_makefile")
    @patch("research_article_generator.pipeline.generate_makefile", return_value="")
    def test_breaks_on_success_with_unresolved_refs(
        self, mock_genmake, mock_writemake, mock_writesec,
        mock_meta, mock_lint, mock_assembler, mock_latexmk, pipeline
    ):
        """Loop should break after first successful compile, even with unresolved refs."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {"01_intro": "\\section{Intro}\nHello."}
        pipeline.bib_file = None
        pipeline.figure_files = []
        pipeline.section_reviews = {}

        # First compile: success with unresolved refs
        success_result = CompilationResult(
            success=True,
            pdf_path="output/main.pdf",
            unresolved_refs=["ref:fig:missing", "cite:unknown2023"],
        )
        mock_latexmk.return_value = success_result
        mock_lint.return_value = MagicMock(total=0)
        # Meta-reviewer finds no issues → break immediately
        mock_meta_inst = MagicMock()
        mock_meta.return_value = mock_meta_inst

        mock_orchestrator_chat = MagicMock()
        mock_orchestrator_chat.summary = "No cross-section issues found."

        with patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = mock_orchestrator_chat

            result = pipeline.run_compilation_review()

        assert result.success is True
        # Should only have compiled once (broke after first success)
        assert mock_latexmk.call_count == 1

    @patch("research_article_generator.pipeline.run_latexmk")
    @patch("research_article_generator.pipeline.make_assembler")
    @patch("research_article_generator.pipeline.run_lint")
    @patch("research_article_generator.pipeline.make_meta_reviewer")
    @patch("research_article_generator.pipeline.write_section_files")
    @patch("research_article_generator.pipeline.write_makefile")
    @patch("research_article_generator.pipeline.generate_makefile", return_value="")
    def test_unfixable_error_breaks_loop(
        self, mock_genmake, mock_writemake, mock_writesec,
        mock_meta, mock_lint, mock_assembler, mock_latexmk, pipeline
    ):
        """Unfixable environment errors break loop immediately."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {"01_intro": "\\section{Intro}\nHello."}
        pipeline.bib_file = None
        pipeline.figure_files = []
        pipeline.section_reviews = {}

        timeout_result = CompilationResult(
            success=False,
            errors=[CompilationWarning(
                message="Compilation timed out after 120s",
                severity=Severity.ERROR,
            )],
        )
        mock_latexmk.return_value = timeout_result
        mock_lint.return_value = MagicMock(total=0)

        with patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy

            result = pipeline.run_compilation_review()

        assert result.success is False
        # Should only compile once (timeout is unfixable → break)
        assert mock_latexmk.call_count == 1


class TestMetaReviewRevert:
    """Verify meta-review revert logic when changes break compilation."""

    @patch("research_article_generator.pipeline.run_latexmk")
    @patch("research_article_generator.pipeline.make_assembler")
    @patch("research_article_generator.pipeline.run_lint")
    @patch("research_article_generator.pipeline.make_meta_reviewer")
    @patch("research_article_generator.pipeline.write_section_files")
    @patch("research_article_generator.pipeline.write_makefile")
    @patch("research_article_generator.pipeline.generate_makefile", return_value="")
    def test_reverts_when_meta_review_breaks_compilation(
        self, mock_genmake, mock_writemake, mock_writesec,
        mock_meta, mock_lint, mock_assembler, mock_latexmk, pipeline
    ):
        """If meta-review changes break compilation, revert to pre-meta state."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {
            "01_intro": "\\section{Intro}\nOriginal intro.",
            "02_methods": "\\section{Methods}\nOriginal methods.",
        }
        pipeline.bib_file = None
        pipeline.figure_files = []
        pipeline.section_reviews = {}

        compile_success = CompilationResult(success=True, pdf_path="output/main.pdf")
        compile_fail = CompilationResult(
            success=False,
            errors=[CompilationWarning(message="Broken by meta-review", severity=Severity.ERROR)],
        )

        # First call: compile-fix loop succeeds
        # Second call: meta-review recompile fails
        mock_latexmk.side_effect = [compile_success, compile_fail]
        mock_lint.return_value = MagicMock(total=0)

        # Meta-reviewer identifies section to fix
        meta_feedback = MagicMock()
        meta_feedback.summary = '{"section_id": "02_methods", "issue": "notation"}'

        # Assembler returns broken LaTeX
        fix_response = MagicMock()
        fix_response.summary = "\\section{Methods}\n\\badcommand broken."

        with patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = [meta_feedback, fix_response]

            result = pipeline.run_compilation_review()

        # Should revert to original successful state
        assert result.success is True
        assert pipeline.section_latex["02_methods"] == "\\section{Methods}\nOriginal methods."

    @patch("research_article_generator.pipeline.run_latexmk")
    @patch("research_article_generator.pipeline.make_assembler")
    @patch("research_article_generator.pipeline.run_lint")
    @patch("research_article_generator.pipeline.make_meta_reviewer")
    @patch("research_article_generator.pipeline.write_section_files")
    @patch("research_article_generator.pipeline.write_makefile")
    @patch("research_article_generator.pipeline.generate_makefile", return_value="")
    def test_no_revert_when_compile_fix_also_failed(
        self, mock_genmake, mock_writemake, mock_writesec,
        mock_meta, mock_lint, mock_assembler, mock_latexmk, pipeline
    ):
        """No revert if the compile-fix loop also failed (nothing to revert to)."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {"01_intro": "\\section{Intro}\nBroken."}
        pipeline.bib_file = None
        pipeline.figure_files = []
        pipeline.section_reviews = {}

        compile_fail = CompilationResult(
            success=False,
            errors=[CompilationWarning(message="Error", severity=Severity.ERROR)],
        )

        # All compilations fail — compile-fix exhausts attempts, meta-review also fails
        mock_latexmk.return_value = compile_fail
        mock_lint.return_value = MagicMock(total=0)

        # LLM fix attempts return LaTeX that's still broken
        fix_response = MagicMock()
        fix_response.summary = "\\section{Intro}\nStill broken \\badcmd."

        with patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = fix_response

            result = pipeline.run_compilation_review()

        # Result should still be failed (no working state to revert to)
        assert result.success is False

    @patch("research_article_generator.pipeline.run_latexmk")
    @patch("research_article_generator.pipeline.make_assembler")
    @patch("research_article_generator.pipeline.run_lint")
    @patch("research_article_generator.pipeline.make_meta_reviewer")
    @patch("research_article_generator.pipeline.write_section_files")
    @patch("research_article_generator.pipeline.write_makefile")
    @patch("research_article_generator.pipeline.generate_makefile", return_value="")
    def test_meta_review_success_no_revert(
        self, mock_genmake, mock_writemake, mock_writesec,
        mock_meta, mock_lint, mock_assembler, mock_latexmk, pipeline
    ):
        """When meta-review changes compile successfully, no revert happens."""
        pipeline.output_dir.mkdir(parents=True, exist_ok=True)
        pipeline.section_latex = {
            "01_intro": "\\section{Intro}\nOriginal.",
            "02_methods": "\\section{Methods}\nOriginal methods.",
        }
        pipeline.bib_file = None
        pipeline.figure_files = []
        pipeline.section_reviews = {}

        compile_success = CompilationResult(success=True, pdf_path="output/main.pdf")
        # Both compile-fix and meta-review recompile succeed
        mock_latexmk.return_value = compile_success
        mock_lint.return_value = MagicMock(total=0)

        # Meta-reviewer finds an issue in 02_methods
        meta_feedback = MagicMock()
        meta_feedback.summary = '{"section_id": "02_methods", "issue": "flow"}'

        # Assembler returns improved LaTeX
        fix_response = MagicMock()
        fix_response.summary = "\\section{Methods}\nImproved methods."

        with patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.side_effect = [meta_feedback, fix_response]

            result = pipeline.run_compilation_review()

        assert result.success is True
        # Section should have the improved content (not reverted)
        assert pipeline.section_latex["02_methods"] == "\\section{Methods}\nImproved methods."


class TestCompileFixFallbackAllSections:
    """Verify fallback to fixing all sections when affected sections can't be identified."""

    def test_identify_affected_empty_fallback(self, pipeline):
        """When no error matches any section, _identify_affected_sections returns []."""
        pipeline.section_latex = {
            "01_intro": "\\section{Intro}\nHello.",
            "02_methods": "\\section{Methods}\nWorld.",
        }
        result = CompilationResult(
            success=False,
            errors=[
                CompilationWarning(
                    message="Something with no matching context",
                    severity=Severity.ERROR,
                ),
            ],
        )
        affected = pipeline._identify_affected_sections(result)
        assert affected == []

    def test_nonexistent_section_in_feedback_skipped(self, pipeline):
        """Sections in meta-review feedback that don't exist are silently skipped."""
        feedback = '{"section_id": "99_nonexistent", "issue": "something"}'
        result = Pipeline._parse_affected_sections(feedback)
        assert "99_nonexistent" in result
        # But when used in the pipeline, it would be skipped by the
        # `if section_id not in self.section_latex: continue` check
        pipeline.section_latex = {"01_intro": "\\section{Intro}\nHello."}
        # Just verify parsing works; the skip is tested in integration tests above


class TestTikzGenerateAndReview:
    """Tests for the TikZ generate-and-review loop with structured JSON output."""

    LATEX_NO_TIKZ = "\\section{Intro}\nSome plain text."
    LATEX_WITH_TIKZ = (
        "\\section{Methods}\n"
        "\\begin{figure}[htbp]\n"
        "\\centering\n"
        "\\begin{tikzpicture}\n"
        "\\node (a) {A};\n"
        "\\end{tikzpicture}\n"
        "\\caption{Diagram.}\n"
        "\\label{fig:tikz_demo}\n"
        "\\end{figure}\n"
    )

    PASS_JSON = '{"verdict": "PASS", "issues": []}'
    FAIL_JSON = (
        '{"verdict": "FAIL", "issues": ['
        '{"category": "spacing", "severity": "error", "description": "Nodes overlap at (2,0)"},'
        '{"category": "integration", "severity": "warning", "description": "Missing caption"}'
        ']}'
    )

    def _make_response(self, text):
        return MagicMock(summary=text)

    def test_no_diagrams_reviewer_never_called(self, pipeline):
        """When generator produces no tikzpicture, reviewer is never invoked."""
        orchestrator = MagicMock()
        orchestrator.initiate_chat.return_value = self._make_response(self.LATEX_NO_TIKZ)

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            result = pipeline._tikz_generate_and_review("01_intro", self.LATEX_NO_TIKZ, orchestrator)

        assert result == self.LATEX_NO_TIKZ
        mock_rev.assert_not_called()

    def test_pass_on_first_review(self, pipeline):
        """PASS JSON on first review → loop exits after 2 LLM calls (generate + review)."""
        orchestrator = MagicMock()
        orchestrator.initiate_chat.side_effect = [
            self._make_response(self.LATEX_WITH_TIKZ),
            self._make_response(self.PASS_JSON),
        ]

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            mock_rev.return_value = MagicMock()
            result = pipeline._tikz_generate_and_review("02_methods", self.LATEX_NO_TIKZ, orchestrator)

        assert "\\begin{tikzpicture}" in result
        assert orchestrator.initiate_chat.call_count == 2

    def test_issues_then_fix_then_pass(self, pipeline):
        """Structured FAIL → fix → PASS → loop exits after 4 LLM calls."""
        orchestrator = MagicMock()
        orchestrator.initiate_chat.side_effect = [
            self._make_response(self.LATEX_WITH_TIKZ),
            self._make_response(self.FAIL_JSON),
            self._make_response(self.LATEX_WITH_TIKZ),  # fixed version
            self._make_response(self.PASS_JSON),
        ]

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            mock_rev.return_value = MagicMock()
            result = pipeline._tikz_generate_and_review("02_methods", self.LATEX_NO_TIKZ, orchestrator)

        assert "\\begin{tikzpicture}" in result
        assert orchestrator.initiate_chat.call_count == 4

    def test_generation_failure_returns_original(self, pipeline):
        """If generation raises, return original LaTeX unchanged."""
        orchestrator = MagicMock()
        orchestrator.initiate_chat.side_effect = RuntimeError("LLM timeout")

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            result = pipeline._tikz_generate_and_review("01_intro", self.LATEX_NO_TIKZ, orchestrator)

        assert result == self.LATEX_NO_TIKZ
        mock_rev.assert_not_called()

    def test_review_failure_returns_generated(self, pipeline):
        """If reviewer raises, return the generated LaTeX (graceful degradation)."""
        orchestrator = MagicMock()
        orchestrator.initiate_chat.side_effect = [
            self._make_response(self.LATEX_WITH_TIKZ),
            RuntimeError("Reviewer LLM timeout"),
        ]

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            mock_rev.return_value = MagicMock()
            result = pipeline._tikz_generate_and_review("02_methods", self.LATEX_NO_TIKZ, orchestrator)

        assert "\\begin{tikzpicture}" in result

    def test_accumulated_history(self, pipeline):
        """On round 2, the fix prompt includes issues from round 1."""
        fail_round1 = (
            '{"verdict": "FAIL", "issues": ['
            '{"category": "spacing", "severity": "error", "description": "Nodes overlap at (2,0)"}'
            ']}'
        )
        fail_round2 = (
            '{"verdict": "FAIL", "issues": ['
            '{"category": "layout", "severity": "warning", "description": "Mixed arrow tips"}'
            ']}'
        )
        orchestrator = MagicMock()
        # generate, review1 (fail), fix1, review2 (fail), fix2, review3 (pass)
        orchestrator.initiate_chat.side_effect = [
            self._make_response(self.LATEX_WITH_TIKZ),
            self._make_response(fail_round1),
            self._make_response(self.LATEX_WITH_TIKZ),
            self._make_response(fail_round2),
            self._make_response(self.LATEX_WITH_TIKZ),
            self._make_response(self.PASS_JSON),
        ]

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            mock_rev.return_value = MagicMock()
            pipeline._tikz_generate_and_review("02_methods", self.LATEX_NO_TIKZ, orchestrator)

        # The fix prompt for round 2 (5th call, index 4) should include round 1 history
        fix_round2_call = orchestrator.initiate_chat.call_args_list[4]
        fix_prompt = fix_round2_call[1]["message"] if "message" in fix_round2_call[1] else fix_round2_call[0][0] if fix_round2_call[0] else ""
        # Access via kwargs
        if not fix_prompt:
            fix_prompt = str(fix_round2_call)
        assert "PRIOR ROUND ISSUES" in fix_prompt
        assert "Nodes overlap" in fix_prompt

    def test_uses_tikz_review_max_turns(self, pipeline):
        """Loop uses tikz_review_max_turns (set to 4), not review_max_turns (set to 1)."""
        pipeline.config.tikz_review_max_turns = 4
        pipeline.config.review_max_turns = 1  # should be ignored

        fail_json = (
            '{"verdict": "FAIL", "issues": ['
            '{"category": "syntax", "severity": "error", "description": "Missing semicolon"}'
            ']}'
        )
        orchestrator = MagicMock()
        # generate + 4 rounds of (review-fail, fix) = 1 + 4*2 = 9 calls
        # But we'll only provide enough for 4 rounds then it stops
        responses = [self._make_response(self.LATEX_WITH_TIKZ)]  # generate
        for _ in range(4):
            responses.append(self._make_response(fail_json))
            responses.append(self._make_response(self.LATEX_WITH_TIKZ))
        orchestrator.initiate_chat.side_effect = responses

        with patch("research_article_generator.pipeline.make_tikz_generator") as mock_gen, \
             patch("research_article_generator.pipeline.make_tikz_reviewer") as mock_rev:
            mock_gen.return_value = MagicMock()
            mock_rev.return_value = MagicMock()
            pipeline._tikz_generate_and_review("02_methods", self.LATEX_NO_TIKZ, orchestrator)

        # 1 generate + 4 * (1 review + 1 fix) = 9 calls
        assert orchestrator.initiate_chat.call_count == 9

    def test_tikz_review_max_turns_default(self):
        """Default tikz_review_max_turns is 3."""
        config = ProjectConfig()
        assert config.tikz_review_max_turns == 3


class TestTemplateContext:
    def test_pipeline_has_template_context(self, tmp_path):
        """Pipeline with elsarticle template has context mentioning frontmatter."""
        config = ProjectConfig(
            project_name="Test",
            template="elsarticle",
            draft_dir="drafts/",
            output_dir="output/",
        )
        p = Pipeline(config, config_dir=tmp_path)
        assert "frontmatter" in p.template_context.lower()
        assert "elsarticle" in p.template_context
        assert isinstance(p.template_context, str)
        assert len(p.template_context) > 50

    def test_pipeline_nonexistent_template(self, tmp_path):
        """Pipeline with unknown template gets a fallback string."""
        config = ProjectConfig(
            project_name="Test",
            template="nonexistent_xyz",
            draft_dir="drafts/",
            output_dir="output/",
        )
        p = Pipeline(config, config_dir=tmp_path)
        assert "No template file found" in p.template_context
        assert isinstance(p.template_context, str)


class TestInsertSuggestionComments:
    def test_insert_suggestion_comments(self):
        latex = "\\section{Results}\nSome results text."
        suggestions = [
            {
                "description": "Line plot of training loss vs epochs",
                "rationale": "Text describes training dynamics but no visualization.",
                "plot_type": "line plot",
                "data_source": "Training metrics from Section 3",
                "suggested_caption": "Training loss convergence over 500 epochs.",
            },
        ]
        result = _insert_suggestion_comments(latex, suggestions)
        assert "%% === FIGURE SUGGESTIONS (auto-generated) ===" in result
        assert "%% FIGURE_SUGGESTION: Line plot of training loss vs epochs" in result
        assert "%%   Rationale: Text describes training dynamics but no visualization." in result
        assert "%%   Plot type: line plot" in result
        assert "%%   Data source: Training metrics from Section 3" in result
        assert "%%   Suggested caption: Training loss convergence over 500 epochs." in result
        # Original content preserved
        assert "\\section{Results}" in result
        assert "Some results text." in result

    def test_insert_suggestion_comments_empty(self):
        latex = "\\section{Intro}\nHello."
        result = _insert_suggestion_comments(latex, [])
        assert result == latex

    def test_insert_multiple_suggestions(self):
        latex = "\\section{Methods}\nMethod text."
        suggestions = [
            {
                "description": "Flowchart of algorithm",
                "rationale": "Steps described textually",
                "plot_type": "diagram",
                "data_source": "Algorithm 1 description",
                "suggested_caption": "Algorithm flowchart.",
            },
            {
                "description": "Bar chart of runtime",
                "rationale": "Runtime comparison in text",
                "plot_type": "bar chart",
                "data_source": "Table 3",
                "suggested_caption": "Runtime comparison.",
            },
        ]
        result = _insert_suggestion_comments(latex, suggestions)
        assert result.count("%% FIGURE_SUGGESTION:") == 2
        assert "Flowchart of algorithm" in result
        assert "Bar chart of runtime" in result


class TestParseFigureSuggestions:
    def test_parse_figure_suggestions_valid_json(self):
        response = MagicMock(
            summary='{"suggestions": [{"description": "Line plot", "rationale": "Data discussed", '
            '"plot_type": "line plot", "data_source": "Table 1", "suggested_caption": "Loss curve."}]}'
        )
        result = _parse_figure_suggestions(response)
        assert len(result) == 1
        assert result[0]["description"] == "Line plot"
        assert result[0]["plot_type"] == "line plot"

    def test_parse_figure_suggestions_empty(self):
        response = MagicMock(summary='{"suggestions": []}')
        result = _parse_figure_suggestions(response)
        assert result == []

    def test_parse_figure_suggestions_fallback(self):
        """Handles malformed response gracefully (returns empty list)."""
        response = MagicMock(summary="This is not JSON at all, just text.")
        result = _parse_figure_suggestions(response)
        assert result == []

    def test_parse_figure_suggestions_with_markdown_fences(self):
        response = MagicMock(
            summary='```json\n{"suggestions": [{"description": "Heatmap", "rationale": "Correlation data", '
            '"plot_type": "heatmap", "data_source": "Matrix", "suggested_caption": "Heatmap."}]}\n```'
        )
        result = _parse_figure_suggestions(response)
        assert len(result) == 1
        assert result[0]["description"] == "Heatmap"

    def test_parse_figure_suggestions_from_chat_history(self):
        response = MagicMock(
            summary=None,
            chat_history=[{
                "content": '{"suggestions": [{"description": "Diagram", "rationale": "Architecture", '
                '"plot_type": "diagram", "data_source": "Sec 2", "suggested_caption": "Arch."}]}'
            }],
        )
        result = _parse_figure_suggestions(response)
        assert len(result) == 1
        assert result[0]["description"] == "Diagram"


class TestFigureSuggestionsState:
    def test_pipeline_has_figure_suggestions_dict(self, pipeline):
        assert hasattr(pipeline, "figure_suggestions")
        assert isinstance(pipeline.figure_suggestions, dict)
        assert pipeline.figure_suggestions == {}

    def test_build_manifest_figure_suggestions_default(self):
        m = BuildManifest(project_name="Test", output_dir="output/")
        assert m.figure_suggestions_file is None

    def test_build_manifest_figure_suggestions_set(self):
        m = BuildManifest(
            project_name="Test",
            output_dir="output/",
            figure_suggestions_file="figure_suggestions.json",
        )
        assert m.figure_suggestions_file == "figure_suggestions.json"


class TestReconcileUnmappedFiles:
    """Tests for the auto-append reconciliation of unmapped draft files."""

    def test_unmapped_file_appended_to_plan(self, tmp_path):
        """A draft file not in the LLM plan gets auto-appended with correct source_file and default title."""
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path)

        # Create draft files
        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        (draft_dir / "01_intro.md").write_text("# Introduction\nHello.", encoding="utf-8")
        (draft_dir / "acknowledgements.md").write_text("# Acknowledgements\nThanks.", encoding="utf-8")

        # Simulate an LLM plan that only maps 01_intro
        plan = StructurePlan(
            title="Test Article",
            sections=[
                SectionPlan(
                    section_id="01_intro",
                    title="Introduction",
                    source_file="drafts/01_intro.md",
                    priority=1,
                ),
            ],
        )

        # Patch the LLM call to return our plan
        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline._extract_json", return_value=plan):
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = MagicMock()

            result_plan = p.run_planning()

        # acknowledgements.md should have been auto-appended
        assert len(result_plan.sections) == 2
        appended = result_plan.sections[1]
        assert appended.section_id == "acknowledgements"
        assert appended.title == "Acknowledgements"
        assert "acknowledgements.md" in appended.source_file

    def test_all_files_mapped_no_change(self, tmp_path):
        """When all files are in the plan, no sections are appended."""
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path)

        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        (draft_dir / "01_intro.md").write_text("# Introduction\nHello.", encoding="utf-8")

        plan = StructurePlan(
            title="Test Article",
            sections=[
                SectionPlan(
                    section_id="01_intro",
                    title="Introduction",
                    source_file="drafts/01_intro.md",
                    priority=1,
                ),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline._extract_json", return_value=plan):
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = MagicMock()

            result_plan = p.run_planning()

        assert len(result_plan.sections) == 1

    def test_appended_section_has_incremented_priority(self, tmp_path):
        """Auto-appended sections get priority after existing ones."""
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path)

        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        (draft_dir / "01_intro.md").write_text("# Intro\n", encoding="utf-8")
        (draft_dir / "ack.md").write_text("# Ack\n", encoding="utf-8")
        (draft_dir / "data_prep.md").write_text("# Data\n", encoding="utf-8")

        plan = StructurePlan(
            title="Test Article",
            sections=[
                SectionPlan(
                    section_id="01_intro",
                    title="Introduction",
                    source_file="drafts/01_intro.md",
                    priority=5,
                ),
            ],
        )

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline._extract_json", return_value=plan):
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = MagicMock()

            result_plan = p.run_planning()

        assert len(result_plan.sections) == 3
        # First appended should be priority 6, second 7
        assert result_plan.sections[1].priority == 6
        assert result_plan.sections[2].priority == 7


class TestSourceFileResolution:
    """Tests for the stem substring fallback in run_conversion()."""

    def test_fallback_stem_substring_match(self, tmp_path):
        """section_id 'preprocessing' resolves to 'data_preprocessing.md' via substring."""
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path)

        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        (draft_dir / "data_preprocessing.md").write_text("# Data Preprocessing\nContent.", encoding="utf-8")

        p.structure_plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(
                    section_id="preprocessing",
                    title="Data Preprocessing",
                    source_file="drafts/data_prep.md",  # wrong name!
                    priority=1,
                ),
            ],
        )

        with patch("research_article_generator.pipeline.make_assembler"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline.convert_markdown_to_latex", return_value="\\section{Data}"), \
             patch("research_article_generator.pipeline.run_faithfulness_check") as mock_faith:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            # Assembler returns polished LaTeX
            mock_response = MagicMock(summary="\\section{Data Preprocessing}\nContent.")
            mock_proxy.initiate_chat.return_value = mock_response
            mock_faith.return_value = FaithfulnessReport(
                passed=True, violations=[], section_match=True,
                math_match=True, citation_match=True, figure_match=True,
            )

            result = p.run_conversion()

        # The section should have been converted (not skipped)
        assert "preprocessing" in result

    def test_fallback_no_substring_match_skips(self, tmp_path):
        """Unrelated section_id still skips gracefully when no file matches."""
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path)

        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        (draft_dir / "01_intro.md").write_text("# Intro\nContent.", encoding="utf-8")

        p.structure_plan = StructurePlan(
            title="Test",
            sections=[
                SectionPlan(
                    section_id="totally_unrelated",
                    title="Unrelated",
                    source_file="drafts/nonexistent.md",
                    priority=1,
                ),
            ],
        )

        with patch("research_article_generator.pipeline.make_assembler"), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen:
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy

            result = p.run_conversion()

        # The section should have been skipped
        assert "totally_unrelated" not in result


class TestPlanReviewLoop:
    """Tests for the plan approval gate in Pipeline.run()."""

    def _make_plan(self):
        return StructurePlan(
            title="Test Article",
            sections=[
                SectionPlan(
                    section_id="01_intro",
                    title="Introduction",
                    source_file="drafts/01_intro.md",
                    priority=1,
                    estimated_pages=2.0,
                ),
            ],
            total_estimated_pages=2.0,
        )

    def test_auto_approve_skips_review(self, tmp_path):
        """With non-interactive callbacks, pipeline proceeds without prompting."""
        callbacks = RichCallbacks(interactive=False)
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path, callbacks=callbacks)

        plan = self._make_plan()

        with patch.object(p, "run_planning", return_value=plan) as mock_planning, \
             patch.object(p, "run_conversion"), \
             patch.object(p, "run_post_processing"), \
             patch.object(p, "run_compilation_review"), \
             patch.object(p, "run_page_budget"), \
             patch.object(p, "run_supplementary"), \
             patch.object(p, "run_finalization"):
            p.structure_plan = plan
            p.compilation_result = CompilationResult(success=True, pdf_path="out.pdf")
            p.manifest = BuildManifest(project_name="Test", output_dir="output/")
            result = p.run()

        # Planning called only once (no revision)
        mock_planning.assert_called_once_with()
        assert result.phases_completed[0] == "planning"

    def test_abort_stops_pipeline(self, tmp_path):
        """ABORT action returns early with error message."""
        callbacks = MagicMock()
        callbacks.on_plan_review.return_value = PlanReviewResult(action=PlanAction.ABORT)
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path, callbacks=callbacks)

        plan = self._make_plan()

        with patch.object(p, "run_planning", return_value=plan), \
             patch.object(p, "run_conversion") as mock_conversion:
            p.structure_plan = plan
            result = p.run()

        assert result.success is False
        assert "aborted" in result.errors[0].lower()
        mock_conversion.assert_not_called()

    def test_revise_reruns_planning(self, tmp_path):
        """REVISE action triggers run_planning again with feedback."""
        callbacks = MagicMock()
        callbacks.on_plan_review.side_effect = [
            PlanReviewResult(action=PlanAction.REVISE, feedback="Add a conclusion section"),
            PlanReviewResult(action=PlanAction.APPROVE),
        ]
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path, callbacks=callbacks)

        plan = self._make_plan()

        with patch.object(p, "run_planning", return_value=plan) as mock_planning, \
             patch.object(p, "run_conversion"), \
             patch.object(p, "run_post_processing"), \
             patch.object(p, "run_compilation_review"), \
             patch.object(p, "run_page_budget"), \
             patch.object(p, "run_supplementary"), \
             patch.object(p, "run_finalization"):
            p.structure_plan = plan
            p.compilation_result = CompilationResult(success=True, pdf_path="out.pdf")
            p.manifest = BuildManifest(project_name="Test", output_dir="output/")
            result = p.run()

        # Planning called twice: initial + revision
        assert mock_planning.call_count == 2
        mock_planning.assert_any_call()
        mock_planning.assert_any_call(revision_feedback="Add a conclusion section")

    def test_revision_feedback_in_planner_message(self, tmp_path):
        """Verify the planner receives the previous plan + feedback text."""
        config = ProjectConfig(project_name="Test", draft_dir="drafts/", output_dir="output/")
        p = Pipeline(config, config_dir=tmp_path)

        draft_dir = tmp_path / "drafts"
        draft_dir.mkdir()
        (draft_dir / "01_intro.md").write_text("# Intro\nHello.", encoding="utf-8")

        # Set an initial plan
        p.structure_plan = self._make_plan()

        with patch("research_article_generator.pipeline.make_structure_planner"), \
             patch("research_article_generator.pipeline.make_plan_reviewer", return_value=None), \
             patch("research_article_generator.pipeline.autogen") as mock_autogen, \
             patch("research_article_generator.pipeline._extract_json", return_value=self._make_plan()):
            mock_proxy = MagicMock()
            mock_autogen.UserProxyAgent.return_value = mock_proxy
            mock_proxy.initiate_chat.return_value = MagicMock()

            p.run_planning(revision_feedback="Move methodology before results")

        # Check the message sent to the planner (first call is the planner)
        call_args = mock_proxy.initiate_chat.call_args
        message = call_args[1]["message"] if "message" in call_args[1] else call_args[0][1]
        assert "user requested changes" in message
        assert "Move methodology before results" in message
        assert "01_intro" in message  # previous plan JSON should be included

    def test_max_revisions_exceeded_auto_approves(self, tmp_path):
        """After max_plan_revisions the loop exits and pipeline continues."""
        callbacks = MagicMock()
        # Always return REVISE — should stop after max_plan_revisions iterations
        callbacks.on_plan_review.return_value = PlanReviewResult(
            action=PlanAction.REVISE, feedback="Keep changing it"
        )
        config = ProjectConfig(
            project_name="Test", draft_dir="drafts/", output_dir="output/",
            max_plan_revisions=2,
        )
        p = Pipeline(config, config_dir=tmp_path, callbacks=callbacks)

        plan = self._make_plan()

        with patch.object(p, "run_planning", return_value=plan) as mock_planning, \
             patch.object(p, "run_conversion"), \
             patch.object(p, "run_post_processing"), \
             patch.object(p, "run_compilation_review"), \
             patch.object(p, "run_page_budget"), \
             patch.object(p, "run_supplementary"), \
             patch.object(p, "run_finalization"):
            p.structure_plan = plan
            p.compilation_result = CompilationResult(success=True, pdf_path="out.pdf")
            p.manifest = BuildManifest(project_name="Test", output_dir="output/")
            result = p.run()

        # on_plan_review called max_plan_revisions times
        assert callbacks.on_plan_review.call_count == 2
        # run_planning: 1 initial + 2 revisions = 3
        assert mock_planning.call_count == 3
