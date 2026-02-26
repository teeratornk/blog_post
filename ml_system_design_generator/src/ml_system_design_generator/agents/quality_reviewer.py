"""QualityReviewer agent — checks for readability, placeholders, and formatting."""

from __future__ import annotations

import autogen

from ..models import ProjectConfig
from .design_reviewer import _maybe


def make_quality_reviewer(config: ProjectConfig) -> autogen.AssistantAgent | None:
    """Create the QualityReviewer agent if enabled."""
    return _maybe(
        "QualityReviewer",
        "quality_reviewer",
        "a quality-assurance reviewer. Check for: "
        "(1) TODO markers or HTML comment placeholders that must be removed; "
        "(2) garbled, truncated, or incomplete sentences; "
        "(3) broken markdown formatting (unclosed fences, malformed tables); "
        "(4) placeholder text like 'Lorem ipsum', 'TBD', 'INSERT X HERE', "
        "'to be specified', 'to be determined', or '(TBD)'; "
        "(5) coherence — each paragraph should logically follow the previous one; "
        "(6) readability — flag overly dense or jargon-heavy passages without explanation; "
        "(7) asterisk placeholders — sequences like '****' or '***' used as stand-ins "
        "for missing content MUST be flagged; "
        "(8) empty table cells — tables with blank cells or cells containing only "
        "dashes/placeholders indicate incomplete content; "
        "(9) deferred items — phrases like '(to be specified)', '(TBD)', "
        "'will be defined later', or 'pending' that defer decisions instead of providing content; "
        "(10) incomplete acceptance criteria — success metrics or acceptance criteria "
        "that lack concrete numbers or thresholds",
        config,
    )
