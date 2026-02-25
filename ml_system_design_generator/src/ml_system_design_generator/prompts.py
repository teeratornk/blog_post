"""Interactive Rich prompts for missing configuration."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

from .tools.template_loader import list_available_styles

console = Console()


def prompt_style() -> str:
    """Prompt user to choose a design doc style."""
    styles = list_available_styles()
    console.print("\n[bold]Choose a design document style:[/]")
    for i, s in enumerate(styles, 1):
        console.print(f"  {i}. {s}")

    while True:
        choice = Prompt.ask("Style number or name", default="2")
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(styles):
                return styles[idx]
        elif choice in styles:
            return choice
        console.print(f"[yellow]Invalid choice. Pick 1-{len(styles)} or a style name.[/]")


def prompt_infrastructure_provider() -> str:
    """Prompt user for infrastructure provider."""
    providers = ["azure", "aws", "gcp", "on_prem", "hybrid", "local"]
    console.print("\n[bold]Target infrastructure provider:[/]")
    for i, p in enumerate(providers, 1):
        console.print(f"  {i}. {p}")

    choice = Prompt.ask("Provider number or name", default="1")
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(providers):
            return providers[idx]
    if choice in providers:
        return choice
    return choice  # free text


def prompt_tech_stack() -> list[str]:
    """Prompt user for tech stack (comma-separated)."""
    raw = Prompt.ask(
        "\n[bold]Tech stack[/] (comma-separated)",
        default="python, pytorch, kubernetes",
    )
    return [s.strip() for s in raw.split(",") if s.strip()]


def prompt_max_pages(style_default: int | None = None) -> int | None:
    """Prompt user for max pages."""
    default_str = str(style_default) if style_default else "none"
    raw = Prompt.ask(f"\n[bold]Max pages[/]", default=default_str)
    if raw.lower() in ("none", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        return style_default


def prompt_team_size() -> int | None:
    """Prompt user for team size."""
    raw = Prompt.ask("\n[bold]Team size[/]", default="none")
    if raw.lower() in ("none", ""):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def prompt_timeline() -> str | None:
    """Prompt user for timeline."""
    raw = Prompt.ask("\n[bold]Timeline[/] (e.g. '3 months')", default="none")
    if raw.lower() in ("none", ""):
        return None
    return raw


def prompt_constraints() -> list[str]:
    """Prompt user for constraints (comma-separated)."""
    raw = Prompt.ask(
        "\n[bold]Constraints[/] (comma-separated, e.g. 'GDPR, latency < 100ms')",
        default="none",
    )
    if raw.lower() in ("none", ""):
        return []
    return [s.strip() for s in raw.split(",") if s.strip()]


def prompt_target_audience() -> str:
    """Prompt user for target audience."""
    audiences = ["engineering", "leadership", "mixed"]
    choice = Prompt.ask(
        "\n[bold]Target audience[/]",
        choices=audiences,
        default="engineering",
    )
    return choice


def run_interactive_prompts(config_dict: dict) -> dict:
    """Run interactive prompts for missing config fields.

    Modifies and returns config_dict with user-provided values.
    """
    console.print("\n[bold blue]Interactive Configuration[/]")
    console.print("Fill in missing fields (press Enter for defaults).\n")

    if not config_dict.get("style"):
        config_dict["style"] = prompt_style()

    infra = config_dict.get("infrastructure", {})
    if isinstance(infra, dict) and not infra.get("provider"):
        infra["provider"] = prompt_infrastructure_provider()
        config_dict["infrastructure"] = infra

    if not config_dict.get("tech_stack"):
        config_dict["tech_stack"] = prompt_tech_stack()

    if config_dict.get("max_pages") is None:
        from .tools.template_loader import get_style_max_pages
        style_default = get_style_max_pages(config_dict.get("style", "amazon_6page"))
        config_dict["max_pages"] = prompt_max_pages(style_default)

    if config_dict.get("team_size") is None:
        config_dict["team_size"] = prompt_team_size()

    if not config_dict.get("timeline"):
        config_dict["timeline"] = prompt_timeline()

    if not config_dict.get("constraints"):
        config_dict["constraints"] = prompt_constraints()

    if not config_dict.get("target_audience"):
        config_dict["target_audience"] = prompt_target_audience()

    return config_dict
