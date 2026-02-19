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

```bash
# Full pipeline
rag run --config config.yaml --output-dir output/

# Dry run (planning only, no LLM)
rag plan --config config.yaml

# Single section conversion (for testing)
rag convert-section --config config.yaml --section drafts/02_methodology.md

# Compile only (no LLM)
rag compile --output-dir output/

# Validate faithfulness only
rag validate --config config.yaml --output-dir output/
```

Verbosity: `--verbose` / default / `--quiet`

## Configuration

Create a `config.yaml` (see `examples/cmame_example/config.yaml`):

```yaml
project_name: "My Research Article"
template: elsarticle
journal_name: "My Journal"
page_budget: 15
draft_dir: drafts/
figure_dir: figures/
bibliography: references.bib

azure:
  api_key: "${AZURE_OPENAI_API_KEY}"
  api_version: "${AZURE_OPENAI_API_VERSION}"
  endpoint: "${AZURE_OPENAI_ENDPOINT}"
```

## Testing

```bash
uv run pytest tests/ -v
```

## Templates

Built-in preamble templates: `elsarticle`, `revtex4`, `ieeetran`. Place custom templates in `templates/preamble_templates/` or specify `template_file` in config.
