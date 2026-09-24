"""
Terminal UI renderer for OmniCode using Rich.
Renders banners, streaming markdown, reasoning panels, tool execution cards, and status metrics.
"""

import time
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from rich.syntax import Syntax
from rich.live import Live
from rich.rule import Rule
from rich.align import Align


BANNER_ART = r"""[bold cyan]
  ___                      _ _____           _      
 / _ \ _ __ ___  _ __  _  (_) ____|___   __| | ___  
| | | | '_ ` _ \| '_ \| | | | |   / _ \ / _` |/ _ \ 
| |_| | | | | | | | | | |_| | |__| (_) | (_| |  __/ 
 \___/|_| |_| |_|_| |_|\__,_|\_____\___/ \__,_|\___| 
[/bold cyan]"""


class TerminalRenderer:
    """Rich terminal renderer for agent UI interactions."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console(legacy_windows=False)

    def print_banner(
        self,
        provider: str,
        model: str,
        base_url: str,
        permission_mode: str,
        branch: Optional[str] = None,
        cwd: Optional[str] = None,
    ):
        """Display stylish welcome banner with session metadata."""
        self.console.print(BANNER_ART)

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column(style="white")

        table.add_row("Model:", f"[bold green]{model}[/bold green] [dim]({provider})[/dim]")
        table.add_row("Endpoint:", f"[dim]{base_url}[/dim]")
        table.add_row("Permissions:", f"[bold yellow]{permission_mode}[/bold yellow]")
        if branch:
            table.add_row("Git Branch:", f"[bold magenta]🌿 {branch}[/bold magenta]")
        if cwd:
            table.add_row("Workspace:", f"[dim]{cwd}[/dim]")

        self.console.print(
            Panel(
                table,
                title="[bold white]OmniCode • Autonomous AI Coding Agent[/bold white]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        self.console.print(
            "[dim]Type [bold white]/help[/bold white] for commands, [bold white]@path[/bold white] to reference files, or ask any coding task.[/dim]\n"
        )

    def print_user_prompt(self, prompt: str):
        """Render user input box."""
        self.console.print(f"\n[bold green]❯[/bold green] [bold white]{prompt}[/bold white]")

    def print_reasoning(self, reasoning: str):
        """Render collapsible reasoning / chain-of-thought block."""
        if not reasoning.strip():
            return
        panel = Panel(
            f"[dim italic]{reasoning.strip()}[/dim italic]",
            title="[dim cyan]🧠 Thinking Process[/dim cyan]",
            border_style="dim cyan",
            padding=(0, 1),
        )
        self.console.print(panel)

    def print_assistant_message(self, content: str):
        """Render assistant markdown response."""
        if not content.strip():
            return
        md = Markdown(content)
        self.console.print(md)

    def render_tool_start(self, tool_name: str, args: Dict[str, Any]):
        """Render start of a tool call."""
        arg_str = ", ".join(f"[cyan]{k}[/cyan]=[dim]{repr(v)[:50]}[/dim]" for k, v in args.items())
        if len(arg_str) > 120:
            arg_str = arg_str[:120] + "..."
        self.console.print(f"  [bold yellow]⚡ Tool Call:[/bold yellow] [bold cyan]{tool_name}[/bold cyan]({arg_str})")

    def render_tool_result(self, tool_name: str, success: bool, output: str, duration_sec: float = 0.0):
        """Render the output of a tool execution."""
        status_badge = "[bold green]✓ SUCCESS[/bold green]" if success else "[bold red]✗ FAILED[/bold red]"
        time_str = f" [dim]({duration_sec:.2f}s)[/dim]" if duration_sec > 0 else ""

        # Limit displayed output in UI
        preview_output = output.strip()
        if len(preview_output) > 600:
            preview_output = preview_output[:600] + f"\n... [Truncated: {len(output)} chars total]"

        border_color = "green" if success else "red"
        self.console.print(
            Panel(
                preview_output or "[dim]No output[/dim]",
                title=f"{status_badge} [bold white]{tool_name}[/bold white]{time_str}",
                border_style=border_color,
                padding=(0, 1),
            )
        )

    def print_step_divider(self, step_num: int):
        """Render subtle divider between agent execution iterations."""
        self.console.print(Rule(f"[dim]Step {step_num}[/dim]", style="dim"))

    def print_token_summary(
        self, prompt_tokens: int, completion_tokens: int, cost_usd: float
    ):
        """Render token usage and cost metrics."""
        total = prompt_tokens + completion_tokens
        cost_str = f" • Est. Cost: [green]${cost_usd:.4f}[/green]" if cost_usd > 0 else ""
        self.console.print(
            f"\n[dim]Tokens: [bold]{total:,}[/bold] (in: {prompt_tokens:,}, out: {completion_tokens:,}){cost_str}[/dim]"
        )

    def print_help(self):
        """Display slash commands reference table."""
        table = Table(title="[bold cyan]OmniCode Commands[/bold cyan]", show_header=True, header_style="bold magenta")
        table.add_column("Command", style="cyan", width=18)
        table.add_column("Description", style="white")

        commands = [
            ("/help", "Show this help table and list of commands"),
            ("/clear", "Clear screen and reset conversation history"),
            ("/compact", "Compact conversation context to free tokens"),
            ("/auth", "Configure LLM provider, API key, and auto-discover models"),
            ("/models", "Discover and list models from server /v1/models"),
            ("/model [name]", "Show or switch active LLM model"),
            ("/provider [name]", "Show or switch provider preset (openai/openrouter/deepseek/groq/ollama/etc.)"),
            ("/mode [mode]", "Switch permissions mode (ask / auto-read / yolo)"),
            ("/save [project]", "Save current endpoint and model settings to config"),
            ("/diff", "Show current git diff for workspace"),
            ("/status", "Show git status and active branch"),
            ("/commit [msg]", "Stage and commit changes with a git message"),
            ("/sessions", "List all saved conversation sessions"),
            ("/resume [id]", "Resume a saved conversation session"),
            ("/history", "Show recent session history"),
            ("/rules", "Show loaded project instructions (.omnicoderules)"),
            ("/tools", "List all registered agent tools and parameters"),
            ("/exit or /quit", "Exit the interactive session"),
        ]

        for cmd, desc in commands:
            table.add_row(cmd, desc)

        self.console.print(table)
