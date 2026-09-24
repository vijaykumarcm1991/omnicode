"""
Permission and confirmation engine for OmniCode.
Controls tool execution safety with interactive prompts, diff inspection, and session whitelists.
"""

from typing import Set, Dict, Any, Optional
from enum import Enum
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax


class PermissionMode(str, Enum):
    ASK = "ask"
    AUTO_READ = "auto-read"
    YOLO = "yolo"


class PermissionManager:
    """Manages permissions and user confirmation for tool executions."""

    def __init__(self, mode: str = "auto-read", console: Optional[Console] = None):
        self.mode = PermissionMode(mode.lower()) if mode in ["ask", "auto-read", "yolo"] else PermissionMode.AUTO_READ
        self.console = console or Console(legacy_windows=False)
        self.session_allowed_tools: Set[str] = set()

    def set_mode(self, mode: str):
        self.mode = PermissionMode(mode.lower())

    async def check_permission(
        self,
        tool_name: str,
        is_read_only: bool,
        arguments: Dict[str, Any],
    ) -> bool:
        """Evaluate whether tool execution should proceed or requires confirmation."""
        # YOLO mode allows all
        if self.mode == PermissionMode.YOLO:
            return True

        # Tool previously whitelisted for session
        if tool_name in self.session_allowed_tools:
            return True

        # AUTO_READ mode allows read-only tools
        if self.mode == PermissionMode.AUTO_READ and is_read_only:
            return True

        # Needs explicit user confirmation
        return await self._prompt_confirmation(tool_name, arguments)

    async def _prompt_confirmation(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> bool:
        """Render rich confirmation box for sensitive actions."""
        self.console.print()

        # Command execution prompt
        if tool_name == "run_command":
            cmd = arguments.get("command", "")
            cwd = arguments.get("cwd", ".")
            self.console.print(
                Panel(
                    f"[bold yellow]⚠️  Tool Request:[/bold yellow] [cyan]run_command[/cyan]\n"
                    f"[bold]Command:[/bold] [bold white]{cmd}[/bold white]\n"
                    f"[dim]Directory: {cwd}[/dim]",
                    title="[bold yellow]Command Execution Permission[/bold yellow]",
                    border_style="yellow",
                )
            )

        # File write/edit prompt
        elif tool_name in ["write_file", "edit_file", "apply_patch"]:
            file_path = arguments.get("file_path", "")
            if tool_name == "edit_file":
                old_c = arguments.get("old_content", "")
                new_c = arguments.get("new_content", "")
                self.console.print(
                    Panel(
                        f"[bold yellow]⚠️  Tool Request:[/bold yellow] [cyan]edit_file[/cyan] on [bold green]{file_path}[/bold green]\n"
                        f"[red]- {old_c[:150]}...[/red]\n"
                        f"[green]+ {new_c[:150]}...[/green]",
                        title="[bold yellow]File Modification Permission[/bold yellow]",
                        border_style="yellow",
                    )
                )
            else:
                self.console.print(
                    Panel(
                        f"[bold yellow]⚠️  Tool Request:[/bold yellow] [cyan]{tool_name}[/cyan] on [bold green]{file_path}[/bold green]",
                        title="[bold yellow]File Write Permission[/bold yellow]",
                        border_style="yellow",
                    )
                )
        else:
            self.console.print(
                Panel(
                    f"[bold yellow]⚠️  Tool Request:[/bold yellow] [cyan]{tool_name}[/cyan]\n"
                    f"[dim]Args: {arguments}[/dim]",
                    title="[bold yellow]Tool Permission[/bold yellow]",
                    border_style="yellow",
                )
            )

        ans = Prompt.ask(
            "[bold white]Allow this action?[/bold white] [[bold green]y[/bold green]=Yes, [bold red]n[/bold red]=No, [bold cyan]a[/bold cyan]=Always allow this tool, [bold yellow]yolo[/bold yellow]=Allow everything]",
            choices=["y", "n", "a", "yolo", "yes", "no"],
            default="y",
            console=self.console,
        ).lower()

        if ans in ["y", "yes"]:
            return True
        elif ans == "a":
            self.session_allowed_tools.add(tool_name)
            self.console.print(
                f"[dim green]✓ Always allowing '{tool_name}' for this session.[/dim green]"
            )
            return True
        elif ans == "yolo":
            self.mode = PermissionMode.YOLO
            self.console.print(
                "[bold magenta]⚡ Switched to YOLO mode. All tool actions will be automatically approved.[/bold magenta]"
            )
            return True
        else:
            self.console.print("[red]❌ Action rejected by user.[/red]")
            return False
