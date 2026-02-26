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
    FeasibilityItem,
    FeasibilityReport,
    GapItem,
    GapReport,
    InfrastructureConfig,
    ModelConfig,
    Opportunity,
    OpportunityReport,
    OpportunitySelection,
    OpportunitySelectionAction,
    PipelinePhase,
    PipelineResult,
    PlanAction,
    PlanReviewResult,
    ProjectConfig,
    ReviewFeedback,
    Severity,
    SplitDecision,
    SupplementaryClassification,
    SupplementaryPlan,
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

    def test_with_split_decision(self):
        decision = SplitDecision(action="ok", current_pages=5, budget_pages=6)
        result = PipelineResult(success=True, split_decision=decision)
        assert result.split_decision is not None
        assert result.split_decision.action == "ok"


class TestPlanAction:
    def test_values(self):
        assert PlanAction.APPROVE == "approve"
        assert PlanAction.REVISE == "revise"
        assert PlanAction.ABORT == "abort"


class TestPlanReviewResult:
    def test_defaults(self):
        review = PlanReviewResult()
        assert review.action == PlanAction.APPROVE
        assert review.feedback == ""

    def test_revise(self):
        review = PlanReviewResult(action=PlanAction.REVISE, feedback="Add more sections")
        assert review.action == PlanAction.REVISE
        assert review.feedback == "Add more sections"


class TestSupplementaryClassification:
    def test_creation(self):
        cls = SupplementaryClassification(
            section_id="appendix_data",
            placement="supplementary",
            reasoning="Extended data tables",
            priority=5,
            estimated_pages=2.0,
        )
        assert cls.section_id == "appendix_data"
        assert cls.placement == "supplementary"
        assert cls.priority == 5


class TestSupplementaryPlan:
    def test_defaults(self):
        plan = SupplementaryPlan()
        assert plan.mode == "appendix"
        assert plan.main_sections == []
        assert plan.supplementary_sections == []

    def test_full_plan(self):
        plan = SupplementaryPlan(
            mode="standalone",
            main_sections=["situation", "approach"],
            supplementary_sections=["data_schema"],
            classifications=[
                SupplementaryClassification(
                    section_id="situation",
                    placement="main",
                    reasoning="Core",
                ),
                SupplementaryClassification(
                    section_id="data_schema",
                    placement="supplementary",
                    reasoning="Detail",
                ),
            ],
            estimated_main_pages=4.0,
            estimated_supp_pages=2.0,
        )
        assert len(plan.classifications) == 2
        assert plan.estimated_main_pages == 4.0


class TestSplitDecision:
    def test_ok(self):
        decision = SplitDecision(action="ok", current_pages=5, budget_pages=6)
        assert decision.action == "ok"
        assert decision.supplementary_plan is None

    def test_split_with_plan(self):
        plan = SupplementaryPlan(
            mode="appendix",
            main_sections=["situation"],
            supplementary_sections=["extras"],
        )
        decision = SplitDecision(
            action="split",
            current_pages=10,
            budget_pages=6,
            sections_to_move=["extras"],
            estimated_savings=4.0,
            supplementary_plan=plan,
        )
        assert decision.action == "split"
        assert decision.supplementary_plan is not None
        assert decision.supplementary_plan.mode == "appendix"

    def test_json_roundtrip(self):
        decision = SplitDecision(
            action="warn_over",
            current_pages=8,
            budget_pages=6,
            sections_to_move=["detail"],
            estimated_savings=2.0,
            recommendations="Move detail section",
        )
        json_str = decision.model_dump_json()
        parsed = SplitDecision.model_validate_json(json_str)
        assert parsed.action == "warn_over"
        assert parsed.sections_to_move == ["detail"]


class TestDesignSectionExtended:
    def test_priority_and_word_count(self):
        section = DesignSection(
            section_id="approach",
            title="Approach",
            priority=2,
            target_word_count=500,
        )
        assert section.priority == 2
        assert section.target_word_count == 500

    def test_defaults(self):
        section = DesignSection(section_id="test", title="Test")
        assert section.priority == 1
        assert section.target_word_count is None


