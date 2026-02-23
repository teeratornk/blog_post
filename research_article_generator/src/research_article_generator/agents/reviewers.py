"""Reviewer agents: LaTeXLinter, StyleChecker, FaithfulnessChecker, MetaReviewer.

Uses the same nested chat pattern as blog_post/agents.py:
- Each reviewer outputs structured JSON: {"Reviewer": "Name", "Review": "..."}
- FaithfulnessChecker is a HARD GATE — critical violations block the pipeline
- MetaReviewer aggregates all feedback
"""

from __future__ import annotations

import json
import re
from typing import Any

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig, ReviewFeedback

# ---------------------------------------------------------------------------
# Structured output validation (adapted from blog_post/utils.py)
# ---------------------------------------------------------------------------


def _strip_fences(raw: str) -> str:
    """Remove markdown fences."""
    return re.sub(r"```(?:json)?|```", "", raw).strip()


def _attempt_repair(raw: str) -> str | None:
    """Lightweight repair for common LLM JSON mistakes."""
    txt = raw.strip()
    if not txt:
        return None
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    txt = txt.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    txt = re.sub(r",\s*([}\]])", r"\1", txt)
    txt = re.sub(r'(?m)^(\s*)(Reviewer|Review)\s*:\s*', lambda m: f'{m.group(1)}"{m.group(2)}": ', txt)
    # Fix unescaped backslashes (e.g. LaTeX commands like \textwidth inside JSON strings).
    # Replace lone backslashes that aren't already valid JSON escapes.
    txt = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', txt)
    return txt


def _fallback_from_lines(raw: str) -> ReviewFeedback | None:
    """Extract Reviewer/Review from line-based output."""
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
    """4-stage parse fallback for reviewer output → ReviewFeedback."""
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
# Reviewer agent factory
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
# Reflection message (context passing for nested chats)
# ---------------------------------------------------------------------------


def reflection_message(recipient: Any, messages: list[dict], sender: Any, config: Any) -> str:
    """Extract the latest LaTeX content and format a review prompt."""
    last_content = ""
    if messages:
        for m in reversed(messages):
            c = m.get("content")
            if c:
                last_content = c
                break

    agent_name = getattr(recipient, "name", "Reviewer")
    example = f'{{"Reviewer": "{agent_name}", "Review": "- improve X; - fix Y; - clarify Z"}}'
    return (
        "Return ONLY a valid JSON object with keys Reviewer and Review. "
        f"Example: {example}\n\nCONTENT TO REVIEW:\n{last_content}"
    )


# ---------------------------------------------------------------------------
# Make all reviewers + register nested chats
# ---------------------------------------------------------------------------


def make_plan_reviewer(config: ProjectConfig) -> autogen.AssistantAgent | None:
    """Create the PlanReviewer agent if enabled in config."""
    return _maybe(
        "PlanReviewer", "plan_reviewer",
        "a structure plan reviewer for research articles. You receive a StructurePlan JSON "
        "and check for: (1) logical section ordering — introduction before methods, methods "
        "before results, results before discussion/conclusion; (2) all draft files covered; "
        "(3) page estimates reasonable vs budget; (4) missing standard sections (abstract, "
        "conclusion); (5) section granularity. In your Review field, list only actionable "
        "issues. If the plan is sound, say 'No issues found'",
        config,
    )


def make_reviewers(config: ProjectConfig) -> dict[str, autogen.AssistantAgent | None]:
    """Create all reviewer agents based on config."""
    return {
        "LaTeXLinter": _maybe(
            "LaTeXLinter", "latex_linter",
            "a LaTeX quality reviewer checking for compilation issues, style problems, "
            "and best practices in LaTeX formatting",
            config,
        ),
        "StyleChecker": _maybe(
            "StyleChecker", "style_checker",
            "an academic writing style reviewer checking for clarity, conciseness, "
            "passive voice overuse, and journal-appropriate academic tone. "
            "Flag any subjective opinions, value judgments, hedging phrases "
            "(e.g. 'we believe', 'arguably', 'remarkable'), or unsupported claims "
            "in sections other than Discussion — all non-Discussion sections must "
            "be strictly fact-based",
            config,
        ),
        "FaithfulnessChecker": _maybe(
            "FaithfulnessChecker", "faithfulness_checker",
            "a faithfulness checker that receives diff output from deterministic checks "
            "and evaluates whether any meaning-altering changes were made. "
            "Flag any content that differs from the source material",
            config,
        ),
    }


def make_meta_reviewer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the MetaReviewer that aggregates cross-section feedback."""
    return autogen.AssistantAgent(
        name="MetaReviewer",
        llm_config=build_role_llm_config("meta_reviewer", config),
        system_message=(
            "You are a meta reviewer for a multi-file research article LaTeX pipeline. "
            "You receive per-section review summaries (NOT the full document). "
            "Focus on CROSS-SECTION issues:\n"
            "1. Narrative flow — do sections connect logically?\n"
            "2. Notation consistency — are symbols/variables defined once and used consistently?\n"
            "3. Bibliography coherence — are citations used consistently across sections?\n"
            "4. Redundancy — is content repeated across sections?\n"
            "For every issue, specify the affected section_id(s) so fixes can be targeted. "
            "Format: {\"section_id\": \"<id>\", \"issue\": \"<description>\", \"severity\": \"<warning|error|critical>\"}. "
            "Prioritize faithfulness issues as CRITICAL."
        ),
    )


def register_review_chats(
    trigger_agent: autogen.AssistantAgent,
    config: ProjectConfig,
) -> None:
    """Register nested review chats on the trigger agent (same pattern as blog_post).

    The trigger agent (typically the orchestrator's proxy or assembler) triggers
    nested chats with each enabled reviewer, followed by the MetaReviewer.
    """
    reviewers = make_reviewers(config)
    meta = make_meta_reviewer(config)
    summary_args = build_summary_args()

    review_chats: list[dict] = []
    for name, agent in reviewers.items():
        if agent is not None:
            review_chats.append({
                "recipient": agent,
                "message": reflection_message,
                "summary_method": "reflection_with_llm",
                "summary_args": summary_args,
                "max_turns": config.review_max_turns,
            })

    review_chats.append({
        "recipient": meta,
        "message": "Aggregate feedback from all reviewers and give final suggestions. Prioritize faithfulness issues.",
        "max_turns": config.review_max_turns,
    })

    trigger_agent.register_nested_chats(review_chats, trigger=autogen.AssistantAgent)
