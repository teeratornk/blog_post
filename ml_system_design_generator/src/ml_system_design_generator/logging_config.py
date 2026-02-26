"""Rich console setup and pipeline progress helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

if TYPE_CHECKING:
    from .models import DesignPlan, PlanReviewResult, UserFeedback

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
