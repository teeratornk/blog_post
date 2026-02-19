# CLAUDE.md — Research Article LaTeX Generator

## Project Overview

CLI tool that transforms markdown research drafts + figures into publication-ready LaTeX documents. Uses AG2 multi-agent orchestration with a **Pandoc-first** architecture: deterministic Pandoc conversion before LLM polishing minimizes errors.

## Tech Stack

- **Python 3.10+**, **AG2/AutoGen** (multi-agent), **Azure OpenAI** (LLM backend)
- **Pandoc + pandoc-crossref** — deterministic md→LaTeX first pass
- **Pydantic v2** — structured output validation
- **Click + rich-click** — CLI, **Rich** — console output
- **latexmk** — compilation, **ChkTeX** — linting

## Project Structure

```
src/research_article_generator/
├── cli.py                  — Click entry points (rag run/plan/convert-section/compile/validate)
├── config.py               — YAML config loader, ${ENV_VAR} interpolation, build_role_llm_config()
├── models.py               — All Pydantic models (StructurePlan, CompilationResult, etc.)
├── pipeline.py             — Pipeline class — 6-phase orchestration
├── logging_config.py       — Rich console, PipelineCallbacks, RichCallbacks
├── agents/                 — AG2 agent definitions
│   ├── structure_planner.py, latex_assembler.py, equation_formatter.py
│   ├── figure_integrator.py, citation_agent.py, page_budget_manager.py
│   └── reviewers.py        — LaTeXLinter, StyleChecker, FaithfulnessChecker, MetaReviewer
└── tools/                  — Deterministic tools (no LLM)
    ├── pandoc_converter.py — Pandoc + SAFE_ZONE annotation
    ├── latex_builder.py    — Preamble generation, document assembly
    ├── compiler.py         — latexmk wrapper + log parsing
    ├── linter.py           — ChkTeX + lacheck
    ├── diff_checker.py     — Faithfulness layers 1-4 (structure, math, citations, text diff)
    └── page_counter.py     — pdfinfo / log fallback
```

## Key Architecture

1. **Pandoc converts first** — handles math, figures, tables, citations deterministically
2. **LLM polishes** — only modifies text between `%% SAFE_ZONE` markers
3. **Multi-layer faithfulness** — 4 deterministic checks + 1 LLM reviewer as hard gate
4. **Compile-fix loop** — latexmk → error extraction with ±5 line context → LLM fix → retry

## Running

```bash
cd research_article_generator
uv sync
uv run rag run --config examples/cmame_example/config.yaml --output-dir output/
uv run pytest tests/
```

## Style Guidelines

- Use `build_role_llm_config(role, config)` — never hardcode model names
- All reviewer agents return `{"Reviewer": "Name", "Review": "..."}` JSON
- Tools in `tools/` are deterministic (no LLM calls) — fully testable in isolation
- Agent system prompts must enforce SAFE_ZONE read-only rules
- Never commit `.env` or API keys
