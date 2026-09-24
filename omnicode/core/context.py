"""
Context management, system prompt builder, session persistence, and auto-compaction for OmniCode.
"""

import os
import json
import uuid
import re
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

    def save_session(self, custom_name: Optional[str] = None) -> str:
        """Persist session state to ~/.omnicode/sessions/<session_id>.json."""
        try:
            sessions_dir = get_global_config_dir() / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            old_file = sessions_dir / f"{self.session_id}.json"

            if custom_name:
                clean_name = re.sub(r"[^\w\-\.]", "_", custom_name.strip())
                if clean_name and clean_name != self.session_id:
                    if old_file.is_file():
                        try:
                            old_file.unlink()
                        except Exception:
                            pass
                    self.session_id = clean_name

            session_file = sessions_dir / f"{self.session_id}.json"

            # Compute preview of first user request
            preview = ""
            for m in self.messages:
                if m.get("role") == "user":
                    preview = m.get("content", "").replace("\n", " ")[:80]
                    break

            data = {
                "session_id": self.session_id,
                "timestamp": datetime.now().isoformat(),
                "model": self.config.model,
                "workspace": str(self.workspace_root),
                "preview": preview,
                "messages": self.messages,
                "token_summary": self.token_tracker.get_summary(),
            }
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return str(session_file)
        except Exception:
            return ""

    def load_session(self, session_identifier: str = "") -> bool:
        """
        Load conversation from saved session file.
        Supports exact session_id, prefix/substring match, 'latest', or index (1, 2, ...).
        """
        sessions_dir = get_global_config_dir() / "sessions"
        if not sessions_dir.exists():
            return False

        target_file: Optional[Path] = None

        # 1. If empty or 'latest', find most recent session
        if not session_identifier or session_identifier.lower() == "latest":
            all_sessions = list_saved_sessions()
            if all_sessions:
                target_file = Path(all_sessions[0]["path"])
        
        # 2. If integer index (1-based from list_saved_sessions)
        elif session_identifier.isdigit():
            idx = int(session_identifier)
            all_sessions = list_saved_sessions()
            if 1 <= idx <= len(all_sessions):
                target_file = Path(all_sessions[idx - 1]["path"])

        # 3. Direct filename match
        elif (sessions_dir / f"{session_identifier}.json").is_file():
            target_file = sessions_dir / f"{session_identifier}.json"

        # 4. Prefix or substring search
        if not target_file:
            matches = list(sessions_dir.glob(f"*{session_identifier}*.json"))
            if matches:
                # Pick newest matching file
                matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                target_file = matches[0]

        if not target_file or not target_file.is_file():
            return False

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.session_id = data.get("session_id", target_file.stem)
            self.messages = data.get("messages", [])
            
            # Restore model if available and workspace match
            saved_model = data.get("model")
            if saved_model:
                self.config.model = saved_model
                self.token_tracker.model_name = saved_model

            return True
        except Exception:
            return False


def list_saved_sessions(workspace_filter: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan ~/.omnicode/sessions and return sorted metadata for all saved sessions."""
    sessions_dir = get_global_config_dir() / "sessions"
    if not sessions_dir.exists():
        return []

    results = []
    for file_path in sessions_dir.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            ws = data.get("workspace", "")
            if workspace_filter and ws and str(workspace_filter) != ws:
                continue

            iso_time = data.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(iso_time)
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                formatted_time = iso_time or "Unknown"

            messages = data.get("messages", [])
            preview = data.get("preview", "")
            if not preview:
                for m in messages:
                    if m.get("role") == "user":
                        preview = m.get("content", "").replace("\n", " ")[:80]
                        break

            results.append({
                "session_id": data.get("session_id", file_path.stem),
                "path": str(file_path),
                "timestamp": formatted_time,
                "raw_timestamp": iso_time,
                "model": data.get("model", "unknown"),
                "workspace": ws,
                "message_count": len(messages),
                "preview": preview or "(empty session)",
                "mtime": file_path.stat().st_mtime,
            })
        except Exception:
            continue

    # Sort newest first by file modification time or raw timestamp
    results.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return results


def delete_saved_session(session_identifier: str) -> bool:
    """Delete a saved session by ID, prefix, or index."""
    sessions = list_saved_sessions()
    if not sessions:
        return False

    target_path = None
    if session_identifier.isdigit():
        idx = int(session_identifier)
        if 1 <= idx <= len(sessions):
            target_path = Path(sessions[idx - 1]["path"])
    else:
        for s in sessions:
            if s["session_id"] == session_identifier or session_identifier in s["session_id"]:
                target_path = Path(s["path"])
                break

    if target_path and target_path.is_file():
        try:
            target_path.unlink()
            return True
        except Exception:
            return False
    return False

