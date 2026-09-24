"""
Command execution tools for OmniCode.
Runs shell commands (bash/PowerShell/cmd) with timeouts, cwd support, streaming, and background process handling.
"""

import asyncio
import os
import platform
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from .base import BaseTool, ToolResult
from ..utils.system_info import get_default_shell


class RunCommandTool(BaseTool):
    """Tool to execute shell commands in the workspace environment."""

    name = "run_command"
    description = (
        "Execute a terminal command in the workspace. "
        "Supports bash (macOS/Linux) or PowerShell/cmd (Windows). "
        "Captures stdout, stderr, and exit code. Supports working directory and timeout."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.default_shell = get_default_shell()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact shell command to execute.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional working directory relative to workspace root.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum execution time in seconds (default: 60).",
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 60,
        **kwargs,
    ) -> ToolResult:
        try:
            work_dir = self.workspace_root
            if cwd:
                p = Path(cwd)
                work_dir = p if p.is_absolute() else (self.workspace_root / p).resolve()

            if not work_dir.exists():
                return ToolResult(
                    success=False,
                    error=f"Working directory does not exist: {cwd}",
                )

            is_windows = platform.system().lower() == "windows"

            if is_windows:
                # Use powershell on Windows
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=str(work_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True,
                )
            else:
                # Use default shell or bash on Unix
                process = await asyncio.create_subprocess_shell(
                    command,
                    cwd=str(work_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True,
                    executable=self.default_shell,
                )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except Exception:
                    pass
                return ToolResult(
                    success=False,
                    error=f"Command timed out after {timeout} seconds: {command}",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            exit_code = process.returncode

            # Truncate extremely large outputs (e.g. max 12,000 characters) to avoid context limit
            max_chars = 12000
            if len(stdout) > max_chars:
                stdout = stdout[:max_chars] + f"\n\n... [Stdout truncated ({len(stdout)} total chars)]"
            if len(stderr) > max_chars:
                stderr = stderr[:max_chars] + f"\n\n... [Stderr truncated ({len(stderr)} total chars)]"

            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr}")
            if not stdout and not stderr:
                output_parts.append("[Command produced no output]")

            output_parts.append(f"Exit code: {exit_code}")
            full_output = "\n\n".join(output_parts)

            return ToolResult(
                success=(exit_code == 0),
                output=full_output,
                error=None if exit_code == 0 else f"Command exited with code {exit_code}",
                metadata={"exit_code": exit_code, "command": command},
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to execute command: {str(e)}"
            )
