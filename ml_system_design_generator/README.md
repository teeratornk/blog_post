# ML System Design Generator

A multi-agent CLI tool that reads markdown source documents and generates publication-quality ML system design documents in LaTeX. Powered by [AG2 (AutoGen)](https://github.com/ag2ai/ag2) and Azure OpenAI.

## How It Works

The tool runs a 4-phase pipeline:

1. **Configuration** — Validates project config; optionally prompts interactively for missing fields (style, infrastructure, tech stack, constraints).
2. **Document Understanding** — Reads source `.md` files, produces per-document summaries via a DocAnalyzer agent, identifies gaps with a GapAnalyzer, and cross-checks with an UnderstandingReviewer. Large doc sets are automatically embedded into a local ChromaDB vector store for retrieval during writing.
3. **Design Generation** — A DesignPlanner agent adapts a style template into a concrete section plan. A DesignWriter writes each section as markdown, a DesignReviewer reviews it, and a ConsistencyChecker + InfraAdvisor perform cross-section review. Sections are converted to LaTeX via Pandoc, polished by a LaTeXAssembler agent, assembled into `main.tex`, and compiled with `latexmk` (with an automatic compile-fix loop).
4. **User Review** — Presents the draft for approval. The user can approve, request revisions (with per-section comments), or abort.

## Supported Styles

| Style | Description | Default Pages |
|-------|-------------|:---:|
| `amazon_6page` | Amazon 6-Page Narrative Memo | 6 |
| `amazon_2page` | Amazon PR/FAQ (press release + FAQ) | 2 |
| `google_design` | Google Design Doc (context, goals, design, alternatives) | 8 |
| `anthropic_design` | Anthropic Design Doc (context, goals, design, risks, open questions) | 6 |

Each style defines required sections, content guidance, and page budgets. Templates live in `templates/styles/`.

## Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Azure OpenAI credentials
- `pandoc` on PATH (for markdown-to-LaTeX conversion)
- `latexmk` + a TeX distribution on PATH (for PDF compilation)
- Optional: `chromadb` is included as a dependency for vector store support

## Installation

```bash
cd ml_system_design_generator
uv sync
```

## Environment Variables

Create a `.env` file (or export directly):

```
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
```

These are automatically resolved via `${oc.env:...}` interpolation in the Hydra config.

## Usage

### Full pipeline

```bash
uv run mlsd \
  --config-dir examples/grid_spec_example \
  --config-name config \
  mode=run
```

### Understand docs only (Phase 1 + 2)

```bash
uv run mlsd \
  --config-dir examples/grid_spec_example \
  --config-name config \
  mode=understand
```

### Plan only (Phase 1 + 2 + structure planning)

```bash
uv run mlsd \
  --config-dir examples/grid_spec_example \
  --config-name config \
  mode=plan
```

### Re-compile existing LaTeX

```bash
uv run mlsd mode=compile output_dir=output/
```

### CLI overrides

Any config field can be overridden from the command line via Hydra syntax:

```bash
uv run mlsd \
  --config-dir examples/grid_spec_example \
  --config-name config \
  style=google_design \
  max_pages=10 \
  target_audience=leadership \
  design_review_max_turns=5
```

### Non-interactive mode

```bash
uv run mlsd \
  --config-dir examples/grid_spec_example \
  --config-name config \
  no_interactive=true \
  no_approve=true
```

## Project Config

Configuration is managed through YAML files with Hydra. See `examples/grid_spec_example/config.yaml` for a complete example:

```yaml
project_name: "ML-Powered Grid Operations Decision Support System"
style: amazon_6page
max_pages: 6
docs_dir: ../../docs/grid_spec/
output_dir: output/

infrastructure:
  provider: azure
  compute: [gpu_a100, cpu_cluster]
  storage: [blob_storage, cosmos_db]
  services: [kubernetes, azure_ml]

tech_stack: [python, pytorch, fastapi, kubernetes, azure_ml]
team_size: 5
timeline: "6 months"
constraints:
  - "Latency < 500ms for real-time predictions"
  - "NERC CIP compliance"
target_audience: engineering

azure:
  api_key: "${oc.env:AZURE_OPENAI_API_KEY}"
  api_version: "${oc.env:AZURE_OPENAI_API_VERSION}"
  endpoint: "${oc.env:AZURE_OPENAI_ENDPOINT}"

models:
  default: gpt-5.2

enabled_reviewers:
  DesignReviewer: true
  ConsistencyChecker: true
  InfraAdvisor: true
```

## Agents

| Agent | Phase | Role |
|-------|:-----:|------|
| DocAnalyzer | 2 | Reads and summarizes each source document |
| GapAnalyzer | 2 | Identifies missing information in source material |
| UnderstandingReviewer | 2 | Cross-checks summaries and gap analysis |
| DesignPlanner | 3 | Plans document structure from style template |
| DesignWriter | 3 | Writes each section as markdown |
| DesignReviewer | 3 | Reviews sections for quality and completeness |
| ConsistencyChecker | 3 | Cross-section terminology and logic consistency |
| InfraAdvisor | 3 | Validates infrastructure feasibility |
| LaTeXAssembler | 3 | Polishes Pandoc-converted LaTeX within SAFE_ZONE markers |

Reviewers can be individually toggled via `enabled_reviewers` in the config.

## Project Structure

```
ml_system_design_generator/
├── pyproject.toml
├── src/ml_system_design_generator/
│   ├── cli.py                  # Hydra entry point, mode dispatch
│   ├── _hydra_conf.py          # MlsdConf dataclass (Hydra schema)
│   ├── config.py               # build_role_llm_config(), Azure fallbacks
│   ├── models.py               # Pydantic models (18 total)
│   ├── pipeline.py             # 4-phase pipeline orchestration
│   ├── prompts.py              # Rich interactive prompts
│   ├── logging_config.py       # Rich console, PipelineCallbacks
│   ├── conf/config.yaml        # Hydra defaults
│   ├── agents/                 # 9 agent factories
│   │   ├── doc_analyzer.py
│   │   ├── gap_analyzer.py
│   │   ├── understanding_reviewer.py
│   │   ├── design_planner.py
│   │   ├── design_writer.py
│   │   ├── design_reviewer.py
│   │   ├── consistency_checker.py
│   │   ├── infra_advisor.py
│   │   └── latex_assembler.py
│   └── tools/                  # Deterministic, testable utilities
│       ├── doc_reader.py       # Read & chunk markdown files
│       ├── vector_store.py     # ChromaDB embed/query
│       ├── template_loader.py  # Load style YAML templates
│       ├── pandoc_converter.py # Markdown → LaTeX via Pandoc
│       ├── latex_builder.py    # Preamble generation, main.tex assembly
│       ├── compiler.py         # latexmk wrapper, log parsing
│       └── page_counter.py     # PDF page count
├── templates/
│   ├── styles/                 # Style template definitions
│   │   ├── amazon_6page.yaml
│   │   ├── amazon_2page.yaml
│   │   ├── google_design.yaml
│   │   └── anthropic_design.yaml
│   └── preamble_templates/
│       └── design_doc.tex      # LaTeX preamble template
├── examples/
│   └── grid_spec_example/
│       └── config.yaml
└── tests/
    ├── test_models.py
    ├── test_doc_reader.py
    ├── test_template_loader.py
    ├── test_vector_store.py
    └── test_compiler.py
```

## Tests

```bash
uv run pytest tests/ -v
```

## Output

A successful run produces:

```
output/
├── main.tex              # Root document
├── main.pdf              # Compiled PDF
├── sections/
│   ├── situation.tex
│   ├── approach.tex
│   ├── risks.tex
│   └── ...
└── manifest.json         # Build provenance record
```
