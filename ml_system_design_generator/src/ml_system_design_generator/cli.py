"""CLI entry point using Hydra.

Usage examples:
  mlsd --config-dir examples/grid_spec_example --config-name config mode=run
  mlsd --config-dir examples/grid_spec_example --config-name config mode=plan
  mlsd --config-dir examples/grid_spec_example --config-name config mode=understand
  mlsd mode=compile output_dir=output/
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Any

import hydra
from omegaconf import DictConfig, OmegaConf

from ._hydra_conf import CLI_ONLY_KEYS, register_configs
from .config import apply_azure_fallbacks
from .logging_config import RichCallbacks, console, setup_logging
from .models import ProjectConfig

register_configs()

# Suppress Hydra 1.1 deprecation warning about automatic schema matching.
# Our user configs already reference the schema explicitly via ``defaults``.
warnings.filterwarnings("ignore", category=UserWarning, message=r"(?s).*ConfigStore schema.*")

# ---------------------------------------------------------------------------
# Hydra DictConfig -> Pydantic ProjectConfig bridge
# ---------------------------------------------------------------------------


def _to_project_config(cfg: DictConfig) -> ProjectConfig:
    """Convert a Hydra DictConfig to a Pydantic ProjectConfig."""
    container: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # type: ignore[assignment]
    for key in CLI_ONLY_KEYS:
        container.pop(key, None)
    config = ProjectConfig.model_validate(container)
    return apply_azure_fallbacks(config)


def _get_config_dir() -> Path:
    """Extract --config-dir from sys.argv."""
    for i, arg in enumerate(sys.argv):
        if arg == "--config-dir" and i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1])
        if arg.startswith("--config-dir="):
            return Path(arg.split("=", 1)[1])
    return Path.cwd()


# ---------------------------------------------------------------------------
# Mode handlers
# ---------------------------------------------------------------------------


def _run_mode(cfg: DictConfig) -> None:
    config = _to_project_config(cfg)
    config_dir = _get_config_dir()

    # Interactive prompts for missing config
    if not cfg.get("no_interactive", False):
        from .prompts import run_interactive_prompts
        container: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # type: ignore[assignment]
        for key in CLI_ONLY_KEYS:
            container.pop(key, None)
        updated = run_interactive_prompts(container)
        config = ProjectConfig.model_validate(updated)
        config = apply_azure_fallbacks(config)

    from .pipeline import Pipeline

    callbacks = RichCallbacks(interactive=not cfg.get("no_approve", False))
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    console.print("[bold]Starting full pipeline...[/]")
    result = pipeline.run()

    if result.success:
        console.print("\n[bold green]Pipeline completed successfully![/]")
        if result.output_dir:
            console.print(f"  Output: {result.output_dir}")
        if result.compilation_result and result.compilation_result.pdf_path:
            console.print(f"  PDF: {result.compilation_result.pdf_path}")
            console.print(f"  Pages: {result.compilation_result.page_count or 'unknown'}")
    else:
        console.print("\n[bold red]Pipeline failed.[/]")
        for err in result.errors:
            console.print(f"  [red]{err}[/]")
        sys.exit(1)


def _plan_mode(cfg: DictConfig) -> None:
    config = _to_project_config(cfg)
    config_dir = _get_config_dir()

    from .pipeline import Pipeline

    callbacks = RichCallbacks()
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    report, plan = pipeline.run_plan_only()

    console.print("\n[bold]Understanding Report:[/]")
    console.print(f"  Documents analyzed: {len(report.documents)}")
    console.print(f"  Cross-references: {', '.join(report.cross_references) or 'none'}")
    console.print(f"  Gap confidence: {report.gap_report.confidence_score:.1%}")
    if report.gap_report.gaps:
        console.print(f"  Gaps identified: {len(report.gap_report.gaps)}")

    console.print("\n[bold]Design Plan:[/]")
    console.print(f"  Title: {plan.title}")
    console.print(f"  Style: {plan.style}")
    console.print(f"  Sections: {len(plan.sections)}")
    for s in plan.sections:
        console.print(f"    - {s.section_id}: {s.title} (~{s.estimated_pages} pages)")
    console.print(f"  Total estimated pages: {plan.total_estimated_pages}")


def _understand_mode(cfg: DictConfig) -> None:
    config = _to_project_config(cfg)
    config_dir = _get_config_dir()

    from .pipeline import Pipeline

    callbacks = RichCallbacks()
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    report = pipeline.run_understand_only()

    console.print("\n[bold]Understanding Report:[/]")
    for doc in report.documents:
        console.print(f"\n  [cyan]{doc.title}[/] ({doc.file_path})")
        console.print(f"    Topics: {', '.join(doc.key_topics)}")
        console.print(f"    Words: {doc.word_count}")
        console.print(f"    Summary: {doc.summary[:150]}...")

    console.print(f"\n  Cross-references: {', '.join(report.cross_references) or 'none'}")
    console.print(f"  Vector DB created: {report.vector_db_created}")
    if report.vector_db_created:
        console.print(f"  Total chunks: {report.total_chunks}")

    if report.gap_report.gaps:
        console.print(f"\n  [yellow]Gaps ({len(report.gap_report.gaps)}):[/]")
        for gap in report.gap_report.gaps:
            console.print(f"    [{gap.severity.value}] {gap.area}: {gap.description}")


def _compile_mode(cfg: DictConfig) -> None:
    from .tools.compiler import run_latexmk

    output_dir = cfg.get("output_dir", "output/")
    result = run_latexmk(output_dir)
    if result.success:
        console.print(f"[green]Compilation successful: {result.pdf_path}[/]")
        if result.page_count:
            console.print(f"  Pages: {result.page_count}")
    else:
        console.print("[red]Compilation failed.[/]")
        for err in result.errors:
            console.print(f"  [red]L{err.line or '?'}: {err.message}[/]")
        sys.exit(1)


_MODE_DISPATCH: dict[str, Any] = {
    "run": _run_mode,
    "plan": _plan_mode,
    "understand": _understand_mode,
    "compile": _compile_mode,
}


# ---------------------------------------------------------------------------
# Hydra entry point
# ---------------------------------------------------------------------------


@hydra.main(config_path=None, config_name="config", version_base=None)
def hydra_entry(cfg: DictConfig) -> None:
    """Hydra-managed CLI entry point."""
    setup_logging(verbose=cfg.get("verbose", False), quiet=cfg.get("quiet", False))

    mode = cfg.get("mode", "run")
    handler = _MODE_DISPATCH.get(mode)
    if handler is None:
        console.print(f"[red]Unknown mode: {mode!r}. Choose from: {', '.join(_MODE_DISPATCH)}[/]")
        sys.exit(1)

    handler(cfg)


def main() -> None:
    """Package entry point (``[project.scripts]`` target)."""
    hydra_entry()  # pylint: disable=no-value-for-parameter
