"""CitationAgent — validates citations against .bib file.

CRITICAL: The LLM must NEVER "fix" citation keys that look like typos.
Keys must match .bib exactly. The agent only flags mismatches;
diff_checker.py validates keys deterministically as a safety net.
"""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT = """\
You are a citation validation specialist for LaTeX research articles.

You receive:
1. The full LaTeX document
2. A list of valid citation keys from the .bib file

Your job is to:
- Flag any \\cite{} keys that do NOT appear in the .bib file
- Flag any .bib entries that are never cited (optional references)
- Check that citation formatting is consistent (\\cite vs \\citep vs \\citet)
- Verify citations appear in appropriate contexts

CRITICAL RULES:
- NEVER modify citation keys. Even if a key looks like a typo, report it as-is.
- NEVER add new citations that weren't in the source.
- NEVER remove existing citations.
- Only report mismatches — the user decides what to fix.

Output a JSON report:
{
  "Reviewer": "CitationAgent",
  "Review": "- finding 1; - finding 2",
  "missing_keys": ["key_not_in_bib"],
  "uncited_entries": ["bib_entry_never_cited"]
}
"""


def make_citation_agent(config: ProjectConfig) -> autogen.AssistantAgent:
    """Create the CitationAgent."""
    return autogen.AssistantAgent(
        name="CitationAgent",
        system_message=SYSTEM_PROMPT,
        llm_config=build_role_llm_config("citation_agent", config),
    )
