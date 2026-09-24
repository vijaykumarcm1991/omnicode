"""
Main Click CLI interface for OmniCode.
Provides interactive REPL, single-prompt execution, piped stdin support, and configuration management.
"""

import sys
import os
import asyncio
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table

from .config import (
    load_config,
    save_global_config,
    save_project_config,
    save_current_config,
    save_profile,
    list_profiles,
    set_active_profile,
    get_global_config_path,
    PROVIDER_PRESETS,
)
from .core.agent import OmniAgent
from .ui.repl import InteractiveREPL

# Reconfigure UTF-8 encoding on Windows to support emojis and unicode characters
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(legacy_windows=False)


@click.group(
    invoke_without_command=True,
    context_settings=dict(help_option_names=["-h", "--help"], allow_extra_args=True),
)
@click.option("-p", "--prompt", "prompt_opt", help="Prompt to execute in non-interactive batch mode.")
@click.option("-m", "--model", help="Target LLM model name (e.g. gpt-4o, deepseek-chat, internal-coder-70b).")
@click.option("--provider", help="Provider preset (openai, openrouter, deepseek, groq, ollama, lmstudio, vllm).")
@click.option("-b", "--base-url", help="OpenAI-compatible API base URL.")
@click.option("-k", "--api-key", help="API key for LLM endpoint.")
@click.option("-P", "--profile", help="Use a specific saved endpoint profile.")
@click.option("-s", "--save", "--save-config", is_flag=True, help="Persist these endpoint & model settings to global config (~/.omnicode/config.json).")
@click.option("--save-project", is_flag=True, help="Persist these endpoint & model settings to project config (.omnicode/config.json).")
@click.option("-y", "--yes", "--yolo", "--dangerously-skip-permissions", is_flag=True, help="Auto-approve all tool actions without confirmation.")
@click.option("--permission-mode", type=click.Choice(["ask", "auto-read", "yolo"]), help="Tool permission mode.")
@click.option("--resume", help="Resume previous session by ID or 'latest'.")
@click.option("--max-steps", type=int, help="Maximum agent steps per turn.")
@click.pass_context
def main(
    ctx,
    prompt_opt: Optional[str],
    model: Optional[str],
    provider: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    profile: Optional[str],
    save: bool,
    save_project: bool,
    yes: bool,
    permission_mode: Optional[str],
    resume: Optional[str],
    max_steps: Optional[int],
):
    """OmniCode: OpenAI-API Compatible Autonomous Coding Agent & CLI Tool."""
    # If a subcommand like 'config', 'models', or 'init' was called, pass through
    if ctx.invoked_subcommand is not None:
        return

    workspace_root = Path.cwd()
    perm_mode = "yolo" if yes else (permission_mode or None)

    config = load_config(
        workspace_root=workspace_root,
        override_model=model,
        override_base_url=base_url,
        override_api_key=api_key,
        override_provider=provider,
        override_permission_mode=perm_mode,
        override_profile=profile,
    )

    if max_steps:
        config.max_agent_steps = max_steps

    # If --save or --save-project was specified, persist to disk
    if save or save_project:
        saved_path = save_current_config(config, is_project=save_project, workspace_root=workspace_root)
        dest_str = "project config (.omnicode/config.json)" if save_project else f"global config ({saved_path})"
        console.print(f"[bold green]✓ Configuration saved to {dest_str}.[/bold green]")
        console.print(f"[dim]Endpoint: {config.base_url} | Model: {config.model}[/dim]\n")

    # Extract prompt if provided
    extra_tokens = list(ctx.args)
    if prompt_opt:
        user_query = prompt_opt
    elif extra_tokens:
        user_query = " ".join(extra_tokens).strip()
    else:
        user_query = ""

    if user_query == "-":
        user_query = sys.stdin.read().strip()

    # Create Agent
    agent = OmniAgent(
        config=config,
        workspace_root=workspace_root,
        console=console,
        session_id=resume if resume and resume != "latest" else None,
    )

    # If resume requested
    if resume:
        if resume == "latest":
            from .config import get_global_config_dir
            sess_files = sorted(
                list((get_global_config_dir() / "sessions").glob("*.json")),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if sess_files:
                agent.context_manager.load_session(sess_files[0].stem)
                console.print(f"[bold green]✓ Resumed latest session: {sess_files[0].stem}[/bold green]")
        else:
            if agent.context_manager.load_session(resume):
                console.print(f"[bold green]✓ Resumed session: {resume}[/bold green]")
            else:
                console.print(f"[yellow]Warning: Could not find session '{resume}', starting fresh.[/yellow]")

    # Run in Single-Prompt mode or Interactive REPL mode
    if user_query:
        # Non-interactive single query mode
        asyncio.run(agent.run(user_query))
    else:
        # Interactive REPL mode
        repl = InteractiveREPL(agent=agent, console=console)
        asyncio.run(repl.start())


@main.command("setup")
@click.option("-b", "--base-url", help="OpenAI-compatible endpoint base URL.")
@click.option("-k", "--api-key", help="API key for endpoint.")
@click.option("-m", "--model", help="Default model name.")
@click.option("-P", "--profile", help="Save under a named profile.")
@click.option("--project", is_flag=True, help="Save to project config instead of global.")
def setup_cmd(
    base_url: Optional[str],
    api_key: Optional[str],
    model: Optional[str],
    profile: Optional[str],
    project: bool,
):
    """Interactive endpoint setup wizard: test endpoint, pick model, and save."""
    from rich.prompt import Prompt
    from .core.llm_client import LLMClient

    console.print("\n[bold cyan]🔧 OmniCode Endpoint Setup Wizard[/bold cyan]")
    console.print("[dim]Configure your custom or cloud LLM endpoint so you don't have to re-enter flags.[/dim]\n")

    current_cfg = load_config()

    # 1. Base URL
    b_url = base_url or Prompt.ask(
        "[bold white]OpenAI-compatible Base URL[/bold white]",
        default=current_cfg.base_url or "https://api.openai.com/v1",
        console=console,
    ).strip()

    # 2. API Key
    a_key = api_key
    if a_key is None:
        def_key_display = f"{current_cfg.api_key[:6]}..." if current_cfg.api_key else ""
        prompt_label = f"[bold white]API Key[/bold white]" + (f" [dim](current: {def_key_display})[/dim]" if def_key_display else "")
        a_key_input = Prompt.ask(prompt_label, default=current_cfg.api_key or "", console=console, password=True)
        a_key = a_key_input.strip()

    test_cfg = OmniConfig(base_url=b_url, api_key=a_key, model="test")
    test_client = LLMClient(test_cfg)

    # 3. Discover models
    discovered_models = []
    with console.status(f"[cyan]Connecting to {b_url}/models to verify...[/cyan]"):
        try:
            discovered_models = asyncio.run(test_client.list_models())
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not query /v1/models ({str(e)}). You can still specify model manually.[/yellow]")

    selected_model = model
    if discovered_models:
        console.print(f"[bold green]✓ Connection successful! Found {len(discovered_models)} models.[/bold green]")
        table = Table(title="Discovered Models Preview")
        table.add_column("#", style="dim", width=4)
        table.add_column("Model ID", style="bold cyan")
        table.add_column("Owner", style="dim")
        for i, m in enumerate(discovered_models[:15], 1):
            table.add_row(str(i), m["id"], m["owned_by"])
        console.print(table)
        if len(discovered_models) > 15:
            console.print(f"[dim]... and {len(discovered_models) - 15} more models.[/dim]")

        if not selected_model:
            selected_model = Prompt.ask(
                "[bold white]Select default model[/bold white]",
                default=discovered_models[0]["id"] if discovered_models else (current_cfg.model or "gpt-4o"),
                console=console,
            ).strip()
    else:
        if not selected_model:
            selected_model = Prompt.ask(
                "[bold white]Target model name[/bold white]",
                default=current_cfg.model or "gpt-4o",
                console=console,
            ).strip()

    # 4. Save
    save_data = {
        "base_url": b_url,
        "api_key": a_key,
        "model": selected_model,
    }

    if profile:
        save_profile(profile, save_data)
        set_active_profile(profile)
        console.print(f"[bold green]✓ Saved and activated profile '{profile}'.[/bold green]")
    elif project:
        save_project_config(Path.cwd(), save_data)
        console.print(f"[bold green]✓ Saved to project config (.omnicode/config.json).[/bold green]")
    else:
        save_global_config(save_data)
        console.print(f"[bold green]✓ Saved to global config (~/.omnicode/config.json).[/bold green]")

    console.print(f"\n[bold green]🚀 Setup complete! You can now just run [bold white]omnicode[/bold white] directly.[/bold green]\n")


@main.command("login")
@click.option("-b", "--base-url", help="OpenAI-compatible endpoint base URL.")
@click.option("-k", "--api-key", help="API key for endpoint.")
@click.option("-m", "--model", help="Default model name.")
@click.option("-P", "--profile", help="Save under a named profile.")
@click.option("--project", is_flag=True, help="Save to project config instead of global.")
@click.pass_context
def login_cmd(ctx, base_url, api_key, model, profile, project):
    """Alias for 'omnicode setup'."""
    ctx.invoke(setup_cmd, base_url=base_url, api_key=api_key, model=model, profile=profile, project=project)


@main.group("profile")
def profile_group():
    """Manage named endpoint profiles (e.g. work, local, openrouter)."""
    pass


@profile_group.command("list")
def profile_list():
    """List all saved endpoint profiles."""
    profiles = list_profiles()
    cfg_path = get_global_config_path()
    active = ""
    if cfg_path.is_file():
        import json
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                active = json.load(f).get("active_profile", "")
        except Exception:
            pass

    if not profiles:
        console.print("[dim]No saved profiles found. Save one using: [bold white]omnicode profile save <name> -b <url> -m <model>[/bold white][/dim]")
        return

    table = Table(title="[bold cyan]Saved Endpoint Profiles[/bold cyan]")
    table.add_column("Active", style="bold green", width=8)
    table.add_column("Profile Name", style="bold cyan")
    table.add_column("Base URL", style="white")
    table.add_column("Model", style="green")

    for name, data in profiles.items():
        is_act = "● Active" if name == active else ""
        table.add_row(is_act, name, data.get("base_url", ""), data.get("model", ""))

    console.print(table)


@profile_group.command("save")
@click.argument("name")
@click.option("-b", "--base-url", required=True, help="OpenAI-compatible base URL.")
@click.option("-k", "--api-key", default="", help="API key.")
@click.option("-m", "--model", required=True, help="Default model name.")
@click.option("--provider", default="custom", help="Provider name tag.")
def profile_save_cmd(name: str, base_url: str, api_key: str, model: str, provider: str):
    """Save a new named profile."""
    save_profile(name, {
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "provider": provider,
    })
    console.print(f"[bold green]✓ Profile '{name}' saved.[/bold green]")
    console.print(f"[dim]Use it with: omnicode -P {name} or omnicode profile use {name}[/dim]")


@profile_group.command("use")
@click.argument("name")
def profile_use_cmd(name: str):
    """Set a profile as the active default."""
    if set_active_profile(name):
        console.print(f"[bold green]✓ Switched active profile to '{name}'.[/bold green]")
    else:
        console.print(f"[bold red]Profile '{name}' not found. Run 'omnicode profile list' to see available profiles.[/bold red]")


@main.command("init")
@click.option("--global-config", is_flag=True, help="Initialize global config file (~/.omnicode/config.json).")
def init_cmd(global_config: bool):
    """Initialize project rules (.omnicoderules) or configuration."""
    if global_config:
        cfg_path = get_global_config_path()
        if cfg_path.is_file():
            console.print(f"[yellow]Global config already exists at: {cfg_path}[/yellow]")
            return
        save_global_config({
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "permission_mode": "auto-read",
        })
        console.print(f"[bold green]✓ Created global config at {cfg_path}[/bold green]")
        return

    # Project init
    rules_file = Path.cwd() / ".omnicoderules"
    if not rules_file.exists():
        template = """# OmniCode Project Rules

## Coding Standards & Conventions
- Write clean, modular, well-documented code.
- Follow existing project style and patterns.
- Ensure all tests pass before completing tasks.

## Build & Test Commands
# - Test: pytest
# - Lint: ruff check .
# - Run: python -m src.main
"""
        with open(rules_file, "w", encoding="utf-8") as f:
            f.write(template)
        console.print(f"[bold green]✓ Created .omnicoderules in current project.[/bold green]")
    else:
        console.print("[yellow].omnicoderules already exists in workspace.[/yellow]")

    # Create .omnicode directory
    proj_dir = Path.cwd() / ".omnicode"
    proj_dir.mkdir(exist_ok=True)
    console.print("[bold green]✓ OmniCode workspace initialized.[/bold green]")


@main.command("models")
@click.option("-r", "--remote", "--fetch", "fetch_remote", is_flag=True, help="Fetch live models directly from the /v1/models API endpoint.")
@click.option("-b", "--base-url", help="Override base URL for model discovery.")
@click.option("-k", "--api-key", help="Override API key for model discovery.")
@click.option("--provider", help="Provider preset to query.")
def models_cmd(
    fetch_remote: bool = False,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
):
    """List supported provider presets and discover models from /v1/models."""
    cfg = load_config(
        override_base_url=base_url,
        override_api_key=api_key,
        override_provider=provider,
    )

    if fetch_remote:
        from .core.llm_client import LLMClient
        client = LLMClient(cfg)
        try:
            with console.status(f"[bold cyan]Querying {cfg.base_url}/models ...[/bold cyan]"):
                models = asyncio.run(client.list_models())

            if not models:
                console.print(f"[yellow]No models returned from {cfg.base_url}/models.[/yellow]")
                return

            table = Table(title=f"[bold cyan]Live Discovered Models ({cfg.base_url}/models)[/bold cyan]")
            table.add_column("Model ID", style="bold green")
            table.add_column("Owner", style="cyan")

            for m in models:
                table.add_row(m["id"], m["owned_by"])

            console.print(table)
            console.print(f"[dim]Total: {len(models)} models available on endpoint.[/dim]")
            return
        except Exception as e:
            console.print(f"[bold red]Discovery Error:[/bold red] {str(e)}")
            console.print("[dim]Falling back to preset list...[/dim]\n")

    # Display provider presets table
    table = Table(title="[bold cyan]Supported Provider Presets[/bold cyan]")
    table.add_column("Provider", style="bold cyan")
    table.add_column("Default Model", style="green")
    table.add_column("Base URL", style="dim")
    table.add_column("Key Models", style="white")

    for name, data in PROVIDER_PRESETS.items():
        models_str = ", ".join(data.get("models", [])[:3])
        table.add_row(name, data.get("default_model", ""), data.get("base_url", ""), models_str)

    console.print(table)
    console.print("[dim]Tip: Run [bold white]omnicode models --fetch[/bold white] (or [bold white]/models[/bold white] in REPL) to discover live models from your server.[/dim]")


@main.group("config")
def config_group():
    """Manage global and project OmniCode configuration."""
    pass


@config_group.command("list")
def config_list():
    """List current effective configuration."""
    cfg = load_config()
    table = Table(title="[bold cyan]OmniCode Configuration[/bold cyan]")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="bold white")

    table.add_row("provider", cfg.provider)
    table.add_row("model", cfg.model)
    table.add_row("base_url", cfg.base_url)
    table.add_row("api_key", f"{cfg.api_key[:6]}..." if cfg.api_key else "[dim]<not set>[/dim]")
    table.add_row("permission_mode", cfg.permission_mode)
    table.add_row("temperature", str(cfg.temperature))
    table.add_row("context_window", str(cfg.context_window))
    table.add_row("max_agent_steps", str(cfg.max_agent_steps))

    console.print(table)


@config_group.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--project", is_flag=True, help="Save to project config (.omnicode/config.json) instead of global.")
def config_set(key: str, value: str, project: bool):
    """Set a configuration property."""
    data = {key: value}
    if project:
        save_project_config(Path.cwd(), data)
        console.print(f"[bold green]✓ Set '{key}' = '{value}' in project config.[/bold green]")
    else:
        save_global_config(data)
        console.print(f"[bold green]✓ Set '{key}' = '{value}' in global config.[/bold green]")


if __name__ == "__main__":
    main()
