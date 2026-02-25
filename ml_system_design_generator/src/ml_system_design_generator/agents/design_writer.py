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

Return ONLY the markdown content for this section. No meta-commentary.
"""


def make_design_writer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the DesignWriter agent."""
    return autogen.AssistantAgent(
        name="DesignWriter",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("design_writer", config),
    )
