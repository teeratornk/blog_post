"""Rich console setup and pipeline progress helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

if TYPE_CHECKING:
    from .models import (
        DesignPlan,
        FeasibilityReport,
        OpportunityReport,
        OpportunitySelection,
        PlanReviewResult,
        UserFeedback,
    )

console = Console()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Configure root logger with Rich handler."""
    level = logging.DEBUG if verbose else (logging.ERROR if quiet else logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=verbose)],
        force=True,
    )


logger = logging.getLogger("mlsd")


# ---------------------------------------------------------------------------
# Pipeline callbacks protocol
# ---------------------------------------------------------------------------


class PipelineCallbacks(Protocol):
    """Protocol for pipeline progress reporting."""

    def on_phase_start(self, phase: str, description: str) -> None: ...
    def on_phase_end(self, phase: str, success: bool) -> None: ...
    def on_section_start(self, section_id: str) -> None: ...
    def on_section_end(self, section_id: str) -> None: ...
    def on_section_review(self, section_id: str, reviewer: str) -> None: ...
    def on_compile_attempt(self, attempt: int, max_attempts: int) -> None: ...
    def on_review_round(self, round_num: int, max_rounds: int) -> None: ...
    def on_plan_approval(self, plan: DesignPlan) -> PlanReviewResult: ...
    def on_plan_review(self, plan: DesignPlan) -> UserFeedback: ...
    def on_opportunity_review(self, report: OpportunityReport) -> OpportunitySelection: ...
    def on_feasibility_review(self, report: FeasibilityReport) -> PlanReviewResult: ...
    def on_warning(self, message: str) -> None: ...
    def on_error(self, message: str) -> None: ...


