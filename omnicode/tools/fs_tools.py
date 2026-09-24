"""
File system tools for OmniCode.
Includes view_file, write_file, edit_file, apply_patch, list_dir, file_search, and grep_search.
"""

import os
import re
import difflib
from pathlib import Path
from typing import Dict, Any, Optional, List
from .base import BaseTool, ToolResult
from ..utils.file_utils import is_binary_file, load_gitignore, is_ignored


class ViewFileTool(BaseTool):
    """Tool to read the contents of a file with line numbers, slicing, and pagination."""

    name = "view_file"
    description = (
        "View the contents of a file in the workspace. Supports line ranges (1-indexed) "
        "and pagination for large files. Shows line numbers."
    )
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to view (relative to workspace or absolute).",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional starting line number (1-indexed, inclusive).",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional ending line number (1-indexed, inclusive).",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to return (default: 500).",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_lines: int = 500,
        **kwargs,
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = (self.workspace_root / path).resolve()

            if not path.exists():
                return ToolResult(
                    success=False, error=f"File not found: {file_path}"
                )

            if path.is_dir():
                return ToolResult(
                    success=False,
                    error=f"Path '{file_path}' is a directory. Use list_dir instead.",
                )

            if is_binary_file(path):
                file_size = path.stat().st_size
                return ToolResult(
                    success=True,
                    output=f"[Binary file: {path.name}, size: {file_size} bytes]",
                )

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            if total_lines == 0:
                return ToolResult(success=True, output="[File is empty]")

            s_line = max(1, start_line or 1)
            e_line = min(total_lines, end_line or (s_line + max_lines - 1))

            if s_line > total_lines:
                return ToolResult(
                    success=False,
                    error=f"Start line {s_line} is beyond total lines ({total_lines}).",
                )

            selected = lines[s_line - 1 : e_line]
            formatted_lines = []
            num_padding = len(str(e_line))

            for idx, line in enumerate(selected, start=s_line):
                clean_line = line.rstrip("\r\n")
                formatted_lines.append(f"{idx:>{num_padding}} | {clean_line}")

            header = f"--- File: {path.name} (Lines {s_line}-{e_line} of {total_lines}) ---\n"
            content = header + "\n".join(formatted_lines)

            if e_line < total_lines:
                content += f"\n\n[Lines {e_line + 1}-{total_lines} truncated. Specify start_line={e_line + 1} to view next slice]"

            return ToolResult(
                success=True,
                output=content,
                metadata={"total_lines": total_lines, "start_line": s_line, "end_line": e_line},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read file: {str(e)}")


class WriteFileTool(BaseTool):
    """Tool to create or overwrite a file."""

    name = "write_file"
    description = (
        "Write content to a file. Creates any necessary parent directories automatically. "
        "Use overwrite=True if replacing an existing file."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to create or overwrite (relative or absolute).",
                },
                "content": {
                    "type": "string",
                    "description": "The complete text content to write to the file.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to overwrite if the file already exists (default: true).",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(
        self, file_path: str, content: str, overwrite: bool = True, **kwargs
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = (self.workspace_root / path).resolve()

            is_new = not path.exists()
            if not is_new and not overwrite:
                return ToolResult(
                    success=False,
                    error=f"File '{file_path}' already exists and overwrite is set to False.",
                )

            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

            lines_count = len(content.splitlines())
            action_desc = "Created" if is_new else "Overwrote"
            return ToolResult(
                success=True,
                output=f"{action_desc} file '{file_path}' ({lines_count} lines, {len(content.encode('utf-8'))} bytes).",
                metadata={"is_new": is_new, "lines": lines_count, "path": str(path)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write file: {str(e)}")


class EditFileTool(BaseTool):
    """Tool to perform precise targeted edits by replacing old content with new content."""

    name = "edit_file"
    description = (
        "Edit an existing file by replacing an exact chunk of text (`old_content`) with "
        "`new_content`. Includes fuzzy fallback if whitespace differs slightly."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to edit.",
                },
                "old_content": {
                    "type": "string",
                    "description": "The exact block of text in the file to replace.",
                },
                "new_content": {
                    "type": "string",
                    "description": "The new block of text to replace old_content with.",
                },
                "allow_multiple": {
                    "type": "boolean",
                    "description": "Replace multiple occurrences if found (default: false).",
                },
            },
            "required": ["file_path", "old_content", "new_content"],
        }

    async def execute(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
        allow_multiple: bool = False,
        **kwargs,
    ) -> ToolResult:
        try:
            path = Path(file_path)
            if not path.is_absolute():
                path = (self.workspace_root / path).resolve()

            if not path.exists():
                return ToolResult(
                    success=False, error=f"File not found: {file_path}"
                )

            with open(path, "r", encoding="utf-8") as f:
                original_text = f.read()

            # Normalize newlines for matching
            norm_orig = original_text.replace("\r\n", "\n")
            norm_old = old_content.replace("\r\n", "\n")
            norm_new = new_content.replace("\r\n", "\n")

            count = norm_orig.count(norm_old)

            if count == 0:
                # Attempt whitespace-trimmed match
                norm_old_strip = norm_old.strip()
                if norm_old_strip and norm_old_strip in norm_orig:
                    # Found stripped version
                    idx = norm_orig.find(norm_old_strip)
                    updated_text = (
                        norm_orig[:idx]
                        + norm_new
                        + norm_orig[idx + len(norm_old_strip) :]
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=(
                            f"Target old_content was not found in '{file_path}'. "
                            "Please verify the file content using view_file and specify exact text."
                        ),
                    )
            elif count > 1 and not allow_multiple:
                return ToolResult(
                    success=False,
                    error=(
                        f"Found {count} occurrences of old_content in '{file_path}'. "
                        "Please provide more surrounding context lines to make it unique, or set allow_multiple=True."
                    ),
                )
            else:
                if allow_multiple:
                    updated_text = norm_orig.replace(norm_old, norm_new)
                else:
                    updated_text = norm_orig.replace(norm_old, norm_new, 1)

            # Generate unified diff
            diff_lines = list(
                difflib.unified_diff(
                    norm_orig.splitlines(keepends=True),
                    updated_text.splitlines(keepends=True),
                    fromfile=f"a/{path.name}",
                    tofile=f"b/{path.name}",
                    n=3,
                )
            )
            diff_str = "".join(diff_lines)

            # Write updated file
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(updated_text)

            return ToolResult(
                success=True,
                output=f"Successfully edited '{file_path}'.\n\nDiff:\n{diff_str}",
                metadata={"diff": diff_str, "file_path": str(path)},
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to edit file: {str(e)}")


class ApplyPatchTool(BaseTool):
    """Tool to apply a unified diff patch to the workspace."""

    name = "apply_patch"
    description = (
        "Apply a unified diff patch to one or more files in the workspace. "
        "Supports standard patch headers (--- a/file, +++ b/file)."
    )
    is_read_only = False

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "The unified diff patch string to apply.",
                }
            },
            "required": ["patch"],
        }

    async def execute(self, patch: str, **kwargs) -> ToolResult:
        try:
            # Parse patch chunks
            lines = patch.splitlines()
            current_file = None
            hunks = []
            current_hunk = []

            for line in lines:
                if line.startswith("+++ b/"):
                    current_file = line[6:].strip()
                elif line.startswith("+++ "):
                    current_file = line[4:].strip()
                elif line.startswith("@@"):
                    if current_hunk:
                        hunks.append((current_file, current_hunk))
                        current_hunk = []
                    current_hunk.append(line)
                elif current_hunk is not None:
                    current_hunk.append(line)

            if current_file and current_hunk:
                hunks.append((current_file, current_hunk))

            if not hunks:
                return ToolResult(
                    success=False, error="No valid unified diff hunks found in patch."
                )

            applied_files = []
            for target_rel, hunk_lines in hunks:
                if not target_rel:
                    continue
                path = (self.workspace_root / target_rel).resolve()
                if not path.exists():
                    return ToolResult(
                        success=False,
                        error=f"Target file from patch not found: {target_rel}",
                    )

                with open(path, "r", encoding="utf-8") as f:
                    content_lines = f.read().splitlines()

                # Basic hunk application
                orig_slice = []
                new_slice = []
                for hl in hunk_lines:
                    if hl.startswith("@@"):
                        continue
                    elif hl.startswith("-"):
                        orig_slice.append(hl[1:])
                    elif hl.startswith("+"):
                        new_slice.append(hl[1:])
                    elif hl.startswith(" "):
                        orig_slice.append(hl[1:])
                        new_slice.append(hl[1:])

                orig_chunk = "\n".join(orig_slice)
                new_chunk = "\n".join(new_slice)
                full_content = "\n".join(content_lines)

                if orig_chunk in full_content:
                    updated = full_content.replace(orig_chunk, new_chunk, 1)
                    with open(path, "w", encoding="utf-8", newline="\n") as f:
                        f.write(updated)
                    applied_files.append(target_rel)
                else:
                    return ToolResult(
                        success=False,
                        error=f"Hunk mismatch in {target_rel}. Try using edit_file instead.",
                    )

            return ToolResult(
                success=True,
                output=f"Successfully applied patch to: {', '.join(applied_files)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to apply patch: {str(e)}")


class ListDirTool(BaseTool):
    """Tool to list directory contents respecting .gitignore and displaying metadata."""

    name = "list_dir"
    description = (
        "List files and subdirectories in a directory path. "
        "Shows directories, files, sizes, and respects .gitignore."
    )
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "Directory path to list (default: workspace root '.').",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Whether to list subdirectories recursively (default: false).",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Max depth for recursive listing (default: 2).",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        dir_path: str = ".",
        recursive: bool = False,
        max_depth: int = 2,
        **kwargs,
    ) -> ToolResult:
        try:
            path = Path(dir_path)
            if not path.is_absolute():
                path = (self.workspace_root / path).resolve()

            if not path.exists():
                return ToolResult(
                    success=False, error=f"Directory not found: {dir_path}"
                )

            if not path.is_dir():
                return ToolResult(
                    success=False,
                    error=f"'{dir_path}' is a file. Use view_file instead.",
                )

            spec = load_gitignore(self.workspace_root)
            results = []

            def _scan(curr: Path, depth: int):
                if depth > max_depth:
                    return
                try:
                    entries = sorted(
                        list(curr.iterdir()),
                        key=lambda p: (not p.is_dir(), p.name.lower()),
                    )
                except Exception:
                    return

                for entry in entries:
                    try:
                        rel = entry.relative_to(self.workspace_root).as_posix()
                        if is_ignored(rel, spec):
                            continue
                        rel_curr = entry.relative_to(path).as_posix()
                        if entry.is_dir():
                            results.append(f"📁 {rel_curr}/")
                            if recursive:
                                _scan(entry, depth + 1)
                        else:
                            size = entry.stat().st_size
                            size_str = f"{size} B" if size < 1024 else f"{size/1024:.1f} KB"
                            results.append(f"📄 {rel_curr} ({size_str})")
                    except Exception:
                        continue

            _scan(path, 1)

            if not results:
                return ToolResult(
                    success=True, output=f"Directory '{dir_path}' is empty."
                )

            header = f"Contents of '{dir_path}' ({len(results)} items):\n"
            return ToolResult(success=True, output=header + "\n".join(results))
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list directory: {str(e)}")


