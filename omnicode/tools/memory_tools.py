"""
Task tracking, todo management, and memory tools for OmniCode.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult


class ManageTodoTool(BaseTool):
    """Tool to manage task list and todos for multi-step tasks."""

    name = "manage_todo"
    description = (
        "Manage project task checklist for complex tasks. "
        "Actions: 'list', 'add', 'complete', 'update', 'clear'."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.todos: List[Dict[str, Any]] = []

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "add", "complete", "update", "clear"],
                    "description": "Action to perform on todo list.",
                },
                "task": {
                    "type": "string",
                    "description": "Task description (for 'add' or 'update').",
                },
                "task_id": {
                    "type": "integer",
                    "description": "1-indexed task ID (for 'complete' or 'update').",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        task: Optional[str] = None,
        task_id: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        try:
            if action == "add":
                if not task:
                    return ToolResult(
                        success=False, error="Task description required for 'add'."
                    )
                item = {"id": len(self.todos) + 1, "task": task, "done": False}
                self.todos.append(item)
                return ToolResult(
                    success=True,
                    output=f"Added task #{item['id']}: '{task}'",
                )

            elif action == "complete":
                if not task_id or task_id < 1 or task_id > len(self.todos):
                    return ToolResult(
                        success=False,
                        error=f"Invalid task_id: {task_id}. Current tasks count: {len(self.todos)}",
                    )
                self.todos[task_id - 1]["done"] = True
                return ToolResult(
                    success=True,
                    output=f"Completed task #{task_id}: '{self.todos[task_id - 1]['task']}'",
                )

            elif action == "clear":
                self.todos.clear()
                return ToolResult(success=True, output="Cleared all tasks.")

            elif action == "list" or not action:
                if not self.todos:
                    return ToolResult(
                        success=True, output="Task list is currently empty."
                    )
                lines = ["Current Task Checklist:"]
                for t in self.todos:
                    status = "✅" if t["done"] else "⬜"
                    lines.append(f"{t['id']}. {status} {t['task']}")
                return ToolResult(success=True, output="\n".join(lines))

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(success=False, error=f"Todo error: {str(e)}")


class ProjectMemoryTool(BaseTool):
    """Tool to persist and retrieve project knowledge and conventions in .omnicode/memory.json."""

    name = "project_memory"
    description = (
        "Store or retrieve persistent project notes, conventions, and architectural decisions. "
        "Actions: 'get', 'set', 'list'."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.memory_file = workspace_root / ".omnicode" / "memory.json"

    def _load(self) -> Dict[str, str]:
        if self.memory_file.is_file():
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self, data: Dict[str, str]):
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set", "list"],
                    "description": "Action to perform ('get', 'set', 'list').",
                },
                "key": {
                    "type": "string",
                    "description": "Memory key name (e.g., 'architecture', 'api_conventions').",
                },
                "value": {
                    "type": "string",
                    "description": "Memory note value to store (for 'set').",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        key: Optional[str] = None,
        value: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        try:
            mem = self._load()
            if action == "set":
                if not key or value is None:
                    return ToolResult(
                        success=False,
                        error="Both 'key' and 'value' are required for 'set'.",
                    )
                mem[key] = value
                self._save(mem)
                return ToolResult(
                    success=True, output=f"Saved memory key '{key}'."
                )

            elif action == "get":
                if not key or key not in mem:
                    return ToolResult(
                        success=False, error=f"Memory key '{key}' not found."
                    )
                return ToolResult(success=True, output=f"[{key}]:\n{mem[key]}")

            elif action == "list":
                if not mem:
                    return ToolResult(
                        success=True, output="No persistent memory stored yet."
                    )
                out = "Stored Project Memory Keys:\n" + "\n".join(
                    f"- {k}: {v[:80]}..." if len(v) > 80 else f"- {k}: {v}"
                    for k, v in mem.items()
                )
                return ToolResult(success=True, output=out)

            return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            return ToolResult(success=False, error=f"Memory tool error: {str(e)}")
