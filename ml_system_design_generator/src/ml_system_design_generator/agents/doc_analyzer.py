"""DocAnalyzer agent — reads and summarizes source documents."""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import DocumentSummary, ProjectConfig

SYSTEM_PROMPT = """\
You are a technical document analyst specializing in ML systems and operations.

Read the document thoroughly and produce a structured summary as a JSON object
matching the DocumentSummary schema:
{{
  "file_path": "path/to/file.md",
  "title": "Document Title",
  "key_topics": ["topic1", "topic2"],
  "personas": ["operator", "engineer"],
  "word_count": 1500,
  "summary": "Concise 2-3 sentence summary of the document content."
}}

Focus on:
- Key technical concepts, systems, and processes described
- Personas and stakeholders mentioned
- Data flows, decision matrices, and operational procedures
- Relationships to other potential system components

Return ONLY valid JSON matching the schema. No markdown fences or explanations.
"""


def make_doc_analyzer(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the DocAnalyzer agent."""
    agent = autogen.AssistantAgent(
        name="DocAnalyzer",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("doc_analyzer", config),
    )
    if isinstance(agent.llm_config, dict):
        agent.llm_config["response_format"] = DocumentSummary
    return agent
