"""
Context management, system prompt builder, session persistence, and auto-compaction for OmniCode.
"""

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..config import OmniConfig, get_global_config_dir
from ..utils.system_info import get_platform_info, get_default_shell
from ..utils.git_utils import get_git_branch, get_git_status_summary
from ..utils.file_utils import get_workspace_tree
from .token_tracker import TokenTracker


SYSTEM_PROMPT_TEMPLATE = """You are OmniCode, an expert autonomous AI software engineer and terminal pair programmer.
You are running directly in the user's workspace on their system.

<system_environment>
Operating System: {os_info}
Current Working Directory: {cwd}
Default Shell: {shell}
Git Status: {git_info}
</system_environment>

<workspace_overview>
{workspace_tree}
</workspace_overview>

<core_principles>
1. **Thorough & Autonomous**: Explore files, search code, and understand context before suggesting or executing changes.
2. **Precision Editing**: When modifying code, use `edit_file` with exact target strings or `write_file` for new files. Always verify edits afterward.
3. **Verify by Testing**: After making modifications, run tests, linter, or validation commands using `run_command` to confirm fixes work without breaking other components.
4. **Safety & Clarity**: Do not perform destructive actions (like deleting unknown branches or force-pushing) without confirmation.
5. **Concise Communication**: Answer clearly and directly. Use github-flavored markdown. Avoid rambling; let your actions and code speak for themselves.
</core_principles>

{custom_instructions}
"""


class SessionMessage(dict):
    """Message object in OpenAI chat format."""
    pass


class ContextManager:
    """Manages conversation messages, system prompt, token budget, and persistence."""

    def __init__(
        self,
        config: OmniConfig,
        workspace_root: Path,
        session_id: Optional[str] = None,
    ):
        self.config = config
        self.workspace_root = workspace_root
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_") + str(uuid.uuid4())[:6]
        self.token_tracker = TokenTracker(config.model)
        self.messages: List[Dict[str, Any]] = []
        self.system_prompt: str = ""
        self._build_system_prompt()

    def _build_system_prompt(self):
        """Construct dynamic system prompt with workspace state."""
        plat = get_platform_info()
        os_str = f"{plat['os']} {plat['os_release']} ({plat['architecture']})"
        shell = get_default_shell()
        cwd = str(self.workspace_root)

        git_summary = get_git_status_summary(self.workspace_root)
        if git_summary.get("is_repo"):
            git_info = f"Branch: '{git_summary['branch']}', {git_summary['total_changes']} uncommitted changes"
        else:
            git_info = "Not a git repository"

        tree = get_workspace_tree(self.workspace_root, max_depth=2, max_files=80)

        custom = ""
        if self.config.system_prompt_extra:
            custom = f"<user_instructions>\n{self.config.system_prompt_extra}\n</user_instructions>"

        self.system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            os_info=os_str,
            cwd=cwd,
            shell=shell,
            git_info=git_info,
            workspace_tree=tree,
            custom_instructions=custom,
        ).strip()

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """Return full messages list formatted for OpenAI API."""
        return [{"role": "system", "content": self.system_prompt}] + self.messages

    def add_user_message(self, content: str):
        """Add user input to history."""
        self.messages.append({"role": "user", "content": content})
        self.save_session()

    def add_assistant_message(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        reasoning: Optional[str] = None,
    ):
        """Add assistant response to history."""
        msg: Dict[str, Any] = {"role": "assistant"}
        if content is not None:
            msg["content"] = content
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning:
            msg["reasoning_content"] = reasoning
        self.messages.append(msg)
        self.save_session()

    def add_tool_result(self, tool_call_id: str, name: str, content: str):
        """Add tool execution response to history."""
        self.messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": name,
                "content": content,
            }
        )
        self.save_session()

    def clear_history(self):
        """Reset conversation messages."""
        self.messages.clear()
        self.save_session()

    def get_current_token_count(self) -> int:
        """Estimate tokens for current conversation."""
        all_msgs = self.get_messages_for_llm()
        return self.token_tracker.estimate_messages_tokens(all_msgs)

    def is_approaching_limit(self) -> bool:
        """Check if message tokens exceed compaction threshold."""
        current_tokens = self.get_current_token_count()
        threshold = int(self.config.context_window * self.config.auto_compact_threshold)
        return current_tokens >= threshold

    async def compact_history(self, llm_client=None) -> str:
        """Summarize older messages to keep conversation within token limits."""
        if len(self.messages) <= 4:
            return "Conversation too short to compact."

        # Keep last 3 messages intact
        cutoff = len(self.messages) - 3
        old_messages = self.messages[:cutoff]
        recent_messages = self.messages[cutoff:]

        # Basic text compaction summary
        summary_points = []
        for m in old_messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                summary_points.append(f"User requested: {content[:200]}")
            elif role == "assistant" and content:
                summary_points.append(f"Agent summary: {content[:200]}")
            elif role == "tool":
                summary_points.append(f"Tool {m.get('name')}: executed")

        summary_text = (
            "### Previous Conversation Summary (Compacted)\n"
            + "\n".join(f"- {p}" for p in summary_points[:20])
        )

        compacted_message = {
            "role": "user",
            "content": f"[Context Summary from prior turns]:\n{summary_text}",
        }
        compacted_ack = {
            "role": "assistant",
            "content": "Understood. I have preserved the prior context summary and will continue with our current task.",
        }

        self.messages = [compacted_message, compacted_ack] + recent_messages
        self.save_session()
        return f"Compacted {cutoff} messages into summary. Current estimated tokens: {self.get_current_token_count()}"

    def save_session(self):
        """Persist session state to ~/.omnicode/sessions/<session_id>.json."""
        try:
            session_file = get_global_config_dir() / "sessions" / f"{self.session_id}.json"
            data = {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "model": self.config.model,
                "workspace": str(self.workspace_root),
                "messages": self.messages,
                "token_summary": self.token_tracker.get_summary(),
            }
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def load_session(self, session_id: str) -> bool:
        """Load conversation from saved session file."""
        try:
            session_file = get_global_config_dir() / "sessions" / f"{session_id}.json"
            if not session_file.is_file():
                # Try finding match by prefix
                matches = list((get_global_config_dir() / "sessions").glob(f"*{session_id}*.json"))
                if matches:
                    session_file = matches[0]
                else:
                    return False

            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.session_id = data.get("session_id", self.session_id)
            self.messages = data.get("messages", [])
            return True
        except Exception:
            return False
