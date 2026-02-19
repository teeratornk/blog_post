"""Tests for config.py — YAML loading and LLM config building."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from research_article_generator.config import load_config, build_role_llm_config, _resolve_env_vars
from research_article_generator.models import ProjectConfig


class TestResolveEnvVars:
    def test_string_replacement(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "hello")
        assert _resolve_env_vars("${TEST_VAR}") == "hello"

    def test_missing_var_becomes_empty(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        assert _resolve_env_vars("${NONEXISTENT_VAR}") == ""

    def test_nested_dict(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret")
        result = _resolve_env_vars({"api_key": "${MY_KEY}", "other": "plain"})
        assert result == {"api_key": "secret", "other": "plain"}

    def test_list(self, monkeypatch):
        monkeypatch.setenv("X", "val")
        assert _resolve_env_vars(["${X}", "static"]) == ["val", "static"]

    def test_non_string_passthrough(self):
        assert _resolve_env_vars(42) == 42
        assert _resolve_env_vars(None) is None


class TestLoadConfig:
    def test_load_sample_config(self, sample_config_path, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-01-01")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        config = load_config(sample_config_path)
        assert config.project_name == "Physics-Informed Neural Networks for PDEs"
        assert config.template == "elsarticle"
        assert config.page_budget == 15
        assert config.azure.api_key == "test-key"

    def test_missing_config_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_env_fallback(self, sample_config_path, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fallback-key")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-01-01")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://fallback.openai.azure.com/")
        config = load_config(sample_config_path)
        assert config.azure.api_key == "fallback-key"
        # Trailing slash should be stripped
        assert not config.azure.endpoint.endswith("/")


class TestBuildRoleLlmConfig:
    def test_assembler_role(self):
        config = ProjectConfig(
            models={"default": "gpt-4", "assembler": "gpt-5"},
            azure={"api_key": "k", "api_version": "v", "endpoint": "https://test.openai.azure.com"},
        )
        llm_config = build_role_llm_config("assembler", config)
        assert llm_config["config_list"][0]["model"] == "gpt-5"
        assert llm_config["config_list"][0]["api_type"] == "azure"

    def test_unknown_role_uses_default(self):
        config = ProjectConfig(
            models={"default": "gpt-4"},
            azure={"api_key": "k", "api_version": "v", "endpoint": "https://test.openai.azure.com"},
        )
        llm_config = build_role_llm_config("unknown_role", config)
        assert llm_config["config_list"][0]["model"] == "gpt-4"

    def test_non_azure_endpoint(self):
        config = ProjectConfig(
            models={"default": "gpt-4"},
            azure={"api_key": "k", "api_version": "v", "endpoint": "https://custom-api.example.com"},
        )
        llm_config = build_role_llm_config("assembler", config)
        entry = llm_config["config_list"][0]
        assert "api_type" not in entry
        assert entry["base_url"] == "https://custom-api.example.com"
