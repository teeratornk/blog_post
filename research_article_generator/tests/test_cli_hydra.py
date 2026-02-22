"""Tests for the Hydra-based CLI (cli.py)."""

from __future__ import annotations

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from research_article_generator.cli import _MODE_DISPATCH, _to_project_config
from research_article_generator._hydra_conf import register_configs, RagConf, CLI_ONLY_KEYS
from research_article_generator.models import ProjectConfig


class TestDefaultConfig:
    """Verify the package's conf/config.yaml loads correctly."""

    def test_default_config_loads(self):
        register_configs()
        import research_article_generator
        from pathlib import Path

        conf_dir = str(Path(research_article_generator.__file__).resolve().parent / "conf")
        with initialize_config_dir(config_dir=conf_dir, version_base=None):
            cfg = compose(config_name="config")
            assert cfg.mode == "run"
            assert cfg.no_approve is False
            assert cfg.template == "elsarticle"

    def test_default_config_converts_to_project_config(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test")
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-01-01")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")

        register_configs()
        import research_article_generator
        from pathlib import Path

        conf_dir = str(Path(research_article_generator.__file__).resolve().parent / "conf")
        with initialize_config_dir(config_dir=conf_dir, version_base=None):
            cfg = compose(config_name="config")
            pc = _to_project_config(cfg)
            assert isinstance(pc, ProjectConfig)
            assert pc.project_name == "research-article"


class TestModeDispatch:
    """Verify mode dispatch table."""

    def test_all_modes_present(self):
        expected = {"run", "plan", "compile", "validate", "convert_section"}
        assert set(_MODE_DISPATCH.keys()) == expected

    def test_all_modes_are_callable(self):
        for name, handler in _MODE_DISPATCH.items():
            assert callable(handler), f"Handler for mode {name!r} is not callable"


class TestCompileModeNoProjectConfig:
    """Compile mode should not require full azure credentials."""

    def test_compile_mode_minimal_config(self):
        cfg = OmegaConf.create({
            "mode": "compile",
            "output_dir": "output/",
            "engine": "pdflatex",
        })
        # compile mode only reads output_dir and engine from cfg — no ProjectConfig needed
        assert cfg.mode == "compile"
        assert cfg.output_dir == "output/"
        assert cfg.engine == "pdflatex"


class TestCliOnlyKeys:
    """CLI_ONLY_KEYS should match the extra fields in RagConf."""

    def test_cli_keys_not_in_project_config(self):
        pc_fields = set(ProjectConfig.model_fields.keys())
        for key in CLI_ONLY_KEYS:
            assert key not in pc_fields, f"CLI-only key {key!r} found in ProjectConfig"

    def test_cli_keys_in_rag_conf(self):
        rag_fields = {f.name for f in RagConf.__dataclass_fields__.values()}
        for key in CLI_ONLY_KEYS:
            assert key in rag_fields, f"CLI-only key {key!r} not found in RagConf"
