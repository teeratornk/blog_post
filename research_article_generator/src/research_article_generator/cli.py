"""CLI entry points using Click + rich-click.

Commands:
  rag run              — Full pipeline
  rag plan             — Dry run (planning only, no LLM)
  rag convert-section  — Single section conversion (for testing)
  rag compile          — Compile only (no LLM)
  rag validate         — Validate faithfulness only
"""

from __future__ import annotations

import sys
from pathlib import Path

import rich_click as click

from .config import load_config
from .logging_config import RichCallbacks, console, setup_logging
from .pipeline import Pipeline


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Full agent logs")
@click.option("--quiet", "-q", is_flag=True, help="Errors only")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, quiet: bool) -> None:
    """Research Article LaTeX Generator — transform markdown drafts into publication-ready LaTeX."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    setup_logging(verbose=verbose, quiet=quiet)


@cli.command()
@click.option("--config", "-c", "config_path", required=True, type=click.Path(exists=True), help="Path to config.yaml")
@click.option("--output-dir", "-o", type=click.Path(), default=None, help="Override output directory")
@click.pass_context
def run(ctx: click.Context, config_path: str, output_dir: str | None) -> None:
    """Run the full pipeline."""
    config_file = Path(config_path)
    config = load_config(config_file)
    config_dir = config_file.parent

    if output_dir:
        config.output_dir = output_dir

    callbacks = RichCallbacks()
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


@cli.command()
@click.option("--config", "-c", "config_path", required=True, type=click.Path(exists=True), help="Path to config.yaml")
@click.pass_context
def plan(ctx: click.Context, config_path: str) -> None:
    """Dry run — planning only, no LLM calls."""
    config_file = Path(config_path)
    config = load_config(config_file)
    config_dir = config_file.parent

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


@cli.command("convert-section")
@click.option("--config", "-c", "config_path", required=True, type=click.Path(exists=True), help="Path to config.yaml")
@click.option("--section", "-s", required=True, type=click.Path(exists=True), help="Path to section .md file")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output .tex file (stdout if omitted)")
@click.pass_context
def convert_section(ctx: click.Context, config_path: str, section: str, output: str | None) -> None:
    """Convert a single section (for testing)."""
    config_file = Path(config_path)
    config = load_config(config_file)
    config_dir = config_file.parent

    callbacks = RichCallbacks()
    pipeline = Pipeline(config, config_dir=config_dir, callbacks=callbacks)

    latex = pipeline.run_convert_section(section)

    if output:
        Path(output).write_text(latex, encoding="utf-8")
        console.print(f"[green]Written to {output}[/]")
    else:
        console.print(latex)


@cli.command()
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True), help="Output directory with main.tex")
@click.option("--engine", default="pdflatex", type=click.Choice(["pdflatex", "xelatex", "lualatex"]))
@click.pass_context
def compile(ctx: click.Context, output_dir: str, engine: str) -> None:
    """Compile existing LaTeX project (no LLM)."""
    from .tools.compiler import run_latexmk

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


@cli.command()
@click.option("--config", "-c", "config_path", required=True, type=click.Path(exists=True), help="Path to config.yaml")
@click.option("--output-dir", "-o", required=True, type=click.Path(exists=True), help="Output directory with main.tex")
@click.pass_context
def validate(ctx: click.Context, config_path: str, output_dir: str) -> None:
    """Validate faithfulness of generated LaTeX against source."""
    config_file = Path(config_path)
    config = load_config(config_file)
    config_dir = config_file.parent
    config.output_dir = output_dir

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
