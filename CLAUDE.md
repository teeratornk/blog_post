# CLAUDE.md

## Project Overview

Multi-Agent Blogpost Generator — a Streamlit web app that orchestrates 9+ specialized AI agents via AG2 (AutoGen) and Azure OpenAI to collaboratively generate, review, and refine blog posts.

## Tech Stack

- **Python 3.10+**
- **Streamlit** — web UI and session state
- **AG2/AutoGen** (`autogen`) — multi-agent orchestration
- **Azure OpenAI** — LLM backend (gpt-5.2, O3, gpt-image-1)
- **Pydantic v2** — structured output validation
- **python-dotenv** — environment config

## Project Structure

```
app.py        — Main Streamlit application (UI, orchestration, image generation, post-processing)
agents.py     — Agent definitions, nested chat registration, reviewer/image agent setup
config.py     — Azure OpenAI config, role-based model mapping, LLM config builders
utils.py      — ReviewModel (Pydantic), JSON parsing/repair, reviewer defaults
```

## Key Architecture Decisions

- Agents are created in `agents.py:make_agents()` which returns `(writer, critic)`. The critic registers nested chats with all enabled reviewers.
- Reviewers output structured JSON: `{"Reviewer": "Name", "Review": "- point 1; - point 2"}`. Parsing is handled by `utils.py:validate_review()` with multi-stage fallback (direct parse → repair → heuristic extraction).
- Config uses a `Config` class singleton (`_env`) in `config.py`. Role-to-model mapping is in `build_role_llm_config()`.
- Image generation uses Azure DALL-E via direct REST calls, not the AG2 framework.

## Environment Variables

Required in `.env`:
```
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=
AZURE_OPENAI_ENDPOINT=
```

Optional (fall back to `AZURE_OPENAI_MODEL_DEFAULT`, then `gpt-4`):
```
AZURE_OPENAI_MODEL_DEFAULT=
AZURE_OPENAI_MODEL_WRITER=
AZURE_OPENAI_MODEL_EDITOR=
AZURE_OPENAI_MODEL_CRITIC=
AZURE_OPENAI_MODEL_T2I=
```

## Running the App

```bash
uv sync
uv run streamlit run app.py
```

## Common Patterns

- Agent creation follows the pattern: `autogen.AssistantAgent(name=..., system_message=..., llm_config=build_role_llm_config(role))`.
- Reviewer agents are conditionally created via `_maybe()` in `agents.py` based on `enabled_reviewers` dict.
- Structured output is enforced by setting `agent.llm_config["response_format"] = ReviewModel`.
- Nested chats use `reflection_message()` for context passing and `build_summary_args()` for schema-based summaries.

## Style Guidelines

- Keep agent system prompts concise and directive.
- All reviewer agents must return the standard `{"Reviewer": "...", "Review": "..."}` JSON format.
- Use `build_role_llm_config(role)` for agent LLM configs — never hardcode model names.
- Streamlit session state keys are used extensively in `app.py`; check existing keys before adding new ones.
- Never commit `.env` files or API keys.
