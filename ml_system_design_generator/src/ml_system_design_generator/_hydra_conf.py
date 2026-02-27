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
class ModelEndpointOverrideConf:
    endpoint: str = ""
    api_key: str | None = None
    api_version: str | None = None
    api_type: str | None = None


@dataclass
class ModelConf:
    default: str = "gpt-5.2"
    analyzer: str | None = None
    writer: str | None = None
    reviewer: str | None = None
    planner: str | None = None
    advisor: str | None = None
    overrides: dict[str, ModelEndpointOverrideConf] = field(default_factory=dict)


@dataclass
class InfraConf:
    provider: str = ""
    compute: list[str] = field(default_factory=list)
    storage: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)


@dataclass
class MlsdConf:
    # --- CLI-only fields ---
    mode: str = "run"                     # run | plan | understand | discover | compile
    no_approve: bool = False
    no_interactive: bool = False
    verbose: bool = False
    quiet: bool = False

    # --- ProjectConfig fields ---
    project_name: str = "ml-system-design"
    author: str = ""
    style: str = "amazon_6page"
    max_pages: int | None = None
    docs_dir: str = "docs/"
    output_dir: str = "output/"

    # Infrastructure & tech
    infrastructure: InfraConf = field(default_factory=InfraConf)
    tech_stack: list[str] = field(default_factory=list)
    team_size: int | None = None
    timeline: str | None = None
    constraints: list[str] = field(default_factory=list)
    target_audience: str = "leadership"

    # Azure OpenAI
    azure: AzureConf = field(default_factory=AzureConf)
    models: ModelConf = field(default_factory=ModelConf)

    # Tuning
    understanding_max_rounds: int = 3
    design_review_max_turns: int = 3
    design_revision_max_rounds: int = 3
    writing_review_max_rounds: int = 2
    compile_max_attempts: int = 3
    vector_db_enabled: bool = True
    vector_db_threshold_kb: int = 50
    timeout: int = 120
    seed: int = 42

    # Opportunity discovery & feasibility
    max_opportunities: int = 5
    feasibility_max_rounds: int = 2

    # Page budget & supplementary
    supplementary_mode: str = "auto"
    supplementary_threshold: float = 1.3
    max_plan_revisions: int = 3
    words_per_page: int = 350

    enabled_reviewers: dict[str, bool] = field(default_factory=lambda: {
        "DesignReviewer": True,
        "ConsistencyChecker": True,
        "InfraAdvisor": True,
        "QualityReviewer": True,
        "LaTeXCosmeticReviewer": True,
    })


# Keys in MlsdConf that are NOT part of ProjectConfig.
CLI_ONLY_KEYS = frozenset({
    "mode", "no_approve", "no_interactive", "verbose", "quiet",
})


def register_configs() -> None:
    """Register the structured config schema with Hydra's ConfigStore.

    Two entries are stored:
    - ``mlsd_schema`` — referenced by user config files via ``defaults: [mlsd_schema]``
    - ``config`` — fallback when no ``--config-dir`` is provided (e.g. ``mlsd mode=compile``)
    """
    cs = ConfigStore.instance()
    cs.store(name="mlsd_schema", node=MlsdConf)
    cs.store(name="config", node=MlsdConf)
