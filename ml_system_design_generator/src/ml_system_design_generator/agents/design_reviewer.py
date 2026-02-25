"""DesignReviewer agent — reviews design sections for quality."""

from __future__ import annotations

import json
import re

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, ReviewFeedback

# ---------------------------------------------------------------------------
# Structured output validation (same 4-stage fallback as research_article_generator)
# ---------------------------------------------------------------------------


def _strip_fences(raw: str) -> str:
    return re.sub(r"```(?:json)?|```", "", raw).strip()


def _attempt_repair(raw: str) -> str | None:
    txt = raw.strip()
    if not txt:
        return None
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    txt = txt.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    txt = re.sub(r",\s*([}\]])", r"\1", txt)
    txt = re.sub(r'(?m)^(\s*)(Reviewer|Review)\s*:\s*', lambda m: f'{m.group(1)}"{m.group(2)}": ', txt)
    txt = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', txt)
    return txt


def _fallback_from_lines(raw: str) -> ReviewFeedback | None:
    reviewer = None
    review_lines: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"Reviewer\s*[:|-]\s*(.+)", line, re.IGNORECASE)
        if m:
            reviewer = m.group(1).strip()
            continue
        if reviewer:
            review_lines.append(line.lstrip("-* "))
    if reviewer and review_lines:
        try:
            return ReviewFeedback(Reviewer=reviewer[:60], Review="; ".join(review_lines)[:1000])
        except Exception:
            return None
    return None


def validate_review(raw: str) -> tuple[ReviewFeedback | None, str | None]:
    """4-stage parse fallback for reviewer output -> ReviewFeedback."""
    errors: list[str] = []
    stripped = _strip_fences(raw)

    # Stage 1: direct JSON parse
    try:
        if "{" in stripped and "}" in stripped:
            segment = stripped[stripped.find("{"):stripped.rfind("}") + 1]
            return ReviewFeedback.model_validate_json(segment), None
    except Exception as e:
        errors.append(f"direct: {e}")

    # Stage 2: repair + parse
    repaired = _attempt_repair(stripped)
    if repaired:
        try:
            return ReviewFeedback.model_validate_json(repaired), None
        except Exception as e:
            errors.append(f"repair: {e}")

    # Stage 3: line-based fallback
    fb = _fallback_from_lines(stripped)
    if fb:
        return fb, None

    return None, "; ".join(errors) or "Unparseable"


def build_summary_args() -> dict:
    """Build summary_args for nested chat summaries."""
    schema = ReviewFeedback.model_json_schema()
    schema_str = json.dumps(schema.get("properties", {}), ensure_ascii=False)
    return {
        "summary_prompt": (
            "Return ONLY valid JSON matching this schema with required keys Reviewer and Review. "
            f"Schema: {schema_str}. No extra keys, no markdown, no explanations."
        )
    }


# ---------------------------------------------------------------------------
# Reviewer system messages
# ---------------------------------------------------------------------------


def _reviewer_system_message(role_desc: str, role_name: str) -> str:
    return (
        f"You are {role_desc}. Respond with a single JSON object: "
        f'{{"Reviewer": "{role_name}", "Review": "- point 1; - point 2; - point 3"}}. '
        "Guidelines: (1) Reviewer must equal your agent name exactly; "
        "(2) Review value is one string containing up to 3 semicolon-separated concise actionable bullet points; "
        "(3) No markdown fences, no lists/arrays, no extra keys. Return that JSON object only."
    )


def _maybe(
    name: str,
    role_key: str,
    desc: str,
    config: ProjectConfig,
) -> autogen.AssistantAgent | None:
    """Create a reviewer agent if enabled in config."""
    if not config.enabled_reviewers.get(name, False):
        return None
    agent = autogen.AssistantAgent(
        name=name,
        llm_config=build_role_llm_config(role_key, config),
        system_message=_reviewer_system_message(desc, name),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = ReviewFeedback
    return agent


# ---------------------------------------------------------------------------
# Reviewer factories
# ---------------------------------------------------------------------------


def make_design_reviewer(config: ProjectConfig) -> autogen.AssistantAgent | None:
    """Create the DesignReviewer agent if enabled."""
    return _maybe(
        "DesignReviewer", "design_reviewer",
        "a design document reviewer checking for technical accuracy, completeness, "
        "clarity, and adherence to the template style. Verify that claims are "
        "grounded in source documents. Flag vague or unsupported statements",
        config,
    )
