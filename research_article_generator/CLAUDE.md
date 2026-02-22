# CLAUDE.md — Research Article LaTeX Generator

## Project Overview

CLI tool that transforms markdown research drafts + figures into publication-ready LaTeX documents. Uses AG2 multi-agent orchestration with a **Pandoc-first** architecture: deterministic Pandoc conversion before LLM polishing minimizes errors.

## Tech Stack

- **Python 3.10+**, **AG2/AutoGen** (multi-agent), **Azure OpenAI** (LLM backend)
- **Pandoc + pandoc-crossref** — deterministic md→LaTeX first pass
- **Pydantic v2** — structured output validation
- **Hydra + OmegaConf** — CLI & config composition, **Rich** — console output
- **latexmk** — compilation, **ChkTeX** — linting

## Project Structure

```
src/research_article_generator/
├── cli.py                  — Hydra entry point, mode dispatch (run/plan/compile/validate/convert_section)
├── _hydra_conf.py          — Structured config dataclasses (RagConf) + ConfigStore registration
├── conf/config.yaml        — Hydra default config (merged with user config via defaults list)
├── config.py               — YAML config loader (legacy), apply_azure_fallbacks(), build_role_llm_config()
├── models.py               — All Pydantic models (StructurePlan, CompilationResult, ProjectConfig, etc.)
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

# Full pipeline (auto-approve)
uv run rag --config-dir examples/cmame_example --config-name config mode=run no_approve=true

# Planning only
uv run rag --config-dir examples/cmame_example --config-name config mode=plan

# Compile existing LaTeX (no LLM)
uv run rag mode=compile output_dir=output/ engine=pdflatex

# Validate faithfulness
uv run rag --config-dir examples/cmame_example --config-name config mode=validate output_dir=output/

# Convert a single section
uv run rag --config-dir examples/cmame_example --config-name config mode=convert_section section_file=drafts/01_intro.md section_output=out.tex

# Override any config field from CLI
uv run rag --config-dir examples/cmame_example --config-name config mode=run page_budget=25 tikz_enabled=true

# Help
uv run rag --help

# Tests
uv run pytest tests/
```

## Config System

Uses **Hydra** for config composition. User config files need a `defaults` list at the top:

```yaml
defaults:
  - rag_schema    # loads structured schema defaults from RagConf
  - _self_        # user values override schema defaults

project_name: "My Paper"
azure:
  api_key: "${oc.env:AZURE_OPENAI_API_KEY}"    # Hydra OmegaConf env resolution
  api_version: "${oc.env:AZURE_OPENAI_API_VERSION}"
  endpoint: "${oc.env:AZURE_OPENAI_ENDPOINT}"
# ...
```

`--config-dir` points to the directory containing the user's `config.yaml`. `--config-name` selects the file (without `.yaml`). All config fields can be overridden from the CLI as `key=value` pairs.

Legacy `load_config()` in `config.py` still works for programmatic use (uses `${VAR}` interpolation instead of `${oc.env:VAR}`).

## Style Guidelines

- Use `build_role_llm_config(role, config)` — never hardcode model names
- All reviewer agents return `{"Reviewer": "Name", "Review": "..."}` JSON
- Tools in `tools/` are deterministic (no LLM calls) — fully testable in isolation
- Agent system prompts must enforce SAFE_ZONE read-only rules
- Never commit `.env` or API keys
