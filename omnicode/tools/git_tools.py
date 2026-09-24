"""
Git version control tools for OmniCode.
Provides git_status, git_diff, git_log, git_commit.
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from .base import BaseTool, ToolResult
from ..utils.git_utils import is_git_repo, get_git_branch, get_git_status_summary


class GitStatusTool(BaseTool):
    """Tool to inspect git status of the project repository."""

    name = "git_status"
    description = (
        "Check git status of the workspace, including current branch, "
        "modified files, staged files, and untracked files."
    )
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, **kwargs) -> ToolResult:
        try:
            if not is_git_repo(self.workspace_root):
                return ToolResult(
                    success=False,
                    error="Current workspace is not inside a git repository.",
                )

            summary = get_git_status_summary(self.workspace_root)
            branch = summary.get("branch", "unknown")
            raw = summary.get("raw_status", "")

            if not raw:
                return ToolResult(
                    success=True,
                    output=f"Branch: {branch}\nWorking tree clean (no changes).",
                )

            out = f"Branch: {branch}\nChanges ({summary['total_changes']}):\n{raw}"
            return ToolResult(success=True, output=out, metadata=summary)
        except Exception as e:
            return ToolResult(success=False, error=f"Git status failed: {str(e)}")


class GitDiffTool(BaseTool):
    """Tool to view uncommitted git changes."""

    name = "git_diff"
    description = "View git diff for working tree or staged changes."
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Show staged diff (--cached) instead of unstaged diff (default: false).",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional specific file to diff.",
                },
            },
            "required": [],
        }

    async def execute(
        self, staged: bool = False, file_path: Optional[str] = None, **kwargs
    ) -> ToolResult:
        try:
            if not is_git_repo(self.workspace_root):
                return ToolResult(
                    success=False,
                    error="Current workspace is not inside a git repository.",
                )

            cmd = ["git", "diff"]
            if staged:
                cmd.append("--cached")
            if file_path:
                cmd.extend(["--", file_path])

            res = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=15,
            )

            diff_text = res.stdout.strip()
            if not diff_text:
                return ToolResult(
                    success=True,
                    output="No diff found (no modifications detected).",
                )

            # Truncate if diff is huge
            if len(diff_text) > 15000:
                diff_text = diff_text[:15000] + "\n\n... [Diff truncated due to size]"

            return ToolResult(success=True, output=diff_text)
        except Exception as e:
            return ToolResult(success=False, error=f"Git diff failed: {str(e)}")


class GitCommitTool(BaseTool):
    """Tool to stage and commit git changes."""

    name = "git_commit"
    description = (
        "Stage files and create a git commit with a clear, descriptive message."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Descriptive commit message.",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of files to stage, or empty/omitted to stage all modified files (git add -A).",
                },
            },
            "required": ["message"],
        }

    async def execute(
        self, message: str, files: Optional[list] = None, **kwargs
    ) -> ToolResult:
        try:
            if not is_git_repo(self.workspace_root):
                return ToolResult(
                    success=False,
                    error="Current workspace is not inside a git repository.",
                )

            # Stage files
            if files:
                add_cmd = ["git", "add"] + files
            else:
                add_cmd = ["git", "add", "-A"]

            res_add = subprocess.run(
                add_cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res_add.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to stage files: {res_add.stderr.strip()}",
                )

            # Commit
            res_commit = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res_commit.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Commit failed: {res_commit.stderr.strip() or res_commit.stdout.strip()}",
                )

            return ToolResult(
                success=True,
                output=f"Successfully committed:\n{res_commit.stdout.strip()}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Git commit failed: {str(e)}")


class GitLogTool(BaseTool):
    """Tool to view recent git commit logs."""

    name = "git_log"
    description = "View recent git commit logs with commit hash, author, and message."
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_count": {
                    "type": "integer",
                    "description": "Number of commits to return (default: 10).",
                }
            },
            "required": [],
        }

    async def execute(self, max_count: int = 10, **kwargs) -> ToolResult:
        try:
            if not is_git_repo(self.workspace_root):
                return ToolResult(
                    success=False,
                    error="Current workspace is not inside a git repository.",
                )

            res = subprocess.run(
                [
                    "git",
                    "log",
                    f"-n{max_count}",
                    "--pretty=format:%h - %an (%ar): %s",
                ],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                return ToolResult(
                    success=False, error=f"Git log failed: {res.stderr.strip()}"
                )

            out = res.stdout.strip() or "No commits yet in this repository."
            return ToolResult(success=True, output=out)
        except Exception as e:
            return ToolResult(success=False, error=f"Git log failed: {str(e)}")
