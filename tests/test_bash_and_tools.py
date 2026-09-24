"""
Unit tests for OmniCode bash tool, memory tool, and interactive tool.
"""

import pytest
import asyncio
from pathlib import Path
from omnicode.tools.bash_tools import RunCommandTool
from omnicode.tools.memory_tools import ManageTodoTool, ProjectMemoryTool


@pytest.mark.asyncio
async def test_run_command_echo(tmp_path):
    tool = RunCommandTool(tmp_path)
    res = await tool.execute("python -c \"print('OmniCode Test')\"")
    assert res.success is True
    assert "OmniCode Test" in res.output


@pytest.mark.asyncio
async def test_run_command_exit_code(tmp_path):
    tool = RunCommandTool(tmp_path)
    res = await tool.execute("python -c \"import sys; sys.exit(42)\"")
    assert res.success is False
    assert res.metadata.get("exit_code") == 42


@pytest.mark.asyncio
async def test_manage_todo(tmp_path):
    tool = ManageTodoTool(tmp_path)
    # Add task
    add_res = await tool.execute(action="add", task="Implement REST API")
    assert add_res.success is True
    assert "Added task #1" in add_res.output

    # List tasks
    list_res = await tool.execute(action="list")
    assert list_res.success is True
    assert "1. ⬜ Implement REST API" in list_res.output

    # Complete task
    comp_res = await tool.execute(action="complete", task_id=1)
    assert comp_res.success is True
    assert "Completed task #1" in comp_res.output

    # Verify completed
    list_res2 = await tool.execute(action="list")
    assert "1. ✅ Implement REST API" in list_res2.output


@pytest.mark.asyncio
async def test_project_memory(tmp_path):
    tool = ProjectMemoryTool(tmp_path)
    # Set memory
    res_set = await tool.execute(action="set", key="architecture", value="FastAPI + SQLAlchemy")
    assert res_set.success is True

    # Get memory
    res_get = await tool.execute(action="get", key="architecture")
    assert res_get.success is True
    assert "FastAPI + SQLAlchemy" in res_get.output
