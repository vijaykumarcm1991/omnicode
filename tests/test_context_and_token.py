"""
Unit tests for ContextManager, TokenTracker, and Config loader.
"""

import pytest
from pathlib import Path
from omnicode.config import OmniConfig, load_config
from omnicode.core.context import ContextManager
from omnicode.core.token_tracker import TokenTracker


def test_token_tracker_estimation():
    tracker = TokenTracker("gpt-4o")
    text = "Hello world! This is a test of OmniCode token counter."
    tokens = tracker.estimate_tokens(text)
    assert tokens > 5
    assert tokens < 30

    cost = tracker.get_estimated_cost(1000, 500)
    assert cost > 0.0


def test_context_manager_system_prompt(tmp_path):
    config = OmniConfig(model="gpt-4o", system_prompt_extra="Follow PEP8 rules strictly.")
    ctx = ContextManager(config=config, workspace_root=tmp_path)

    assert "OmniCode" in ctx.system_prompt
    assert "Follow PEP8 rules strictly." in ctx.system_prompt

    # Test adding messages
    ctx.add_user_message("Create a hello world script")
    ctx.add_assistant_message("Here is the script", tool_calls=[{"id": "call_1", "function": {"name": "write_file", "arguments": "{}"}}])
    ctx.add_tool_result("call_1", "write_file", "File created")

    llm_msgs = ctx.get_messages_for_llm()
    assert len(llm_msgs) == 4
    assert llm_msgs[0]["role"] == "system"
    assert llm_msgs[1]["role"] == "user"
    assert llm_msgs[2]["role"] == "assistant"
    assert llm_msgs[3]["role"] == "tool"


@pytest.mark.asyncio
async def test_context_compaction(tmp_path):
    config = OmniConfig(model="gpt-4o", context_window=1000)
    ctx = ContextManager(config=config, workspace_root=tmp_path)

    # Add several messages
    for i in range(10):
        ctx.add_user_message(f"User message {i}")
        ctx.add_assistant_message(f"Assistant response {i}")

    assert len(ctx.messages) == 20
    summary_msg = await ctx.compact_history()
    assert "Compacted" in summary_msg
    assert len(ctx.messages) < 10


def test_session_persistence_and_resume(tmp_path, monkeypatch):
    from omnicode.core.context import list_saved_sessions, delete_saved_session
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    config = OmniConfig(model="deepseek-chat")
    ctx = ContextManager(config=config, workspace_root=tmp_path)
    ctx.add_user_message("Refactor database schema")
    ctx.add_assistant_message("Schema refactored successfully.")

    # Save session with custom name
    saved_path = ctx.save_session(custom_name="db-refactor")
    assert "db-refactor" in saved_path

    # List saved sessions
    sessions = list_saved_sessions()
    assert len(sessions) >= 1
    assert any(s["session_id"] == "db-refactor" for s in sessions)
    assert any("Refactor database schema" in s["preview"] for s in sessions)

    # Resume into fresh context manager
    new_ctx = ContextManager(config=config, workspace_root=tmp_path)
    assert new_ctx.load_session("db-refactor") is True
    assert len(new_ctx.messages) == 2
    assert new_ctx.messages[0]["content"] == "Refactor database schema"

    # Test resume latest
    latest_ctx = ContextManager(config=config, workspace_root=tmp_path)
    assert latest_ctx.load_session("latest") is True
    assert len(latest_ctx.messages) == 2

    # Test delete session
    assert delete_saved_session("db-refactor") is True
    assert len(list_saved_sessions()) == 0

