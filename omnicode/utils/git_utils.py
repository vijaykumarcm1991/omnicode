"""
Git integration utilities for OmniCode.
Inspects repo state, branch, unstaged changes, and diffs.
"""

import subprocess
from pathlib import Path
from typing import Optional, Dict, Any


def is_git_repo(path: Path) -> bool:
    """Check if the directory is part of a git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def get_git_branch(path: Path) -> Optional[str]:
    """Get current active git branch."""
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            branch = res.stdout.strip()
            if branch:
                return branch
        # Fallback for detached HEAD
        res_head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res_head.returncode == 0:
            return f"HEAD ({res_head.stdout.strip()})"
    except Exception:
        pass
    return None


def get_git_status_summary(path: Path) -> Dict[str, Any]:
    """Get summarized git status (branch, modified, untracked files)."""
    if not is_git_repo(path):
        return {"is_repo": False}

    branch = get_git_branch(path)
    status_output = ""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            status_output = res.stdout.strip()
    except Exception:
        pass

    lines = [line for line in status_output.splitlines() if line.strip()]
    modified = [l for l in lines if l.startswith(" M") or l.startswith("M ")]
    untracked = [l for l in lines if l.startswith("??")]
    added = [l for l in lines if l.startswith("A ") or l.startswith("AM")]
    deleted = [l for l in lines if l.startswith(" D") or l.startswith("D ")]

    return {
        "is_repo": True,
        "branch": branch or "unknown",
        "total_changes": len(lines),
        "modified": len(modified),
        "untracked": len(untracked),
        "added": len(added),
        "deleted": len(deleted),
        "raw_status": status_output,
    }


def get_git_diff(path: Path, cached: bool = False) -> str:
    """Get git diff output."""
    if not is_git_repo(path):
        return ""
    cmd = ["git", "diff"]
    if cached:
        cmd.append("--cached")
    try:
        res = subprocess.run(
            cmd,
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return res.stdout if res.returncode == 0 else ""
    except Exception:
        return ""
