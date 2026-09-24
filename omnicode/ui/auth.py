"""
Interactive Authentication and Provider Configuration Wizard for OmniCode.
Supports known providers, custom endpoints, live /v1/models discovery, and auto context limit detection.
"""

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from rich.panel import Panel

from ..config import (
    OmniConfig,
    KNOWN_PROVIDERS,
    detect_context_limit,
    save_current_config,
    save_profile,
    set_active_profile,
    load_config,
)
from ..core.llm_client import LLMClient
from .model_browser import browse_models_interactive


async def run_auth_wizard(
    console: Console,
    current_config: Optional[OmniConfig] = None,
    workspace_root: Optional[Path] = None,
) -> OmniConfig:
    """Run interactive /auth wizard to configure provider, credentials, model, and context window."""
    root = workspace_root or Path.cwd()
    cfg = current_config or load_config(workspace_root=root)

    console.print("\n[bold cyan]🔐 OmniCode Provider & Authentication Setup[/bold cyan]")
    console.print("[dim]Select a provider or enter a custom OpenAI-compatible endpoint.[/dim]\n")

    # Build provider options table
    table = Table(title="[bold]Select Provider[/bold]", show_header=True, header_style="bold magenta")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Provider", style="bold white", width=22)
    table.add_column("API URL (Configured Automatically)", style="dim")

    provider_keys = list(KNOWN_PROVIDERS.keys())
    for idx, key in enumerate(provider_keys, 1):
        info = KNOWN_PROVIDERS[key]
        table.add_row(str(idx), info["name"], info["base_url"])

    custom_opt_num = len(provider_keys) + 1
    table.add_row(str(custom_opt_num), "[bold yellow]Custom Provider[/bold yellow]", "[yellow]Enter your own Base URL & Key[/yellow]")

    console.print(table)

    choices = [str(i) for i in range(1, custom_opt_num + 1)]
    choice = Prompt.ask(
        "\n[bold white]Choose provider number[/bold white]",
        choices=choices,
        default="1",
        console=console,
    )

    choice_idx = int(choice)
    if choice_idx <= len(provider_keys):
        p_key = provider_keys[choice_idx - 1]
        p_info = KNOWN_PROVIDERS[p_key]
        provider_name = p_key
        base_url = p_info["base_url"]
        requires_key = p_info["requires_key"]

        console.print(f"\n[green]✓ Selected:[/green] [bold]{p_info['name']}[/bold] ([dim]{base_url}[/dim])")

        # Prompt for key
        if requires_key:
            current_preview = f"{cfg.api_key[:6]}..." if cfg.api_key and cfg.base_url == base_url else ""
            prompt_label = "[bold white]Enter API Key[/bold white]" + (f" [dim](press enter to keep: {current_preview})[/dim]" if current_preview else "")
            key_input = Prompt.ask(prompt_label, default=cfg.api_key if current_preview else "", console=console, password=True)
            api_key = key_input.strip()
        else:
            console.print("[dim]API Key is typically optional for this local provider.[/dim]")
            key_input = Prompt.ask("[bold white]API Key (optional, press enter to leave empty)[/bold white]", default="", console=console, password=True)
            api_key = key_input.strip() or "EMPTY"
    else:
        # Custom Provider
        provider_name = "custom"
        console.print("\n[bold yellow]Configuring Custom Provider[/bold yellow]")
        base_url = Prompt.ask(
            "[bold white]Enter OpenAI-compatible API Base URL[/bold white]",
            default=cfg.base_url or "https://api.openai.com/v1",
            console=console,
        ).strip()
        # Clean trailing slashes
        base_url = base_url.rstrip("/")

        current_preview = f"{cfg.api_key[:6]}..." if cfg.api_key and cfg.base_url == base_url else ""
        prompt_label = "[bold white]Enter API Key[/bold white]" + (f" [dim](press enter to keep: {current_preview})[/dim]" if current_preview else "")
        key_input = Prompt.ask(prompt_label, default=cfg.api_key if current_preview else "", console=console, password=True)
        api_key = key_input.strip() or "EMPTY"

    # Temporary config for model discovery
    test_cfg = OmniConfig(provider=provider_name, base_url=base_url, api_key=api_key, model="discovery")
    client = LLMClient(test_cfg)

    # 3. Model Discovery via /v1/models
    discovered_models: List[Dict[str, Any]] = []
    with console.status(f"[bold cyan]Connecting to {base_url}/models to discover models...[/bold cyan]"):
        try:
            discovered_models = await client.list_models()
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not auto-discover models from {base_url}/models ({str(e)}).[/yellow]")

    selected_model = ""
    context_window = 128000

    if discovered_models:
        console.print(f"[bold green]✓ Discovered {len(discovered_models)} models from endpoint:[/bold green]\n")
        selected_model, context_window = browse_models_interactive(
            discovered_models=discovered_models,
            console=console,
            default_model=cfg.model or "default",
            page_size=15,
        )
    else:
        selected_model = Prompt.ask(
            "[bold white]Enter model name[/bold white]",
            default=cfg.model or "default",
            console=console,
        ).strip()
        context_window = detect_context_limit(selected_model)

    console.print(f"[dim green]✓ Selected model: [bold]{selected_model}[/bold] (Context limit: [bold]{context_window:,}[/bold] tokens).[/dim green]")


    # Create new config object
    new_cfg = OmniConfig(
        provider=provider_name,
        base_url=base_url,
        api_key=api_key,
        model=selected_model,
        context_window=context_window,
        permission_mode=cfg.permission_mode,
        temperature=cfg.temperature,
    )

    # 4. Save destination
    dest = Prompt.ask(
        "\n[bold white]Save destination[/bold white]",
        choices=["global", "project", "profile"],
        default="global",
        console=console,
    )

    if dest == "global":
        save_path = save_current_config(new_cfg, is_project=False)
        console.print(f"[bold green]✓ Configuration saved to global config ({save_path}).[/bold green]")
    elif dest == "project":
        save_path = save_current_config(new_cfg, is_project=True, workspace_root=root)
        console.print(f"[bold green]✓ Configuration saved to project config ({save_path}).[/bold green]")
    elif dest == "profile":
        prof_name = Prompt.ask("[bold white]Profile name[/bold white]", default="default", console=console).strip()
        save_profile(prof_name, {
            "provider": provider_name,
            "base_url": base_url,
            "api_key": api_key,
            "model": selected_model,
            "context_window": context_window,
        })
        set_active_profile(prof_name)
        console.print(f"[bold green]✓ Saved and activated profile '{prof_name}'.[/bold green]")

    console.print(f"\n[bold green]🚀 Ready! Connected to [cyan]{base_url}[/cyan] using model [bold cyan]{selected_model}[/bold cyan].[/bold green]\n")
    return new_cfg
