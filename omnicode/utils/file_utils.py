"""
File handling utilities, gitignore filtering, and safety checks.
"""

import os
from pathlib import Path
from typing import List, Optional
import pathspec

# Standard directories to ignore if no .gitignore exists
DEFAULT_IGNORES = [
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".next",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
    ".ds_store",
    "Thumbs.db",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.so",
    "*.dylib",
    "*.dll",
    "*.exe",
]


def is_binary_file(file_path: Path) -> bool:
    """Check if a file appears to be binary by inspecting initial bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
            # Check for high ratio of non-text characters
            text_chars = bytearray(
                {7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F}
            )
            nontext = chunk.translate(None, text_chars)
            return len(nontext) / max(len(chunk), 1) > 0.3
    except Exception:
        return True


def load_gitignore(root_dir: Path) -> Optional[pathspec.PathSpec]:
    """Load gitignore patterns from workspace root and return PathSpec matcher."""
    patterns = list(DEFAULT_IGNORES)
    gitignore_path = root_dir / ".gitignore"
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                patterns.extend(f.readlines())
        except Exception:
            pass
    try:
        return pathspec.PathSpec.from_lines("gitignore", patterns)
    except Exception:
        return None


def is_ignored(rel_path: str, spec: Optional[pathspec.PathSpec]) -> bool:
    """Check if relative path matches gitignore spec or default ignores."""
    norm_path = rel_path.replace("\\", "/")
    # Always ignore .git directory
    if norm_path == ".git" or norm_path.startswith(".git/"):
        return True
    if spec:
        return spec.match_file(norm_path)
    # Fallback to simple matching
    parts = norm_path.split("/")
    for ignore in DEFAULT_IGNORES:
        if ignore in parts:
            return True
    return False


def get_workspace_tree(
    root_dir: Path, max_depth: int = 3, max_files: int = 150
) -> str:
    """Generate a clean visual tree of the workspace respecting ignores."""
    spec = load_gitignore(root_dir)
    tree_lines: List[str] = [f"{root_dir.name}/"]
    count = 0

    def _walk(current_dir: Path, prefix: str, depth: int):
        nonlocal count
        if depth > max_depth or count >= max_files:
            return

        try:
            entries = sorted(
                list(current_dir.iterdir()),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except (PermissionError, OSError):
            return

        # Filter entries
        valid_entries = []
        for entry in entries:
            try:
                rel = entry.relative_to(root_dir).as_posix()
                if is_ignored(rel, spec):
                    continue
                valid_entries.append(entry)
            except Exception:
                continue

        for i, entry in enumerate(valid_entries):
            if count >= max_files:
                tree_lines.append(f"{prefix}... (more files truncated)")
                break

            is_last = i == len(valid_entries) - 1
            branch = "└── " if is_last else "├── "
            tree_lines.append(f"{prefix}{branch}{entry.name}{'/' if entry.is_dir() else ''}")
            count += 1

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(root_dir, "", 1)
    return "\n".join(tree_lines)