class RichCallbacks:
    """Rich-based implementation of PipelineCallbacks."""

    def __init__(self, *, interactive: bool = False) -> None:
        self._progress: Progress | None = None
        self.interactive = interactive

    def on_phase_start(self, phase: str, description: str) -> None:
        console.rule(f"[bold blue]{phase}[/] — {description}")

    def on_phase_end(self, phase: str, success: bool) -> None:
        status = "[green]OK[/]" if success else "[red]FAILED[/]"
        console.print(f"  Phase {phase}: {status}")

    def on_section_start(self, section_id: str) -> None:
        console.print(f"  [dim]Processing section:[/] {section_id}")

    def on_section_end(self, section_id: str) -> None:
        console.print(f"  [dim]Done:[/] {section_id}")

    def on_section_review(self, section_id: str, reviewer: str) -> None:
        console.print(f"  [cyan]Reviewing {section_id}[/] with {reviewer}")

    def on_compile_attempt(self, attempt: int, max_attempts: int) -> None:
        console.print(f"  [yellow]Compile attempt {attempt}/{max_attempts}[/]")

    def on_review_round(self, round_num: int, max_rounds: int) -> None:
        console.print(f"  [cyan]Review round {round_num}/{max_rounds}[/]")

    def on_plan_approval(self, plan: DesignPlan) -> PlanReviewResult:
        from .models import PlanAction, PlanReviewResult

        if not self.interactive:
            return PlanReviewResult(action=PlanAction.APPROVE)

        # Display plan as a Rich table with word limits and priority
        table = Table(title="Design Plan (Pre-Writing Approval)", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Section ID", style="cyan")
        table.add_column("Title")
        table.add_column("Est. Pages", justify="right")
        table.add_column("Word Limit", justify="right")
        table.add_column("Priority", justify="right")

        for i, section in enumerate(plan.sections, 1):
            word_limit = str(section.target_word_count) if section.target_word_count else "—"
            table.add_row(
                str(i),
                section.section_id,
                section.title,
                f"{section.estimated_pages:.1f}",
                word_limit,
                str(section.priority),
            )

        console.print()
        console.print(table)
        console.print(
            f"\n  Total estimated pages: [bold]{plan.total_estimated_pages:.1f}[/]"
        )
        if plan.page_budget:
            console.print(f"  Page budget: {plan.page_budget}")

        console.print()

        while True:
            choice = console.input("[bold]\\[a]pprove / \\[r]evise / \\[q]uit:[/] ").strip().lower()
            if choice in ("a", "approve"):
                return PlanReviewResult(action=PlanAction.APPROVE)
            elif choice in ("q", "quit"):
                return PlanReviewResult(action=PlanAction.ABORT)
            elif choice in ("r", "revise"):
                console.print("Enter revision feedback (empty line to finish):")
                lines: list[str] = []
                while True:
                    line = console.input("")
                    if not line:
                        break
                    lines.append(line)
                feedback = "\n".join(lines)
                return PlanReviewResult(action=PlanAction.REVISE, feedback=feedback)
            else:
                console.print("[yellow]Please enter 'a', 'r', or 'q'.[/]")

    def on_plan_review(self, plan: DesignPlan) -> UserFeedback:
        from .models import UserFeedback

        if not self.interactive:
            return UserFeedback(action="approve")

        # Display plan as a Rich table
        table = Table(title="Design Plan", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Section ID", style="cyan")
        table.add_column("Title")
        table.add_column("Est. Pages", justify="right")

        for i, section in enumerate(plan.sections, 1):
            table.add_row(
                str(i),
                section.section_id,
                section.title,
                f"{section.estimated_pages:.1f}",
            )

        console.print()
        console.print(table)
        console.print(
            f"\n  Total estimated pages: [bold]{plan.total_estimated_pages:.1f}[/]"
        )
        if plan.page_budget:
            console.print(f"  Page budget: {plan.page_budget}")

        console.print()

        while True:
            choice = console.input("[bold]\\[a]pprove / \\[r]evise / \\[q]uit:[/] ").strip().lower()
            if choice in ("a", "approve"):
                return UserFeedback(action="approve")
            elif choice in ("q", "quit"):
                return UserFeedback(action="abort")
            elif choice in ("r", "revise"):
                console.print("Enter revision feedback (empty line to finish):")
                lines: list[str] = []
                while True:
                    line = console.input("")
                    if not line:
                        break
                    lines.append(line)
                feedback = "\n".join(lines)
                return UserFeedback(action="revise", comments=feedback)
            else:
                console.print("[yellow]Please enter 'a', 'r', or 'q'.[/]")

    def on_opportunity_review(self, report: OpportunityReport) -> OpportunitySelection:
        from .models import OpportunitySelection, OpportunitySelectionAction

        if not self.interactive:
            # Auto-select the highest-impact opportunity
            best = None
            for opp in report.opportunities:
                if opp.potential_impact == "high":
                    best = opp
                    break
            if best is None and report.opportunities:
                best = report.opportunities[0]
            if best:
                return OpportunitySelection(
                    action=OpportunitySelectionAction.SELECT,
                    selected_ids=[best.opportunity_id],
                )
            return OpportunitySelection(action=OpportunitySelectionAction.ABORT)

        # Display opportunity table
        table = Table(title="ML Opportunity Discovery", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Category")
        table.add_column("Complexity", justify="center")
        table.add_column("Impact", justify="center")
        table.add_column("Evidence")

        _impact_style = {"high": "bold green", "medium": "yellow", "low": "dim"}
        _complexity_style = {"high": "red", "medium": "yellow", "low": "green"}

        for i, opp in enumerate(report.opportunities, 1):
            impact_s = _impact_style.get(opp.potential_impact, "")
            complex_s = _complexity_style.get(opp.estimated_complexity, "")
            table.add_row(
                str(i),
                opp.opportunity_id,
                opp.title,
                opp.category,
                f"[{complex_s}]{opp.estimated_complexity}[/]",
                f"[{impact_s}]{opp.potential_impact}[/]",
                ", ".join(opp.source_evidence[:2]) or "—",
            )

        console.print()
        console.print(table)
        if report.summary:
            console.print(f"\n  [dim]{report.summary}[/]")
        console.print(
            "\n  Enter a number to preview full description, or choose an action:"
        )

        while True:
            choice = (
                console.input(
                    "[bold]\\[s]elect (comma-sep #s) / \\[c]ustom / \\[q]uit:[/] "
                )
                .strip()
                .lower()
            )

            # Preview: user typed a number
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(report.opportunities):
                    opp = report.opportunities[idx]
                    console.print(f"\n  [cyan]{opp.title}[/] ({opp.opportunity_id})")
                    console.print(f"  {opp.description}")
                    console.print(
                        f"  Evidence: {', '.join(opp.source_evidence) or '—'}\n"
                    )
                else:
                    console.print("[yellow]Invalid number.[/]")
                continue

            if choice in ("q", "quit"):
                return OpportunitySelection(action=OpportunitySelectionAction.ABORT)

            if choice in ("c", "custom"):
                console.print("Describe your custom ML direction (empty line to finish):")
                lines: list[str] = []
                while True:
                    line = console.input("")
                    if not line:
                        break
                    lines.append(line)
                custom = "\n".join(lines)
                return OpportunitySelection(
                    action=OpportunitySelectionAction.CUSTOM,
                    custom_opportunity=custom,
                )

            if choice.startswith("s") or "," in choice:
                # Parse selection numbers
                nums_str = choice.lstrip("select").strip()
                if not nums_str and choice in ("s", "select"):
                    nums_str = console.input("Enter numbers (comma-separated): ").strip()
                try:
                    nums = [int(n.strip()) for n in nums_str.split(",") if n.strip()]
                except ValueError:
                    console.print("[yellow]Invalid input. Enter comma-separated numbers.[/]")
                    continue

                selected_ids: list[str] = []
                for n in nums:
                    idx = n - 1
                    if 0 <= idx < len(report.opportunities):
                        selected_ids.append(report.opportunities[idx].opportunity_id)
                    else:
                        console.print(f"[yellow]Skipping invalid number: {n}[/]")

                if not selected_ids:
                    console.print("[yellow]No valid selections. Try again.[/]")
                    continue

                combination_note = ""
                if len(selected_ids) > 1:
                    combination_note = console.input(
                        "[dim]Optional combination note (or Enter to skip):[/] "
                    ).strip()

                return OpportunitySelection(
                    action=OpportunitySelectionAction.SELECT,
                    selected_ids=selected_ids,
                    combination_note=combination_note,
                )

            console.print("[yellow]Please enter 's', 'c', 'q', or a number.[/]")

    def on_feasibility_review(self, report: FeasibilityReport) -> PlanReviewResult:
        from .models import PlanAction, PlanReviewResult

        if not self.interactive:
            if report.overall_feasible:
                return PlanReviewResult(action=PlanAction.APPROVE)
            return PlanReviewResult(action=PlanAction.ABORT)

        # Display feasibility table
        table = Table(title="Feasibility Assessment", show_lines=True)
        table.add_column("Area", style="cyan")
        table.add_column("Risk", justify="center")
        table.add_column("Assessment")
        table.add_column("Mitigation")

        _risk_style = {
            "none": "green",
            "low": "green",
            "medium": "yellow",
            "high": "red",
            "critical": "bold red",
        }

        for item in report.items:
            style = _risk_style.get(item.risk_level, "")
            table.add_row(
                item.area,
                f"[{style}]{item.risk_level}[/]",
                item.assessment,
                item.mitigation or "—",
            )

        console.print()
        console.print(table)

        verdict = "[green]FEASIBLE[/]" if report.overall_feasible else "[red]NOT FEASIBLE[/]"
        console.print(f"\n  Overall: {verdict}")
        if report.overall_summary:
            console.print(f"  {report.overall_summary}")
        if report.recommendations:
            console.print("  Recommendations:")
            for rec in report.recommendations:
                console.print(f"    - {rec}")

        console.print()

        while True:
            choice = (
                console.input(
                    "[bold]\\[a]pprove (proceed to plan) / \\[r]e-select opportunities / \\[q]uit:[/] "
                )
                .strip()
                .lower()
            )
            if choice in ("a", "approve"):
                return PlanReviewResult(action=PlanAction.APPROVE)
            elif choice in ("q", "quit"):
                return PlanReviewResult(action=PlanAction.ABORT)
            elif choice in ("r", "revise", "re-select"):
                return PlanReviewResult(action=PlanAction.REVISE)
            else:
                console.print("[yellow]Please enter 'a', 'r', or 'q'.[/]")

    def on_warning(self, message: str) -> None:
        console.print(f"  [yellow]WARNING:[/] {message}")

    def on_error(self, message: str) -> None:
        console.print(f"  [red]ERROR:[/] {message}")


def create_progress() -> Progress:
    """Create a Rich progress bar for section processing."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )
