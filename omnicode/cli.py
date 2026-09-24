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
    OmniConfig,
    load_config,
    save_global_config,
    save_project_config,
    save_current_config,
    save_profile,
    list_profiles,
    set_active_profile,
    get_global_config_path,
    KNOWN_PROVIDERS,
    PROVIDER_PRESETS,
)
from .core.agent import OmniAgent
from .core.context import list_saved_sessions, delete_saved_session
from .ui.repl import InteractiveREPL
from .ui.model_browser import build_models_table, browse_models_interactive, filter_models
from .utils.system_info import prevent_windows_quick_edit


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
@click.option("-r", "--resume", "resume", is_flag=False, flag_value="latest", help="Resume previous session by ID, index, or 'latest'.")
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
    prevent_windows_quick_edit()

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

    # If not configured (no base_url or model) and running interactive mode, launch auth wizard
    if not user_query and (not config.base_url or not config.model):
        from .ui.auth import run_auth_wizard
        console.print("[bold yellow]⚡ No LLM provider or model configured yet.[/bold yellow]")
        config = asyncio.run(run_auth_wizard(console=console, current_config=config, workspace_root=workspace_root))

    # Create Agent
    agent = OmniAgent(
        config=config,
        workspace_root=workspace_root,
        console=console,
        session_id=resume if resume and resume != "latest" else None,
    )

    # If resume requested
    if resume:
        if agent.context_manager.load_session(resume):
            count = len(agent.context_manager.messages)
            console.print(f"[bold green]✓ Resumed session '{agent.context_manager.session_id}' ({count} messages, Model: {agent.config.model}).[/bold green]\n")
        else:
            console.print(f"[yellow]Warning: Could not find session matching '{resume}', starting fresh session.[/yellow]\n")

    # Run in Single-Prompt mode or Interactive REPL mode
    if user_query:
        if not config.base_url or not config.model:
            console.print("[bold red]Error: No provider or model configured. Run 'omnicode auth' first or specify -b and -m.[/bold red]")
            return
        # Non-interactive single query mode
        asyncio.run(agent.run(user_query))
    else:
        # Interactive REPL mode
        repl = InteractiveREPL(agent=agent, console=console)
        asyncio.run(repl.start())


@main.command("sessions")
@click.option("-d", "--delete", help="Delete a saved session by ID or number.")
@click.option("-w", "--workspace-only", is_flag=True, help="Only show sessions from current workspace.")
def sessions_cmd(delete: Optional[str], workspace_only: bool):
    """List or manage saved conversation sessions."""
    if delete:
        if delete_saved_session(delete):
            console.print(f"[bold green]✓ Deleted session '{delete}'.[/bold green]")
        else:
            console.print(f"[bold red]Could not find session matching '{delete}'.[/bold red]")
        return

    ws = Path.cwd() if workspace_only else None
    sessions = list_saved_sessions(workspace_filter=ws)
    if not sessions:
        console.print("[dim]No saved sessions found. Sessions are saved automatically as you chat.[/dim]")
        return

    table = Table(title="[bold cyan]Saved OmniCode Conversation Sessions[/bold cyan]", show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Session ID", style="bold cyan")
    table.add_column("Date / Time", style="dim")
    table.add_column("Model", style="green")
    table.add_column("Msgs", style="white", justify="right", width=5)
    table.add_column("Initial Prompt / Goal", style="white")

    for i, s in enumerate(sessions[:25], 1):
        table.add_row(
            str(i),
            s["session_id"],
            s["timestamp"],
            s["model"],
            str(s["message_count"]),
            s["preview"],
        )

    console.print(table)
    console.print("\n[dim]Resume a session with: [bold white]omnicode resume <#>[/bold white] or [bold white]omnicode -r <session_id>[/bold white][/dim]")


@main.command("resume")
@click.argument("session_id", required=False, default="latest")
@click.pass_context
def resume_cmd(ctx, session_id: str):
    """Resume an existing conversation session by ID or index number (default: latest)."""
    # Forward to main with resume parameter
    ctx.invoke(main, resume=session_id)


@main.command("history")
@click.pass_context
def history_cmd(ctx):
    """Alias for 'omnicode sessions'."""
    ctx.invoke(sessions_cmd, delete=None, workspace_only=False)



@main.command("auth")
def auth_cmd():
    """Interactive authentication wizard: select known provider or custom endpoint, enter key, and auto-discover models."""
    from .ui.auth import run_auth_wizard
    asyncio.run(run_auth_wizard(console=console, workspace_root=Path.cwd()))


@main.command("setup")
def setup_cmd():
    """Alias for 'omnicode auth'."""
    auth_cmd()


@main.command("login")
def login_cmd():
    """Alias for 'omnicode auth'."""
    auth_cmd()



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
@click.option("-s", "--search", default="", help="Search/filter models by keyword.")
@click.option("-p", "--page", default=1, type=int, help="Page number to view.")
@click.option("--page-size", default=15, type=int, help="Number of models per page (default: 15).")
@click.option("-i", "--interactive", is_flag=True, help="Open interactive scrolling & search browser.")
@click.option("-a", "--all", "show_all", is_flag=True, help="Display all discovered models without pagination.")
def models_cmd(
    fetch_remote: bool = False,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    search: str = "",
    page: int = 1,
    page_size: int = 15,
    interactive: bool = False,
    show_all: bool = False,
):
    """List supported providers and discover models from /v1/models with pagination."""
    cfg = load_config(
        override_base_url=base_url,
        override_api_key=api_key,
        override_provider=provider,
    )

    # If base_url or fetch flag is specified, discover models from endpoint
    if fetch_remote or base_url or cfg.base_url:
        from .core.llm_client import LLMClient
        client = LLMClient(cfg)
        try:
            with console.status(f"[bold cyan]Querying {cfg.base_url}/models ...[/bold cyan]"):
                models = asyncio.run(client.list_models())

            if not models:
                console.print(f"[yellow]No models returned from {cfg.base_url}/models.[/yellow]")
                return

            if interactive:
                browse_models_interactive(
                    discovered_models=models,
                    console=console,
                    default_model=cfg.model,
                    page_size=page_size,
                )
                return

            effective_page_size = len(models) if show_all else page_size
            table, total_pages, total_count = build_models_table(
                models=models,
                page=page,
                page_size=effective_page_size,
                query=search,
                title_prefix=f"Live Discovered Models ({cfg.base_url}/models)",
            )
            console.print(table)

            if total_pages > 1 and not show_all:
                console.print(
                    f"[dim]Tip: Use [bold white]omnicode models -p 2[/bold white] for next page, "
                    f"[bold white]-s <name>[/bold white] to search, or [bold white]-i[/bold white] for interactive browser.[/dim]"
                )
            return
        except Exception as e:
            console.print(f"[bold red]Discovery Error:[/bold red] {str(e)}")
            console.print("[dim]Falling back to known providers list...[/dim]\n")

    # Display known providers table
    table = Table(title="[bold cyan]Supported LLM Providers[/bold cyan]", show_header=True, header_style="bold magenta")
    table.add_column("Provider Key", style="bold cyan")
    table.add_column("Provider Name", style="white")
    table.add_column("Preconfigured Base URL", style="dim")
    table.add_column("API Key Required", style="green")

    for key, data in KNOWN_PROVIDERS.items():
        req_str = "Yes" if data.get("requires_key", True) else "Optional (Local)"
        table.add_row(key, data.get("name", key), data.get("base_url", ""), req_str)

    console.print(table)
    console.print("[dim]Tip: Run [bold white]omnicode auth[/bold white] to connect and auto-discover models from any provider or custom server.[/dim]")


@main.command("uninstall")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def uninstall_cmd(yes: bool):
    """Clean up OmniCode configuration, cached data, and print full uninstallation steps."""
    import shutil
    global_dir = Path.home() / ".omnicode"
    local_dir = Path.cwd() / ".omnicode"
    local_rules = Path.cwd() / ".omnicoderules"

    console.print("[bold red]⚠️ OmniCode Uninstallation Assistant[/bold red]\n")
    console.print("This will remove OmniCode configuration files, saved profiles, and history:")
    console.print(f"  • Global data directory: [cyan]{global_dir}[/cyan]")
    if local_dir.exists():
        console.print(f"  • Local workspace config: [cyan]{local_dir}[/cyan]")
    if local_rules.exists():
        console.print(f"  • Local workspace rules: [cyan]{local_rules}[/cyan]")

    if not yes:
        from rich.prompt import Confirm
        proceed = Confirm.ask("\n[bold red]Proceed with deleting configuration and data?[/bold red]", console=console, default=False)
        if not proceed:
            console.print("[yellow]Uninstallation cancelled.[/yellow]")
            return

    # Delete global dir
    if global_dir.exists():
        try:
            shutil.rmtree(global_dir)
            console.print(f"[bold green]✓ Deleted global directory: {global_dir}[/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not remove {global_dir}: {e}[/yellow]")

    # Delete local dir
    if local_dir.exists():
        try:
            shutil.rmtree(local_dir)
            console.print(f"[bold green]✓ Deleted local workspace config: {local_dir}[/bold green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Could not remove {local_dir}: {e}[/yellow]")

    console.print("\n[bold cyan]📦 To completely remove the OmniCode package and executable from your system:[/bold cyan]")
    console.print("  [bold white]pip uninstall omnicode -y[/bold white]")
    console.print("\n[dim]If you cloned the source code, you can now safely delete the repository folder:[/dim]")
    console.print("  [dim]Windows: rmdir /s /q omnicode[/dim]")
    console.print("  [dim]Linux/macOS: rm -rf omnicode[/dim]\n")



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
