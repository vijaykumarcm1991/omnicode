"""
Core autonomous agent loop for OmniCode.
Executes multi-step ReAct loops, handles streaming, permissions, tools, and token tracking.
"""

import time
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from rich.console import Console

from ..config import OmniConfig
from .context import ContextManager
from .llm_client import LLMClient
from .permissions import PermissionManager
from .token_tracker import TokenTracker
from ..tools.registry import ToolRegistry, create_default_registry
from ..ui.renderer import TerminalRenderer


class OmniAgent:
    """Autonomous coding agent driving the interactive workflow and tool execution loop."""

    def __init__(
        self,
        config: OmniConfig,
        workspace_root: Optional[Path] = None,
        console: Optional[Console] = None,
        registry: Optional[ToolRegistry] = None,
        session_id: Optional[str] = None,
    ):
        self.config = config
        self.workspace_root = workspace_root or Path.cwd()
        self.console = console or Console()
        self.renderer = TerminalRenderer(self.console)
        self.permission_manager = PermissionManager(
            mode=config.permission_mode, console=self.console
        )
        self.context_manager = ContextManager(
            config=config,
            workspace_root=self.workspace_root,
            session_id=session_id,
        )
        self.llm_client = LLMClient(config)
        self.registry = registry or create_default_registry(
            self.workspace_root, prompt_callback=self._interactive_prompt_callback
        )
        self.is_running = False

    async def _interactive_prompt_callback(
        self, question: str, options: Optional[List[str]] = None
    ) -> str:
        """Callback used by AskUserTool to interactively ask the user questions."""
        self.console.print(f"\n[bold yellow]❓ Question:[/bold yellow] [bold white]{question}[/bold white]")
        if options:
            self.console.print("[dim]Suggested options:[/dim]")
            for i, opt in enumerate(options, 1):
                self.console.print(f"  [cyan]{i}[/cyan]. {opt}")
        
        from rich.prompt import Prompt
        ans = Prompt.ask("[bold green]Your answer[/bold green]", console=self.console)
        return ans

    async def run(self, user_prompt: str) -> str:
        """Execute agent workflow for a given user prompt."""
        self.is_running = True
        self.context_manager.add_user_message(user_prompt)

        # Check for auto-compaction before executing
        if self.context_manager.is_approaching_limit():
            compact_msg = await self.context_manager.compact_history(self.llm_client)
            self.console.print(f"[dim yellow]⚡ {compact_msg}[/dim yellow]")

        step = 0
        max_steps = self.config.max_agent_steps
        tools_schema = self.registry.get_openai_tools()
        final_response_text = ""

        try:
            while step < max_steps and self.is_running:
                step += 1
                if step > 1:
                    self.renderer.print_step_divider(step)

                # Prepare payload
                messages = self.context_manager.get_messages_for_llm()

                # Stream and complete model turn
                streaming_content = []
                streaming_reasoning = []

                async def on_content(chunk: str):
                    streaming_content.append(chunk)

                async def on_reasoning(chunk: str):
                    streaming_reasoning.append(chunk)

                with self.console.status("[bold cyan]Thinking & Analyzing...[/bold cyan]", spinner="dots"):
                    response = await self.llm_client.complete_turn(
                        messages=messages,
                        tools=tools_schema if tools_schema else None,
                        on_content_chunk=on_content,
                        on_reasoning_chunk=on_reasoning,
                    )

                # Estimate & record token usage
                in_tokens = self.context_manager.token_tracker.estimate_messages_tokens(messages)
                out_tokens = self.context_manager.token_tracker.estimate_tokens(
                    (response.content or "") + (response.reasoning or "")
                )
                self.context_manager.token_tracker.record_usage(in_tokens, out_tokens)

                # Render reasoning block if present
                if response.reasoning and self.config.show_reasoning:
                    self.renderer.print_reasoning(response.reasoning)

                # Render text response if present
                if response.content:
                    self.renderer.print_assistant_message(response.content)
                    final_response_text = response.content

                # Record assistant message in context
                self.context_manager.add_assistant_message(
                    content=response.content if response.content else None,
                    tool_calls=response.tool_calls if response.tool_calls else None,
                    reasoning=response.reasoning if response.reasoning else None,
                )

                # If no tool calls, task / turn is finished
                if not response.tool_calls:
                    break

                # Execute requested tools
                for tc in response.tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args_raw = fn.get("arguments", "{}")
                    call_id = tc.get("id", f"call_{int(time.time())}")

                    try:
                        parsed_args = (
                            json.loads(fn_args_raw)
                            if isinstance(fn_args_raw, str) and fn_args_raw.strip()
                            else {}
                        )
                    except Exception:
                        parsed_args = {}

                    self.renderer.render_tool_start(fn_name, parsed_args)

                    # Check tool permissions
                    tool_instance = self.registry.get(fn_name)
                    is_read_only = tool_instance.is_read_only if tool_instance else False

                    permitted = await self.permission_manager.check_permission(
                        tool_name=fn_name,
                        is_read_only=is_read_only,
                        arguments=parsed_args,
                    )

                    if not permitted:
                        result_msg = "Error: User denied permission to execute this tool."
                        self.renderer.render_tool_result(fn_name, False, result_msg)
                        self.context_manager.add_tool_result(call_id, fn_name, result_msg)
                        continue

                    # Execute tool
                    start_time = time.time()
                    tool_result = await self.registry.execute(fn_name, parsed_args)
                    duration = time.time() - start_time

                    self.renderer.render_tool_result(
                        fn_name,
                        tool_result.success,
                        tool_result.to_message_content(),
                        duration_sec=duration,
                    )

                    # Add result to history
                    self.context_manager.add_tool_result(
                        call_id, fn_name, tool_result.to_message_content()
                    )

            if step >= max_steps:
                self.console.print(
                    f"\n[bold yellow]⚠️ Reached maximum step limit ({max_steps}). Use a follow-up prompt to continue.[/bold yellow]"
                )

            # Display token and cost summary
            summary = self.context_manager.token_tracker.get_summary()
            self.renderer.print_token_summary(
                summary["last_turn_prompt_tokens"],
                summary["last_turn_completion_tokens"],
                self.context_manager.token_tracker.get_estimated_cost(
                    summary["last_turn_prompt_tokens"],
                    summary["last_turn_completion_tokens"],
                ),
            )

        except asyncio.CancelledError:
            self.console.print("\n[bold red]⚠️ Operation cancelled by user.[/bold red]")
        except Exception as e:
            self.console.print(f"\n[bold red]❌ Error:[/bold red] {str(e)}")
        finally:
            self.is_running = False

        return final_response_text
