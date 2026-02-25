"""ConsistencyChecker agent — cross-section consistency review."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, ReviewFeedback
from .design_reviewer import _maybe


def make_consistency_checker(config: ProjectConfig) -> autogen.AssistantAgent | None:
    """Create the ConsistencyChecker agent if enabled."""
    return _maybe(
        "ConsistencyChecker", "consistency_checker",
        "a cross-section consistency reviewer for ML system design documents. "
        "Review all section summaries for consistency: terminology, architecture "
        "references, metric definitions, timeline alignment. Flag contradictions "
        "and inconsistencies across sections",
        config,
    )