class FileSearchTool(BaseTool):
    """Tool to search for files matching a pattern or name substring."""

    name = "file_search"
    description = (
        "Search for files by name pattern or glob across the workspace. "
        "Respects .gitignore rules."
    )
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "File name substring or glob pattern (e.g., '*.py', 'test_*', 'config').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum matching files to return (default: 50).",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, query: str, max_results: int = 50, **kwargs
    ) -> ToolResult:
        try:
            spec = load_gitignore(self.workspace_root)
            matches = []
            q_lower = query.lower()
            is_glob = any(c in query for c in ["*", "?", "["])

            for root, dirs, files in os.walk(self.workspace_root):
                rel_root = Path(root).relative_to(self.workspace_root).as_posix()
                if rel_root != "." and is_ignored(rel_root, spec):
                    dirs.clear()
                    continue

                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(self.workspace_root).as_posix()
                    if is_ignored(rel_p, spec):
                        continue

                    matched = False
                    if is_glob:
                        matched = Path(rel_p).match(query) or Path(f).match(query)
                    else:
                        matched = q_lower in rel_p.lower()

                    if matched:
                        matches.append(rel_p)
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break

            if not matches:
                return ToolResult(
                    success=True, output=f"No files matching query '{query}'."
                )

            return ToolResult(
                success=True,
                output=f"Found {len(matches)} files matching '{query}':\n"
                + "\n".join(matches),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"File search failed: {str(e)}")


