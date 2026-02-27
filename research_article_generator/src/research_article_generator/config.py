"""Configuration loader and LLM config builder.

Reads project settings from a YAML config file with ``${ENV_VAR}`` interpolation.
Adapted from ``blog_post/config.py`` — Streamlit session state replaced by
``ProjectConfig`` passed explicitly.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import AzureConfig, ModelConfig, ModelEndpointOverride, ProjectConfig

load_dotenv()

# ---------------------------------------------------------------------------
# YAML loading with ${ENV_VAR} interpolation
# ---------------------------------------------------------------------------

_ENV_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: Any) -> Any:
    """Recursively resolve ``${ENV_VAR}`` references in strings."""
    if isinstance(value, str):
        def _replace(m: re.Match) -> str:
            env_name = m.group(1)
            env_val = os.environ.get(env_name, "")
            return env_val
        return _ENV_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def apply_azure_fallbacks(config: ProjectConfig) -> ProjectConfig:
    """Fill empty azure credentials from environment variables and normalise endpoint."""
    if not config.azure.api_key:
        config.azure.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    if not config.azure.api_version:
        config.azure.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "")
    if not config.azure.endpoint:
        config.azure.endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    config.azure.endpoint = config.azure.endpoint.rstrip("/")
    return config


def load_config(config_path: str | Path) -> ProjectConfig:
    """Load a ``ProjectConfig`` from a YAML file.

    Environment variables referenced as ``${VAR_NAME}`` are resolved.
    If ``azure`` fields are empty after resolution, they fall back to
    well-known environment variables (``AZURE_OPENAI_*``).
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    resolved = _resolve_env_vars(raw)
    config = ProjectConfig.model_validate(resolved)
    return apply_azure_fallbacks(config)


# ---------------------------------------------------------------------------
# LLM config builder (adapted from blog_post/config.py)
# ---------------------------------------------------------------------------

def _is_azure_openai_endpoint(endpoint: str) -> bool:
    """Return True for Azure OpenAI endpoints, False for Azure AI Model Inference."""
    lower = endpoint.lower()
    return "openai.azure.com" in lower or "cognitiveservices.azure.com" in lower


def _build_single_entry(
    model: str,
    azure: AzureConfig,
    override: ModelEndpointOverride | None = None,
) -> dict[str, Any]:
    """Build a single AG2 config_list entry for the given model.

    When an override specifies ``api_type`` (e.g. ``"anthropic"``), that type
    is used directly with the override endpoint as ``base_url``.

    Otherwise Azure OpenAI endpoints (``openai.azure.com``,
    ``cognitiveservices.azure.com``) use ``api_type: "azure"`` with
    deployment-based routing, and other endpoints are treated as
    OpenAI-compatible via ``base_url``.
    """
    api_key = azure.api_key
    api_version = azure.api_version
    endpoint = azure.endpoint
    forced_api_type: str | None = None

    if override:
        endpoint = override.endpoint.rstrip("/")
        if override.api_key:
            api_key = override.api_key
        if override.api_version:
            api_version = override.api_version
        forced_api_type = override.api_type

    entry: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
    }

    if forced_api_type:
        # Explicit api_type from override (e.g. "anthropic")
        entry["api_type"] = forced_api_type
        entry["base_url"] = endpoint
    elif endpoint and _is_azure_openai_endpoint(endpoint):
        entry.update({
            "api_type": "azure",
            "azure_endpoint": endpoint,
            "api_version": api_version,
            "azure_deployment": model,
        })
    elif endpoint:
        entry["base_url"] = endpoint
    return entry


def build_role_llm_config(role: str, config: ProjectConfig) -> dict[str, Any]:
    """Return an AG2-compatible ``llm_config`` dict for the given *role*.

    Role mapping:
    - ``assembler`` → models.assembler (or default)
    - ``planner`` → models.planner (or default)
    - ``reviewer`` / all reviewer names → models.reviewer (or default)
    - ``editor`` → models.editor (or default)

    If ``config.models.overrides`` contains an entry for the chosen model name,
    that entry's endpoint / api_key / api_version take precedence over the
    global ``config.azure`` values.
    """
    models = config.models
    role_map: dict[str, str | None] = {
        "assembler": models.assembler,
        "planner": models.planner,
        "reviewer": models.reviewer,
        "latex_linter": models.reviewer,
        "style_checker": models.reviewer,
        "faithfulness_checker": models.reviewer,
        "meta_reviewer": models.reviewer,
        "equation_formatter": models.assembler,
        "figure_integrator": models.assembler,
        "tikz_generator": models.assembler,
        "tikz_reviewer": models.assembler,
        "citation_agent": models.reviewer,
        "figure_suggester": models.reviewer,
        "plan_reviewer": models.reviewer,
        "page_budget": models.reviewer,
        "editor": models.editor,
        "latex_cosmetic_reviewer": models.reviewer,
    }
    chosen = role_map.get(role.lower()) or models.default
    override = models.overrides.get(chosen)
    entry = _build_single_entry(chosen, config.azure, override=override)
    return {
        "config_list": [entry],
        "timeout": config.timeout,
        "seed": config.seed,
    }
