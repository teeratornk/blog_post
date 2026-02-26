"""Configuration loader and LLM config builder.

Adapted from research_article_generator/config.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import AzureConfig, ModelConfig, ProjectConfig

load_dotenv()

# ---------------------------------------------------------------------------
# YAML loading with ${ENV_VAR} interpolation
# ---------------------------------------------------------------------------

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ``${ENV_VAR}`` references in strings."""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            return os.environ.get(m.group(1), "")
        return _ENV_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def apply_azure_fallbacks(config: ProjectConfig) -> ProjectConfig:
    """Fill empty azure credentials from environment variables."""
    if not config.azure.api_key:
        config.azure.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    if not config.azure.api_version:
        config.azure.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "")
    if not config.azure.endpoint:
        config.azure.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    config.azure.endpoint = config.azure.endpoint.rstrip("/")
    return config


def load_config(config_path: str | Path) -> ProjectConfig:
    """Load a ``ProjectConfig`` from a YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    resolved = _resolve_env_vars(raw)
    config = ProjectConfig.model_validate(resolved)
    return apply_azure_fallbacks(config)


# ---------------------------------------------------------------------------
# LLM config builder
# ---------------------------------------------------------------------------

def _build_single_entry(model: str, azure: AzureConfig) -> dict[str, Any]:
    """Build a single AG2 config_list entry for the given model."""
    entry: dict[str, Any] = {
        "model": model,
        "api_key": azure.api_key,
    }
    endpoint = azure.endpoint
    if endpoint and ("azure" in endpoint.lower() or "cognitiveservices" in endpoint.lower()):
        entry.update({
            "api_type": "azure",
            "azure_endpoint": endpoint,
            "api_version": azure.api_version,
            "azure_deployment": model,
        })
    elif endpoint:
        entry["base_url"] = endpoint
    return entry


def build_role_llm_config(role: str, config: ProjectConfig) -> dict[str, Any]:
    """Return an AG2-compatible ``llm_config`` dict for the given *role*.

    Role mapping:
    - ``analyzer`` / ``doc_analyzer`` / ``gap_analyzer`` → models.analyzer (or default)
    - ``writer`` / ``design_writer`` / ``latex_assembler`` → models.writer (or default)
    - ``reviewer`` / ``design_reviewer`` / ``consistency_checker`` → models.reviewer (or default)
    - ``planner`` / ``design_planner`` → models.planner (or default)
    - ``advisor`` / ``infra_advisor`` → models.advisor (or default)
    """
    models = config.models
    role_map: dict[str, str | None] = {
        "analyzer": models.analyzer,
        "doc_analyzer": models.analyzer,
        "gap_analyzer": models.analyzer,
        "understanding_reviewer": models.reviewer,
        "writer": models.writer,
        "design_writer": models.writer,
        "latex_assembler": models.writer,
        "reviewer": models.reviewer,
        "design_reviewer": models.reviewer,
        "consistency_checker": models.reviewer,
        "planner": models.planner,
        "design_planner": models.planner,
        "advisor": models.advisor,
        "infra_advisor": models.advisor,
        "opportunity_analyzer": models.analyzer,
        "feasibility_assessor": models.advisor,
        "page_budget": models.reviewer,
    }
    chosen = role_map.get(role.lower()) or models.default
    entry = _build_single_entry(chosen, config.azure)
    return {
        "config_list": [entry],
        "timeout": config.timeout,
        "seed": config.seed,
    }
