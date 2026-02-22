"""Hydra structured config dataclasses.

These mirror the Pydantic ``ProjectConfig`` for Hydra schema validation.
At runtime the Hydra DictConfig is converted to ``ProjectConfig`` via
``cli._to_project_config()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hydra.core.config_store import ConfigStore


@dataclass
class AzureConf:
    api_key: str = "${oc.env:AZURE_OPENAI_API_KEY,''}"
    api_version: str = "${oc.env:AZURE_OPENAI_API_VERSION,''}"
    endpoint: str = "${oc.env:AZURE_OPENAI_ENDPOINT,''}"


@dataclass
class ModelConf:
    default: str = "gpt-5.2"
    assembler: str | None = None
    planner: str | None = None
    reviewer: str | None = None
    editor: str | None = None


@dataclass
class RagConf:
    # --- Dispatch + CLI-only fields ---
    mode: str = "run"
    no_approve: bool = False
    verbose: bool = False
    quiet: bool = False
    engine: str = "pdflatex"
    section_file: str | None = None
    section_output: str | None = None

    # --- ProjectConfig fields (1:1 mapping) ---
    project_name: str = "research-article"
    template: str = "elsarticle"
    template_file: str | None = None
    journal_name: str = ""
    page_budget: int | None = None
    latex_engine: str = "pdflatex"
    bib_style: str = "elsarticle-num"

    draft_dir: str = "drafts/"
    figure_dir: str = "figures/"
    bibliography: str | None = None
    output_dir: str = "output/"

    azure: AzureConf = field(default_factory=AzureConf)
    models: ModelConf = field(default_factory=ModelConf)

    compile_max_attempts: int = 3
    review_max_turns: int = 2
    review_max_rounds: int = 2
    max_plan_revisions: int = 3
    timeout: int = 120
    seed: int = 42

    supplementary_mode: str = "disabled"
    supplementary_threshold: float = 1.2

    enabled_reviewers: dict[str, bool] = field(default_factory=lambda: {
        "LaTeXLinter": True,
        "StyleChecker": True,
        "FaithfulnessChecker": True,
        "MetaReviewer": True,
    })

    tikz_enabled: bool = False
    tikz_review_max_turns: int = 3

    figure_suggestion_enabled: bool = False
    figure_suggestion_max: int = 3


# Keys present in RagConf that are NOT part of ProjectConfig.
CLI_ONLY_KEYS = frozenset({
    "mode", "no_approve", "verbose", "quiet", "engine",
    "section_file", "section_output",
})


def register_configs() -> None:
    """Register the structured config schema with Hydra's ConfigStore."""
    cs = ConfigStore.instance()
    cs.store(name="rag_schema", node=RagConf)