class TestBuildManifestExtended:
    def test_supplementary_fields(self):
        manifest = BuildManifest(
            project_name="test",
            output_dir="/tmp/out",
            supplementary_tex="supplementary.tex",
            supplementary_pdf="/tmp/out/supplementary.pdf",
            supplementary_sections=["extras", "data_schema"],
        )
        assert manifest.supplementary_tex == "supplementary.tex"
        assert len(manifest.supplementary_sections) == 2

    def test_supplementary_defaults(self):
        manifest = BuildManifest(project_name="test", output_dir="/tmp/out")
        assert manifest.supplementary_tex is None
        assert manifest.supplementary_sections == []


class TestProjectConfigExtended:
    def test_supplementary_defaults(self):
        config = ProjectConfig()
        assert config.supplementary_mode == "disabled"
        assert config.supplementary_threshold == 1.3
        assert config.max_plan_revisions == 3
        assert config.words_per_page == 500

    def test_custom_supplementary(self):
        config = ProjectConfig(
            supplementary_mode="auto",
            supplementary_threshold=1.5,
            max_plan_revisions=5,
            words_per_page=400,
        )
        assert config.supplementary_mode == "auto"
        assert config.supplementary_threshold == 1.5


class TestOpportunity:
    def test_creation(self):
        opp = Opportunity(
            opportunity_id="anomaly_detection",
            title="Anomaly Detection System",
            category="anomaly_detection",
            description="Build a real-time anomaly detection system.",
            source_evidence=["Doc A", "Doc B"],
            estimated_complexity="medium",
            potential_impact="high",
        )
        assert opp.opportunity_id == "anomaly_detection"
        assert opp.title == "Anomaly Detection System"
        assert opp.potential_impact == "high"
        assert len(opp.source_evidence) == 2

    def test_defaults(self):
        opp = Opportunity(opportunity_id="test", title="Test")
        assert opp.category == ""
        assert opp.estimated_complexity == "medium"
        assert opp.potential_impact == "medium"
        assert opp.source_evidence == []

    def test_json_roundtrip(self):
        opp = Opportunity(
            opportunity_id="pred_maint",
            title="Predictive Maintenance",
            category="forecasting",
            description="Predict equipment failures.",
            estimated_complexity="high",
            potential_impact="high",
        )
        json_str = opp.model_dump_json()
        parsed = Opportunity.model_validate_json(json_str)
        assert parsed.opportunity_id == "pred_maint"
        assert parsed.category == "forecasting"


class TestOpportunityReport:
    def test_creation(self):
        report = OpportunityReport(
            opportunities=[
                Opportunity(opportunity_id="a", title="A"),
                Opportunity(opportunity_id="b", title="B"),
            ],
            summary="Two opportunities found.",
        )
        assert len(report.opportunities) == 2
        assert report.summary == "Two opportunities found."

    def test_defaults(self):
        report = OpportunityReport()
        assert report.opportunities == []
        assert report.summary == ""

    def test_json_roundtrip(self):
        report = OpportunityReport(
            opportunities=[Opportunity(opportunity_id="x", title="X")],
            summary="One opportunity.",
        )
        json_str = report.model_dump_json()
        parsed = OpportunityReport.model_validate_json(json_str)
        assert len(parsed.opportunities) == 1
        assert parsed.opportunities[0].opportunity_id == "x"


class TestOpportunitySelection:
    def test_defaults(self):
        sel = OpportunitySelection()
        assert sel.action == OpportunitySelectionAction.SELECT
        assert sel.selected_ids == []
        assert sel.custom_opportunity == ""
        assert sel.combination_note == ""

    def test_select(self):
        sel = OpportunitySelection(
            action=OpportunitySelectionAction.SELECT,
            selected_ids=["anomaly_detection", "pred_maint"],
            combination_note="Combine into unified monitoring.",
        )
        assert sel.action == OpportunitySelectionAction.SELECT
        assert len(sel.selected_ids) == 2
        assert sel.combination_note == "Combine into unified monitoring."

    def test_custom(self):
        sel = OpportunitySelection(
            action=OpportunitySelectionAction.CUSTOM,
            custom_opportunity="Build an agentic AI decision support system.",
        )
        assert sel.action == OpportunitySelectionAction.CUSTOM
        assert "agentic AI" in sel.custom_opportunity

    def test_abort(self):
        sel = OpportunitySelection(action=OpportunitySelectionAction.ABORT)
        assert sel.action == OpportunitySelectionAction.ABORT

    def test_action_values(self):
        assert OpportunitySelectionAction.SELECT == "select"
        assert OpportunitySelectionAction.CUSTOM == "custom"
        assert OpportunitySelectionAction.ABORT == "abort"


