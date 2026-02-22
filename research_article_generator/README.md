# Research Article LaTeX Generator

CLI tool that transforms markdown research drafts and figures into publication-ready LaTeX documents using a multi-agent AI pipeline.

## Architecture

**Pandoc-first pipeline**: Pandoc handles deterministic conversion (math, figures, tables, citations), then specialized AI agents polish for journal style and validate faithfulness.

```
Markdown drafts → [Pandoc] → structural LaTeX → [LLM polish] → compiled PDF
```

### 6-Phase Pipeline

1. **Planning** — StructurePlanner analyzes inputs, produces section-by-section plan
2. **Conversion** — Pandoc converts each section, LaTeXAssembler polishes style
3. **Post-processing** — Equation formatting, figure placement, citation validation
4. **Compilation + Review** — latexmk compile, ChkTeX lint, nested reviewer chats
5. **Page Budget** — Advisory page count analysis (user decides on changes)
6. **Finalization** — Output manifest, final verification

## Prerequisites

System dependencies (not managed by uv):
- [Pandoc](https://pandoc.org/) + [pandoc-crossref](https://github.com/lierdakil/pandoc-crossref)
- LaTeX distribution (TeX Live / MiKTeX) with `latexmk`
- ChkTeX (optional, for linting)
- poppler-utils / pdfinfo (optional, for page counting)

## Installation

```bash
cd research_article_generator
uv sync
```

## Usage

The CLI uses [Hydra](https://hydra.cc/) for configuration. Point `--config-dir` at the directory containing your `config.yaml` and select the mode:

```bash
# Full pipeline (auto-approve plan)
rag --config-dir examples/cmame_example --config-name config mode=run no_approve=true

# Dry run (planning only, no LLM)
rag --config-dir examples/cmame_example --config-name config mode=plan

# Single section conversion (for testing)
rag --config-dir examples/cmame_example --config-name config \
    mode=convert_section section_file=drafts/02_methodology.md section_output=out.tex

# Compile only (no LLM)
rag mode=compile output_dir=output/ engine=pdflatex

# Validate faithfulness only
rag --config-dir examples/cmame_example --config-name config mode=validate output_dir=output/
```

Any config field can be overridden from the command line:

```bash
rag --config-dir examples/cmame_example --config-name config mode=run page_budget=25 tikz_enabled=true
```

Verbosity: `verbose=true` / default / `quiet=true`

## Configuration

Create a `config.yaml` (see `examples/cmame_example/config.yaml`). The file must start with a Hydra `defaults` list:

```yaml
defaults:
  - rag_schema
  - _self_

project_name: "My Research Article"
template: elsarticle
journal_name: "My Journal"
page_budget: 15
draft_dir: drafts/
figure_dir: figures/
bibliography: references.bib

azure:
  api_key: "${oc.env:AZURE_OPENAI_API_KEY}"
  api_version: "${oc.env:AZURE_OPENAI_API_VERSION}"
  endpoint: "${oc.env:AZURE_OPENAI_ENDPOINT}"
```

- `rag_schema` loads structured defaults from the built-in schema — you only need to specify fields you want to override.
- Environment variables use OmegaConf syntax: `${oc.env:VAR_NAME}`.
- Azure credentials also fall back to `AZURE_OPENAI_*` env vars automatically if omitted.

## Testing

```bash
uv run pytest tests/ -v
```

## Templates

Built-in preamble templates: `elsarticle`, `revtex4`, `ieeetran`. Place custom templates in `templates/preamble_templates/` or specify `template_file` in config.
