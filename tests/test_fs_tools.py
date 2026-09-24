"""
Unit tests for OmniCode File System Tools.
"""

import pytest
import asyncio
from pathlib import Path
from omnicode.tools.fs_tools import (
    ViewFileTool,
    WriteFileTool,
    EditFileTool,
    ApplyPatchTool,
    ListDirTool,
    FileSearchTool,
    GrepSearchTool,
)


@pytest.fixture
def temp_workspace(tmp_path):
    # Setup sample project structure
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    print('Hello World')\n\nif __name__ == '__main__':\n    hello()\n",
        encoding="utf-8",
    )
    (src / "utils.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Test Project\nSample description.\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_view_file(temp_workspace):
    tool = ViewFileTool(temp_workspace)
    res = await tool.execute("src/main.py")
    assert res.success is True
    assert "def hello():" in res.output
    assert "1 |" in res.output


@pytest.mark.asyncio
async def test_view_file_slice(temp_workspace):
    tool = ViewFileTool(temp_workspace)
    res = await tool.execute("src/main.py", start_line=2, end_line=3)
    assert res.success is True
    assert "2 |     print('Hello World')" in res.output


@pytest.mark.asyncio
async def test_write_file(temp_workspace):
    tool = WriteFileTool(temp_workspace)
    res = await tool.execute("src/new_module.py", "def greet(name):\n    return f'Hi {name}'\n")
    assert res.success is True
    assert (temp_workspace / "src" / "new_module.py").exists()
    assert (temp_workspace / "src" / "new_module.py").read_text(encoding="utf-8") == "def greet(name):\n    return f'Hi {name}'\n"


@pytest.mark.asyncio
async def test_edit_file(temp_workspace):
    tool = EditFileTool(temp_workspace)
    res = await tool.execute(
        file_path="src/main.py",
        old_content="def hello():\n    print('Hello World')",
        new_content="def hello():\n    print('Hello OmniCode')",
    )
    assert res.success is True
    content = (temp_workspace / "src" / "main.py").read_text(encoding="utf-8")
    assert "Hello OmniCode" in content


@pytest.mark.asyncio
async def test_list_dir(temp_workspace):
    tool = ListDirTool(temp_workspace)
    res = await tool.execute(".", recursive=True)
    assert res.success is True
    assert "src/" in res.output
    assert "main.py" in res.output
    assert "README.md" in res.output


@pytest.mark.asyncio
async def test_file_search(temp_workspace):
    tool = FileSearchTool(temp_workspace)
    res = await tool.execute("*.py")
    assert res.success is True
    assert "main.py" in res.output
    assert "utils.py" in res.output


@pytest.mark.asyncio
async def test_grep_search(temp_workspace):
    tool = GrepSearchTool(temp_workspace)
    res = await tool.execute("multiply")
    assert res.success is True
    assert "utils.py:4:" in res.output or "utils.py" in res.output
