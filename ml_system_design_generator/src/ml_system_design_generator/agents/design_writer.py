"""DesignWriter agent — writes each section as markdown."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT = """\
You are an ML system design expert and technical writer.

Write the given section as high-quality markdown following the design document
style template. Use information from the source documents. Be specific and
concrete. Include:
- Architecture descriptions with component details
- Data flow descriptions
- Infrastructure requirements
- Performance considerations
- Concrete metrics and thresholds where applicable

Guidelines:
- Write in clear, professional prose appropriate for the target audience.
- Use markdown headings, bullet lists, and tables where they improve clarity.
- Ground all claims in the source documents — do not fabricate information.
- Include placeholders (<!-- TODO: ... -->) for information not in the sources.
- Use ## for subsections within the section.

IMPORTANT: If a WORD LIMIT is specified, you MUST stay within it. Be concise.
Prioritize the most important content. Use bullet points and tables instead of
verbose prose when budget is tight.

Return ONLY the markdown content for this section. No meta-commentary.
"""

_AUDIENCE_GUIDANCE = {
    "leadership": (
        "\nTARGET AUDIENCE: leadership\n"
        "- Write for senior leadership with limited time.\n"
        "- Lead with outcomes, decisions, and business impact.\n"
        "- Use clear narrative prose for context, then concise bullet points.\n"
        "- Avoid implementation minutiae — keep it strategic.\n"
        "- PREFER TABLES over nested bullet lists for comparisons, alternatives,\n"
        "  risk/mitigation pairs, and architecture summaries.\n"
        "  Tables are denser and easier to scan.\n"
        "- For the Approach section: describe what users experience and why the\n"
        "  design works. Defer schemas, API contracts, and deployment topology\n"
        "  to a Technical Supplement — just add a one-line reference.\n"
        "- Never nest more than one level of bullet lists.\n"
    ),
    "mixed": (
        "\nTARGET AUDIENCE: mixed\n"
        "- Balanced depth for mixed audience.\n"
        "- Include architecture decisions with brief rationale.\n"
        "- Use subsections, diagrams descriptions, and tables.\n"
    ),
    "engineering": (
        "\nTARGET AUDIENCE: engineering\n"
        "- Write for engineers who will implement this.\n"
        "- Include API contracts, data schemas, failure modes.\n"
        "- Add code-level architecture, sequence flows, edge cases.\n"
        "- Use detailed tables and specification-style content.\n"
    ),
}


def make_design_writer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the DesignWriter agent."""
    detail = _AUDIENCE_GUIDANCE.get(config.target_audience, _AUDIENCE_GUIDANCE["mixed"])
    return autogen.AssistantAgent(
        name="DesignWriter",
        system_message=SYSTEM_PROMPT + detail,
        llm_config=build_role_llm_config("design_writer", config),
    )