class TestFeasibilityItem:
    def test_creation(self):
        item = FeasibilityItem(
            area="Data Availability",
            assessment="Sufficient data in data lake.",
            risk_level="low",
            mitigation="",
        )
        assert item.area == "Data Availability"
        assert item.risk_level == "low"

    def test_defaults(self):
        item = FeasibilityItem(area="Compute")
        assert item.assessment == ""
        assert item.risk_level == "low"
        assert item.mitigation == ""

    def test_json_roundtrip(self):
        item = FeasibilityItem(
            area="Timeline",
            assessment="Tight deadline.",
            risk_level="high",
            mitigation="Reduce scope to MVP.",
        )
        json_str = item.model_dump_json()
        parsed = FeasibilityItem.model_validate_json(json_str)
        assert parsed.area == "Timeline"
        assert parsed.risk_level == "high"
        assert parsed.mitigation == "Reduce scope to MVP."


class TestFeasibilityReport:
    def test_creation(self):
        report = FeasibilityReport(
            selected_opportunities=["anomaly_detection"],
            items=[
                FeasibilityItem(area="Data", assessment="OK", risk_level="low"),
                FeasibilityItem(area="Compute", assessment="GPU needed", risk_level="medium"),
            ],
            overall_feasible=True,
            overall_summary="Feasible with minor risks.",
            recommendations=["Provision GPU cluster early."],
        )
        assert len(report.items) == 2
        assert report.overall_feasible is True
        assert len(report.recommendations) == 1

    def test_defaults(self):
        report = FeasibilityReport()
        assert report.selected_opportunities == []
        assert report.items == []
        assert report.overall_feasible is True
        assert report.overall_summary == ""
        assert report.recommendations == []

    def test_not_feasible(self):
        report = FeasibilityReport(
            overall_feasible=False,
            overall_summary="Critical blockers identified.",
            items=[
                FeasibilityItem(
                    area="Regulatory",
                    assessment="GDPR blocks data collection.",
                    risk_level="critical",
                ),
            ],
        )
        assert report.overall_feasible is False
        assert report.items[0].risk_level == "critical"

    def test_json_roundtrip(self):
        report = FeasibilityReport(
            selected_opportunities=["a", "b"],
            items=[FeasibilityItem(area="Cost", assessment="High", risk_level="high")],
            overall_feasible=True,
            overall_summary="OK.",
            recommendations=["Optimise costs."],
        )
        json_str = report.model_dump_json()
        parsed = FeasibilityReport.model_validate_json(json_str)
        assert parsed.selected_opportunities == ["a", "b"]
        assert len(parsed.items) == 1


class TestPipelinePhaseExtended:
    def test_new_phases(self):
        assert PipelinePhase.PLAN_APPROVAL == "plan_approval"
        assert PipelinePhase.PAGE_BUDGET == "page_budget"
        assert PipelinePhase.SUPPLEMENTARY == "supplementary"
        assert PipelinePhase.OPPORTUNITY_DISCOVERY == "opportunity_discovery"
        assert PipelinePhase.FEASIBILITY_CHECK == "feasibility_check"


class TestPipelineResultExtended:
    def test_with_opportunity_fields(self):
        opp_report = OpportunityReport(
            opportunities=[Opportunity(opportunity_id="x", title="X")],
        )
        selection = OpportunitySelection(
            action=OpportunitySelectionAction.SELECT,
            selected_ids=["x"],
        )
        feas_report = FeasibilityReport(overall_feasible=True)
        result = PipelineResult(
            success=True,
            opportunity_report=opp_report,
            opportunity_selection=selection,
            feasibility_report=feas_report,
        )
        assert result.opportunity_report is not None
        assert result.opportunity_selection is not None
        assert result.feasibility_report is not None
        assert result.feasibility_report.overall_feasible is True


class TestProjectConfigOpportunity:
    def test_opportunity_defaults(self):
        config = ProjectConfig()
        assert config.max_opportunities == 5
        assert config.feasibility_max_rounds == 2

    def test_custom_opportunity_config(self):
        config = ProjectConfig(max_opportunities=10, feasibility_max_rounds=4)
        assert config.max_opportunities == 10
        assert config.feasibility_max_rounds == 4
