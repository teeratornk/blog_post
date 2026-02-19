"""Rich console setup and pipeline progress helpers."""

from __future__ import annotations

import logging
from typing import Protocol

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

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


logger = logging.getLogger("rag")


# ---------------------------------------------------------------------------
# Pipeline callbacks protocol
# ---------------------------------------------------------------------------


class PipelineCallbacks(Protocol):
    """Protocol for pipeline progress reporting."""

    def on_phase_start(self, phase: str, description: str) -> None: ...
    def on_phase_end(self, phase: str, success: bool) -> None: ...
    def on_section_start(self, section_id: str) -> None: ...
    def on_section_end(self, section_id: str) -> None: ...
    def on_compile_attempt(self, attempt: int, max_attempts: int) -> None: ...
    def on_review_round(self, round_num: int, max_rounds: int) -> None: ...
    def on_warning(self, message: str) -> None: ...
    def on_error(self, message: str) -> None: ...


class RichCallbacks:
    """Rich-based implementation of PipelineCallbacks."""

    def __init__(self) -> None:
        self._progress: Progress | None = None

    def on_phase_start(self, phase: str, description: str) -> None:
        console.rule(f"[bold blue]{phase}[/] — {description}")

    def on_phase_end(self, phase: str, success: bool) -> None:
        status = "[green]OK[/]" if success else "[red]FAILED[/]"
        console.print(f"  Phase {phase}: {status}")

    def on_section_start(self, section_id: str) -> None:
        console.print(f"  [dim]Processing section:[/] {section_id}")

    def on_section_end(self, section_id: str) -> None:
        console.print(f"  [dim]Done:[/] {section_id}")

    def on_compile_attempt(self, attempt: int, max_attempts: int) -> None:
        console.print(f"  [yellow]Compile attempt {attempt}/{max_attempts}[/]")

    def on_review_round(self, round_num: int, max_rounds: int) -> None:
        console.print(f"  [cyan]Review round {round_num}/{max_rounds}[/]")

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
