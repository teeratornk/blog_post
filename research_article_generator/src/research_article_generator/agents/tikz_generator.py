"""TikZGenerator agent — creates TikZ diagrams from section text."""

from __future__ import annotations

import json
import logging
import re

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, TikZIssue, TikZReviewResult, Severity

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a TikZ diagram specialist for LaTeX research articles.

Given a LaTeX section, analyze the text for concepts that would benefit from a diagram:
- Block diagrams (system architectures, processing pipelines)
- Flowcharts (algorithms, decision processes, workflows)
- Neural network architecture schematics (layers, connections)
- General schematics (domain decomposition, boundary conditions)

When you identify a diagram opportunity:
1. Generate TikZ code wrapped in a figure environment:
   \\begin{figure}[htbp]
   \\centering
   \\begin{tikzpicture}[...]
   ...
   \\end{tikzpicture}
   \\caption{Descriptive caption.}
   \\label{fig:tikz_<descriptive_name>}
   \\end{figure}
2. Insert the figure near the paragraph that describes the concept.

Constraints:
- Use ONLY these TikZ libraries: arrows.meta, positioning, shapes.geometric, calc, fit, backgrounds, decorations.pathreplacing
- Do NOT generate pgfplots or mathematical plots.
- Do NOT modify existing text content.
- Do NOT duplicate or replace existing \\begin{figure} environments.
- Preserve all existing content exactly as provided.
- If no diagram opportunity exists, return the LaTeX unchanged.

Return the modified LaTeX only, without explanations.
"""


def make_tikz_generator(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the TikZGenerator agent."""
    return autogen.AssistantAgent(
        name="TikZGenerator",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("tikz_generator", config),
    )


# ---------------------------------------------------------------------------
# TikZ Reviewer
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM_PROMPT = """\
You are a TikZ diagram reviewer for LaTeX research articles.
Given a LaTeX section containing \\begin{tikzpicture} environments, apply these checks with the concrete thresholds below.

## 1. Syntax
- Every \\begin{tikzpicture} has a matching \\end{tikzpicture}.
- Every \\node statement ends with a semicolon.
- Every \\draw and \\path statement ends with a semicolon.
- Coordinates are numeric (x,y) or relative ($(...)$).

## 2. Spacing
- Adjacent nodes must be >= 1.5cm apart.
- Nodes using the positioning library (e.g. right=of) must specify distance >= 1.5cm (e.g. right=2cm of).
- No two nodes may share the same coordinate.

## 3. Labels
- Nodes with text must use minimum width=2cm, minimum height=0.8cm (or larger).
- Font size must be \\small or larger (no \\tiny or \\scriptsize).
- Multi-word labels should use text width to prevent overflow.

## 4. Libraries
- Allowed: arrows.meta, positioning, shapes.geometric, calc, fit, backgrounds, decorations.pathreplacing.
- Flag any \\usetikzlibrary not in this list.
- Flag any pgfplots usage.

## 5. Layout
- Flow diagrams must have a single dominant direction (top-to-bottom OR left-to-right).
- Arrow tips must all use the same style (recommend -Stealth).
- Line widths should be consistent across connections.

## 6. Integration
- Each tikzpicture must be inside \\begin{figure}[htbp]\\centering...\\end{figure}.
- Must have both \\caption{...} and \\label{fig:tikz_...}.

## Output format
Return ONLY a JSON object matching this schema:
{"verdict": "PASS", "issues": []}
or
{"verdict": "FAIL", "issues": [{"category": "<cat>", "severity": "<error|warning|info>", "description": "<text>"}]}

Categories: syntax, spacing, labels, libraries, layout, integration.
Do NOT return modified LaTeX code. Return ONLY the JSON object.
"""


def make_tikz_reviewer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the TikZReviewer agent."""
    return autogen.AssistantAgent(
        name="TikZReviewer",
        system_message=REVIEWER_SYSTEM_PROMPT,
        llm_config=build_role_llm_config("tikz_reviewer", config),
    )


# ---------------------------------------------------------------------------
# Structured output validation for TikZ reviews
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = {"syntax", "spacing", "labels", "libraries", "layout", "integration"}
_SEVERITY_MAP = {"error": Severity.ERROR, "warning": Severity.WARNING, "info": Severity.INFO}


def _strip_fences(raw: str) -> str:
    """Remove markdown fences."""
    return re.sub(r"```(?:json)?|```", "", raw).strip()


def _attempt_repair(raw: str) -> str | None:
    """Lightweight repair for common LLM JSON mistakes."""
    txt = raw.strip()
    if not txt:
        return None
    if "{" in txt and "}" in txt:
        # Find the outermost JSON object
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    # Curly/smart quotes
    txt = txt.replace("\u201c", '"').replace("\u201d", '"')
    txt = txt.replace("\u2018", "'").replace("\u2019", "'")
    # Trailing commas before } or ]
    txt = re.sub(r",\s*([}\]])", r"\1", txt)
    # Unescaped backslashes (LaTeX commands inside JSON strings)
    txt = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', txt)
    return txt


def _fallback_from_text(raw: str) -> TikZReviewResult | None:
    """Extract verdict and issues from freeform text as last resort."""
    upper = raw.upper()
    if "PASS" in upper and "FAIL" not in upper:
        return TikZReviewResult(verdict="PASS", issues=[])

    # Look for numbered issue lines: "1. ...", "2. ..."
    issue_lines = re.findall(r"^\s*\d+\.\s*(.+)", raw, re.MULTILINE)
    if not issue_lines:
        # Try bullet points
        issue_lines = re.findall(r"^\s*[-*]\s*(.+)", raw, re.MULTILINE)
    if not issue_lines:
        return None

    issues: list[TikZIssue] = []
    for line in issue_lines:
        lower = line.lower()
        # Guess category from keywords
        category = "syntax"
        for cat in _VALID_CATEGORIES:
            if cat in lower:
                category = cat
                break
        if "overlap" in lower or "spacing" in lower or "apart" in lower:
            category = "spacing"
        elif "caption" in lower or "label" in lower or "figure" in lower:
            category = "integration"
        elif "arrow" in lower or "direction" in lower or "flow" in lower:
            category = "layout"
        elif "font" in lower or "text width" in lower or "minimum" in lower:
            category = "labels"
        elif "library" in lower or "pgfplots" in lower:
            category = "libraries"

        # Guess severity
        severity = Severity.ERROR if "error" in lower else Severity.WARNING
        issues.append(TikZIssue(category=category, severity=severity, description=line.strip()))

    if issues:
        return TikZReviewResult(verdict="FAIL", issues=issues)
    return None


def validate_tikz_review(raw: str) -> TikZReviewResult | None:
    """3-stage parser for TikZ reviewer output -> TikZReviewResult.

    Stage 1: Direct JSON parse.
    Stage 2: Repair (curly quotes, trailing commas, backslash escaping) then parse.
    Stage 3: Fallback regex extraction from freeform text.

    Returns None only on completely unparseable garbage.
    """
    stripped = _strip_fences(raw)

    # Stage 1: Direct JSON parse
    if "{" in stripped and "}" in stripped:
        segment = stripped[stripped.find("{"):stripped.rfind("}") + 1]
        try:
            return TikZReviewResult.model_validate_json(segment)
        except Exception:
            pass

    # Stage 2: Repair + parse
    repaired = _attempt_repair(stripped)
    if repaired:
        try:
            return TikZReviewResult.model_validate_json(repaired)
        except Exception:
            pass

    # Stage 3: Fallback from freeform text
    result = _fallback_from_text(stripped)
    if result is not None:
        return result

    return None
