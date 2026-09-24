"""
Interactive tools for OmniCode.
Allows the agent to ask the user clarifying questions or solicit choices.
"""

from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult


class AskUserTool(BaseTool):
    """Tool to ask the user a clarifying question during agent execution."""

    name = "ask_user"
    description = (
        "Ask the user a question to clarify requirements, solicit preferences, "
        "or resolve ambiguity before proceeding with a major change."
    )
    is_read_only = True

    def __init__(self, prompt_callback=None):
        self.prompt_callback = prompt_callback

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The specific question to ask the user.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of suggested answers / choices.",
                },
            },
            "required": ["question"],
        }

    async def execute(
        self,
        question: str,
        options: Optional[List[str]] = None,
        **kwargs,
    ) -> ToolResult:
        if self.prompt_callback:
            answer = await self.prompt_callback(question, options)
            return ToolResult(
                success=True,
                output=f"User responded: {answer}",
                metadata={"answer": answer},
            )
        else:
            # Fallback for non-interactive mode
            return ToolResult(
                success=True,
                output=f"[Interactive question posed to user]: '{question}'. User provided no input in automated mode.",
            )
