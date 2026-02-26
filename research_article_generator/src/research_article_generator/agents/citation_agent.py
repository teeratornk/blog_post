"""CitationAgent — validates citations against .bib file.

The agent only flags mismatches between \\cite{} keys and .bib entries;
diff_checker.py validates keys deterministically as a safety net.
"""

from __future__ import annotations

import autogen

from ..config import build_role_llm_config
from ..models import ProjectConfig

SYSTEM_PROMPT = """\
You are a citation validation specialist for LaTeX research articles.

You receive:
1. A LaTeX section
2. A list of valid citation keys from the .bib file

Your job is to:
- Flag any \\cite{} keys that do not appear in the .bib file.
- Flag any .bib entries that are not cited (optional references).
- Check that citation formatting is consistent (\\cite vs \\citep vs \\citet).
- Verify citations appear in appropriate contexts.

Constraints:
- Do not modify citation keys. Report them exactly as they appear.
- Do not add new citations that were not in the source.
- Do not remove existing citations.
- Only report mismatches; the user decides what to fix.

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
