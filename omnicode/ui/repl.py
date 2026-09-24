from __future__ import annotations

import os
import sys
import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Optional, List, Any
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.table import Table

from ..config import OmniConfig, PROVIDER_PRESETS, save_project_config, detect_context_limit
from .model_browser import build_models_table, browse_models_interactive, filter_models
from ..utils.git_utils import get_git_branch, get_git_diff, get_git_status_summary
from ..utils.file_utils import load_gitignore, is_ignored

if TYPE_CHECKING:
    from ..core.agent import OmniAgent


class OmniCompleter(Completer):
    """Custom completer for slash commands, dynamic model IDs, and @file autocompletion."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.discovered_models: List[str] = []
        self.slash_commands = [
            ("/help", "Show help and commands"),
            ("/auth", "Configure endpoint provider, API key, and model"),
            ("/clear", "Clear screen and reset context"),
            ("/compact", "Compact conversation context"),
            ("/cost", "Show token metrics and cost"),
            ("/models", "Discover and list models from /v1/models"),
            ("/model", "Switch active LLM model"),
            ("/provider", "Switch provider preset"),
            ("/mode", "Change permissions mode"),
            ("/save", "Save current endpoint/model config to disk"),
            ("/diff", "Show git diff"),
            ("/status", "Show git status"),
            ("/commit", "Commit staged/modified changes"),
            ("/history", "List saved conversation sessions"),
            ("/rules", "View active project rules"),
            ("/tools", "List available tools"),
            ("/exit", "Exit OmniCode"),
            ("/quit", "Exit OmniCode"),
        ]

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        word = document.get_word_before_cursor()

        # Specific command arguments autocompletion
        if text.startswith("/model "):
            q = text[7:].strip().lower()
            all_models = list(self.discovered_models)
            for p in PROVIDER_PRESETS.values():
                for m in p.get("models", []):
                    if m not in all_models:
                        all_models.append(m)
            for m in all_models:
                if q in m.lower():
                    yield Completion(m, start_position=-len(text[7:]), display=m)
            return

        elif text.startswith("/provider "):
            q = text[10:].strip().lower()
            for p in PROVIDER_PRESETS.keys():
                if q in p.lower():
                    yield Completion(p, start_position=-len(text[10:]), display=p)
            return

        elif text.startswith("/mode "):
            q = text[6:].strip().lower()
            for mode in ["ask", "auto-read", "yolo"]:
                if q in mode:
                    yield Completion(mode, start_position=-len(text[6:]), display=mode)
            return

        # Slash command root completion
        if text.startswith("/"):
            for cmd, desc in self.slash_commands:
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc,
                    )
            return

        # @file completion
        if "@" in text:
            at_idx = text.rfind("@")
            file_query = text[at_idx + 1 :]
            spec = load_gitignore(self.workspace_root)

            try:
                for root, dirs, files in os.walk(self.workspace_root):
                    rel_r = Path(root).relative_to(self.workspace_root).as_posix()
                    if rel_r != "." and is_ignored(rel_r, spec):
                        dirs.clear()
                        continue
                    for f in files:
                        full_p = Path(root) / f
                        rel_f = full_p.relative_to(self.workspace_root).as_posix()
                        if not is_ignored(rel_f, spec):
                            if file_query.lower() in rel_f.lower():
                                yield Completion(
                                    rel_f,
                                    start_position=-len(file_query),
                                    display=f"@{rel_f}",
                                    display_meta=f"{full_p.stat().st_size} B",
                                )
            except Exception:
                pass


def create_prompt_style() -> Style:
    """Create color style for Prompt Toolkit."""
    return Style.from_dict(
        {
            "prompt": "#00d7ff bold",
            "model": "#00ff87",
            "branch": "#af87ff",
            "at": "#888888",
        }
    )


class InteractiveREPL:
    """Interactive REPL driving continuous conversation with OmniCode."""

    def __init__(self, agent: OmniAgent, console: Optional[Console] = None):
        self.agent = agent
        self.console = console or Console()
        self.workspace_root = agent.workspace_root
        self.completer = OmniCompleter(self.workspace_root)
        self.kb = KeyBindings()
        self._setup_keybindings()
        self._cached_models: List[Dict[str, Any]] = []
        self._models_page: int = 1
        self.session = PromptSession(
            completer=self.completer,
            style=create_prompt_style(),
            key_bindings=self.kb,
            multiline=False,
        )

    def _setup_keybindings(self):
        @self.kb.add("c-c")
        def _(event):
            """Ctrl+C clears current input."""
            event.current_buffer.text = ""

    def _get_prompt_html(self) -> HTML:
        """Construct prompt line with model and branch tags."""
        branch = get_git_branch(self.workspace_root)
        branch_tag = f" <branch>🌿 {branch}</branch>" if branch else ""
        return HTML(
            f"<b><prompt>omnicode</prompt></b>[<model>{self.agent.config.model}</model>{branch_tag}] ❯ "
        )

    async def start(self):
        """Start the interactive REPL loop."""
        # Show banner
        branch = get_git_branch(self.workspace_root)
        self.agent.renderer.print_banner(
            provider=self.agent.config.provider,
            model=self.agent.config.model,
            base_url=self.agent.config.base_url,
            permission_mode=self.agent.config.permission_mode,
            branch=branch,
            cwd=str(self.workspace_root),
        )

        while True:
            try:
                prompt_text = await self.session.prompt_async(self._get_prompt_html())
                prompt_text = prompt_text.strip()

                if not prompt_text:
                    continue

                # Process slash commands
                if prompt_text.startswith("/"):
                    handled = await self._handle_slash_command(prompt_text)
                    if handled == "exit":
                        break
                    continue

                # Expand @file references inline
                expanded_prompt = self._expand_file_references(prompt_text)

                # Run agent turn
                await self.agent.run(expanded_prompt)

            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Goodbye![/dim]")
                break
            except Exception as e:
                self.console.print(f"[bold red]REPL Error:[/bold red] {str(e)}")

    def _expand_file_references(self, prompt: str) -> str:
        """Replace @path/to/file with actual file contents if found."""
        words = prompt.split()
        expanded_words = []
        for word in words:
            if word.startswith("@") and len(word) > 1:
                rel_path = word[1:]
                target = (self.workspace_root / rel_path).resolve()
                if target.is_file():
                    try:
                        with open(target, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        expanded_words.append(
                            f"\n[File `{rel_path}`]:\n```\n{content}\n```\n"
                        )
                        continue
                    except Exception:
                        pass
            expanded_words.append(word)
        return " ".join(expanded_words)

    async def _handle_slash_command(self, cmd_text: str) -> Optional[str]:
        """Handle execution of REPL slash commands."""
        parts = cmd_text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ["/exit", "/quit", "/q"]:
            self.console.print("[dim]Exiting OmniCode...[/dim]")
            return "exit"

        elif cmd == "/help":
            self.agent.renderer.print_help()

        elif cmd == "/clear":
            self.agent.context_manager.clear_history()
            os.system("cls" if os.name == "nt" else "clear")
            self.console.print("[bold green]✓ Conversation context reset.[/bold green]")

        elif cmd == "/compact":
            msg = await self.agent.context_manager.compact_history(self.agent.llm_client)
            self.console.print(f"[bold green]✓ {msg}[/bold green]")

        elif cmd == "/cost":
            summary = self.agent.context_manager.token_tracker.get_summary()
            table = Table(title="[bold cyan]Session Usage & Cost[/bold cyan]")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="bold white")
            table.add_row("Model", summary["model"])
            table.add_row("Session Prompt Tokens", f"{summary['session_prompt_tokens']:,}")
            table.add_row("Session Completion Tokens", f"{summary['session_completion_tokens']:,}")
            table.add_row("Session Total Tokens", f"{summary['session_total_tokens']:,}")
            table.add_row("Estimated Cost", f"${summary['session_cost_usd']:.4f} USD")
            self.console.print(table)

        elif cmd == "/model":
            if arg:
                self.agent.config.model = arg
                self.agent.llm_client.config.model = arg
                self.agent.context_manager.config.model = arg
                self.agent.context_manager.token_tracker.model_name = arg
                raw_meta = next(
                    (m.get("raw") for m in self._cached_models if m["id"].lower() == arg.lower()),
                    None,
                )
                new_ctx = detect_context_limit(arg, raw_meta)
                self.agent.config.context_window = new_ctx
                self.console.print(
                    f"[bold green]✓ Switched model to: {arg} (Context limit: {new_ctx:,} tokens)[/bold green]"
                )
            else:
                self.console.print(
                    f"Current Model: [bold green]{self.agent.config.model}[/bold green] "
                    f"(Context Limit: [bold magenta]{self.agent.config.context_window:,}[/bold magenta] tokens, Endpoint: {self.agent.config.base_url})"
                )

        elif cmd == "/models":
            # Fetch if not cached or force refresh
            if not self._cached_models or arg.lower() in ["refresh", "reload"]:
                try:
                    with self.console.status(f"[cyan]Discovering models from {self.agent.config.base_url}/models ...[/cyan]"):
                        self._cached_models = await self.agent.llm_client.list_models()
                        self.completer.discovered_models = [m["id"] for m in self._cached_models]
                except Exception as e:
                    self.console.print(f"[dim yellow]Could not auto-fetch from /v1/models: {str(e)}[/dim yellow]")

            if not self._cached_models:
                self.console.print(f"[yellow]No models found or endpoint not reachable ({self.agent.config.base_url}).[/yellow]")
                return

            arg_lower = arg.strip().lower()

            if arg_lower in ["browse", "-i", "interactive"]:
                selected, ctx = browse_models_interactive(
                    discovered_models=self._cached_models,
                    console=self.console,
                    default_model=self.agent.config.model,
                    page_size=15,
                )
                self.agent.config.model = selected
                self.agent.llm_client.config.model = selected
                self.agent.context_manager.config.model = selected
                self.agent.context_manager.token_tracker.model_name = selected
                self.agent.config.context_window = ctx
                self.console.print(f"[bold green]✓ Switched model to: {selected} (Context limit: {ctx:,} tokens)[/bold green]")
                return

            # Determine page or query
            page_to_show = self._models_page
            query_filter = ""
            if arg_lower.isdigit():
                page_to_show = int(arg_lower)
                self._models_page = page_to_show
            elif arg_lower in ["n", "next"]:
                self._models_page += 1
                page_to_show = self._models_page
            elif arg_lower in ["p", "prev", "previous"]:
                self._models_page = max(1, self._models_page - 1)
                page_to_show = self._models_page
            elif arg_lower:
                query_filter = arg.strip()
                page_to_show = 1

            table, total_pages, total_count = build_models_table(
                models=self._cached_models,
                page=page_to_show,
                page_size=15,
                query=query_filter,
                title_prefix=f"Models Discovered from {self.agent.config.base_url}",
            )
            self.console.print(table)
            if total_pages > 1:
                self.console.print(
                    f"[dim]Navigation: [bold white]/models {min(page_to_show + 1, total_pages)}[/bold white] (page), "
                    f"[bold white]/models <query>[/bold white] (search), or [bold white]/models -i[/bold white] (interactive browser).[/dim]"
                )
            self.console.print(f"[dim]Switch model with: [bold white]/model <name>[/bold white][/dim]")


        elif cmd == "/auth":
            from .auth import run_auth_wizard
            from ..core.llm_client import LLMClient
            new_cfg = await run_auth_wizard(console=self.console, current_config=self.agent.config, workspace_root=self.workspace_root)
            self.agent.config = new_cfg
            self.agent.llm_client = LLMClient(new_cfg)
            self.agent.context_manager.config = new_cfg
            self.agent.context_manager.token_tracker.model_name = new_cfg.model
            self.completer.discovered_models.clear()
            self.console.print(f"[bold green]✓ Session authenticated with {new_cfg.base_url} (Model: {new_cfg.model}, Context: {new_cfg.context_window:,} tokens)[/bold green]")

        elif cmd == "/provider":
            if arg:
                pname = arg.lower()
                if pname in PROVIDER_PRESETS:
                    preset = PROVIDER_PRESETS[pname]
                    self.agent.config.provider = pname
                    self.agent.config.base_url = preset["base_url"]
                    self.console.print(
                        f"[bold green]✓ Switched provider to: {pname} (Endpoint: {preset['base_url']})[/bold green]"
                    )
                    self.console.print("[dim]Run [bold white]/models[/bold white] to discover models on this provider.[/dim]")
                else:
                    self.console.print(f"[bold red]Unknown provider: {arg}. Available: {list(PROVIDER_PRESETS.keys())}[/bold red]")
            else:
                self.console.print(f"Current Provider: [bold green]{self.agent.config.provider or 'custom'}[/bold green] ({self.agent.config.base_url})")

        elif cmd == "/mode":
            if arg:
                self.agent.permission_manager.set_mode(arg)
                self.agent.config.permission_mode = arg
                self.console.print(f"[bold green]✓ Permission mode set to: {arg}[/bold green]")
            else:
                self.console.print(f"Permission mode: [bold yellow]{self.agent.permission_manager.mode.value}[/bold yellow]")

        elif cmd == "/diff":
            diff = get_git_diff(self.workspace_root)
            if diff:
                from .diff_viewer import render_diff
                self.console.print(diff)
            else:
                self.console.print("[dim]No uncommitted git changes.[/dim]")

        elif cmd == "/status":
            summary = get_git_status_summary(self.workspace_root)
            if not summary.get("is_repo"):
                self.console.print("[yellow]Not a git repository.[/yellow]")
            else:
                self.console.print(f"Branch: [magenta]{summary['branch']}[/magenta]")
                self.console.print(f"Total Changes: [bold]{summary['total_changes']}[/bold]")
                if summary.get("raw_status"):
                    self.console.print(summary["raw_status"])

        elif cmd == "/commit":
            if not arg:
                self.console.print("[yellow]Usage: /commit <commit message>[/yellow]")
            else:
                res = await self.agent.registry.execute("git_commit", {"message": arg})
                if res.success:
                    self.console.print(f"[bold green]✓ {res.output}[/bold green]")
                else:
                    self.console.print(f"[bold red]Commit failed: {res.error}[/bold red]")

        elif cmd == "/tools":
            tools = self.agent.registry.list_all()
            table = Table(title="[bold cyan]Registered Tools[/bold cyan]")
            table.add_column("Tool Name", style="bold cyan")
            table.add_column("Type", style="magenta")
            table.add_column("Description", style="white")
            for t in tools:
                ttype = "[green]Read-Only[/green]" if t.is_read_only else "[yellow]Modifying[/yellow]"
                table.add_row(t.name, ttype, t.description)
            self.console.print(table)

        elif cmd in ["/save", "/save-config"]:
            from ..config import save_current_config
            is_proj = (arg.strip().lower() == "project")
            saved_file = save_current_config(self.agent.config, is_project=is_proj, workspace_root=self.workspace_root)
            dest = "project config (.omnicode/config.json)" if is_proj else f"global config ({saved_file})"
            self.console.print(f"[bold green]✓ Current configuration saved to {dest}.[/bold green]")
            self.console.print(f"[dim]Endpoint: {self.agent.config.base_url} | Model: {self.agent.config.model}[/dim]")

        elif cmd == "/rules":
            if self.agent.config.system_prompt_extra:
                self.console.print(self.agent.config.system_prompt_extra)
            else:
                self.console.print("[dim]No custom rules or .omnicoderules found.[/dim]")

        else:
            self.console.print(f"[yellow]Unknown command '{cmd}'. Type /help for available commands.[/yellow]")

        return None
