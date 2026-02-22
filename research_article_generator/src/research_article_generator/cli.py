"""CLI entry point using Hydra.

Usage examples:
  rag --config-dir examples/cmame_example --config-name config mode=run no_approve=true
  rag --config-dir examples/cmame_example --config-name config mode=plan
  rag mode=compile output_dir=output/ engine=xelatex
  rag --config-dir . --config-name config mode=validate
  rag --config-dir . --config-name config mode=convert_section section_file=drafts/01_intro.md section_output=out.tex
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import hydra
from omegaconf import DictConfig, OmegaConf

from ._hydra_conf import CLI_ONLY_KEYS, register_configs
from .config import apply_azure_fallbacks
from .logging_config import RichCallbacks, console, setup_logging
from .models import ProjectConfig

register_configs()

# ---------------------------------------------------------------------------
# Hydra DictConfig → Pydantic ProjectConfig bridge
# ---------------------------------------------------------------------------


def _to_project_config(cfg: DictConfig) -> ProjectConfig:
    """Convert a Hydra *DictConfig* to a Pydantic ``ProjectConfig``.

    CLI-only keys (``mode``, ``verbose``, etc.) are stripped before validation.
    Azure credential env-var fallbacks are applied afterwards.
    """
    container: dict[str, Any] = OmegaConf.to_container(cfg, resolve=True)  # type: ignore[assignment]
    for key in CLI_ONLY_KEYS:
        container.pop(key, None)
    config = ProjectConfig.model_validate(container)
    return apply_azure_fallbacks(config)


def _get_config_dir() -> Path:
    """Extract ``--config-dir`` from *sys.argv* (before Hydra consumes it).

    Falls back to the current working directory.
    """
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

    if cfg.get("output_dir") is not None:
        config.output_dir = cfg.output_dir

    from .pipeline import Pipeline

    callbacks = RichCallbacks(interactive=not cfg.no_approve)
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    console.print("[bold]Starting full pipeline...[/]")
    result = pipeline.run()

    if result.success:
        console.print("\n[bold green]Pipeline completed successfully![/]")
        if result.manifest:
            console.print(f"  Output: {result.manifest.output_dir}")
            if result.manifest.pdf_file:
                console.print(f"  PDF: {result.manifest.pdf_file}")
            console.print(f"  Pages: {result.manifest.page_count or 'unknown'}")
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

    structure = pipeline.run_plan_only()
    console.print("\n[bold]Structure Plan:[/]")
    console.print(f"  Title: {structure.title}")
    console.print(f"  Sections: {len(structure.sections)}")
    for s in structure.sections:
        console.print(f"    - {s.section_id}: {s.title} (~{s.estimated_pages} pages)")
    console.print(f"  Total estimated pages: {structure.total_estimated_pages}")
    if structure.page_budget:
        console.print(f"  Budget: {structure.page_budget} pages ({structure.budget_status})")


def _compile_mode(cfg: DictConfig) -> None:
    from .tools.compiler import run_latexmk

    output_dir = cfg.get("output_dir", "output/")
    engine = cfg.get("engine", "pdflatex")

    result = run_latexmk(output_dir, engine)
    if result.success:
        console.print(f"[green]Compilation successful: {result.pdf_path}[/]")
        if result.page_count:
            console.print(f"  Pages: {result.page_count}")
    else:
        console.print("[red]Compilation failed.[/]")
        for err in result.errors:
            console.print(f"  [red]L{err.line or '?'}: {err.message}[/]")
        sys.exit(1)


def _validate_mode(cfg: DictConfig) -> None:
    config = _to_project_config(cfg)
    config_dir = _get_config_dir()

    if cfg.get("output_dir") is not None:
        config.output_dir = cfg.output_dir

    from .pipeline import Pipeline

    callbacks = RichCallbacks()
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    report = pipeline.run_validate_only()

    if report.passed:
        console.print("[bold green]Faithfulness check PASSED[/]")
    else:
        console.print("[bold red]Faithfulness check FAILED[/]")

    console.print(f"  Section match: {'OK' if report.section_match else 'FAIL'}")
    console.print(f"  Math match: {'OK' if report.math_match else 'FAIL'}")
    console.print(f"  Citation match: {'OK' if report.citation_match else 'FAIL'}")
    console.print(f"  Figure match: {'OK' if report.figure_match else 'FAIL'}")

    if report.violations:
        console.print(f"\n  Violations ({len(report.violations)}):")
        for v in report.violations:
            console.print(f"    [{v.severity.value}] {v.issue}")
            if v.recommendation:
                console.print(f"      → {v.recommendation}")

    if not report.passed:
        sys.exit(1)


def _convert_section_mode(cfg: DictConfig) -> None:
    config = _to_project_config(cfg)
    config_dir = _get_config_dir()

    section_file = cfg.get("section_file")
    section_output = cfg.get("section_output")

    if not section_file:
        console.print("[red]section_file is required for convert_section mode[/]")
        sys.exit(1)

    from .pipeline import Pipeline

    callbacks = RichCallbacks()
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    latex = pipeline.run_convert_section(section_file)

    if section_output:
        Path(section_output).write_text(latex, encoding="utf-8")
        console.print(f"[green]Written to {section_output}[/]")
    else:
        console.print(latex)


_MODE_DISPATCH: dict[str, Any] = {
    "run": _run_mode,
    "plan": _plan_mode,
    "compile": _compile_mode,
    "validate": _validate_mode,
    "convert_section": _convert_section_mode,
}


# ---------------------------------------------------------------------------
# Hydra entry point
# ---------------------------------------------------------------------------

_PACKAGE_CONF = str(Path(__file__).resolve().parent / "conf")


@hydra.main(config_path="conf", config_name="config", version_base=None)
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
