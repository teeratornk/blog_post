"""InfraAdvisor agent — infrastructure feasibility review."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, ReviewFeedback
from .design_reviewer import _maybe


def make_infra_advisor(config: ProjectConfig) -> autogen.AssistantAgent | None:
    """Create the InfraAdvisor agent if enabled."""
    return _maybe(
        "InfraAdvisor", "infra_advisor",
        "an infrastructure advisor for ML systems. Given the infrastructure "
        "config and tech stack, review the design for feasibility. Flag "
        "unrealistic resource assumptions, suggest alternatives, validate "
        "cloud service choices. Consider cost, scalability, and operational "
        "complexity",
        config,
    )
