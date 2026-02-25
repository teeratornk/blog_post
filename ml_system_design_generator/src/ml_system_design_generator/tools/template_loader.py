"""Load design document style templates from YAML files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "templates" / "styles"

VALID_STYLES = ("amazon_2page", "amazon_6page", "google_design", "anthropic_design")


def load_style_template(style: str) -> dict[str, Any]:
    """Load a design doc style template by name.

    Args:
        style: one of amazon_2page, amazon_6page, google_design, anthropic_design.

    Returns:
        Parsed YAML dict with keys: name, description, max_pages_default, sections.
    """
    if style not in VALID_STYLES:
        raise ValueError(f"Unknown style: {style!r}. Choose from: {VALID_STYLES}")

    template_path = TEMPLATES_DIR / f"{style}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    with open(template_path) as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Template {style} has invalid format")

    return data


def get_style_sections(style: str) -> list[dict[str, Any]]:
    """Return the sections list from a style template."""
    template = load_style_template(style)
    return template.get("sections", [])


def get_style_max_pages(style: str) -> int | None:
    """Return the default max pages for a style."""
    template = load_style_template(style)
    return template.get("max_pages_default")


def summarize_style(style: str) -> str:
    """Return a human-readable summary of the style template for LLM agents."""
    try:
        template = load_style_template(style)
    except (ValueError, FileNotFoundError):
        return f"(Unknown style: {style})"

    parts = [f"=== Design Doc Style: {template.get('name', style)} ==="]
    parts.append(f"Description: {template.get('description', '')}")

    max_pages = template.get("max_pages_default")
    if max_pages:
        parts.append(f"Default max pages: {max_pages}")

    sections = template.get("sections", [])
    if sections:
        parts.append(f"\nSections ({len(sections)}):")
        for s in sections:
            optional = " (optional)" if s.get("optional", False) else ""
            parts.append(
                f"  - {s['id']}: {s['title']} (~{s.get('estimated_pages', 1.0)} pages){optional}"
            )
            if s.get("guidance"):
                parts.append(f"    Guidance: {s['guidance'][:120]}...")

    return "\n".join(parts)


def list_available_styles() -> list[str]:
    """Return list of available style names."""
    return list(VALID_STYLES)
