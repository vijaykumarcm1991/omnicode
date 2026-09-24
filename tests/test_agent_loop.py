"""
Unit tests for OmniAgent execution loop and tool calling with mock LLM client.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from omnicode.config import OmniConfig
from omnicode.core.agent import OmniAgent
from omnicode.core.llm_client import LLMResponse


@pytest.mark.asyncio
async def test_agent_tool_loop(tmp_path):
    config = OmniConfig(model="gpt-4o", permission_mode="yolo")
    agent = OmniAgent(config=config, workspace_root=tmp_path)

    # Mock the LLM client to execute 1 tool call turn and then finish
    turn1 = LLMResponse(
        content="I will create the file for you.",
        reasoning="Creating hello.py",
        tool_calls=[
            {
                "id": "call_123",
                "function": {
                    "name": "write_file",
                    "arguments": '{"file_path": "hello.py", "content": "print(\'Hello Agent\')\\n"}',
                },
            }
        ],
    )
    turn2 = LLMResponse(
        content="The file hello.py has been created successfully.",
        reasoning=None,
        tool_calls=None,
    )

    agent.llm_client.complete_turn = AsyncMock(side_effect=[turn1, turn2])

    result = await agent.run("Create hello.py with a print statement")

    assert "created successfully" in result
    assert (tmp_path / "hello.py").exists()
    assert (tmp_path / "hello.py").read_text(encoding="utf-8") == "print('Hello Agent')\n"
