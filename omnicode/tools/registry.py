"""
Tool registry for OmniCode agent tools.
Handles tool registration, discovery, OpenAI schema generation, and dispatching.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult
from .fs_tools import (
    ViewFileTool,
    WriteFileTool,
    EditFileTool,
    ApplyPatchTool,
    ListDirTool,
    FileSearchTool,
    GrepSearchTool,
)
from .bash_tools import RunCommandTool
from .git_tools import GitStatusTool, GitDiffTool, GitCommitTool, GitLogTool
from .web_tools import FetchWebPageTool, WebSearchTool
from .interactive_tools import AskUserTool
from .memory_tools import ManageTodoTool, ProjectMemoryTool


class ToolRegistry:
    """Registry managing all active tools for the agent."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Get tool instance by name."""
        return self._tools.get(name)

    def list_all(self) -> List[BaseTool]:
        """Return list of all registered tools."""
        return list(self._tools.values())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Return OpenAI tool schemas for all registered tools."""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: Any) -> ToolResult:
        """Execute a tool with given arguments (dict or JSON string)."""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool '{name}'. Available tools: {list(self._tools.keys())}",
            )

        parsed_args: Dict[str, Any] = {}
        if isinstance(arguments, str):
            try:
                parsed_args = json.loads(arguments) if arguments.strip() else {}
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=f"Failed to parse arguments JSON for tool '{name}': {str(e)}",
                )
        elif isinstance(arguments, dict):
            parsed_args = arguments

        try:
            return await tool.execute(**parsed_args)
        except TypeError as e:
            return ToolResult(
                success=False,
                error=f"Invalid arguments for tool '{name}': {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool execution failed for '{name}': {str(e)}",
            )


def create_default_registry(
    workspace_root: Path, prompt_callback=None
) -> ToolRegistry:
    """Instantiate and register all default agent tools."""
    registry = ToolRegistry()

    # File system tools
    registry.register(ViewFileTool(workspace_root))
    registry.register(WriteFileTool(workspace_root))
    registry.register(EditFileTool(workspace_root))
    registry.register(ApplyPatchTool(workspace_root))
    registry.register(ListDirTool(workspace_root))
    registry.register(FileSearchTool(workspace_root))
    registry.register(GrepSearchTool(workspace_root))

    # Command execution
    registry.register(RunCommandTool(workspace_root))

    # Git tools
    registry.register(GitStatusTool(workspace_root))
    registry.register(GitDiffTool(workspace_root))
    registry.register(GitCommitTool(workspace_root))
    registry.register(GitLogTool(workspace_root))

    # Web tools
    registry.register(FetchWebPageTool())
    registry.register(WebSearchTool())

    # Interactive & Memory
    registry.register(AskUserTool(prompt_callback))
    registry.register(ManageTodoTool(workspace_root))
    registry.register(ProjectMemoryTool(workspace_root))

    return registry