class GrepSearchTool(BaseTool):
    """Tool to search for text patterns or regex across project files."""

    name = "grep_search"
    description = (
        "Search code files for a regex pattern or text substring. "
        "Returns matching files, line numbers, and context lines."
    )
    is_read_only = True

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern or search substring.",
                },
                "path": {
                    "type": "string",
                    "description": "Optional subdirectory or file path to limit search (default: workspace root).",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether search is case-sensitive (default: false).",
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Maximum number of matching lines to return (default: 100).",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: Optional[str] = None,
        case_sensitive: bool = False,
        max_matches: int = 100,
        **kwargs,
    ) -> ToolResult:
        try:
            target_dir = self.workspace_root
            if path:
                p = Path(path)
                target_dir = (
                    p if p.is_absolute() else (self.workspace_root / p).resolve()
                )

            if not target_dir.exists():
                return ToolResult(
                    success=False, error=f"Search path '{path}' does not exist."
                )

            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except Exception as e:
                return ToolResult(
                    success=False, error=f"Invalid regex pattern: {str(e)}"
                )

            spec = load_gitignore(self.workspace_root)
            results = []
            match_count = 0

            # If target is a single file
            if target_dir.is_file():
                files_to_check = [target_dir]
            else:
                files_to_check = []
                for r, dirs, files in os.walk(target_dir):
                    rel_r = Path(r).relative_to(self.workspace_root).as_posix()
                    if rel_r != "." and is_ignored(rel_r, spec):
                        dirs.clear()
                        continue
                    for f in files:
                        fp = Path(r) / f
                        rel_f = fp.relative_to(self.workspace_root).as_posix()
                        if not is_ignored(rel_f, spec) and not is_binary_file(fp):
                            files_to_check.append(fp)

            for fp in files_to_check:
                try:
                    rel_p = fp.relative_to(self.workspace_root).as_posix()
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, start=1):
                            if regex.search(line):
                                clean = line.rstrip("\r\n")
                                results.append(f"{rel_p}:{idx}: {clean}")
                                match_count += 1
                                if match_count >= max_matches:
                                    break
                except Exception:
                    continue
                if match_count >= max_matches:
                    break

            if not results:
                return ToolResult(
                    success=True, output=f"No matches found for pattern: '{pattern}'"
                )

            header = f"Found {match_count} matches for '{pattern}':\n"
            return ToolResult(success=True, output=header + "\n".join(results))
        except Exception as e:
            return ToolResult(success=False, error=f"Grep search failed: {str(e)}")
